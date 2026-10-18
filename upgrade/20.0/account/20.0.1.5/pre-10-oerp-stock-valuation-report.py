"""The stock valuation report moved from stock_account to account.

19.0 ``stock_account.stock.valuation.report`` is ``account.stock.valuation.report``
in 20.0 (account/report/account_stock_valuation_report.py). account loads before
stock_account, so the model is renamed here.
"""
from odoo.upgrade import util


def _model_exists(cr, model):
    cr.execute("SELECT 1 FROM ir_model WHERE model = %s", [model])
    return bool(cr.rowcount)


def migrate(cr, version):
    if _model_exists(cr, "stock_account.stock.valuation.report"):
        util.rename_model(
            cr, "stock_account.stock.valuation.report", "account.stock.valuation.report",
            rename_table=False)
