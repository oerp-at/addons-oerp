"""Fill mail.activity ``phone`` of the phone call activities (see pre-30).

Only activities of loaded models: the others belong to modules the cleanup
uninstalls afterwards.
"""
from odoo.upgrade import util


def migrate(cr, version):
    cr.execute(
        """
        SELECT a.id
          FROM mail_activity a
          JOIN mail_activity_type t ON t.id = a.activity_type_id
         WHERE t.category = 'phonecall'
           AND a.phone IS NULL
           AND a.res_model IN %s
        """,
        [tuple(util.env(cr).registry.models)],
    )
    ids = [r[0] for r in cr.fetchall()]
    if ids:
        util.recompute_fields(cr, "mail.activity", ["phone"], ids=ids)
