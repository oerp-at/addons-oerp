"""Remove the generic 19.0 payment.method records that nothing uses.

20.0 binds every payment method to one provider (required ``provider_id``);
the provider modules create their own records. The 19.0 records of the
payment module are noupdate and would stay without provider. Methods used by
a token or transaction are kept and logged.
"""
import logging

from odoo.upgrade import util

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute(
        """
        SELECT m.id, EXISTS (SELECT 1 FROM payment_token t WHERE t.payment_method_id = m.id)
                     OR EXISTS (SELECT 1 FROM payment_transaction x WHERE x.payment_method_id = m.id)
          FROM payment_method m
        """
    )
    rows = cr.fetchall()
    unused = [mid for mid, used in rows if not used]
    used = [mid for mid, used in rows if used]
    if unused:
        cr.execute("UPDATE payment_method SET primary_payment_method_id = NULL WHERE id IN %s",
                   [tuple(unused)])
        util.remove_records(cr, "payment.method", unused)
    _logger.info("%s unused payment methods removed", len(unused))
    if used:
        _logger.warning("%s payment methods in use are kept, assign their provider: %s",
                        len(used), used)
