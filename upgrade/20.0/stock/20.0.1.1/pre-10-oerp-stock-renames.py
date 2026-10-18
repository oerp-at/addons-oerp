"""Rename the stock fields and models of 19.0 to their 20.0 names.

- the unit fields of moves and move lines are called ``uom_id`` in 20.0
- ``location_final_id`` is ``forecasted_location_id``
- the reception report is the allocation report (field + abstract model)
- product tracking 'none' is gone, NULL means "tracked by quantity" in 20.0
  (stock/models/product.py ``_compute_store_by``)
"""
import logging

from odoo.upgrade import util

_logger = logging.getLogger(__name__)

RENAMES = [
    ("stock.move", "stock_move", "product_uom", "uom_id"),
    ("stock.move.line", "stock_move_line", "product_uom_id", "uom_id"),
    ("stock.move", "stock_move", "location_final_id", "forecasted_location_id"),
    ("stock.picking.type", "stock_picking_type", "auto_show_reception_report",
     "auto_show_allocation_report"),
]


def _model_exists(cr, model):
    cr.execute("SELECT 1 FROM ir_model WHERE model = %s", [model])
    return bool(cr.rowcount)


def migrate(cr, version):
    for model, table, old, new in RENAMES:
        if util.column_exists(cr, table, old):
            util.rename_field(cr, model, old, new)
            _logger.info("%s: %s renamed to %s", model, old, new)

    if _model_exists(cr, "report.stock.report_reception"):
        util.rename_model(cr, "report.stock.report_reception", "stock.allocation.report",
                          rename_table=False)

    util.change_field_selection_values(cr, "product.template", "tracking", {"none": None})
