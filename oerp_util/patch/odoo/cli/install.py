import logging

from . import Command
from .assemble import CommandMixin

_logger = logging.getLogger(__name__)


class Install(CommandMixin, Command):

    def run_config(self):
        self.setup_env()

    def run_config_env(self, env):
        # check module installed
        Module = env['ir.module.module']
        mod = Module.search([('name','=', self.params.module)], limit=1)
        if not mod:
            _logger.error("Unkown module %s!", self.params.module)
            return
        elif mod.state == 'installed':
            _logger.error("Module %s is already installed!", self.params.module)
            return

        # install module
        mod.button_immediate_install()
        env.cr.commit()
