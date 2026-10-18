"""Rename the pos.config and pos.payment.method fields of 19.0.

Journals swap their roles in 20.0:

- 19.0 ``journal_id`` (session entries) is 20.0 ``closing_journal_id``
- 19.0 ``invoice_journal_id`` (invoices) is 20.0 ``journal_id``

Renamed in this order, the closing entries keep their 19.0 journal.

20.0 closes a session with a customer invoice in the closing journal and looks
the POS journal up by code and type ``sale``. The 19.0 journal (``POSS``) is a
general journal, so 20.0 would try to create a second ``POSS`` and closing
fails on the unique code. The closing journal therefore becomes a sale journal;
code, name and the posted 19.0 entries stay as they are.
"""
import logging

from odoo.upgrade import util

_logger = logging.getLogger(__name__)

#: (model, table, old, new) in this order
RENAMES = [
    ("pos.config", "pos_config", "journal_id", "closing_journal_id"),
    ("pos.config", "pos_config", "invoice_journal_id", "journal_id"),
    ("pos.config", "pos_config", "is_order_printer", "use_order_printer"),
    ("pos.config", "pos_config", "is_closing_entry_by_product", "use_closing_entry_by_product"),
    ("pos.config", "pos_config", "is_header_or_footer", "use_header_or_footer"),
    ("pos.config", "pos_config", "auto_validate_terminal_payment", "auto_validate_electronic_payment"),
    # same relation table pos_config_printer_rel in 19.0 and 20.0
    ("pos.config", None, "printer_ids", "preparation_printer_ids"),
    ("pos.payment.method", "pos_payment_method", "use_payment_terminal", "payment_provider"),
]


def _field_exists(cr, model, name):
    cr.execute("SELECT 1 FROM ir_model_fields WHERE model = %s AND name = %s", [model, name])
    return bool(cr.rowcount)


def _closing_journals_to_sale(cr):
    """Turn the general closing journals of 19.0 into sale journals.

    A sale journal needs a default income account, taken from the first sale
    journal of the same company.
    """
    cr.execute(
        """
        UPDATE account_journal j
           SET type = 'sale',
               default_account_id = COALESCE(j.default_account_id, (
                   SELECT s.default_account_id
                     FROM account_journal s
                    WHERE s.company_id = j.company_id
                      AND s.type = 'sale'
                      AND s.default_account_id IS NOT NULL
                    ORDER BY s.sequence, s.id
                    LIMIT 1))
         WHERE j.type = 'general'
           AND j.id IN (SELECT closing_journal_id FROM pos_config
                         WHERE closing_journal_id IS NOT NULL)
     RETURNING j.id, j.code
        """
    )
    for journal_id, code in cr.fetchall():
        _logger.info("account.journal %s (%s): closing journal is now a sale journal", journal_id, code)


def migrate(cr, version):
    for model, table, old, new in RENAMES:
        exists = util.column_exists(cr, table, old) if table else _field_exists(cr, model, old)
        if exists:
            util.rename_field(cr, model, old, new)
            _logger.info("%s: %s renamed to %s", model, old, new)
    if util.column_exists(cr, "pos_config", "closing_journal_id"):
        _closing_journals_to_sale(cr)
