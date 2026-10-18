"""Attach the 20.0 xml ids of the default channel members to existing rows.

mail 20.0 adds ``channel_member_channel_admin_partner_admin`` (admin in the
administrators channel). 19.0 created that member without xml id, so loading
the data file hits the unique constraint ``(channel_id, partner_id)``.
"""
import logging

from odoo.upgrade import util

_logger = logging.getLogger(__name__)

#: xml id of the member -> (xml id of the channel, xml id of the partner)
MEMBERS = {
    "mail.channel_member_channel_admin_partner_admin": ("mail.channel_admin", "base.partner_admin"),
    "mail.channel_member_general_channel_for_admin": ("mail.channel_all_employees", "base.partner_admin"),
}


def migrate(cr, version):
    for xmlid, (channel_xmlid, partner_xmlid) in MEMBERS.items():
        channel_id = util.ref(cr, channel_xmlid)
        partner_id = util.ref(cr, partner_xmlid)
        if not (channel_id and partner_id):
            continue
        member_id = util.ensure_xmlid_match_record(
            cr, xmlid, "discuss.channel.member",
            {"channel_id": channel_id, "partner_id": partner_id})
        if member_id:
            _logger.info("%s -> discuss.channel.member %s", xmlid, member_id)
