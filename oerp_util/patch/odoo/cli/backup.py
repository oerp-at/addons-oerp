import os
import logging
from datetime import datetime
import shutil

from odoo.tools.config import config

from . import Command
from .assemble import CommandMixin, DatabaseMixin

_logger = logging.getLogger(__name__)


class Backup(CommandMixin, Command, DatabaseMixin):
    """ Backup Odoo Instance """

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
        self.setup_db_env(admin_user=self.params.pg_admin_user, admin_password=self.params.pg_admin_password)
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
