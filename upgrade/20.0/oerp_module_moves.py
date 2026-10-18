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
]


def handled_modules():
    """Names of all modules this file takes care of."""
    return set(RENAMED) | set(MERGED) | set(REMOVED)
