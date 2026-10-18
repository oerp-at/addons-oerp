"""Map the 19.0 selection hr.version.employee_type to the employee type records.

20.0 only knows the many2one ``employee_type_id``. Selection values without a
matching 20.0 record (worker, contractor, freelance) stay empty and are logged.
"""
import logging

from odoo.upgrade import util

_logger = logging.getLogger(__name__)

MAP = {
    "employee": "contract_type_employee",
    "student": "contract_type_student",
    "trainee": "contract_type_intern",
}


def migrate(cr, version):
    if not util.column_exists(cr, "hr_version", "employee_type"):
        return
    for value, xid in MAP.items():
        cr.execute(
            """
            UPDATE hr_version v SET employee_type_id = d.res_id
              FROM ir_model_data d
             WHERE d.module = 'hr' AND d.name = %s AND d.model = 'hr.employee.type'
               AND v.employee_type = %s AND v.employee_type_id IS NULL
            """,
            [xid, value],
        )
    cr.execute(
        """
        SELECT employee_type, count(*) FROM hr_version
         WHERE employee_type IS NOT NULL AND employee_type_id IS NULL
         GROUP BY employee_type
        """
    )
    for value, count in cr.fetchall():
        _logger.warning("%s hr.version with employee type %r have no 20.0 type", count, value)
