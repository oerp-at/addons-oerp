"""Map account.move ``checked`` (19.0) to ``review_state`` (20.0).

19.0 ``checked`` = reviewed; a posted move that is not checked was "to check".
20.0 creates ``review_state`` with the default 'no_review' for every move.
19.0 ``deductible_amount`` (0-100) is ``deductible_percentage`` (0-1).
"""
import logging

from odoo.upgrade import util

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if util.column_exists(cr, "account_move", "checked"):
        cr.execute(
            """
            UPDATE account_move
               SET review_state = CASE WHEN checked THEN 'reviewed' ELSE 'todo' END
             WHERE review_state = 'no_review'
               AND (checked OR state = 'posted')
            """
        )
        _logger.info("review_state set on %s moves", cr.rowcount)

    if util.column_exists(cr, "account_move_line", "deductible_amount"):
        cr.execute(
            """
            UPDATE account_move_line
               SET deductible_percentage = deductible_amount / 100.0
             WHERE deductible_amount IS NOT NULL AND deductible_amount <> 100
            """
        )
        if cr.rowcount:
            _logger.info("deductible_percentage set on %s move lines", cr.rowcount)
