"""res.partner ``peppol_eas``/``peppol_endpoint`` are ``routing_scheme``/``routing_endpoint`` in 20.0."""
from odoo.upgrade import util


def migrate(cr, version):
    for old, new in (("peppol_eas", "routing_scheme"), ("peppol_endpoint", "routing_endpoint")):
        if util.column_exists(cr, "res_partner", old):
            util.rename_field(cr, "res.partner", old, new)
