"""Uninstalled modules of 19.0 that 20.0 no longer ships become uninstallable.

Their ir_module_module rows keep the 19.0 auto_install flag and dependencies.
The auto discovery of upgrade-util (base/0.0.0 post) then force installs
them, e.g. hr_work_entry_attendance once hr_work_entry is installed, and the
update stops with "Some modules have inconsistent states". The update of the
module list resets the state of every module it finds on the addons path, so
only modules without source code stay uninstallable.
"""
import logging

from odoo.modules.module import get_manifest

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("SELECT name FROM ir_module_module WHERE state = 'uninstalled' AND auto_install")
    gone = [name for (name,) in cr.fetchall() if not get_manifest(name)]
    if gone:
        cr.execute(
            "UPDATE ir_module_module SET state = 'uninstallable', auto_install = false WHERE name IN %s",
            [tuple(gone)],
        )
        _logger.info("%s auto install modules not in 20.0, now uninstallable: %s",
                     len(gone), ", ".join(sorted(gone)))
