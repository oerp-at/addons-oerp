import logging

from . import Command
from .assemble import CommandMixin

_logger = logging.getLogger(__name__)


class UpdateList(CommandMixin, Command):
    def run_config(self):
        self.setup_env()

    def run_config_env(self, env):
        ModuleModule = env['ir.module.module']
        updated, added = ModuleModule.update_list()
        _logger.info('Modules Updated: %s, Added: %s', updated, added)

        # pylint: disable=invalid-commit
        env.cr.commit()