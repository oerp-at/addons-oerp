import os
import logging

import odoo
from odoo.tools.translate import TranslationImporter

from . import Command
from .assemble import CommandMixin

_logger = logging.getLogger(__name__)


class Po_Import(CommandMixin, Command):
    """ Import *.po File """
    def __init__(self):
        super(Po_Import, self).__init__()
        self.lang = None
        self.langfile = None
        self.langdir = None
        self.modpath = None

        self.parser.add_argument("--overwrite",
                                 action="store_true",
                                 default=True,
                                 help="Override existing translations")

        self.parser.add_argument("--verbose",
                                 action="store_true",
                                 default=False,
                                 help="Verbose translation import")


        self.parser.add_argument(
            "--lang",
            name="lang",
            metavar="LANG",
            help="Language to export"
        )

    def run_config(self):
        # check module
        if not self.params.module:
            _logger.error("No module defined for export!")
            return

        # check path
        self.modpath = odoo.modules.get_module_path(self.params.module)
        if not self.modpath:
            _logger.error("No module %s not found in path!",
                          self.params.module)
            return

        # check language
        if not self.params.lang:
            _logger.error("No language defined for import!")
            return

        # define language vars
        self.lang = self.params.lang
        self.langfile = self.lang.split("_")[0] + ".po"
        self.langdir = os.path.join(self.modpath, "i18n")

        # run with env
        self.setup_env()


    def run_config_env(self, env):
        # check module installed
        if not env["ir.module.module"].search(
            [("state", "=", "installed"), ("name", "=", self.params.module)]):
            _logger.error("No module %s installed!", self.params.module)
            return

        import_file = os.path.join(self.langdir, self.langfile)
        if not os.path.exists(import_file):
            _logger.error("File %s does not exist!", import_file)
            return

        # import
        if self.params.overwrite:
            _logger.info("Overwrite existing translations for %s/%s",
                         self.params.module, self.lang)

        cr = env.cr
        translation_importer = TranslationImporter(cr, verbose=True)
        translation_importer.load_file(import_file, self.lang)
        translation_importer.save(overwrite=self.params.overwrite)

        # and commit
        cr.commit()
