import os
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