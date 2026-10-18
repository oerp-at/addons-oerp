"""Rename the res.partner.bank fields to their Odoo 20.0 names.

Runs in the pre stage of ``base``, before base 20.0 code is loaded. Base 20.0
renames ``acc_number`` and friends; the stored 19.0 extension views of
account/hr still point at the old fields, so the combined-arch validation of
``base.view_partner_bank_form`` fails while base loads. The extension views
are removed here, their modules re-create them from the 20.0 data files.

Must run after ``pre-10-oerp-module-moves``: base_iban is merged into account
there, its views hang below the account extension and go with it.
"""
import logging

from odoo.upgrade import util

_logger = logging.getLogger(__name__)

RENAMES = [
    ("acc_number", "account_number"),
    ("sanitized_acc_number", "sanitized_account_number"),
    ("acc_type", "account_type"),
    ("acc_holder_name", "holder_name"),
]

#: 19.0 extensions of the base res.partner.bank views (descendants go along)
STALE_VIEWS = [
    "account.view_partner_bank_form_inherit_account",
    "account.view_partner_bank_search_inherit",
    "hr.view_partner_bank_form_inherit_hr",
]


def migrate(cr, version):
    util.remove_views(cr, *STALE_VIEWS)

    for old, new in RENAMES:
        if util.column_exists(cr, "res_partner_bank", old):
            util.rename_field(cr, "res.partner.bank", old, new)
            _logger.info("res.partner.bank: %s renamed to %s", old, new)
