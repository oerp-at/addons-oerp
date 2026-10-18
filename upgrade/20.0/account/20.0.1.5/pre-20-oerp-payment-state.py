"""Map account.payment.state of 19.0 to 20.0.

19.0: in_process = not yet matched, paid = matched (account_payment.py _compute_state)
20.0: paid = not yet matched, reconciled = matched

The stored values are not recomputed during the upgrade. 'paid' has to be
moved first, otherwise the former in_process payments would end up reconciled.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("SELECT 1 FROM account_payment WHERE state = 'in_process' LIMIT 1")
    if not cr.rowcount:
        cr.execute("SELECT 1 FROM account_payment WHERE state = 'reconciled' LIMIT 1")
        if cr.rowcount:
            return  # already mapped
    cr.execute("UPDATE account_payment SET state = 'reconciled' WHERE state = 'paid'")
    reconciled = cr.rowcount
    cr.execute("UPDATE account_payment SET state = 'paid' WHERE state = 'in_process'")
    _logger.info("account.payment.state: %s paid -> reconciled, %s in_process -> paid",
                 reconciled, cr.rowcount)
