"""``mass_mailing.mailing_list_merge_action`` is a server action in 20.0
(was a window action), loading the data file fails on the model change."""
from odoo.upgrade import util


def migrate(cr, version):
    util.remove_record(cr, "mass_mailing.mailing_list_merge_action")
