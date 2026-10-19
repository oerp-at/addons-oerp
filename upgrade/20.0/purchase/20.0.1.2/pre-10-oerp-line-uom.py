"""purchase.order.line ``product_uom_id`` is ``uom_id`` in 20.0.

Without the rename the new column is empty and the stored compute
``price_unit_product_uom`` fails on every line with a price.
"""
from odoo.upgrade import util


def migrate(cr, version):
    if util.column_exists(cr, "purchase_order_line", "product_uom_id"):
        util.rename_field(cr, "purchase.order.line", "product_uom_id", "uom_id")
