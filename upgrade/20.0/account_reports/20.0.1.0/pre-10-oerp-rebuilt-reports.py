"""Reports of account_reports that 20.0 rebuilds.

20.0 reuses codes, expression labels and column labels of 19.0 records under
other xml ids (e.g. ``unreconciled_payments`` of the bank reconciliation),
loading the data files then hits the unique constraints of
account.report.line/expression/column. These reports are standard data
without user records (every line has an xml id of the module), so their 19.0
columns, lines and expressions are removed before the update and the data
files create them anew.

Found by comparing the xml ids of a 19.0 database with a fresh 20.0 one; the
other reports only lose records, which the update removes itself.
"""
from odoo.upgrade import util

REPORTS = [
    "account_reports.bank_reconciliation_report",
    "account_reports.customer_statement_report",
    "account_reports.followup_report",
]


def migrate(cr, version):
    for xmlid in REPORTS:
        report_id = util.ref(cr, xmlid)
        if not report_id:
            continue
        cr.execute("SELECT id FROM account_report_line WHERE report_id = %s", [report_id])
        line_ids = [r[0] for r in cr.fetchall()]
        if line_ids:
            cr.execute("SELECT id FROM account_report_expression WHERE report_line_id IN %s",
                       [tuple(line_ids)])
            util.remove_records(cr, "account.report.expression", [r[0] for r in cr.fetchall()])
            util.remove_records(cr, "account.report.line", line_ids)
        cr.execute("SELECT id FROM account_report_column WHERE report_id = %s", [report_id])
        util.remove_records(cr, "account.report.column", [r[0] for r in cr.fetchall()])
