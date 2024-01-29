import os
import json
import logging
from odoo.tools import config

_logger = logging.getLogger(__name__)


class TestMixin(object):
    """ Util class for tests. """

    def getDownloadPath(self, path):
        download_path = config.get('test_download')
        if not download_path:
            _logger.warning('No download path configuered. Please configure test_download in odoo.conf')
            return None

        parent_path = os.path.dirname(path)
        if parent_path:
            # create parent directories
            parent_path = os.path.join(download_path, parent_path)
            os.makedirs(parent_path, exist_ok=True)
        else:
            # or use download path directly
            parent_path = download_path

        return os.path.join(parent_path, path)

    def saveTestData(self, name, data):
        path = self.getDownloadPath(name)
        if path:
            if isinstance(data, dict) or isinstance(data, list):
                if not path.endswith('.json'):
                    path = path + '.json'
                data = json.dumps(data, indent=2)
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(data)
            elif isinstance(data, str):
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(data)
            else:
                with open(path, 'wb') as f:
                    f.write(data)

    def assertPdf(self, data, name=None):
        ''' Asserts that the given data is a valid PDF.
        :param data: PDF data
        :param name: name for the downloaded file, if it should be saved locally
        '''
        self.assertTrue(data)
        self.assertTrue(data.startswith(b'%PDF-'))
        if name:
            path = self.getDownloadPath(name)
            if path:
                with open(path, 'wb') as f:
                    f.write(data)