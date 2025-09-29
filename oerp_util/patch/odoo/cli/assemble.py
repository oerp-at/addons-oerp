# © 2007 Martin Reisenhofer <martin@reisenhofer.biz>
# License BSD-2-Clause or later (https://opensource.org/license/bsd-2-clause/).
import sys
import os
import re
import argparse
import fnmatch
import glob
import locale
import logging
import shutil
import yaml
import json5
import odoo

from odoo import SUPERUSER_ID
from odoo.addons.base.models.ir_model import MODULE_UNINSTALL_FLAG
from odoo.models import LOG_ACCESS_COLUMNS
from odoo.modules.module import MANIFEST_NAMES
from odoo.service.server import ThreadedServer
from odoo.tools import misc, unique
from odoo.tools.config import config
from odoo.tools.translate import (PoFileReader, PoFileWriter,
                                  TranslationModuleReader, TranslationImporter)

from . import Command


_logger = logging.getLogger('config')

ODOO_RELEASE = odoo.release
ADDON_API = ODOO_RELEASE.version
ADDONS_PATTERN = 'addons*'
ADDONS_CUSTOM = 'custom-addons'
ADDONS_CUSTOM_PATTERN = r'^(.*/(custom-addons-(.*)))/.*$'

RESTORED_FILE_NAME = 'restored'
DEFAULT_SLEEP = 5


def get_file_path():
    return os.path.realpath(os.path.dirname(__file__))

def get_base_dir():
    return os.path.abspath(os.path.join(get_file_path(), '../../../'))

def get_server_dir():
    return os.path.abspath(os.path.join(get_file_path(), "../.."))

def update_database(database):
    """ Odoo Database Update """
    registry = odoo.modules.registry.Registry.new(database, update_module=True)

    # refresh
    try:
        if config["reinit"] == "full":
            with registry.cursor() as cr:
                cr.execute("SELECT matviewname FROM pg_matviews")

                for (matview, ) in cr.fetchall():
                    _logger.info("REFRESH MATERIALIZED VIEW %s ...", matview)
                    cr.execute("REFRESH MATERIALIZED VIEW %s" % matview)
                    cr.commit()

                _logger.info("Finished refreshing views")
    except KeyError:
        pass

def get_custom_addons():
    working_dir = os.getcwd()
    if not working_dir.endswith('/'):
        working_dir += '/'
    m = re.match(ADDONS_CUSTOM_PATTERN, working_dir)
    if m:
        return {
            'name': m.group(3),
            'dir': m.group(2),
            'path': m.group(1)
        }
    return None

def get_custom_addons_path():
    custom_addons = get_custom_addons()
    if custom_addons:
        return custom_addons['path']
    return os.path.join(get_base_dir(), ADDONS_CUSTOM)

def is_addon_repository(directory):
    if not directory:
        return False
    if not os.path.isdir(directory):
        return False
    if not glob.glob(f'{directory}/*/'):
        return False
    return True

def get_addon_repositories(directory):
    repositories = set()
    if os.path.isdir(directory):
        for addon_dir in glob.glob(f'{directory}/*/'):
            manifest_file = os.path.join(addon_dir, '__manifest__.py')
            if not os.path.exists(manifest_file):
                repositories |= get_addon_repositories(addon_dir)
            else:
                repositories.add(directory)
    return repositories

def get_custom_addons_paths(postfix='/'):
    dir_custom_addons = get_custom_addons_path()
    if os.path.exists(dir_custom_addons) and is_addon_repository(dir_custom_addons):
        # add custom addons paths
        paths = set()
        for custom_subdir in os.listdir(dir_custom_addons):
            if custom_subdir.startswith('.'):
                continue
            manifest_file = os.path.join(dir_custom_addons, custom_subdir, '__manifest__.py')
            if os.path.exists(manifest_file):
                paths.add(f"{dir_custom_addons}{postfix}")
            else:
                custom_addon_repository_path = f"{dir_custom_addons}/{custom_subdir}"
                repository_dirs = get_addon_repositories(custom_addon_repository_path)
                for repository_dir in repository_dirs:
                    paths.add(f"{repository_dir}{postfix}")

        return list(paths)

    return []


class ConfigException(Exception):
    pass


class Profile(argparse.ArgumentParser):
    """ Profile based argument Parser """

    def __init__(self, name, **kwargs):
        super().__init__(**kwargs)
        self.name = name
        self.defaults = {}
        self.base_dir = get_base_dir()
        self.server_dir = get_server_dir()

        # get profile name
        self.profile = os.path.basename(self.base_dir)
        custom_addons = get_custom_addons()
        if custom_addons:
            self.profile = f"{self.profile}-{custom_addons['name']}"

        # ensure that config dir exist
        self.config_dir = os.path.join(self.base_dir, ".config")
        if not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir)

        # define profile locations
        profile_files = [
            '/etc/odoo/odoo-profile.yml',
            os.path.join(self.base_dir, "odoo-profile.yml"),
            os.path.expanduser('~/.odoo-profile.yml'),
        ]

        # load profile files
        # and update defaults
        for profile_file in profile_files:
            if os.path.exists(profile_file):
                with open(profile_file, encoding="utf-8") as f:
                    profile_defaults = yaml.load(f, Loader=yaml.FullLoader)
                    if profile_defaults:
                        self.update(profile_defaults)

        # path mappping of parameters
        self.path_mapping = {
            'database': ['db']
        }
        # environment var mapping
        self.env_mapping = {
            'ODOO_DATABASE': ['PGDATABASE'],
            'ODOO_DB_USER': ['PGUSER'],
            'ODOO_DB_PASSWORD': ['PGPASSWORD'],
            'ODOO_DB_HOST': ['PGHOST']
        }


    def _merge_dict(self, d1, d2):
        """ merge two dicts based on keys into first dict param """
        for key, value in d2.items():
            current = d1.get(key, None)
            if isinstance(current, dict) and isinstance(value, dict):
                self._merge_dict(current, value)
            else:
                d1[key] = value

    def update(self, profile):
        self._merge_dict(self.defaults, profile)

    def get(self, path, default=None):
        """ get default value for path """
        # determine config paths
        config_paths = (
            [self.profile] + path,
            ['default'] + path
        )
        # search config paths
        for config_path in config_paths:
            # search config
            node = self.defaults or None
            if node:
                for config_item in config_path:
                    node = node.get(config_item, None)
                    if not node:
                        break
            # check if a value was found
            if not node is None:
                return node
        # nothing was found return default
        return default

    def get_default_addon_path(self):
        addon_pattern = [f"{self.base_dir}/{ADDONS_PATTERN}/"]
        # add custom addon paths
        addon_pattern.extend(get_custom_addons_paths())
        # build package paths
        package_paths = set()
        for cur_pattern in addon_pattern:
            for package_dir in glob.glob(cur_pattern):
                if is_addon_repository(package_dir):
                    package_paths.add(package_dir)
        # return package paths
        return ",".join(package_paths) or None

    def get_envvar(self, envvar, default=None):
        """ :return: value of environment variable """
        value = os.environ.get(envvar, default)
        if value is None:
            mappings = self.env_mapping.get(envvar)
            if mappings:
                for mapping in mappings:
                    alt_value = os.environ.get(mapping, default)
                    if alt_value:
                        value = alt_value
                        break
        return value

    def add_argument(self, *args, name=None, envvar=False, **kwargs):
        """ add an argument to the ser"""
        # get name from metavar or dest if not set
        if not name and 'metavar' in kwargs:
            name = kwargs['metavar'].lower()
        elif not name and 'dest' in kwargs:
            name = kwargs['dest']

        def extend_help(add_help_text):
            help_text =  kwargs.get('help') or ''
            if help_text:
                if not help_text.endswith('.'):
                    help_text += "."
            help_text = " ".join([help_text, add_help_text])
            kwargs['help'] = help_text

        # if name is set
        # try to get default value from profile
        if name:
            # check if environment variable is set
            default = None
            if envvar:
                envvar = f'ODOO_{name.upper()}' if not isinstance(envvar, str) else envvar
                default = self.get_envvar(envvar, None)
                if not default is None and kwargs.get('action') == 'store_true':
                    default = bool(default)
                extend_help(f'The environment variable {envvar} can be used instead.')

            # if no env var was found
            # try to get default value from profile
            if default is None:
                # get default value
                path = self.path_mapping.get(name)
                if path:
                    default = self.get(path)
                else:
                    default = self.get([self.name, name])
            # only if a default value was found
            if not default is None:
                kwargs['default'] = default
            elif name == 'addons':
                default_addon_path = self.get_default_addon_path()
                if default_addon_path:
                    kwargs['default'] = default_addon_path
            elif name == "lang":
                default_lang = locale.getlocale()[0]
                if default_lang.startswith("de_"):
                    kwargs["default"] = "de_DE"
                    extend_help(f"Default is {kwargs['default']}")

        return super().add_argument(*args, **kwargs)



###############################################################################
# Setup Utils
###############################################################################


def get_dirs(in_dir):
    res = []
    for dir_name in os.listdir(in_dir):
        if not dir_name.startswith("."):
            if os.path.isdir(os.path.join(in_dir, dir_name)):
                res.append(dir_name)
    return res

def list_dir(in_dir):
    res = []
    for item in os.listdir(in_dir):
        if not item.startswith("."):
            res.append(item)
    return res

def find_file(directory, pattern):
    for root, dirs, files in os.walk(directory):
        for basename in files:
            if fnmatch.fnmatch(basename, pattern):
                filename = os.path.join(root, basename)
                yield filename

def cleanup_python(directory):
    for file_name in find_file(directory, "*.pyc"):
        os.remove(file_name)

def link_file(src, dst):
    if os.path.exists(dst):
        if os.path.islink(dst):
            os.remove(dst)
    os.symlink(src, dst)

def link_directory_entries(src, dst, ignore=None, names=None):
    links = set()

    # remove old links
    for name in list_dir(dst):
        if ignore and name in ignore:
            continue
        if names and not name in names:
            continue
        file_path = os.path.join(dst, name)
        if os.path.islink(file_path):
            os.remove(file_path)

    # set new links
    for name in list_dir(src):
        if ignore and name in ignore:
            continue
        if names and not name in names:
            continue
        src_path = os.path.join(src, name)
        dst_path = os.path.join(dst, name)
        if not name.endswith(".pyc") and not name.startswith("."):
            os.symlink(src_path, dst_path)
            links.add(dst_path)

    return links

# pylint: disable=eval-used
def is_addon(addon_path):
    if not addon_path or not os.path.exists(addon_path) or addon_path.endswith(".pyc"):
        return False
    for manifest_name in MANIFEST_NAMES:
        addon_meta = None
        addon_path_meta = os.path.join(addon_path, manifest_name)
        if os.path.exists(addon_path_meta):
            with open(addon_path_meta, encoding="utf-8") as metaFp:
                addon_meta = eval(metaFp.read())

            # check api
            supported_api = addon_meta.get("api")
            if not supported_api or ADDON_API in supported_api:
                return True
    return False


###############################################################################
# Config Mixin
###############################################################################

class CommandMixin:
    """ Basic config command """

    def __init__(self):
        self.params = None
        self._parser = Profile(self.name, description="Odoo Command")

        self.parser.add_argument(
            "--addons-path",
            metavar="ADDONS",
            envvar=True)

        self.parser.add_argument("-d",
                                 "--database",
                                 metavar="DATABASE",
                                 envvar=True,
                                 help="Specify the database")

        # check for a third parameter
        # and use it as module default
        if len(sys.argv) >= 3 and not sys.argv[2].startswith('-'):
            default_module = sys.argv[2]
            self.parser.add_argument("default_module", help="The default module to use")
        else:
            default_module = None

        self.parser.add_argument("-m",
                                 "--module",
                                 metavar="MODULE",
                                 default=default_module,
                                 required=False)

        self.parser.add_argument("--pg_path",
                                 metavar="PG_PATH",
                                 envvar=True,
                                 help="Specify the pg executable path")
        self.parser.add_argument("--db_host",
                                 metavar="DB_HOST",
                                 envvar=True,
                                 help="Specify the database host")
        self.parser.add_argument("--db_password",
                                 metavar="DB_PASSWORD",
                                 envvar=True,
                                 help="Specify the database password")
        self.parser.add_argument("--db_port",
                                 metavar="DB_PORT",
                                 envvar=True,
                                 help="Specify the database port",
                                 type=int)
        self.parser.add_argument("--db_user",
                                 metavar="DB_USER",
                                 envvar=True,
                                 help="Specify the database user")
        self.parser.add_argument("--db_prefix",
                                 metavar="DB_PREFIX",
                                 envvar=True,
                                 help="Specify database prefix")
        self.parser.add_argument("--config",
                                 metavar="CONFIG",
                                 envvar=True,
                                 help="Specify the configuration")

        self.parser.add_argument("--debug", envvar=True, action="store_true")
        self.parser.add_argument("--exit-error", action="store_true",
                                name="exit_error",
                                envvar=True,
                                help="If an error happened, exit and return error value")

        self.parser.add_argument(
            "--reinit",
            metavar="REINIT",
            default=False,
            help=
            "(Re)init materialized views, yes for reinit or full for reinit and rebuild"
        )

        self.parser.add_argument("--test-enable",
                                 action="store_true",
                                 help="Run tests")

    def run(self, args):
        params = self.parser.parse_args(args)
        config_args = []

        if params.pg_path:
            config_args.append("--pg_path")
            config_args.append(params.pg_path)

        if params.database:
            config_args.append("--database")
            config_args.append(params.database)

        if params.db_host:
            config_args.append("--db_host")
            config_args.append(params.db_host)

        if params.db_password:
            config_args.append("--db_password")
            config_args.append(params.db_password)

        if params.db_port:
            config_args.append("--db_port")
            config_args.append(str(params.db_port))

        if params.db_user:
            config_args.append("--db_user")
            config_args.append(params.db_user)

        if params.addons_path:
            config_args.append("--addons-path")
            config_args.append(params.addons_path)

        if params.config:
            config_args.append("--config")
            config_args.append(params.config)

        config.parse_config(config_args)
        if not params.database:
            params.database = config.get('db_name')

        if params.reinit:
            config["reinit"] = params.reinit

        self.params = params
        self.run_config()

    def run_config_env(self, env):
        pass

    def setup_env(self, database=None):
        if not database:
            database = config.get('db_name')

        if isinstance(database, str):
            database = [database]

        for db_name in database:
            try:
                with odoo.modules.registry.Registry.new(db_name).cursor() as cr:
                    env = odoo.api.Environment(cr, SUPERUSER_ID, {})
                    self.run_config_env(env)
            except Exception as e:
                if self.params.exit_error:
                    raise e
                else:
                    _logger.error(str(e))

###############################################################################
# Assemble Command
###############################################################################

class Assemble(Command):
    """ Setup VSCode environment to environment """
    def __init__(self):
        super(Assemble, self).__init__()
        self.parser.add_argument("--cleanup",
                                 action="store_true",
                                 help="Cleanup links")

    def run(self, args):
        params = self.parser.parse_args(args)

        logging.basicConfig(level=logging.INFO,
                            format="%(asctime)s %(levelname)s %(message)s")

        virtual_env = os.environ.get("VIRTUAL_ENV")
        if not virtual_env:
            _logger.error("Can only executed from virtual environment")
            return

        dir_server = get_server_dir()
        dir_workspace = os.path.abspath(os.path.join(dir_server, ".."))

        lib_path = os.path.join(dir_workspace, "assembly")
        lib_path_odoo = os.path.join(lib_path, "odoo")
        lib_path_addons = os.path.join(lib_path_odoo, "addons")
        bin_path = os.path.join(virtual_env, "bin")

        # check for cleanup
        if params.cleanup:
            _logger.info("Delete %s", lib_path_odoo)
            if os.path.exists(lib_path_odoo):
                shutil.rmtree(lib_path_odoo)
            return

        # create libpath
        if not os.path.exists(lib_path):
            _logger.info("Create directory %s", lib_path)
            os.mkdir(lib_path)

        # create directories
        for dir_path in (lib_path_odoo, lib_path_addons):
            if not os.path.exists(dir_path):
                _logger.info("Create directory %s", dir_path)
                os.mkdir(dir_path)


        dir_enabled_addons = lib_path_addons

        ignore_addons = []
        includeAddons = {
            #       "addon-path" : [
            #          "modulexy"
            #        ]
        }

        def get_addons_set():
            addons = set()
            for name in get_dirs(dir_enabled_addons):
                addons.add(name)
            return addons

        def setup_addons(only_links=False):
            dir_odoo = os.path.join(dir_server, "odoo")
            dir_odoo_addons = os.path.join(dir_odoo, "addons")
            old_addons = get_addons_set()

            # setup odoo libs

            link_directory_entries(dir_odoo, lib_path_odoo, ignore="addons")
            linked_base_entries = link_directory_entries(dir_odoo_addons,
                                                     lib_path_addons)

            # setup odoo

            odoo_bin = os.path.join(dir_server, "odoo-bin")
            link_file(odoo_bin, os.path.join(bin_path, "odoo-bin"))
            link_file(odoo_bin, os.path.join(bin_path, "odoo"))

            # setup addons

            addon_pattern = [
                os.path.join(dir_server, "addons"),
                f"{dir_workspace}/{ADDONS_PATTERN}"
            ]

            # add custom addons

            addon_pattern.extend(get_custom_addons_paths())


            # assemble

            merged = []
            update_failed = []

            if not only_links:
                _logger.info("Cleanup all *.pyc Files")
                cleanup_python(dir_workspace)

            if not os.path.exists(dir_enabled_addons):
                _logger.info("Create directory %s", str(dir_enabled_addons))
                os.makedirs(dir_enabled_addons)

            dir_processed = set()

            _logger.info("Delete current Symbolic links and distributed files %s ...",dir_enabled_addons)
            for cur_link in glob.glob(dir_enabled_addons + "/*"):
                cur_link_path = os.path.join(dir_enabled_addons, cur_link)
                is_link = os.path.islink(cur_link_path)
                if is_link:
                    # ingore system link
                    if cur_link_path in linked_base_entries:
                        continue
                    # remove link
                    os.remove(cur_link_path)

            # link per addons basis
            for cur_pattern in addon_pattern:
                for cur_addon_package_dir in glob.glob(cur_pattern):
                    package_name = os.path.basename(cur_addon_package_dir)
                    if not cur_addon_package_dir in dir_processed:
                        dir_processed.add(cur_addon_package_dir)
                        _logger.info("Process: %s", cur_addon_package_dir)
                        if os.path.isdir(cur_addon_package_dir):
                            # get include list
                            addon_include_list = includeAddons.get(
                                package_name, None)
                            # process addons
                            for cur_addon in list_dir(cur_addon_package_dir):
                                if not cur_addon in ignore_addons and (
                                        addon_include_list is None
                                        or cur_addon in addon_include_list):
                                    cur_addon_path = os.path.join(
                                        cur_addon_package_dir, cur_addon)

                                    if is_addon(cur_addon_path):
                                        dstPath = os.path.join(dir_enabled_addons, cur_addon)
                                        if not os.path.exists(dstPath):
                                            # log.info("Create addon link " + str(dstPath) + " from " + str(cur_addon_path))
                                            os.symlink(
                                                cur_addon_path, dstPath)

                    else:
                        # log.info("processed twice: " + cur_addon_package_dir)
                        pass

            installed_addons = get_addons_set()
            addons_removed = old_addons - installed_addons
            addons_added = installed_addons - old_addons

            _logger.info("Addon API: %s", ADDON_API)

            for addon in addons_removed:
                _logger.info("Removed: %s", addon)

            for addon in addons_added:
                _logger.info("Added: %s", addon)

            if merged:
                _logger.info("\n\nMerged:\n * %s\n", "\n * ".join(merged))

            if update_failed:
                _logger.error("\n\nUnable to update:\n * %s\n",
                              "\n * ".join(update_failed))

            _logger.info("Removed links: %s", len(addons_removed))
            _logger.info("Added links: %s", len(addons_added))


        def switch_odoo_env():
            custom_addons = get_custom_addons()
            if not custom_addons:
                return

            base_dir = get_base_dir()
            launch_file = os.path.join(base_dir, '.vscode/launch.json')
            if not os.path.exists(launch_file):
                return

            _logger.info("Switch environment to %s", custom_addons['name'])

            with open(launch_file, 'r', encoding="utf-8") as f:
                vscode_launch_cfg = json5.load(f)

            # change cwd
            launch_cfgs = vscode_launch_cfg.get('configurations')
            for launch_cfg in launch_cfgs:
                if launch_cfg.get('program') == '${workspaceFolder}/odoo/odoo-bin':
                    old_cwd = launch_cfg.get('cwd', '')
                    new_cwd = '${workspaceFolder}/' + custom_addons['dir']
                    if old_cwd != new_cwd:
                        _logger.info("Change cwd for config %s: %s -> %s", launch_cfg['name'], old_cwd, new_cwd)
                        launch_cfg['cwd'] = new_cwd

            with open(launch_file, 'w', encoding="utf-8") as f:
                json5.dump(vscode_launch_cfg, f, indent=4, quote_keys=True)


        setup_addons(only_links=not params.cleanup)
        switch_odoo_env()

        _logger.info("Finished!")



