import os
import sys
import logging
import subprocess

from . import Command
from .assemble import Profile

_logger = logging.getLogger(__name__)


class AutoEnv(Command):
    """ Run odoo standard commands in auto environment """

    def run(self, cmdargs):
        orignal_cmd = sys.argv[0]
        # create parser
        progname = orignal_cmd.rsplit(os.path.sep, maxsplit=1)[-1]
        parser = Profile(self.name,
            prog=f"{progname} autoenv",
            description=self.__doc__
        )
        # add most used arguments
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

        args, unknown = parser.parse_known_args(args=cmdargs)
        env_vars = os.environ.copy()

        # configure environment variables
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
                    env_vars[env_name] = str(value)

        # run the original command again with new commandss
        command = [orignal_cmd] + cmdargs
        res = subprocess.run(command, check=False, env=env_vars)
        exit(res.returncode)
