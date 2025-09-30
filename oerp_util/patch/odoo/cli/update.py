import logging
from multiprocessing import Pool
import psycopg2
from odoo.tools.config import config

from . import Command
from .assemble import CommandMixin, update_database


_logger = logging.getLogger(__name__)


class Update(CommandMixin, Command):
    """ Run Update Database """

    def __init__(self):
        super().__init__()
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
                # pylint: disable=sql-injection
                cr.execute(f"SELECT datname FROM pg_database WHERE datname LIKE '{self.params.db_prefix}_%'")
                return [r[0] for r in cr.fetchall()]
            finally:
                cr.close()
        finally:
            con.close()

    def run_config(self):
        # update multible databases
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
            # update single databasee
            update_database(self.params.database, modules=self.params.module)