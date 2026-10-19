"""Core modules of Odoo 19.0 that no longer exist in Odoo 20.0.

Single source for the base pre-migration script (which applies the moves) and
for ``odoo migrate --dry-run`` (which reports every installed module that is
neither available nor listed here).
"""

#: old module -> new module; the module keeps its data under the new name
RENAMED = {
    # VIES/VAT validation, same module under a new name
    "base_vat": "l10n_eu_account_vies",
}

#: old module -> module that now contains its code and data
MERGED = {
    "account_add_gln": "account",
    "base_iban": "account",
    "hr_homeworking": "hr",
    "hr_org_chart": "hr",
}

#: modules that are gone without a successor
REMOVED = [
    # only shipped JS assets for the IoT box; point_of_sale 20.0 no longer uses it
    "iot_base",
]

#: (model, field, module after the rename/merge, module that defines it in 20.0)
MOVED_FIELDS = [
    ("res.company", "vat_check_vies", "l10n_eu_account_vies", "account"),
    ("res.config.settings", "vat_check_vies", "l10n_eu_account_vies", "account"),
    # stock valuation settings, account/models/company.py + product.py in 20.0
    ("res.company", "account_stock_valuation_id", "stock_account", "account"),
    ("res.company", "account_stock_journal_id", "stock_account", "account"),
    ("res.company", "cost_method", "stock_account", "account"),
    ("res.company", "inventory_valuation", "stock_account", "account"),
    ("res.company", "inventory_period", "stock_account", "account"),
    ("product.category", "property_valuation", "stock_account", "account"),
    ("product.category", "property_cost_method", "stock_account", "account"),
    ("product.category", "property_stock_journal", "stock_account", "account"),
    ("product.category", "property_stock_valuation_account_id", "stock_account", "account"),
    ("product.category", "property_price_difference_account_id", "stock_account", "account"),
    ("product.category", "account_stock_variation_id", "stock_account", "account"),
]

#: like MOVED_FIELDS, but only when the new module is installed (otherwise
#: the field is dropped with the old module's 19.0 definition)
MOVED_FIELDS_IF_INSTALLED = [
    ("product.template", "sale_delay", "stock", "sale"),
]

#: records that another module defines in 20.0: old xml id -> new xml id
MOVED_XMLIDS = {
    "stock_account.action_report_stock_valuation": "account.action_report_stock_valuation",
    "stock_account.ir_cron_post_stock_valuation": "account.ir_cron_post_stock_valuation",
    "stock_account.ir_cron_post_stock_valuation_ir_actions_server":
        "account.ir_cron_post_stock_valuation_ir_actions_server",
    # base 20.0 defines the default website, website would create a second one
    "website.default_website": "base.default_website",
    # same tag name, documents.tag names are unique
    "documents_hr.document_tag_signature_request": "documents_hr_sign.document_tag_signature_request",
}


def handled_modules():
    """Names of all modules this file takes care of."""
    return set(RENAMED) | set(MERGED) | set(REMOVED)
