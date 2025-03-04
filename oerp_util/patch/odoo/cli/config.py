# © 2007 Martin Reisenhofer <martin@reisenhofer.biz>
# License BSD-2-Clause or later (https://opensource.org/license/bsd-2-clause/).
import re
import uuid
import io
import argparse
import fnmatch
import glob
import locale
import logging
import os
import shutil
import sys
import threading
import time
import itertools
from operator import itemgetter
import subprocess
import tempfile
import unittest
from datetime import datetime
from multiprocessing import Pool
import zipfile
from urllib.parse import urlparse
import polib
import yaml
import json5
import requests

import psycopg2
from tabulate import tabulate

import odoo
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
                if is_addon_repository(custom_addon_repository_path):
                    paths.add(f"{custom_addon_repository_path}{postfix}")

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


class DatabaseMixin(object):

    def setup_db_env(self, admin_user=None, admin_password=None):
        self.db_env = os.environ.copy()
        self.db_name = config['db_name']

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

    def restore_database(self, backup_file, admin=False):
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


class ConfigCommand():

    """ Basic config command """
    def __init__(self):
        self.params = None
        self.parser = Profile(self.name, description="Odoo Command")

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

        self.parser.add_argument("--lang",
                                 required=False,
                                 metavar="LANG",
                                 envvar=True)

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

        if params.module:
            config_args.append("--module")
            config_args.append(params.module)

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

        if params.lang:
            config_args.append("--lang")
            config_args.append(params.lang)

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

    def run_config(self):
        _logger.info("Nothing to do!")

    def run_config_env(self, env):
        _logger.info("Nothing to do!")

    def setup_env(self, fct=None, database=None):
        # get database
        if not database:
            database = config['db_name']

        # setup pool
        error = False
        if database:
            error = True
            registry = odoo.modules.registry.Registry(database)
            with registry.cursor() as cr:
                uid = odoo.SUPERUSER_ID
                ctx = odoo.api.Environment(cr, uid,
                                            {})['res.users'].context_get()
                env = odoo.api.Environment(cr, uid, ctx)
                try:
                    if fct:
                        fct(env)
                    else:
                        self.run_config_env(env)
                    error = False
                    env.flush_all()
                    cr.commit()
                except Exception as e:
                    if self.params.debug:
                        _logger.exception(e)
                    else:
                        _logger.error(e)

                finally:
                    cr.rollback()

        if error and self.params.exit_error:
            sys.exit(-1)

    def install_module(self, env, module_name):
        modul_obj = env['ir.module.module']
        mod = modul_obj.search([('name','=', module_name)], limit=1)
        if not mod:
            _logger.error(f"Unkown module {module_name}!")
            return False
        elif mod.state == 'installed':
            _logger.warning(f"Module {module_name} is already installed!")
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


class Update(ConfigCommand, Command):
    """ Update Module/All """
    def __init__(self):
        super(Update, self).__init__()
        self.parser.add_argument(
            "--db-all",
            action="store_true",
            default=False,
            help="Update all databases which match the defined prefix")
        self.parser.add_argument(
            "--threads",
            metavar="THREADS",
            default=32,
            help="Number of threads for multi database update")

    def get_databases(self):
        # get databases
        params = ["dbname='postgres'"]

        def add_param(name, name2):
            value = config.get(name)
            if value:
                params.append("%s='%s'" % (name2, value))

        add_param("db_host", "host")
        add_param("db_user", "user")
        add_param("db_password", "password")
        add_param("db_port", "port")

        params = " ".join(params)
        con = psycopg2.connect(params)
        try:
            cr = con.cursor()
            try:
                cr.execute(
                    "SELECT datname FROM pg_database WHERE datname LIKE '%s_%%'"
                    % self.params.db_prefix)
                return [r[0] for r in cr.fetchall()]
            finally:
                cr.close()
        finally:
            con.close()

    def run_config(self):
        # set reinit to no
        # if it was not provided
        if not self.params.reinit:
            config["reinit"] = "no"

        if self.params.module:
            config["update"][self.params.module] = 1
        else:
            config["update"]["all"] = 1

        if self.params.db_all:

            if not self.params.db_prefix:
                _logger.error(
                    "For multi database update you need to specify the --db_prefix parameter"
                )
                return

            _logger.info("Create thread pool (%s) for update",
                         self.params.threads)

            pool = Pool(processes=self.params.threads)
            pool.map(update_database, self.get_databases())

        else:
            update_database(self.params.database)


class PoIgnoreFileWriter(PoFileWriter, Command):
    def __init__(self, target, modules, lang, ignore):
        super(PoIgnoreFileWriter, self).__init__(target, lang)
        self.modules = modules
        self.ignore = ignore

    def write_rows(self, rows):
        # we now group the translations by source. That means one translation per source.
        grouped_rows = {}
        for module, type, name, res_id, src, trad, comments in rows:
            row = grouped_rows.setdefault(src, {})
            row.setdefault('modules', set()).add(module)
            if not row.get('translation') and trad != src:
                row['translation'] = trad
            row.setdefault('tnrs', []).append((type, name, res_id))
            row.setdefault('comments', set()).update(comments)

        for src, row in sorted(grouped_rows.items()):
            if not self.lang:
                # translation template, so no translation value
                row['translation'] = ''
            elif not row.get('translation'):
                row['translation'] = ''

            # check if translations should ignored
            write_translation = True
            if self.ignore:
                for tnr in row["tnrs"]:
                    comments = row['comments']
                    if not comments:
                        comments = ['']
                    for comment in comments:
                        # type, name, imd_name, src, value, comments
                        key = (tnr[0], tnr[1], str(tnr[2]), src,
                               row['translation'], comment)
                        if key in self.ignore:
                            write_translation = False

            if write_translation:
                self.add_entry(row['modules'], row['tnrs'], src,
                               row['translation'], row['comments'])

        self.po.header = "Translation of %s.\n" \
                    "This file contains the translation of the following modules:\n" \
                    "%s" % (ODOO_RELEASE.description, ''.join("\t* %s\n" % m for m in self.modules))
        now = datetime.utcnow().strftime('%Y-%m-%d %H:%M+0000')
        self.po.metadata = {
            'Project-Id-Version': "%s %s" % (ODOO_RELEASE.description, ODOO_RELEASE.version),
            'Report-Msgid-Bugs-To': '',
            'POT-Creation-Date': now,
            'PO-Revision-Date': now,
            'Last-Translator': '',
            'Language-Team': '',
            'MIME-Version': '1.0',
            'Content-Type': 'text/plain; charset=UTF-8',
            'Content-Transfer-Encoding': '',
            'Plural-Forms': '',
        }

        # buffer expects bytes
        self.buffer.write(str(self.po).encode())


class Po_Export(ConfigCommand, Command):
    """ Export *.po File """

    def __init__(self):
        super().__init__()
        self.lang = None
        self.langfile = None
        self.pot = False
        self.modpath = None
        self.langdir = None
        self.export_backup_file = None
        self.export_file = None

        self.parser.add_argument(
            "--merge",
            nargs='+',
            name="merge",
            help="*.po files to merge into export file, if the translation is empty"
        )
        self.parser.add_argument(
            "--force-merge",
            nargs='+',
            name="force_merge",
            help="*.po files to merge into export file"
        )
        self.parser.add_argument(
            "--no-merge",
            name="no_merge",
            action="store_true",
            help="No merge of backup file"
        )
        self.parser.add_argument(
            "--pot",
            name="pot",
            action="store_true",
            help="Export translation template"
        )

    def run_config(self):
        # check module
        if not self.params.module:
            _logger.error("No module defined for export!")
            return
        # check path
        self.modpath = odoo.modules.get_module_path(self.params.module)
        if not self.modpath:
            _logger.error("No module %s not found in path!",
                          self.params.module)
            return

        # check if it should be a template
        if (self.params.pot
            or not self.params.lang
            or self.params.lang == "pot"):
            self.lang = None
            self.langfile = self.params.module + ".pot"
            self.pot = True
        else:
            self.lang = self.params.lang
            self.pot = False
            self.langfile = self.lang.split("_")[0] + ".po"

        self.langdir = os.path.join(self.modpath, "i18n")
        if not os.path.exists(self.langdir):
            _logger.warning("Created language directory %s", self.langdir)
            os.mkdir(self.langdir)

        # run with env
        self.setup_env()

    def trans_export(self, lang, modules, buffer, cr, ignore):
        translations = TranslationModuleReader(cr, modules=modules, lang=lang)
        modules = set(t[0] for t in translations)
        writer = PoIgnoreFileWriter(buffer, modules, lang, ignore)
        writer.write_rows(translations)
        del translations

    def load_ignore(self):
        ignore = None
        ignore_filename = f'{self.export_file}.ignore'
        if os.path.exists(ignore_filename):
            _logger.info("Load ignore file %s", ignore_filename)
            ignore = set()
            with misc.file_open(ignore_filename, mode="rb") as fileobj:
                reader = PoFileReader(fileobj)
                for row in reader:
                    if not row.get("value"):
                        # type, name, imd_name, src, value, comments
                        imd_name = row.get("imd_name")
                        module = row.get("module") or ""
                        if imd_name and module and not imd_name.find(
                                ".") > 0:
                            imd_name = f'{module}.{imd_name}'
                        ignore.add(
                            (row["type"], row["name"], imd_name,
                                row["src"], row["value"], row["comments"]))
        return ignore

    def create_backup(self):
        if not self.export_backup_file:
            return False

        _logger.info('Create backup %s', self.export_backup_file)
        shutil.copy(self.export_file, self.export_backup_file)
        return True

    def remove_backup(self):
        if not self.export_backup_file:
            return False
        os.remove(self.export_backup_file)
        return True

    def restore_backup(self):
        if not self.export_backup_file:
            return False
        _logger.warning("Restore previous %s", self.export_file)
        shutil.copy(self.export_backup_file, self.export_file)
        return True

    def merge(self, file_to_merge, force=False):
        """ merge translations from backup to untranslated entries """
        if not file_to_merge:
            return False
        _logger.info('Merge translations with %s', file_to_merge)
        po_file = polib.pofile(self.export_file)

        # merge key function
        def fuzzy_key(entry):
            return entry.msgid_with_context

        # load translations to merge
        po_file_to_merge = polib.pofile(file_to_merge)
        po_fuzzy_merge_entry_set = dict(
            (fuzzy_key(entry), entry) for entry in po_file_to_merge if entry.msgstr.strip()
        )

        # build translation set
        po_merge_entry_set = {
            str(m) for m in po_file_to_merge
        }

        # merge translations
        po_entry_count = 0
        changed = False
        for po_entry in po_file:
            po_entry_count += 1

            if not self.pot and not po_entry.msgstr or force:
                po_merge_entry = po_fuzzy_merge_entry_set.get(fuzzy_key(po_entry))
                if po_merge_entry and po_merge_entry.msgstr:
                    po_entry.msgstr = po_merge_entry.msgstr

            # check if entry is in the translation set
            if str(po_entry) not in po_merge_entry_set:
                changed = True

        # check amount of entries
        if po_entry_count != len(po_merge_entry_set):
            changed = True

        # write po file
        po_file.save(self.export_file)
        return changed

    def run_config_env(self, env):
        # check module installed
        if not env["ir.module.module"].search(
            [("state", "=", "installed"), ("name", "=", self.params.module)]):
            _logger.error("No module %s installed!", self.params.module)
            return
        # set export file
        self.export_file = os.path.join(self.langdir, self.langfile)
        self.export_backup_file = (f'{self.export_file}.backup'
                                    if os.path.exists(self.export_file) else None)
        # preprocessing
        self.create_backup()
        ignore = self.load_ignore()

        # write translations
        with open(self.export_file, "wb") as export_stream:
            _logger.info('Writing %s', self.export_file)
            self.trans_export(self.lang, [self.params.module], export_stream,
                              env.cr, ignore)

        # merge with other files
        if self.params.merge:
            for merge_file in self.params.merge:
                self.merge(merge_file)
        if self.params.force_merge:
            for merge_file in self.params.merge:
                self.merge(merge_file, force=True)

        # merge empty translations with backup file (if exists)
        # and delete backup file afterwards
        if not self.params.no_merge and self.export_backup_file:
            if not self.merge(self.export_backup_file):
                # if no change, restore backup file
                # to keep timestamp
                _logger.warning('No translations changes')
                self.restore_backup()
        # remove backup
        self.remove_backup()


class Po_Import(ConfigCommand, Command):
    """ Import *.po File """
    def __init__(self):
        super(Po_Import, self).__init__()
        self.lang = None
        self.langfile = None
        self.langdir = None
        self.modpath = None

        self.parser.add_argument("--overwrite",
                                 action="store_true",
                                 default=True,
                                 help="Override existing translations")

        self.parser.add_argument("--verbose",
                                 action="store_true",
                                 default=False,
                                 help="Verbose translation import")

    def run_config(self):
        # check module
        if not self.params.module:
            _logger.error("No module defined for export!")
            return

        # check path
        self.modpath = odoo.modules.get_module_path(self.params.module)
        if not self.modpath:
            _logger.error("No module %s not found in path!",
                          self.params.module)
            return

        # check language
        if not self.params.lang:
            _logger.error("No language defined for import!")
            return

        # define language vars
        self.lang = self.params.lang
        self.langfile = self.lang.split("_")[0] + ".po"
        self.langdir = os.path.join(self.modpath, "i18n")

        # run with env
        self.setup_env()


    def run_config_env(self, env):
        # check module installed
        if not env["ir.module.module"].search(
            [("state", "=", "installed"), ("name", "=", self.params.module)]):
            _logger.error("No module %s installed!", self.params.module)
            return

        import_file = os.path.join(self.langdir, self.langfile)
        if not os.path.exists(import_file):
            _logger.error("File %s does not exist!", import_file)
            return

        # import
        if self.params.overwrite:
            _logger.info("Overwrite existing translations for %s/%s",
                         self.params.module, self.lang)

        cr = env.cr
        translation_importer = TranslationImporter(cr, verbose=True)
        translation_importer.load_file(import_file, self.lang)
        translation_importer.save(overwrite=self.params.overwrite)

        # and commit
        cr.commit()



class Test(ConfigCommand, Command):
    """ Run Tests """

    def __init__(self):
        super(Test, self).__init__()
        self.parser.add_argument(
            "--test-prefix",
            metavar="TEST_PREFIX",
            required=False,
            help="Specify the prefix of the method for filtering")
        self.parser.add_argument("--test-case",
                                 metavar="TEST_CASE",
                                 required=False,
                                 help="Specify the test case")
        self.parser.add_argument(
            "--test-download",
            metavar="TEST_DOWNLOAD",
            required=False,
            help="Specify test download diretory (e.g. for reports)")
        self.parser.add_argument("--test-tags",
                                 metavar="TEST_TAGS",
                                 required=False,
                                 help="Specify test tags")
        self.parser.add_argument(
            "--test-position",
            metavar="TEST_POSITION",
            required=False,
            help="Specify position tags: post_install, at_install")

        self.parser.add_argument(
            "--test-addons",
            help="Only thest modules inside addons path like custom-addons/*",
            action="append",
            required=False,

        )

        self.parser.add_argument(
            "--test-server",
            help="Run test server for web tests",
            action="store_true",
            default=True,
            required=False
        )


        self.parser.add_argument(
            "--xml-report",
            help="Generate standard XML unit test report",
            metavar="XML_REPORT"
        )

        self.xml_runner = None
        self.xml_report_data = io.BytesIO()

    def run_config(self):
        if self.params.test_download:
            config["test_download"] = self.params.test_download

        # run with env
        self.setup_env()

    def _get_test_runner(self):

        class OdooTestRunner(object):
            """A test runner class that displays results in in logger.
            Simplified verison of TextTestRunner(
            """

            def run(self, test):
                result = odoo.tests.result.OdooTestResult()
                start_time = time.perf_counter()
                test(result)
                time_taken = time.perf_counter() - start_time
                run = result.testsRun
                _logger.info("Ran %d test%s in %.3fs", run, run != 1 and "s" or "", time_taken)
                return result

        if self.params.xml_report:
            if self.xml_runner is None:
                from xmlrunner import XMLTestRunner
                self.xml_runner = XMLTestRunner(output=self.xml_report_data)
            return self.xml_runner
        else:
            return OdooTestRunner()

    def _get_server(self):
        server = ThreadedServer(odoo.http.root)
        return server

    def run_test(self,
                 module_name,
                 test_prefix=None,
                 test_case=None,
                 test_tags=None,
                 test_position=None):

        # before running tests ensure all imports
        import odoo.tests.loader
        import odoo.tests.result
        from odoo.tests.suite import OdooSuite
        from odoo.tests.loader import get_module_test_cases
        from odoo.tests.tag_selector import TagsSelector  # Avoid import loop
        from ..modules import module

        # define filter and get modules
        def match_filter(test):
            if not test_prefix or not isinstance(test, unittest.TestCase):
                if not test_case:
                    return True
                return type(test).__name__ == test_case
            return test._testMethodName.startswith(test_prefix)

        mods = odoo.tests.loader.get_test_modules(module_name)

        # set testing flags
        threading.current_thread().testing = True
        module.current_test = module_name

        # query modules, tests and run
        config_tags = TagsSelector(test_tags) if test_tags else None
        position_tag = TagsSelector(test_position) if test_position else None
        test_server_enabled = config.get('test_server', False)
        results = []
        for m in mods:
            tests = get_module_test_cases(m)
            suite = OdooSuite(
                t for t in tests
                if (not position_tag or position_tag.check(t))
                   and (not config_tags or config_tags.check(t))
                   and match_filter(t)
                   and (not isinstance(t, odoo.tests.common.HttpCase) or test_server_enabled)
            )

            if suite.countTestCases():
                t0 = time.time()
                t0_sql = odoo.sql_db.sql_counter
                _logger.info('%s running tests.', m.__name__)
                result = self._get_test_runner().run(suite)
                results.append({
                    "module": module_name,
                    "test":  m.__name__,
                    "name":  m.__name__.split(".")[-1],
                    "time": time.time() - t0,
                    "queries": odoo.sql_db.sql_counter - t0_sql,
                    "ok": result.wasSuccessful(),
                    "result": result
                })

        # remove testing flags
        module.current_test = None
        threading.current_thread().testing = False

        return results

    def run_config_env(self, env):
        # important to be here, that it not conflicts
        # with tag parsing
        config["test_enable"] = True
        config["stop_after_init"] = True
        config["test_server"] = config.get("test_server", self.params.test_server)

        module_name = self.params.module
        test_prefix = self.params.test_prefix
        test_case = self.params.test_case
        test_tags = self.params.test_tags
        test_position = self.params.test_position
        cr = env.cr

        if self.params.module:
            modules = [self.params.module]
        else:
            cr.execute(
                "SELECT name from ir_module_module WHERE state = 'installed' ")
            modules = [name for (name, ) in cr.fetchall()]

        if self.params.test_addons:
            dir_server = get_server_dir()
            dir_workspace = os.path.abspath(os.path.join(dir_server, ".."))

            allowed_modules = set()
            for addons_dir_pattern in self.params.test_addons:
                if not addons_dir_pattern.startswith('/'):
                    addons_dir_pattern = f"{dir_workspace}/{addons_dir_pattern}"
                for dir in glob.glob(addons_dir_pattern):
                    if os.path.isdir(dir) and is_addon(dir):
                        allowed_modules.add(os.path.basename(dir))

            modules = [m for m in modules if m in allowed_modules]


        results = []
        if modules:
            # start test server for http tests
            if not odoo.service.server.server:
                server = self._get_server() if config.get("test_server") else None
                if server:
                    _logger.info('Start test server')
                    server.start()
                    # assign running server
                    odoo.service.server.server = server

            # run tests
            for module_name in modules:
                results.extend(self.run_test(module_name, test_prefix, test_case,
                                   test_tags, test_position))


        if not results:
            _logger.warning("No tests!")
        else:
            # write xml report if used
            if self.params.xml_report:
                from xmlrunner.extra.xunit_plugin import transform
                with open(self.params.xml_report, 'wb') as f:
                    f.write(transform(self.xml_report_data.getvalue()))

            failed = list(filter(lambda r: not r["ok"], results))
            successful = list(filter(lambda r: r["ok"], results))
            result_txt = tabulate(
                [
                    [
                        r["module"],
                        r["name"],
                        f"{r['time']:.2f}s",
                        str(r["queries"]),
                        r["ok"] and "OK" or "FAILED"
                    ] for r in successful + failed
                ],
                tablefmt="github",
                headers=['Module','Test','Time','Queries','Status'])

            if not failed:
                _logger.info(f"\n\n{result_txt}\n\n")
                _logger.info("%s Test(s) successful!", len(results))
            else:
                _logger.warning(f"\n\n{result_txt}\n\n")
                raise Exception(f'{len(failed)}/{len(results)} Test(s) failed!')


class CleanUp(ConfigCommand, Command, DatabaseMixin):
    """ CleanUp Database """
    def __init__(self):
        super(CleanUp, self).__init__()

        self.parser.add_argument("--fix",
                                action="store_true",
                                name="fix",
                                help="Do/Fix all offered cleanup(s)")

        self.parser.add_argument("--no-drop",
                                action="store_true",
                                name="nodrop",
                                help="Do not drop columns and tables")

        self.parser.add_argument("--uninstall",
                                type=str,
                                name="uninstall",
                                nargs="+",
                                help="Modules which should be uninstall during cleanup")

        self.parser.add_argument("--only-raw",
                                action="store_true",
                                name="raw",
                                help="Only raw fixes without module update")

        self.addons_paths = None



    def _module_data_uninstall_no_drop(self, env, modules_to_remove):
        """ Deletes all not available modules, but did not drop any columns for tables
        """
        from odoo.addons.base.models.ir_model import IrModelFields, IrModel
        drop_column_fct = IrModelFields._drop_column
        drop_table_fct = IrModel._drop_table
        try:
            IrModelFields._drop_column = lambda *args, **kwargs: True
            IrModel._drop_table = lambda *args, **kwargs: True
            self._module_data_uninstall(env, modules_to_remove)
        finally:
            IrModelFields._drop_column = drop_column_fct
            IrModel._drop_table = drop_table_fct


    def _module_data_uninstall(self, env, modules_to_remove):
        """Deletes all the records referenced by the ir.model.data entries
        ``ids`` along with their corresponding database backed (including
        dropping tables, columns, FKs, etc, as long as there is no other
        ir.model.data entry holding a reference to them (which indicates that
        they are still owned by another module).
        Attempts to perform the deletion in an appropriate order to maximize
        the chance of gracefully deleting all records.
        This step is performed as part of the full uninstallation of a module.
        """

        # enable model/field deletion
        # we deactivate prefetching to not try to read a column that has been deleted
        env = env(context={MODULE_UNINSTALL_FLAG: True, 'prefetch_fields': False})

        # determine records to unlink
        records_items = []              # [(model, id)]
        model_ids = []
        field_ids = []
        selection_ids = []
        constraint_ids = []

        # delete orphaned assets
        cr = env.cr
        for module_name in modules_to_remove:
            cr.execute(f"DELETE FROM ir_asset WHERE path LIKE '/{module_name}/%'")

        # search for model data
        ModelData = env['ir.model.data']
        module_data = ModelData.search([('module', 'in', modules_to_remove)], order='id DESC')
        for data in module_data:
            if data.model == 'ir.model':
                model_ids.append(data.res_id)
            elif data.model == 'ir.model.fields':
                field_ids.append(data.res_id)
            elif data.model == 'ir.model.fields.selection':
                selection_ids.append(data.res_id)
            elif data.model == 'ir.model.constraint':
                constraint_ids.append(data.res_id)
            else:
                records_items.append((data.model, data.res_id))

        # avoid prefetching fields that are going to be deleted: during uninstall, it is
        # possible to perform a recompute (via flush) after the database columns have been
        # deleted but before the new registry has been created, meaning the recompute will
        # be executed on a stale registry, and if some of the data for executing the compute
        # methods is not in cache it will be fetched, and fields that exist in the registry but not
        # in the database will be prefetched, this will of course fail and prevent the uninstall.
        for ir_field in env['ir.model.fields'].browse(field_ids):
            if not ir_field.exists():
                field_ids.remove(ir_field.id)
                continue
            if ir_field.model in env:
                model = env[ir_field.model]
                field = model._fields.get(ir_field.name)
                if field is not None:
                    field.prefetch = False

        # to collect external ids of records that cannot be deleted
        undeletable_ids = []

        def delete(records):
            # do not delete records that have other external ids (and thus do
            # not belong to the modules being installed)
            ref_data = ModelData.search([
                ('model', '=', records._name),
                ('res_id', 'in', records.ids),
            ])
            records -= records.browse((ref_data - module_data).mapped('res_id'))
            if not records:
                return

            # special case for ir.model.fields
            if records._name == 'ir.model.fields':
                missing = records - records.exists()
                if missing:
                    # delete orphan external ids right now;
                    # an orphan ir.model.data can happen if the ir.model.field is deleted via
                    # an ONDELETE CASCADE, in which case we must verify that the records we're
                    # processing exist in the database otherwise a MissingError will be raised
                    orphans = ref_data.filtered(lambda r: r.res_id in missing._ids)
                    _logger.info('Deleting orphan ir_model_data %s', orphans)
                    orphans.unlink()
                    # /!\ this must go before any field accesses on `records`
                    records -= missing
                # do not remove LOG_ACCESS_COLUMNS unless _log_access is False
                # on the model
                records -= records.filtered(lambda f: f.name == 'id' or (
                    f.name in LOG_ACCESS_COLUMNS and
                    f.model in env and env[f.model]._log_access
                ))

            # now delete the records
            _logger.info('Deleting %s', records)
            try:
                with ModelData._cr.savepoint():
                    records.unlink()
            except Exception:
                if len(records) <= 1:
                    undeletable_ids.extend(ref_data._ids)
                else:
                    # divide the batch in two, and recursively delete them
                    half_size = len(records) // 2
                    delete(records[:half_size])
                    delete(records[half_size:])

        # remove non-model records first, grouped by batches of the same model
        for model, items in itertools.groupby(unique(records_items), itemgetter(0)):
            if model in env:
                delete(env[model].browse(item[1] for item in items))

        # Remove copied views. This must happen after removing all records from
        # the modules to remove, otherwise ondelete='restrict' may prevent the
        # deletion of some view. This must also happen before cleaning up the
        # database schema, otherwise some dependent fields may no longer exist
        # in database.
        modules = env['ir.module.module'].search([('name', 'in', modules_to_remove)])
        modules._remove_copied_views()

        # remove constraints
        delete(env['ir.model.constraint'].browse(unique(constraint_ids)))
        constraints = env['ir.model.constraint'].search([('module', 'in', modules.ids)])
        constraints.unlink()

        # If we delete a selection field, and some of its values have ondelete='cascade',
        # we expect the records with that value to be deleted. If we delete the field first,
        # the column is dropped and the selection is gone, and thus the records above will not
        # be deleted.
        delete(env['ir.model.fields.selection'].browse(unique(selection_ids)).exists())
        delete(env['ir.model.fields'].browse(unique(field_ids)))

        if not self.params.no_drop:
            # drop releations
            relations = env['ir.model.relation'].search([('module', 'in', modules.ids)])
            relations._module_data_uninstall()

        # remove models
        delete(env['ir.model'].browse(unique(model_ids)))

        # log undeletable ids
        _logger.info("ir.model.data could not be deleted (%s)", undeletable_ids)

        # sort out which undeletable model data may have become deletable again because
        # of records being cascade-deleted or tables being dropped just above
        for data in ModelData.browse(undeletable_ids).exists():
            if data.model in env:
                record = env[data.model].browse(data.res_id)
                try:
                    with env.cr.savepoint():
                        if record.exists():
                            # record exists therefore the data is still undeletable,
                            # remove it from module_data
                            module_data -= data
                            continue
                except psycopg2.ProgrammingError:
                    # This most likely means that the record does not exist, since record.exists()
                    # is rougly equivalent to `SELECT id FROM table WHERE id=record.id` and it may raise
                    # a ProgrammingError because the table no longer exists (and so does the
                    # record), also applies to ir.model.fields, constraints, etc.
                    pass
        # remove remaining module data records
        module_data.unlink()

    def _cleanup_modules(self, env):
        cr = env.cr
        cr.execute('SELECT name, latest_version FROM ir_module_module')
        rows = cr.fetchall()
        invalid_modules = []
        uninstall_set = set(self.params.uninstall) if self.params.uninstall else set()
        for name, latest_version in rows:
            info = odoo.modules.module.get_manifest(name)
            # add modules which are not available or installable
            if not info or not info.get('installable', True) or name in uninstall_set:
                invalid_modules.append(name)

        # uninstall invalid modules
        invalid_modules = tuple(invalid_modules)
        if invalid_modules:
            for module_name in invalid_modules:
                if self.params.fix:
                    module = env['ir.module.module'].search([('name', '=', module_name)], limit=1)
                    if module:
                        _logger.warning("[FIX] Uninstall module: %s", module_name)

                        # remove module user group relation
                        cr.execute("""DELETE FROM ir_model_data WHERE
                            id IN (
                            SELECT d.id FROM ir_model_data d
                            INNER JOIN res_groups_users_rel rel ON rel.gid = d.res_id
                            WHERE d.model='res.groups'
                            AND d.module = %s
                            )""", (module_name,))

                        if self.params.no_drop:
                            self._module_data_uninstall_no_drop(env, [module_name])
                        else:
                            self._module_data_uninstall(env, [module_name])

                        cr.execute('DELETE FROM ir_module_module WHERE name = %s', (module_name, ))
                else:
                    _logger.warning("[FOUND] Unavailable module: %s", module_name)

            if self.params.fix:
                _logger.warning("[FIX] cleanup module state and dependencies")
                # remove invalid modules from dependency lists
                cr.execute('DELETE FROM ir_module_module_dependency WHERE name in %s', (tuple(invalid_modules), ))
                # reset module state
                cr.execute("UPDATE ir_module_module SET state = 'installed' WHERE state = 'to upgrade'")

        # check unreferenced
        cr.execute("""SELECT d.name FROM ir_model_data d
                    LEFT JOIN ir_module_module m ON m.id = d.res_id
                    WHERE d.model = 'ir.module.module'
                    AND m.id IS NULL""")
        unref_modules = [r[0] for r in cr.fetchall()]
        if unref_modules:
            if self.params.fix:
                # remove unreferenced
                _logger.warning("[FIX] unreferenced modul data: %s", ', '.join(unref_modules))
                cr.execute("""DELETE FROM ir_model_data WHERE id IN (
                    SELECT d.id FROM ir_model_data d
                    LEFT JOIN ir_module_module m ON m.id = d.res_id
                    WHERE d.model = 'ir.module.module'
                    AND m.id IS NULL
                )""")
            else:
                _logger.warning("[FOUND] unreferenced modul data: %s", ', '.join(unref_modules))

    def run_config(self):
        self.addons_paths = self.get_addons_paths()
        self.call_with_cr(self.pre_cleanup)
        if not self.params.only_raw:
            self.setup_env()

    def get_file_path(self, relative_file_path):
        for addon_path in self.addons_paths:
            file_path = os.path.join(addon_path, relative_file_path)
            if os.path.exists(file_path):
                return file_path
        return None

    def pre_cleanup(self, cr):
        self.pre_cleanup_assets(cr)
        self.pre_cleanup_views(cr)

    def pre_cleanup_assets(self, cr):
        cr.execute('SELECT id, path FROM ir_asset WHERE active')
        commit = False
        for asset_id, asset_path in cr.fetchall():
            if not self.get_file_path(asset_path):
                if self.params.fix:
                    _logger.info('[FIX] delete invalid asset %s', asset_path)
                    cr.execute('DELETE FROM ir_asset WHERE id = %s', (asset_id,))
                    commit = True
                else:
                    _logger.info("[FOUND] Invalid asset %s", asset_path)

        if commit:
            cr.execute('COMMIT')

    def pre_cleanup_views(self, cr):
        # cleanup not available views
        cr.execute("""SELECT v.id, v.arch_fs, v.inherit_id, m.latest_version FROM ir_ui_view v
            LEFT JOIN ir_model_data d ON d.res_id = v.id AND d.model = 'ir.ui.view'
            LEFT JOIN ir_module_module m ON m.name = d.module
            WHERE v.arch_prev IS NOT NULL
            AND v.arch_fs IS NOT NULL
            AND v.active""")

        delete_view_ids = {}
        commit = False

        for view_id, arch_fs, inherit_id, module_version in cr.fetchall():
            if not self.get_file_path(arch_fs) or (module_version and module_version < ADDON_API):
                if self.params.fix:
                    delete_view_ids[view_id] = (inherit_id, arch_fs)
                    commit = True
                else:
                    _logger.warning('[FOUND] invalid view %s', arch_fs)

        while delete_view_ids:
            # delete views which have not dependency
            deleted_views = []
            for view_id, (inherit_id, arch_fs) in delete_view_ids.items():
                _logger.warning('[FIX] Removing invalid view %s', arch_fs)
                child_views = [k for k, (child_inherit_id, child_arch_fs) in delete_view_ids.items() if child_inherit_id == view_id]
                if not child_views:
                    cr.execute("DELETE FROM ir_ui_view WHERE inherit_id = %s AND NOT active", (view_id,))
                    cr.execute("DELETE FROM ir_ui_view WHERE id = %s", (view_id,))
                    deleted_views.append(view_id)

            # remove view from dict
            for view_id in deleted_views:
                delete_view_ids.pop(view_id)

            # check if there wehre something to delete
            if not deleted_views and delete_view_ids:
                _logger.error('Unable to delete views with IDs %s', delete_view_ids.keys())
                break

        if commit:
            cr.execute("COMMIT")

    def run_config_env(self, env):
        # check full cleanup
        cr = env.cr
        try:
            self._cleanup_modules(env)
            if self.params.fix:
                cr.commit()
        except Exception as e:
            if self.params.debug:
                _logger.exception(e)
            else:
                _logger.error(e)
            return
        finally:
            cr.rollback()



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
        is_dir = os.path.isdir(dst_path)
        if not name.endswith(".pyc") and not name.startswith("."):
            os.symlink(src_path, dst_path)
            links.add(dst_path)

    return links

def is_addon(addon_path):
    if not addon_path or not os.path.exists(addon_path) or addon_path.endswith('.pyc'):
        return False
    for manifest_name in MANIFEST_NAMES:
        addon_meta = None
        addon_path_meta = os.path.join(addon_path, manifest_name)
        if os.path.exists(addon_path_meta):
            with open(addon_path_meta
                        ) as metaFp:
                addon_meta = eval(metaFp.read())

            # check api
            supported_api = addon_meta.get("api")
            if not supported_api or ADDON_API in supported_api:
                return True
    return False


class Assemble(Command):
    """ Setup VSCode environment to environment """
    def __init__(self):
        super(Assemble, self).__init__()
        self.parser = argparse.ArgumentParser(description="Odoo Config")
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
            _logger.info("Create directory %s" % lib_path)
            os.mkdir(lib_path)

        # create directories
        for dir_path in (lib_path_odoo, lib_path_addons):
            if not os.path.exists(dir_path):
                _logger.info("Create directory %s" % dir_path)
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
                _logger.info("Create directory %s" % str(dir_enabled_addons))
                os.makedirs(dir_enabled_addons)

            dir_processed = set()

            _logger.info(
                "Delete current Symbolic links and distributed files " +
                str(dir_enabled_addons) + " ...")
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
                _logger.info("\n\nMerged:\n * %s\n" % ("\n * ".join(merged), ))

            if update_failed:
                _logger.error("\n\nUnable to update:\n * %s\n" %
                              ("\n * ".join(update_failed), ))

            _logger.info("Removed links: %s" % len(addons_removed))
            _logger.info("Added links: %s" % len(addons_added))


        def switch_odoo_env():
            custom_addons = get_custom_addons()
            if not custom_addons:
                return

            base_dir = get_base_dir()
            launch_file = os.path.join(base_dir, '.vscode/launch.json')
            if not os.path.exists(launch_file):
                return

            _logger.info("Switch environment to %s", custom_addons['name'])

            with open(launch_file, 'r') as f:
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

            with open(launch_file, 'w') as f:
                json5.dump(vscode_launch_cfg, f, indent=4, quote_keys=True)


        setup_addons(only_links=not params.cleanup)
        switch_odoo_env()

        _logger.info("Finished!")



###############################################################################
#  Module Management
###############################################################################


class Install(ConfigCommand, Command):

    def run_config(self):
        self.setup_env()

    def run_config_env(self, env):
        # check module installed
        modul_obj = env['ir.module.module']
        mod = modul_obj.search([('name','=', self.params.module)], limit=1)
        if not mod:
            _logger.error(f"Unkown module {self.params.module}!")
            return
        elif mod.state == 'installed':
            _logger.error(f"Module {self.params.module} is already installed!")
            return

        # install module
        mod.button_immediate_install()
        env.cr.commit()


class UnInstall(ConfigCommand, Command):

    def run_config(self):
        self.setup_env()

    def run_config_env(self, env):
        # check module installed
        modul_obj = env['ir.module.module']
        mod = modul_obj.search([('name','=', self.params.module)], limit=1)
        if not mod:
            _logger.error(f"Unkown module {self.params.module}!")
            return
        elif mod.state != 'installed':
            _logger.error(f"Module {self.params.module} is not installed!")
            return

        # uninstall
        mod.button_immediate_uninstall()
        env.cr.commit()


class Cancel(ConfigCommand, Command):

    def run_config(self):
        self.setup_env()

    def run_config_env(self, env):
        # check module installed
        modul_obj = env['ir.module.module']
        mod = modul_obj.search([('name','=', self.params.module)], limit=1)
        if not mod:
            _logger.error(f"Unkown module {self.params.module}!")
            return
        elif mod.state == 'uninstalled':
            _logger.error(f"Module {self.params.module} is already uninstalled!")
            return

        # cancel modul
        mod.button_install_cancel()
        env.cr.commit()


class Upgrade(ConfigCommand, Command):

    def run_config(self):
        self.setup_env()

    def run_config_env(self, env):
        # check module installed
        modul_obj = env['ir.module.module']
        mod = modul_obj.search([('name','=', self.params.module)], limit=1)
        if not mod:
            _logger.error(f"Unkown module {self.params.module}!")
            return
        elif mod.state != 'installed':
            _logger.error(f"Module {self.params.module} is not installed!")
            return

        # upgrade module
        mod.button_immediate_upgrade()
        env.cr.commit()


class UpdateList(ConfigCommand, Command):

    def run_config(self):
        self.setup_env()

    def run_config_env(self, env):
        # check module installed
        modul_obj = env['ir.module.module']
        updated, added = modul_obj.update_list()
        _logger.info('Modules Updated: %s, Added: %s', updated, added)
        env.cr.commit()



###############################################################################
# Database Management
###############################################################################


class Backup(ConfigCommand, DatabaseMixin):

    def __init__(self):
        super().__init__()

        self.parser.add_argument(
            "--pg_admin_user",
            name="pg_admin_user",
            envvar="PGADMINUSER",
            help="The database admin user"
        )
        self.parser.add_argument(
            "--pg_admin_password",
            name="pg_admin_password",
            help="The database admin password",
            envvar="PGADMINPASSWORD",
        )
        self.parser.add_argument(
            "--backup-dir",
            name="backup_dir",
            required=True,
            help="The backup directory."
        )
        self.parser.add_argument(
            "--only-database",
            action="store_true",
            name="only_database",
            default=False,
            help="Only Database.")

        self.parser.add_argument(
            "--compatible",
            action="store_true",
            name="compatible",
            default=True,
            help="Create a database backup which is compatible with different postgres versions.")

        self.parser.add_argument(
            "--backlog",
            type=int,
            name="backlog",
            default=6,
            help="The amount of database backups to keep.")

    def create_backlog(self, file_path):
        if self.params.backlog > 0 and os.path.exists(file_path):
            # ensure backlog dir
            backlog_dir = os.path.join(os.path.dirname(file_path), ".backlog")
            if not os.path.exists(backlog_dir):
                _logger.warning('Create backlog directory %s', backlog_dir)
                os.mkdir(backlog_dir)

            # ensure max size of backlog
            base_name = os.path.basename(file_path)
            if os.path.exists(backlog_dir):
                for index, backlog_name in enumerate(sorted(os.listdir(backlog_dir), reverse=True)):
                    # delete backlogfile if index is bigger than backlog size
                    backlog_file_path = os.path.join(backlog_dir, backlog_name)
                    if index >= self.params.backlog and os.path.isfile(backlog_file_path):
                        _logger.warning('Delete old backup %s', backlog_file_path)
                        os.unlink(backlog_file_path)

            # build new backlog file
            t = datetime.fromtimestamp(os.path.getctime(file_path))
            new_backup_file = os.path.join(backlog_dir, f'{t.strftime("%Y-%m-%d_%H%M%S")}_{base_name}')
            _logger.info('Backlog current backup %s to %s', file_path, new_backup_file)
            shutil.move(file_path, new_backup_file)

        return file_path

    def run_config(self):
        self.setup_db_env(admin_user=self.pg_admin_user, admin_password=self.params.pg_admin_password)
        self.filestore = os.path.abspath(os.path.join(config['data_dir'], 'filestore', self.db_name))

        # create backup directory
        self.backup_dir = os.path.abspath(os.path.join(self.params.backup_dir))
        if not os.path.exists(self.backup_dir):
            _logger.info('Create backup directory %s', self.backup_dir)
            os.makedirs(self.backup_dir, exist_ok=True)

        # backup file store
        if not self.params.only_database:
            filestore_backup_path = os.path.abspath(os.path.join(self.params.backup_dir, "filestore"))
            self.sync_files(self.filestore, filestore_backup_path, dirs=True, filestore=True, local=True)
            # third check if restored flag is accedently copied
            restored_file_path = os.path.join(filestore_backup_path, 'restored')
            if os.path.exists(restored_file_path):
                _logger.info("Remove %s", restored_file_path)
                os.unlink(restored_file_path)

        # backup database
        backup_file_path = self.create_backlog(os.path.join(self.backup_dir, 'db.dump'))
        self.backup_database(backup_file_path, compatible=self.params.compatible)


class Restore(ConfigCommand, Command, DatabaseMixin):

    def __init__(self):
        super().__init__()
        self.filestore = None
        self.restored_file = None
        self.db_dump = None

        self.parser.add_argument(
            "--update",
            action="store_true",
            name="update",
            default=False,
            help="Update the database after restore.")
        self.parser.add_argument(
            "--install",
            nargs='+',
            name="install",
            help="Install a specific module after restore.")
        self.parser.add_argument(
            "--restore-fs",
            name="restore_fs",
            help="The filestore source for restore."
        )
        self.parser.add_argument(
            "--restore-db",
            name="restore_db",
            help="The database source for restore."
        )
        self.parser.add_argument(
            "--restore-zip",
            name="restore_zip",
            help="The database+filestore within zip for restore."
        )
        self.parser.add_argument(
            "--restore-zip-db",
            name="restore_zip_db",
            help="The database to download as ZIP."
        )
        self.parser.add_argument(
            "--restore-zip-password",
            name="restore_zip_password",
            help="The password needed to download the ZIP."
        )
        self.parser.add_argument(
            "--wait-for-data",
            action="store_true",
            name="wait_for_data",
            default=False,
            help="Wait until restore data is available, and check it every 5 seconds.")
        self.parser.add_argument(
            "--neutralize",
            action="store_true",
            name="neutralize",
            default=False,
            help="Neutralize production data (deleting mail servers etc...).")
        self.parser.add_argument(
            "--development",
            action="store_true",
            name="development",
            default=False,
            help="Prepare development database.")
        self.parser.add_argument(
            "--pg_admin_user",
            name="pg_admin_user",
            envvar="PGADMINUSER",
            help="The database admin user."
        )
        self.parser.add_argument(
            "--pg_admin_password",
            name="pg_admin_password",
            help="The database admin password.",
            envvar="PGADMINPASSWORD",
        )

    def restore_filestore(self, url):
        # prepare urls
        local = False
        if url.netloc:
            rsync_url = f"{url.netloc}:{url.path}/"
        else:
            local = True
            rsync_url = f"{url.path}/"
            if not os.path.exists(rsync_url):
                raise ConfigException(f"No filestore found at {rsync_url}")
        # sync filestore
        self.sync_files(rsync_url, self.filestore, local=local, dirs=True, filestore=True, info="Restore")

    def neutralize(self):
        _logger.info("Neutralize database %s", self.params.database)
        with odoo.sql_db.db_connect(self.params.database).cursor() as cr:
            # update uuid
            database_uuid = str(uuid.uuid4())
            cr.execute("""UPDATE ir_config_parameter
                       SET value = %s
                       WHERE key = 'database.uuid' """, (database_uuid,))
            # remove enterprise data
            remove_keys = (
                'database.expiration_date',
                'database.expiration_reason',
                'database.enterprise_code'
            )
            cr.execute("""DELETE FROM ir_config_parameter
                       WHERE key IN %s """, (remove_keys,))
            # set new creation date
            create_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cr.execute("""UPDATE ir_config_parameter
                       SET value = %s
                       WHERE key = 'database.create_date' """, (create_date,))
            # neutralize database
            cr.execute("SELECT COALESCE(COUNT(id),0) FROM ir_config_parameter WHERE KEY = 'database.is_neutralized' AND value IN ('true', 'True')")
            is_neutralized = cr.fetchone()[0]
            if not is_neutralized:
                odoo.modules.neutralize.neutralize_database(cr)
            else:
                _logger.warning('Database %s is already neutralized', self.params.database)

    def prepare_local_development_before(self):
        _logger.info("Prepare database %s for local development before update", self.params.database)
        with odoo.sql_db.db_connect(self.params.database).cursor() as cr:
            # set url to localhost
            cr.execute("""UPDATE ir_config_parameter
                       SET value = 'http://localhost:8069'
                       WHERE key = 'web.base.url'""")
            # remove url freeze
            cr.execute("DELETE FROM ir_config_parameter WHERE key = 'web.base.url.freeze'")
            # mark database for development
            cr.execute("""INSERT INTO ir_config_parameter (key, value)
                    VALUES ('database.development', 'True')
                    ON CONFLICT (key) DO UPDATE SET value = 'True';""")

    def prepare_local_development_after(self, env):
        _logger.info("Prepare database %s for local development after update", self.params.database)
        cr = env.cr
        # disable cron jobs
        cr.execute("UPDATE ir_cron SET active = FALSE")
        # reset password to admin
        cr.execute("UPDATE res_users SET password = 'admin'")


    def download_database(self, url):
        if url.netloc:
            # get path without wildcard
            ls_params = ''
            url_path_split = url.path.split('/*.')[0]
            if len(url_path_split) > 1:
                url_path = url_path_split[0]
                ls_params = '-tr'
            else:
                url_path = url.path

            # check if database exists
            ssh_url = f"{url.netloc}"
            result = subprocess.check_output(f"ssh {ssh_url} -q 'ls {ls_params} {url.path}'", shell=True).decode()
            if not result:
                raise ConfigException(f"No database found at {str(url)}")

            # download database
            dump_file = [r for r in result.split("\n") if r][-1]
            if not dump_file:
                raise ConfigException(f"No database file found at {str(url)}")
            if dump_file != url_path:
                if dump_file.startswith(url_path):
                    dump_path = dump_file
                else:
                    dump_path = f"{url_path}/{dump_file}"
            else:
                dump_path = url_path

            # detect zip format
            split_dump_file = os.path.splitext(dump_path)
            zip_ext = ''
            extract_cmd = None
            if len(split_dump_file) == 2:
                if split_dump_file[1] == '.bz2':
                    zip_ext = split_dump_file[1]
                    extract_cmd = 'bzip2 -d %s'
                elif split_dump_file[1] == '.gz':
                    zip_ext = split_dump_file[1]
                    extract_cmd = 'gzip -d %s'

            # build paths
            dest_path = os.path.join(self.parser.config_dir, 'db.dump')
            zipped_dest_path = f'{dest_path}{zip_ext}'
            rsync_url = f"{ssh_url}:{dump_path}"

            # sync file
            self.sync_files(rsync_url, zipped_dest_path, info='Download Database')

            # check if there is something to extract
            if extract_cmd:
                if os.path.exists(dest_path):
                    os.remove(dest_path)
                _logger.info("Extract database %s to %s", zipped_dest_path, dest_path)
                subprocess.run(extract_cmd % zipped_dest_path, shell=True, check=True)
                if not os.path.exists(dest_path):
                    raise ConfigException(f"Extracted database not found at {dest_path}")

            self.db_dump = dest_path
        else:
            if not os.path.exists(url.path):
                raise ConfigException(f"No database file found at {str(url)}")
            elif os.path.isdir(url.path):
                db_files = [f for f in os.listdir(url.path) if f.endswith(".dump") or f.endswith(".sql")]
                if not db_files:
                    raise ConfigException(f"No database file found at {str(url)}")
                self.db_dump = os.path.join(url.path, db_files[0])
            else:
                self.db_dump = url.path

    def setup_db_env(self, admin_user=None, admin_password=None):
        super().setup_db_env(admin_user=admin_user, admin_password=admin_password)

        # if not admin user is set, skip
        if not admin_user:
            return

        # get database user
        odoo_db_user = config.get('db_user')
        odoo_db_password = config.get('db_password')
        if not odoo_db_user:
            raise ConfigException('(CreateUser) Odoo database user is not defined')
        if not odoo_db_password:
            raise ConfigException('(CreateUser) Odoo database user password is not defined')

        # prepare new user
        con = self.connect_database_admin(database='postgres')
        try:
            cr = con.cursor()
            try:
                cr.execute('SELECT rolname FROM pg_catalog.pg_roles WHERE rolname = %s', (odoo_db_user,))
                res = cr.fetchall()
                if not res:
                    cr.execute(f'CREATE USER {odoo_db_user} WITH CREATEDB PASSWORD %s', (odoo_db_password, ))
                else:
                    cr.execute(f'ALTER USER {odoo_db_user} WITH CREATEDB PASSWORD %s', (odoo_db_password,))
                cr.execute('COMMIT')
            finally:
                cr.close()
        finally:
            con.close()

    def restore_and_update(self):
        # init needed env
        db_name = config.get('db_name')
        if not db_name:
            raise ConfigException("No database name configured")

        # setup database environment
        self.setup_db_env(admin_user=self.params.pg_admin_user,
                          admin_password=self.params.pg_admin_password)

        # ensure filestore
        self.filestore = os.path.join(config['data_dir'], 'filestore', db_name)
        if not os.path.exists(self.filestore):
            _logger.warning('Create filestore %s', self.filestore)
            os.makedirs(self.filestore, exist_ok=True)

        # remove restored marker if exists
        self.restored_file = os.path.join(self.filestore, RESTORED_FILE_NAME)
        if os.path.exists(self.restored_file):
            os.unlink(self.restored_file)

        # restore filestore
        while True:
            try:
                # copy filestore
                if self.params.restore_fs:
                    restore_url = urlparse(self.params.restore_fs)
                    if not restore_url:
                        raise ConfigException(f"Invalid filestore restore url {self.params.restore_fs}")
                    self.restore_filestore(restore_url)

                # copy database
                if self.params.restore_db:
                    restore_url = urlparse(self.params.restore_db)
                    if not restore_url:
                        raise ConfigException(f"Invalid database restore url {self.params.restore_db}")
                    self.download_database(restore_url)

                break

            except (ConfigException, subprocess.CalledProcessError) as e:
                if self.params.wait_for_data:
                    _logger.warning(str(e))
                    _logger.warning("Waiting another %s seconds for data...", DEFAULT_SLEEP)
                    time.sleep(DEFAULT_SLEEP)
                else:
                    raise e

        # restore database
        if self.db_dump:
            # restore
            self.restore_database(self.db_dump)

            # neutralize and/or development
            if self.params.neutralize or self.params.development:
                self.neutralize()
            if self.params.development:
                self.prepare_local_development_before()

            # update database
            if self.params.update:
                config["update"]["all"] = 1
                update_database(self.params.database)

            # final tasks
            self.setup_env()

    def run_config(self):
        if self.params.restore_zip:
            _logger.info("Restore from zip %s", self.params.restore_zip)
            restore_url = urlparse(self.params.restore_zip)
            if not restore_url:
                raise ConfigException(f"Invalid restore url {self.params.restore_zip}")

            with tempfile.TemporaryDirectory() as temp_dir:
                if restore_url.netloc:
                    if not self.params.restore_zip_password:
                        raise ConfigException("Password needed to be set via --restore-zip-password for ZIP download")
                    if not self.params.restore_zip_db:
                        raise ConfigException("Database needed to be set via --restore-zip-db for ZIP download")
                    payload = {
                        "master_pwd": self.params.restore_zip_password,
                        "name": self.params.restore_zip_db,
                        "backup_format": "zip"
                    }
                    response = requests.post(self.params.restore_zip, data=payload, timeout=1800)
                    response.raise_for_status()
                    self.params.restore_zip = os.path.join(temp_dir, "backup.zip")
                    extract_dir = os.path.join(temp_dir, "backup")
                    with open(self.params.restore_zip, 'wb') as f:
                        f.write(response.content)
                else:
                    extract_dir = temp_dir

                with zipfile.ZipFile(self.params.restore_zip, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)

                self.params.restore_fs = os.path.join(extract_dir, "filestore")
                self.params.restore_db = extract_dir
                self.restore_and_update()
        else:
            self.restore_and_update()

    def run_config_env(self, env):
        # install modules
        if self.params.install:
            for module_name in self.params.install:
                self.install_module(env, module_name)

        # add restored marker
        with open(self.restored_file, "w", encoding="utf-8") as f:
            f.write(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        # after update
        if self.params.development:
            self.prepare_local_development_after(env)



###############################################################################
# Serve
###############################################################################


class Serve(Command):
    """ Quick start the Odoo server for your Project """

    def run(self, cmdargs):
        progname = sys.argv[0].rsplit(os.path.sep, maxsplit=1)[-1]
        parser = Profile(self.name,
            prog=f"{progname} serve",
            description=self.__doc__
        )

        parser.add_argument("--create",
                            action="store_true",
                            help="Create database if it not exist")

        parser.add_argument(
            "-d",
            "--database",
            metavar="DATABASE",
            default=None,
            envvar=True,
            help="Specify the database",
        )

        parser.add_argument(
            "--addons-path",
            metavar="ADDONS",
            envvar=True)

        parser.add_argument("--config",
            metavar="CONFIG",
            envvar=True,
            help="Specify the configuration")

        parser.add_argument("--wait-for-database",
            name="wait_for_database",
            action="store_true",
            envvar=True)

        parser.add_argument("--wait-for-restore",
            name="wait_for_restore",
            action="store_true",
            envvar=True)

        args, unknown = parser.parse_known_args(args=cmdargs)

        # remove additional args
        for additional_arg in ('--wait-for-database', '--wait-for-restore'):
            if additional_arg in cmdargs:
                cmdargs.remove(additional_arg)

        # configure database name
        # (use defaults from parser if not used)
        if args.database:
            if "--db-filter" not in cmdargs:
                cmdargs = [f"--db-filter=^{args.database}$"] + cmdargs
            if "-d" not in cmdargs and "--database" not in cmdargs:
                cmdargs = [f"--database={args.database}"] + cmdargs

        # configure addons paths, if it is not passed
        if "--addons-path" not in cmdargs and args.addons_path:
            cmdargs = [f"--addons-path={args.addons_path}"] + cmdargs

        # configure config file, if it is not passed
        if "--config" not in cmdargs and args.config:
            cmdargs = [f"--config={args.config}"] + cmdargs

        # prepare hook
        report_configuration_fct = odoo.cli.server.report_configuration
        def report_configuration_hook():
            report_configuration_fct()

            # wait for restore
            if args.wait_for_restore:
                restored_file = os.path.join(config['data_dir'], 'filestore', config['db_name'], RESTORED_FILE_NAME)
                while not os.path.exists(restored_file):
                    _logger.warning('Waiting %s seconds for %s...', DEFAULT_SLEEP, restored_file)
                    time.sleep(DEFAULT_SLEEP)

            # add wait for database function
            if args.wait_for_database:
                self.setup_db_env()
                while not self.is_database_ready():
                    _logger.warning('Waiting %s for database %s...', DEFAULT_SLEEP, self.db_name)
                    time.sleep(DEFAULT_SLEEP)

        # install configuration hook and start server
        odoo.cli.server.report_configuration = report_configuration_hook
        odoo.cli.server.main(cmdargs)
