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
import subprocess
import psycopg2
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


def get_db_name(name):
    if isinstance(name, list):
        return name[0]
    return name

def get_file_path():
    return os.path.realpath(os.path.dirname(__file__))

def get_base_dir():
    return os.path.abspath(os.path.join(get_file_path(), '../../../'))

def get_server_dir():
    return os.path.abspath(os.path.join(get_file_path(), "../.."))

def update_database(database, modules=None):
    """ Odoo Database Update """
    if not modules:
        modules = ["base"]
    if isinstance(modules, str):
        modules = [m.strip() for m in modules.split(",")]

    # update databases
    registry = odoo.modules.registry.Registry.new(database, update_module=True, upgrade_modules=modules)

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
        if not name.endswith(".pyc") and not name.startswith(".") and not name == "__pycache__":
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
# Command Mixin
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
            params.database = get_db_name(config.get('db_name'))

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

    def install_module(self, env, module_name):
        modul_obj = env['ir.module.module']
        mod = modul_obj.search([('name','=', module_name)], limit=1)
        if not mod:
            _logger.error("Unkown module %s!", module_name)
            return False
        elif mod.state == 'installed':
            _logger.warning("Module %s is already installed!", module_name)
            return False

        # install module
        mod.button_immediate_install()
        env.cr.commit()
        return True

    def sync_files(self, src, dest, dirs=False, info="Sync", filestore=False, delete=False, local=False):
        if dirs:
            if not src.endswith(os.path.sep) and not src.endswith('/'):
                src += os.path.sep
            if not dest.endswith(os.path.sep) and not dest.endswith('/'):
                dest += os.path.sep

        # build command
        if local:
            if dirs:
                # create destination directory if not exists
                if not os.path.exists(dest):
                    _logger.warning('Create directory %s', dest)
                    os.makedirs(dest, exist_ok=True)
                # tree copy or update /*
                cmd = f'cp -ru "{src}"* "{dest}"'
            else:
                # simple file copy
                cmd = f'cp "{src}" "{dest}"'
        else:
            # rsync
            cmd = ["rsync",
                   "-avz"]

            if delete:
                cmd.append('--delete')
            if filestore:
                cmd.append(f'--exclude /{RESTORED_FILE_NAME}')

            cmd.append(f'"{src}"')
            cmd.append(f'"{dest}"')
            cmd = " ".join(cmd)

        # copy
        _logger.info('%s from %s to %s ...', info, src, dest)
        res = subprocess.run(cmd, check=True, shell=True)

        # sync deletes if local copy is used
        # errors are not handled
        if local and dirs:
            subprocess.run(f'rsync -vr --delete --ignore-existing "{src}" "{dest}"', check=False, shell=True)

        _logger.info('%s from %s to %s done!', info, src, dest)
        return res

    def get_addons_paths(self):
        addons_paths = config.get('addons_path')
        if addons_paths:
            addons_paths = addons_paths.split(',')
        else:
            addons_paths = []

        server_path =  get_server_dir()
        addons_path = os.path.join(server_path, "addons")
        base_addons_path = os.path.join(server_path, "odoo/addons")
        addons_paths.append(addons_path)
        addons_paths.append(base_addons_path)
        return addons_paths


###############################################################################
# Database Mixin
###############################################################################
class DatabaseMixin(object):

    def setup_db_env(self, admin_user=None, admin_password=None):
        self.db_env = os.environ.copy()

        # get database names
        self.db_name = get_db_name(config.get('db_name'))

        # update database params
        changed_db_env = {}
        for config_key, env_name in (
            ('db_user', 'PGUSER'),
            ('db_password', 'PGPASSWORD'),
            ('db_port', 'PGPORT'),
            ('db_host', 'PGHOST'),
            ('db_name', 'PGDATABASE')
            ):
            value = config.get(config_key)
            if config_key == 'db_name':
                value = get_db_name(value)
            if value:
                changed_db_env[env_name] = str(value)

        if changed_db_env:
            self.db_env.update(changed_db_env)

        # create admin env
        self.db_admin_env = None
        self.db_admin_user = admin_user
        self.db_admin_password = admin_password
        if self.db_admin_user:
            self.db_admin_env = self.db_env.copy()
            self.db_admin_env['PGUSER'] = self.db_admin_user
            if not self.db_admin_password is None:
                self.db_admin_env['PGPASSWORD'] = self.db_admin_password

    def get_db_env(self, admin=False):
        if admin and self.db_admin_env:
            return self.db_admin_env
        return self.db_env

    def set_db_name(self, db_name):
        self.db_name = db_name
        config['db_name'] = self.db_name
        self.db_env['PGDATABASE'] = self.db_name
        if self.db_admin_env:
            self.db_admin_env['PGDATABASE'] = self.db_name

    def dropdb_connections(self, database, admin=False, check=False):
        _logger.warning('Terminating database connections to %s', database)
        return subprocess.run(f"psql -d postgres -c \"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{database}'\"", shell=True, check=check, env=self.get_db_env(admin=admin))

    def dropdb(self, database, admin=False):
        _logger.warning('Dropping database %s', database)
        return subprocess.run(f"dropdb --if-exists {database}", shell=True, check=True, env=self.get_db_env(admin=admin))

    def check_database(self):
        return subprocess.check_output('psql -A -c "SELECT COUNT(id) FROM res_company"', shell=True, env=self.get_db_env())

    def connect_database_admin(self, database=None):
        if self.db_admin_user is None:
            return self.connect_database(database=database)
        return self.connect_database(user=self.db_admin_user, password=self.db_admin_password, database=database)

    def backup_database(self, backup_file, compatible=True):
        _logger.info("Backup database %s to %s (compatible=%s)", self.db_name, backup_file, compatible)
        if compatible:
            cmd = f'pg_dump -f {backup_file} {self.db_name}'
        else:
            cmd = f'pg_dump -F c -f {backup_file} {self.db_name}'
        return subprocess.run(cmd, shell=True, check=True, env=self.get_db_env(admin=True))

    def createdb(self, database, admin=False):
        return subprocess.run(f"createdb {database}", shell=True, check=True, env=self.get_db_env(admin=admin))

    def restore_database(self, backup_file, admin=False, force=False):
        if force:
            self.dropdb_connections(self.db_name, admin=admin)
        self.dropdb(self.db_name, admin=admin)
        _logger.info("Restore database %s from %s", self.db_name, backup_file)
        self.createdb(self.db_name, admin=admin)
        db_env=self.get_db_env(admin=admin)
        try:
            subprocess.run(f"pg_restore -d {self.db_name} < {backup_file}", shell=True, check=False, env=db_env)
            self.check_database()
        except subprocess.CalledProcessError:
            subprocess.run(f"psql -d {self.db_name} -f {backup_file}", shell=True, check=False, env=db_env)
            self.check_database()
        _logger.info("Restored database from %s", backup_file)

    def connect_database(self, user=None, password=None, database=None):
        # prepare connection string
        params = []
        def add_param(param_name, config_name):
            value = config.get(config_name)
            if value:
                params.append(f"{param_name}='{value}'")

        add_param("host", "db_host")
        add_param("port", "db_port")

        if database is None:
            add_param("dbname", "db_name")
        elif database:
            params.append(f"dbname='{database}'")

        # allow user overwrite
        if user is None:
            add_param("user", "db_user")
        elif user:
            params.append(f"user='{user}'")

        # allow password override
        if password is None:
            add_param("password", "db_password")
        elif password:
            params.append(f"password='{password}'")

        # connect
        params = " ".join(params)
        return psycopg2.connect(params)

    def call_with_cr(self, fct):
        """ call function with cr """
        con = self.connect_database()
        try:
            cr = con.cursor()
            try:
                cr = con.cursor()
                fct(cr)
            finally:
                cr.close()
        finally:
            con.close()

    def is_database_ready(self):
        try:
            con = self.connect_database()
            # get odoo base version
            base_version = odoo.modules.load_information_from_description_file('base')['version']
            # fetch data from database
            try:
                cr = con.cursor()
                def fetch_value():
                    row = cr.fetchone()
                    return row[0] if row else None
                try:
                    cr.execute("SELECT latest_version FROM ir_module_module WHERE name=%s", ['base'])
                    version = fetch_value()
                    cr.execute("SELECT COUNT(*) FROM ir_module_module WHERE state LIKE %s", ['to %'])
                    changes = fetch_value()
                finally:
                    cr.close()
            finally:
                con.close()
        except psycopg2.DatabaseError as e:
            _logger.warning(str(e))
            return False

        # check results
        if version is None:
            _logger.warning('Database %s has no version', self.db_name)
            return False
        if version != base_version:
            _logger.warning('Database %s has different version %s != %s', self.db_name, version, base_version)
            return False
        if changes:
            _logger.warning('Database %s is currently being updated', self.db_name)
            return False
        # everything fine
        return True


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



