"""Rename, merge and remove the core modules that Odoo 20.0 no longer ships.

Runs in the pre stage of ``base``, before the module graph of the other
modules is loaded, so the moved modules are upgraded under their new names.
"""
import logging

from odoo.upgrade import util
from odoo.upgrade.oerp_module_moves import MERGED, MOVED_FIELDS, REMOVED, RENAMED

_logger = logging.getLogger(__name__)


def _module_exists(cr, name):
    cr.execute("SELECT 1 FROM ir_module_module WHERE name = %s", [name])
    return bool(cr.rowcount)


def migrate(cr, version):
    for old, new in RENAMED.items():
        if not _module_exists(cr, old):
            continue
        if _module_exists(cr, new):
            # the target is already known (e.g. a module list update ran):
            # merging keeps the data instead of creating a duplicate row
            _logger.info("merge renamed module %s into existing %s", old, new)
            util.merge_module(cr, old, new)
        else:
            _logger.info("rename module %s to %s", old, new)
            util.rename_module(cr, old, new)

    for old, into in MERGED.items():
        if _module_exists(cr, old):
            _logger.info("merge module %s into %s", old, into)
            util.merge_module(cr, old, into)

    for model, field, old_module, new_module in MOVED_FIELDS:
        util.move_field_to_module(cr, model, field, old_module, new_module)

    for module in REMOVED:
        if _module_exists(cr, module):
            _logger.info("remove module %s", module)
            util.remove_module(cr, module)
