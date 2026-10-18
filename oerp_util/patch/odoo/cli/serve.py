import os
import sys
import time
import logging

from odoo.tools.config import config
import odoo.cli.server as server_cli

from . import Command
from .assemble import Profile, RESTORED_FILE_NAME, DEFAULT_SLEEP, get_db_name, DatabaseMixin


_logger = logging.getLogger(__name__)


class Serve(Command, DatabaseMixin):
    """ Quick start the Odoo server for your Project """

    def get_migration_state(self):
        """ oerp.migration.state of the database, None if not set or unknown """
        if not self.db_name:
            return None
        try:
            con = self.connect_database()
        except Exception:  # noqa: BLE001 - no database yet, nothing to protect
            return None
        try:
            with con.cursor() as cr:
                cr.execute("SELECT value FROM ir_config_parameter WHERE key = %s",
                           ['oerp.migration.state'])
                row = cr.fetchone()
                return row[0] if row else None
        except Exception:  # noqa: BLE001 - e.g. a fresh database without tables
            return None
        finally:
            con.close()

    def run(self, cmdargs):
        progname = sys.argv[0].rsplit(os.path.sep, maxsplit=1)[-1]
        parser = Profile(self.name,
            prog=f"{progname} serve",
            description=self.__doc__
        )

        # environment arguments
        parser.add_argument(
            "-d",
            "--database",
            metavar="DATABASE",
            default=None,
            envvar=True,
            help="Specify the database",
        )
        parser.add_argument("--db_host",
            metavar="DB_HOST",
            envvar=True,
            help="Specify the database host")
        parser.add_argument("--db_password",
            metavar="DB_PASSWORD",
            envvar=True,
            help="Specify the database password")
        parser.add_argument("--db_port",
            metavar="DB_PORT",
            envvar=True,
            help="Specify the database port",
            type=int)
        parser.add_argument("--db_user",
            metavar="DB_USER",
            envvar=True,
            help="Specify the database user")
        parser.add_argument(
            "--addons-path",
            metavar="ADDONS",
            envvar=True)
        parser.add_argument("--config",
            metavar="CONFIG",
            envvar=True,
            help="Specify the configuration")
        parser.add_argument("--http-port",
            name="http_port",
            metavar="HTTP_PORT",
            type=int,
            envvar=True,
            help="Specify the HTTP port")

        # additional arguments
        parser.add_argument("--wait-for-database",
            name="wait_for_database",
            action="store_true",
            envvar=True)
        parser.add_argument("--wait-for-restore",
            name="wait_for_restore",
            action="store_true",
            envvar=True)
        parser.add_argument("--ignore-migration-state",
            name="ignore_migration_state",
            action="store_true",
            help="Serve even if odoo migrate marked the database as running or failed")

        # parse
        args, other_args = parser.parse_known_args(args=cmdargs)

        # rewrite environment variables
        for config_key, env_name in (
            ('database', 'PGDATABASE'),
            ('db_host', 'PGHOST'),
            ('db_port', 'PGPORT'),
            ('db_user', 'PGUSER'),
            ('db_password', 'PGPASSWORD'),
            ('addons_path', 'ODOO_ADDONS_PATH'),
            ('config', 'ODOO_RC'),
            ('http_port', 'ODOO_HTTP_PORT'),
            ):
            if hasattr(args, config_key):
                value = getattr(args, config_key)
                if value:
                    os.environ[env_name] = str(value)

        # prepare hook
        report_configuration_fct = server_cli.report_configuration
        def report_configuration_hook():
            report_configuration_fct()

            # wait for restore
            if args.wait_for_restore:
                db_name = get_db_name(config['db_name'])
                restored_file = os.path.join(config['data_dir'], 'filestore', db_name, RESTORED_FILE_NAME)
                while not os.path.exists(restored_file):
                    _logger.warning('Waiting %s seconds for %s...', DEFAULT_SLEEP, restored_file)
                    time.sleep(DEFAULT_SLEEP)

            # add wait for database function
            if args.wait_for_database:
                self.setup_db_env()
                while not self.is_database_ready():
                    _logger.warning('Waiting %s for database %s...', DEFAULT_SLEEP, self.db_name)
                    time.sleep(DEFAULT_SLEEP)

            # never serve a half migrated database (marker of odoo migrate)
            if not args.ignore_migration_state:
                self.setup_db_env()
                state = self.get_migration_state()
                if state in ('running', 'failed'):
                    _logger.critical('Migration state of %s is %s, not serving it '
                                     '(--ignore-migration-state to override)', self.db_name, state)
                    sys.exit(1)

        # install configuration hook and start server
        server_cli.report_configuration = report_configuration_hook
        server_cli.main(other_args)
