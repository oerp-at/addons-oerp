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

        # additional arguments
        parser.add_argument("--wait-for-database",
            name="wait_for_database",
            action="store_true",
            envvar=True)
        parser.add_argument("--wait-for-restore",
            name="wait_for_restore",
            action="store_true",
            envvar=True)

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
            ):
            if hasattr(args, config_key):
                value = getattr(args, config_key)
                if value:
                    os.environ[env_name] = value

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

        # install configuration hook and start server
        server_cli.report_configuration = report_configuration_hook
        server_cli.main(other_args)
