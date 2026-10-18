"""mail.message ``starred_partner_ids`` is ``bookmarked_partner_ids`` in 20.0 (new relation table)."""
from odoo.upgrade import util


def migrate(cr, version):
    if (util.table_exists(cr, "mail_message_res_partner_starred_rel")
            and not util.table_exists(cr, "mail_message_res_partner_bookmarked_rel")):
        util.rename_table(cr, "mail_message_res_partner_starred_rel",
                          "mail_message_res_partner_bookmarked_rel")
        util.rename_field(cr, "mail.message", "starred_partner_ids", "bookmarked_partner_ids")
