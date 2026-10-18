"""Clear payment providers of payment methods that no 20.0 module offers.

19.0 ``use_payment_terminal`` became ``payment_provider``; a terminal module
that was not ported leaves a key outside the selection. Runs at the end so
the selection of every module is known.
"""
import logging

from odoo.upgrade import util

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = util.env(cr)
    methods = env["pos.payment.method"].search([("payment_provider", "!=", False)])
    for method in methods:
        selection = dict(method._fields["payment_provider"]._description_selection(env))
        if method.payment_provider not in selection:
            _logger.warning("payment method %s: provider %r is not available, cleared",
                            method.display_name, method.payment_provider)
            method.payment_provider = False
