"""product.supplierinfo ``product_uom_id`` is ``uom_id`` in 20.0."""
from odoo.upgrade import util


def migrate(cr, version):
    if util.column_exists(cr, "product_supplierinfo", "product_uom_id"):
        util.rename_field(cr, "product.supplierinfo", "product_uom_id", "uom_id")
