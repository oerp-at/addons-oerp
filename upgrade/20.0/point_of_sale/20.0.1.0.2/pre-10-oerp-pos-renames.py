"""Rename the pos.config and pos.payment.method fields of 19.0.

Journals swap their roles in 20.0:

- 19.0 ``journal_id`` (session entries) is 20.0 ``closing_journal_id``
- 19.0 ``invoice_journal_id`` (invoices) is 20.0 ``journal_id``

Renamed in this order, the closing entries keep their 19.0 journal. 20.0 only
offers sale journals for closing in the form, the 19.0 general journal still
works for posting.
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


def migrate(cr, version):
    for model, table, old, new in RENAMES:
        exists = util.column_exists(cr, table, old) if table else _field_exists(cr, model, old)
        if exists:
            util.rename_field(cr, model, old, new)
            _logger.info("%s: %s renamed to %s", model, old, new)
