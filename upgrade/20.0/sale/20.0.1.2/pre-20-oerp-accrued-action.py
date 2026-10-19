"""``sale.action_accrued_revenue_entry_sale_order_line`` is a server action in
20.0 (was a window action), loading the wizard views fails on the model change."""
from odoo.upgrade import util


def migrate(cr, version):
    util.remove_record(cr, "sale.action_accrued_revenue_entry_sale_order_line")
