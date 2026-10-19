"""mail.activity ``phone`` is a new stored compute in 20.0.

Computing it while mail loads reads the record of each phone call activity,
which fails for models of modules that are not loaded yet (e.g. crm.lead).
The column is created empty here and filled at the end of the migration.
"""
from odoo.upgrade import util


def migrate(cr, version):
    if not util.column_exists(cr, "mail_activity", "phone"):
        util.create_column(cr, "mail_activity", "phone", "varchar")
