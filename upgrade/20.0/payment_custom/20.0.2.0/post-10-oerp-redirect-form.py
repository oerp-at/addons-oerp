"""Custom payment providers use ``payment.generic_redirect_form`` in 20.0.

``payment_custom.redirect_form`` is gone, but the provider data is noupdate
and still points to it, so removing the obsolete view at the end of the
update fails on the foreign key of payment.provider.
"""
from odoo.upgrade import util


def migrate(cr, version):
    old_id = util.ref(cr, "payment_custom.redirect_form")
    new_id = util.ref(cr, "payment.generic_redirect_form")
    if old_id and new_id:
        cr.execute(
            "UPDATE payment_provider SET redirect_form_view_id = %s WHERE redirect_form_view_id = %s",
            [new_id, old_id],
        )
