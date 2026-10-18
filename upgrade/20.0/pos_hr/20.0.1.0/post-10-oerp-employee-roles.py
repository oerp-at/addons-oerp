"""Copy the 19.0 pos_hr role assignments into the 20.0 relation tables."""
import logging

from odoo.upgrade import util

_logger = logging.getLogger(__name__)

TABLES = [
    ("pos_hr_minimal_employee_hr_employee", "pos_hr_restrictive_employee_hr_employee"),
    ("pos_hr_basic_employee_hr_employee", "pos_hr_cashier_employee_hr_employee"),
    ("pos_hr_advanced_employee_hr_employee", "pos_hr_manager_employee_hr_employee"),
]


def migrate(cr, version):
    for old, new in TABLES:
        if not (util.table_exists(cr, old) and util.table_exists(cr, new)):
            continue
        cr.execute(
            f"""
            INSERT INTO {new} (pos_config_id, hr_employee_id)
            SELECT o.pos_config_id, o.hr_employee_id FROM {old} o
             WHERE NOT EXISTS (SELECT 1 FROM {new} n
                                WHERE n.pos_config_id = o.pos_config_id
                                  AND n.hr_employee_id = o.hr_employee_id)
            """
        )
        _logger.info("%s: %s role assignments copied to %s", old, cr.rowcount, new)
