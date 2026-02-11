import os
import logging
from datetime import datetime
import shutil
import subprocess

from odoo.tools.config import config

from . import Command
from .assemble import CommandMixin, DatabaseMixin, ConfigException

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

        self.parser.add_argument(
            "--compress",
            action="store_true",
            name="compress",
            default=False,
            help="Compress the backup file with gzip.")

        self.parser.add_argument(
            "--backup-store",
            name="backup_store",
            help="The backup store where backups will be pushed via restic (only for full backups)."
        )

        self.parser.add_argument(
            "--backup-store-days",
            name="backup_store_days",
            type=int,
            default=7,
            help="The days the snapshot is kept in the backup store."
        )

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
                backlog_minus_new = self.params.backlog-1
                for index, backlog_name in enumerate(sorted(os.listdir(backlog_dir), reverse=True)):
                    # delete backlogfile if index is bigger than backlog size
                    backlog_file_path = os.path.join(backlog_dir, backlog_name)
                    if index >= backlog_minus_new and os.path.isfile(backlog_file_path):
                        _logger.warning('Delete old backup %s', backlog_file_path)
                        os.unlink(backlog_file_path)

            # build new backlog file
            t = datetime.fromtimestamp(os.path.getctime(file_path))
            new_backup_file = os.path.join(backlog_dir, f'{t.strftime("%Y-%m-%d_%H%M%S")}_{base_name}')
            _logger.info('Backlog current backup %s to %s', file_path, new_backup_file)
            shutil.move(file_path, new_backup_file)

        return file_path

    def push_backup_to_store(self, backup_dir, backup_store, backup_store_days=7):
        _logger.info("Push backup to store %s", backup_store)
        # Check if the remote destination is initialized; if not, initialize it
        result = subprocess.run(f"restic -r {backup_store} snapshots", shell=True, check=False)
        if result.returncode not in (0,3):
            _logger.warning("Initialize restic repository at %s", backup_store)
            subprocess.run(f"restic -r {backup_store} init", shell=True, check=True)
        # Backup
        subprocess.run(f'restic -r {backup_store} backup {backup_dir} --exclude=".backlog"', shell=True, check=True)
        # Forget old backups
        if backup_store_days > 0:
            subprocess.run(f"restic -r {backup_store} forget --keep-within {backup_store_days}d --prune", shell=True, check=True)

    def run_config(self):
        self.setup_db_env(admin_user=self.params.pg_admin_user, admin_password=self.params.pg_admin_password)
        self.filestore = os.path.abspath(os.path.join(config['data_dir'], 'filestore', self.db_name))

        # create backup directory
        if not self.params.backup_dir:
            raise ConfigException("Backup directory is required: --backup-dir <path>")

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

        # prepare backup file path
        backup_file_path = os.path.join(self.backup_dir, 'db.dump')
        zipped_backup_file_path = backup_file_path
        if self.params.compress:
            zipped_backup_file_path = backup_file_path + '.gz'
            # if previous backup file is not compressed, compress it
            if os.path.exists(backup_file_path) and not os.path.exists(zipped_backup_file_path):
                _logger.warning("Compress old backup file %s", backup_file_path)
                subprocess.run(f"gzip {backup_file_path}", shell=True, check=True)

        # create backlog
        self.create_backlog(zipped_backup_file_path)
        # backup database
        self.backup_database(backup_file_path, compatible=self.params.compatible)
        # compress backup file after backup
        if self.params.compress and os.path.exists(backup_file_path):
            # unlink if there still exists a previous compressed backup file
            if os.path.exists(zipped_backup_file_path):
                _logger.warning("Remove old compressed backup file %s", zipped_backup_file_path)
                os.unlink(zipped_backup_file_path)
            _logger.info("Compress backup file %s", zipped_backup_file_path)
            subprocess.run(f"gzip {backup_file_path}", shell=True, check=True)

        # push backup to store
        if self.params.backup_store and not self.params.only_database:
            self.push_backup_to_store(self.backup_dir, self.params.backup_store, self.params.backup_store_days)

