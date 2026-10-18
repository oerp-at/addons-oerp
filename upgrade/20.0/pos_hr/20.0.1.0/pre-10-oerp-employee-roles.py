"""pos_hr roles of 19.0 -> 20.0: minimal -> restrictive, basic -> cashier, advanced -> manager.

The renames keep references in views and filters. The relation tables have
new names in 20.0, their rows are copied in the post script.
"""
from odoo.upgrade import util

RENAMES = [
    ("minimal_employee_ids", "restrictive_employee_ids"),
    ("basic_employee_ids", "cashier_employee_ids"),
    ("advanced_employee_ids", "manager_employee_ids"),
]


def migrate(cr, version):
    for old, new in RENAMES:
        cr.execute("SELECT 1 FROM ir_model_fields WHERE model = 'pos.config' AND name = %s", [old])
        if cr.rowcount:
            util.rename_field(cr, "pos.config", old, new)
