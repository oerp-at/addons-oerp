""" Client of the Odoo upgrade platform (upgrade.odoo.com)

The same API calls as the official script https://upgrade.odoo.com/upgrade,
without its prompts and its fixed filestore path: odoo migrate dumps and
restores the database and merges the filestore itself. The script reports
errors only in its log and exits with 0, which is useless in a job.
"""
import json
import logging
import os
import shutil
import subprocess
import time
from urllib import request as urlrequest

_logger = logging.getLogger(__name__)

UPGRADE_SERVER = os.environ.get('UPGRADE_SERVER_NAME', 'https://upgrade.odoo.com')
DATA_SERVER_USER = 'odoo'
DATA_SERVER_PATH = '/data'
REQUEST_TIMEOUT = 60
STATUS_PERIOD = 30
UPLOAD_NAME = 'origin.dump'
FILESTORE_NAME = 'filestore'
REPORT_NAMES = ('upgrade-report.html', 'upgrade.log')
#: states of a request that can be resumed after an interruption
RESUMABLE = ('pending', 'progress', 'done')


class OdooUpgradeError(Exception):
    pass


class OdooUpgrade:
    """ one upgrade request; all files live in ``workdir``, so an interrupted
    request (e.g. a restarted job) is resumed instead of sent again """

    def __init__(self, contract, target, aim, workdir):
        self.contract = contract
        self.target = target
        self.aim = aim
        self.workdir = workdir
        self.server = UPGRADE_SERVER
        self.data_server = None
        self.token = None
        self.ssh_key = os.path.join(workdir, 'ssh_key')
        self.known_hosts = os.path.join(workdir, 'known_hosts')
        self.token_file = os.path.join(workdir, f'token-{target}-{aim}')
        self.upload_path = os.path.join(workdir, UPLOAD_NAME)
        self.download_dir = os.path.join(workdir, 'download')

    # ------------------------------------------------------------------
    # api
    # ------------------------------------------------------------------

    def call(self, endpoint, params):
        payload = json.dumps({'jsonrpc': '2.0', 'method': 'call', 'params': params, 'id': None})
        req = urlrequest.Request(f'{self.server}/{endpoint}', payload.encode(),
                                 headers={'Content-Type': 'application/json'})
        try:
            with urlrequest.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
                body = response.read().decode('utf-8', 'replace')
        except OSError as e:
            raise OdooUpgradeError(f"Upgrade platform {endpoint}: {e}") from e
        if not body.strip():
            return {}
        try:
            data = json.loads(body)
        except ValueError as e:
            raise OdooUpgradeError(f"Upgrade platform {endpoint}: no JSON response") from e
        if 'error' in data:
            error = data['error']
            message = (error.get('data') or {}).get('message') or error.get('message')
            raise OdooUpgradeError(f"Upgrade platform {endpoint}: {message}")
        result = data.get('result')
        if isinstance(result, dict) and result.get('error'):
            raise OdooUpgradeError(f"Upgrade platform {endpoint}: {result['error']}")
        return result

    def call_checked(self, endpoint, params, keys):
        result = self.call(endpoint, params)
        missing = [k for k in keys if k not in (result or {})]
        if missing:
            raise OdooUpgradeError(f"Upgrade platform {endpoint}: response without {missing}")
        return result

    def set_host(self, host_uri):
        """ a request stays on the host it was assigned to """
        self.server = f'https://{host_uri}'
        self.data_server = host_uri

    def status(self):
        res = self.call_checked('upgrade/request/status', {'token': self.token},
                                ('status', 'host_uri'))
        return res['status'], res['host_uri'], res.get('reason'), res.get('archived')

    def logs(self, from_byte):
        req = urlrequest.Request(f'{self.server}/upgrade/request/logs?token={self.token}',
                                 headers={'Range': f'bytes={from_byte:d}-'})
        try:
            with urlrequest.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
                return response.read()
        except OSError as e:
            _logger.debug("Upgrade platform logs: %s", e)
            return b''

    # ------------------------------------------------------------------
    # request
    # ------------------------------------------------------------------

    def resume(self):
        """ state of an interrupted request of this workdir, None to start anew """
        if not os.path.exists(self.token_file):
            return None
        with open(self.token_file, encoding='utf-8') as f:
            self.token = f.read().strip()
        try:
            state, host_uri, _reason, archived = self.status()
        except OdooUpgradeError as e:
            _logger.warning("Previous upgrade request not resumable: %s", e)
            return None
        if archived or state not in RESUMABLE:
            _logger.info("Previous upgrade request is %s, starting a new one",
                         'archived' if archived else state)
            return None
        self.set_host(host_uri)
        _logger.info("Resume the upgrade request (%s)", state)
        return state

    def create(self):
        """ create the request; raises OdooUpgradeError if Odoo refuses it,
        e.g. an unknown subscription or a target version that is not offered """
        os.makedirs(self.workdir, exist_ok=True)
        for path in (self.ssh_key, self.ssh_key + '.pub', self.token_file):
            if os.path.exists(path):
                os.remove(path)
        self.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', self.ssh_key])
        with open(self.ssh_key + '.pub', encoding='utf-8') as f:
            public_key = f.read()
        res = self.call_checked('upgrade/request/create', {
            'contract': self.contract,
            'target': self.target,
            'aim': self.aim,
            'actuator': 'cli',
            'env_vars': [],
            'ssh_key': public_key,
            'api_version': '0.2',
        }, ('request_id', 'token', 'assigned_host_uri'))
        if res.get('info'):
            _logger.warning("Upgrade platform: %s", res['info'])
        self.token = res['token']
        with open(self.token_file, 'w', encoding='utf-8') as f:
            f.write(self.token)
        self.set_host(res['assigned_host_uri'])
        _logger.info("Odoo upgrade request %s created: %s, aim %s, host %s",
                     res['request_id'], self.target, self.aim, res['assigned_host_uri'])

    def transfer(self, kind, destination):
        """ rsync over ssh to/from the data server of the request """
        keys = ('ssh_port', 'known_hosts') + (('dump_name',) if kind == 'download' else ())
        info = self.call_checked('upgrade/request/transfer/start',
                                 {'token': self.token, 'transfer_type': kind}, keys)
        with open(self.known_hosts, 'w', encoding='utf-8') as f:
            f.write(info['known_hosts'] or '')
        ssh = (f"ssh -p {info['ssh_port']} -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes "
               f"-o UserKnownHostsFile={self.known_hosts} -i {self.ssh_key}")
        remote = f'{DATA_SERVER_USER}@{self.data_server}:{DATA_SERVER_PATH}'
        try:
            if kind == 'upload':
                # the dump is a directory (pg_dump --format d), only its content is sent
                self.run(['rsync', '--recursive', '--links', '--times', '--delete-after',
                          '--rsh=' + ssh, self.upload_path + '/', f'{remote}/{UPLOAD_NAME}'])
            else:
                names = (info['dump_name'], FILESTORE_NAME) + REPORT_NAMES
                self.run(['rsync', '-a', '--ignore-missing-args', '--rsh=' + ssh]
                         + [f'{remote}/{name}' for name in names] + [destination + '/'])
        finally:
            self.call('upgrade/request/transfer/stop', {'token': self.token})
        return info

    def upload(self):
        _logger.info("Upload %s to %s", self.upload_path, self.data_server)
        self.transfer('upload', None)
        res = self.call_checked('upgrade/request/process', {'token': self.token},
                                ('is_pg_version_compatible',))
        if not res['is_pg_version_compatible']:
            raise OdooUpgradeError("The PostgreSQL version here is older than the one Odoo needs "
                                   f"for {self.target}: the upgraded database cannot be restored")

    def wait(self):
        """ follow the log of the platform until the request is finished """
        _logger.info("Odoo upgrades the database, this takes a while")
        state, _host, reason, _archived = self.status()
        offset = 0
        while state in ('pending', 'progress'):
            time.sleep(STATUS_PERIOD)
            if state == 'progress':
                logs = self.logs(offset)
                offset += len(logs)
                for line in logs.decode('utf-8', 'replace').strip().splitlines():
                    _logger.info("upgrade.odoo.com: %s", line)
            state, _host, reason, _archived = self.status()
        if state != 'done':
            raise OdooUpgradeError(f"Odoo upgrade request {state}" + (f": {reason}" if reason else ""))

    def download(self):
        """ :return: (path of the upgraded dump, path of the filestore part) """
        if os.path.isdir(self.download_dir):
            shutil.rmtree(self.download_dir)
        os.makedirs(self.download_dir)
        _logger.info("Download the upgraded database from %s", self.data_server)
        info = self.transfer('download', self.download_dir)
        return (os.path.join(self.download_dir, info['dump_name']),
                os.path.join(self.download_dir, FILESTORE_NAME))

    def finish(self):
        """ keep report and log of the platform, remove dumps, keys and token """
        kept = []
        for name in REPORT_NAMES:
            path = os.path.join(self.download_dir, name)
            if os.path.exists(path):
                kept.append(os.path.join(self.workdir, name))
                shutil.move(path, kept[-1])
        for name in os.listdir(self.workdir):
            path = os.path.join(self.workdir, name)
            if path in kept:
                continue
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
        if kept:
            _logger.info("Report of the Odoo upgrade: %s", ', '.join(kept))

    @staticmethod
    def run(command, env=None):
        res = subprocess.run(command, check=False, capture_output=True, text=True, env=env)
        if res.returncode:
            output = (res.stderr or res.stdout or '').strip()[-2000:]
            raise OdooUpgradeError(f"{command[0]} failed ({res.returncode}): {output}")
        return res
