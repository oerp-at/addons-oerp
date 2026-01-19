import os
import time
import uuid
import tempfile
import logging
import subprocess
import zipfile
from urllib.parse import urlparse
from datetime import datetime
import requests

import odoo
import odoo.modules.neutralize
from odoo.tools.config import config

from . import Command
from .assemble import CommandMixin, DatabaseMixin, ConfigException, RESTORED_FILE_NAME, DEFAULT_SLEEP, update_database


_logger = logging.getLogger(__name__)


class Restore(CommandMixin, Command, DatabaseMixin):
    """ Run database restore """

    def __init__(self):
        super().__init__()
        self.filestore = None
        self.restored_file = None
        self.db_dump = None
        self.db_name = None

        # ensure that restore dir exist
        self.restore_dir = os.path.join(self.parser.base_dir, ".restore")
        if not os.path.exists(self.restore_dir):
            os.makedirs(self.restore_dir)

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
        self.parser.add_argument(
            "--force-drop-db",
            action="store_true",
            name="force_drop_db",
            default=False,
            help="Cancel all connections to the database before restore.")
        self.parser.add_argument(
            "--max-size",
            name="max_size",
            default=None,
            help="Set the maximum allowed size in MB.")
        self.parser.add_argument(
            "--delete",
            action="store_true",
            name="delete",
            default=False,
            help="Full sync of filestore, delete files that are not in the source.")

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
        self.sync_files(rsync_url, self.filestore, local=local, dirs=True, filestore=True, info="Restore", max_size=self.params.max_size, delete=self.params.delete)

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
        #cr.execute("UPDATE res_users SET password = 'admin'")
        cr.execute("""UPDATE res_users
                       SET password = '$pbkdf2-sha512$600000$UWrtfU/JGSMEIESIUUrp3Q$I/P7liB6AwKFLVL49LCiQJSqRIK16D21Fc4MLP7ijeEa1SRKAWQ2ODSWVFm5p/tfd97FXf/FW.xQCmuCHdGQhw'
                       WHERE active AND (password IS NOT NULL OR login = 'admin')""")


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
            dest_path = os.path.join(self.restore_dir, f'{self.db_name}.dump')
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
        if not self.db_name:
            raise ConfigException("No database name configured")

        # setup database environment
        self.setup_db_env(admin_user=self.params.pg_admin_user,
                          admin_password=self.params.pg_admin_password)

        # ensure filestore
        self.filestore = os.path.join(config['data_dir'], 'filestore', self.db_name)
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
            self.restore_database(self.db_dump, force=self.params.force_drop_db)

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
        # get database name
        db_name = config.get('db_name')
        if isinstance(db_name, list):
            db_name = db_name[0]
        self.db_name = db_name

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

