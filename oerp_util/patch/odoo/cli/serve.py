import os
import sys
import time
import logging

from odoo.tools.config import config
import odoo.cli.server as server_cli

from . import Command
from .assemble import Profile, RESTORED_FILE_NAME, DEFAULT_SLEEP


_logger = logging.getLogger(__name__)


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
        report_configuration_fct = server_cli.report_configuration
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
        server_cli.report_configuration = report_configuration_hook
        server_cli.main(cmdargs)
