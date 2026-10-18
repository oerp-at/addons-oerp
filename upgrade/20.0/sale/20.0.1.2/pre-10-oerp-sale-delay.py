"""product.template ``sale_delay`` moved from stock to sale and became company dependent.

The field was handed over to sale in the base pre script (only when sale is
installed). The 19.0 integer column is converted to the jsonb of a company
dependent field before sale loads; the ORM has no cast for that.
"""
from odoo.upgrade import util


def migrate(cr, version):
    if (util.column_exists(cr, "product_template", "sale_delay")
            and util.column_type(cr, "product_template", "sale_delay") != "jsonb"):
        util.make_field_company_dependent(
            cr, "product.template", "sale_delay", "integer", default_value=0)
