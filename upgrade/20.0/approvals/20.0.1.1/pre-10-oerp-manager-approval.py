"""approval.category ``manager_approval``: selection -> boolean.

19.0: empty / 'approver' (manager is in the approver list) / 'required'
(manager must approve). 20.0 only knows "manager is a required approver", so
both values become True; 'approver' categories now require the manager.
"""
from odoo.upgrade import util


def migrate(cr, version):
    if util.column_type(cr, "approval_category", "manager_approval") == "varchar":
        util.alter_column_type(cr, "approval_category", "manager_approval", "boolean",
                               using="COALESCE({0}, '') <> ''")
