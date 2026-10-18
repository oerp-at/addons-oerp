"""Convert the point of sale data of 19.0 to the 20.0 structures.

Runs after point_of_sale 20.0 is loaded and before the columns of removed
fields are dropped at the end of the update.

1. ``pos.payment.method.type`` is stored and required in 20.0, 19.0 computed
   it from the journal (cash/bank, else pay_later)
2. the closing entry ``pos.session.move_id`` is linked from the move
   (``account.move.pos_session_sales_id``)
3. the cash balances of a session live on its cash statement in 20.0; one
   statement per session gets the 19.0 balances and cash lines
4. ``pos.config.default_partner_id`` is new and required. Its default runs on
   the existing configs before the data file creates the partner
   ``point_of_sale.default_session_closing_partner``, so each config gets a
   second "Odoo POS" partner without xmlid. The configs are moved to the
   xmlid partner and the duplicate is removed. Like 20.0 itself, the partner
   gets the POS receivable of each company, otherwise the closing entries
   would book on the general receivable.

Payment providers are checked in the end script, the modules adding them
(e.g. orderjim_pos) load after point_of_sale.
"""
import logging

from odoo.upgrade import util

_logger = logging.getLogger(__name__)


def _fill_payment_method_type(cr):
    cr.execute(
        """
        UPDATE pos_payment_method pm
           SET type = CASE WHEN j.type IN ('cash', 'bank') THEN j.type ELSE 'pay_later' END
          FROM pos_payment_method p
     LEFT JOIN account_journal j ON j.id = p.journal_id
         WHERE pm.id = p.id AND pm.type IS NULL
        """
    )
    _logger.info("type set on %s payment methods", cr.rowcount)
    cr.execute("SELECT 1 FROM pos_payment_method WHERE type IS NULL")
    if not cr.rowcount:
        cr.execute("ALTER TABLE pos_payment_method ALTER COLUMN type SET NOT NULL")


def _link_closing_moves(cr):
    if not util.column_exists(cr, "pos_session", "move_id"):
        return
    cr.execute(
        """
        UPDATE account_move am
           SET pos_session_sales_id = s.id
          FROM pos_session s
         WHERE s.move_id = am.id AND am.pos_session_sales_id IS NULL
        """
    )
    _logger.info("%s closing entries linked to their session", cr.rowcount)


def _create_cash_statements(cr):
    if not util.column_exists(cr, "pos_session", "cash_register_balance_start"):
        return
    cr.execute(
        """
        SELECT s.id, s.name, s.cash_journal_id,
               COALESCE(s.cash_register_balance_start, 0),
               COALESCE(s.cash_register_balance_end_real, 0),
               COALESCE(s.stop_at, s.start_at, s.create_date)::date
          FROM pos_session s
         WHERE s.bank_statement_id IS NULL AND s.cash_journal_id IS NOT NULL
           AND (s.cash_register_balance_start IS NOT NULL
                OR s.cash_register_balance_end_real IS NOT NULL
                OR EXISTS (SELECT 1 FROM account_bank_statement_line l WHERE l.pos_session_id = s.id))
         ORDER BY s.id
        """
    )
    rows = cr.fetchall()
    if not rows:
        return
    env = util.env(cr)
    statements = env["account.bank.statement"]
    for session_id, name, journal_id, balance_start, balance_end_real, day in rows:
        statement = statements.create({
            "name": f"Cash Statement {name}",
            "journal_id": journal_id,
            "balance_start": balance_start,
            "balance_end_real": balance_end_real,
            "date": day,
        })
        statements |= statement
        cr.execute("UPDATE pos_session SET bank_statement_id = %s WHERE id = %s", [statement.id, session_id])
        cr.execute(
            """
            UPDATE account_bank_statement_line SET statement_id = %s
             WHERE pos_session_id = %s AND statement_id IS NULL
            """,
            [statement.id, session_id],
        )
    env.flush_all()
    env.invalidate_all()
    # balances stay as in 19.0, only the values derived from the lines are recomputed
    util.recompute_fields(
        cr, "account.bank.statement", ["date", "first_line_index", "balance_end", "is_complete"],
        ids=statements.ids)
    _logger.info("%s cash statements created for 19.0 sessions", len(statements))


def _merge_default_partner(cr):
    env = util.env(cr)
    partner = env.ref("point_of_sale.default_session_closing_partner", raise_if_not_found=False)
    if not partner:
        return
    configs = env["pos.config"].with_context(active_test=False).search([])
    for company in configs.company_id:
        if company.account_default_pos_receivable_account_id:
            partner.with_company(company).property_account_receivable_id = (
                company.account_default_pos_receivable_account_id
            )
    duplicates = configs.default_partner_id.filtered(
        lambda p: p != partner and p.name == partner.name and not p.get_external_id().get(p.id)
    )
    if not duplicates:
        return
    configs.filtered(lambda c: c.default_partner_id in duplicates).default_partner_id = partner
    duplicates.unlink()
    _logger.info("pos.config: default partner set to %s, %s duplicates removed", partner.id, len(duplicates))


def migrate(cr, version):
    _fill_payment_method_type(cr)
    _link_closing_moves(cr)
    _create_cash_statements(cr)
    _merge_default_partner(cr)
