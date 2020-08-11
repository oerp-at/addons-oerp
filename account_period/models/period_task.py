# -*- coding: utf-8 -*-
#############################################################################
#
#    Copyright (c) 2007 Martin Reisenhofer <martin.reisenhofer@funkring.net>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from collections import OrderedDict

from openerp import models, fields, api, _
from openerp.exceptions import Warning
import openerp.addons.decimal_precision as dp


class PeriodEntryCreator(object):
    """ Helper class for creating entries """

    def __init__(self, task, taskc):
        self.task = task
        self.env = task.env
        self.taskc = taskc
        self.moves = OrderedDict()
        self.sum_fields = (
            "amount_gross",
            "amount_net",
            "amount_tax",
            "payment_amount",
            "amount_base"
        )

    def add_move(self, values):
        # mandatory
        move_id = values["move_id"]
        journal_id = values["journal_id"]
        account_id = values["account_id"]

        # other
        invoice_id = values.get("invoice_id") or 0
        voucher_id = values.get("voucher_id") or 0
        tax_base_id = values.get("tax_base_id") or 0
        tax_code_id = values.get("tax_code_id") or 0
        tax_id = values.get("tax_id") or 0
        sign = values.get("sign", 1.0)
        refund = values.get("refund") or False
        st_line_id = values.get("st_line_id") or 0

        key = (move_id,
                journal_id,
                account_id,
                invoice_id,
                voucher_id,
                tax_id,
                tax_base_id,
                tax_code_id,
                sign,
                refund,
                st_line_id)

        # calculate tax if it is not passed
        if not "amount_tax" in values:
            values["amount_tax"] = values["amount_gross"] - values["amount_net"]
        if not "amount_base" in values:
            values["amount_base"] = values["amount_net"]

        # add move
        move_data = self.moves.get(key, None)
        if move_data is None:
            move_data = dict(values)
            move_data["task_id"] = self.task.id

            for field in self.sum_fields:
                move_data[field] = values.get(field, 0.0)

            self.moves[key] = move_data
        else:
            # sumup fields
            for field in self.sum_fields:
                move_data[field] += values.get(field, 0.0)
        return values


    def flush(self):
        entry_obj = self.env["account.period.entry"]
        self.taskc.substage("Create Entries")

        self.taskc.initLoop(len(self.moves), status="Create entries")
        for entry_values in self.moves.itervalues():
            entry_obj.create(entry_values)
            self.taskc.nextLoop()

        self.taskc.done()
        self.moves = OrderedDict()


class AccountPeriodTask(models.Model):
    _name = "account.period.task"
    _description = "Period Processing"
    _inherit = ["mail.thread", "util.time", "util.report"]
    _inherits = {"automation.task": "task_id"}
    _order = "id desc"

    @api.model
    def _default_company(self):
        return self.env["res.company"]._company_default_get("account.period.task")

    @api.model
    def _default_period(self):
        period_start = self._first_of_last_month_str()
        period_obj = self.env["account.period"]

        period = period_obj.search([("date_start", "=", period_start)], limit=1)
        if not period:
            period = period_obj.search([], limit=1, order="date_start desc")

        return period

    @api.onchange("period_id", "company_id")
    def _onchange_period_profile(self):
        name = "/"
        if self.period_id:
            name = self.period_id.name
        self.name = name

    task_id = fields.Many2one(
        "automation.task", "Task", required=True, index=True, ondelete="cascade"
    )

    period_id = fields.Many2one(
        "account.period",
        "Period",
        required=True,
        ondelete="restrict",
        default=_default_period,
        readonly=True,
        states={"draft": [("readonly", False)]},
    )

    company_id = fields.Many2one(
        "res.company",
        "Company",
        ondelete="restrict",
        required=True,
        default=_default_company,
        readonly=True,
        states={"draft": [("readonly", False)]},
    )

    journal_id = fields.Many2one("account.journal", "Journal",
                    reference="company_id.account_period_journal_id",
                    readonly=True)

    entry_count = fields.Integer(
        "Entries", compute="_compute_entry_count", store=False, readonly=True
    )

    entry_ids = fields.One2many(
        "account.period.entry", "task_id", "Entries", readonly=True
    )

    tax_ids = fields.One2many("account.period.tax", "task_id", "Taxes", readonly=True)

    balance_ids = fields.One2many("account.period.balance", "task_id", "Account Balance", readonly=True)

    balance_count = fields.Integer(
        "Accounts", compute="_compute_balance_count", store=False, readonly=True
    )

    tax_total = fields.Float(
        "Total Tax", digits=dp.get_precision("Account"), readonly=True
    )

    currency_id = fields.Many2one(
        "res.currency", "Currency", relation="company_id.currency_id", readonly=True
    )

    @api.multi
    def _compute_entry_count(self):
        for task in self:
            self.entry_count = len(task.entry_ids)

    @api.multi
    def _compute_balance_count(self):
        task_ids = self.ids
        if task_ids:
            self._cr.execute("""SELECT task_id, COUNT(id)
                FROM account_period_balance
                WHERE task_id IN %s
                  AND move_lines > 0
                GROUP BY 1
            """, (tuple(self.ids),))
            count_dict = dict(self._cr.fetchall())
            for obj in self:
                obj.balance_count = count_dict.get(obj.id, 0)

    @api.multi
    def entry_action(self):
        for task in self:
            return {
                "display_name": _("Entries"),
                "view_type": "form",
                "view_mode": "tree,form",
                "res_model": "account.period.entry",
                "domain": [("task_id", "=", task.id)],
                "type": "ir.actions.act_window",
            }

    @api.multi
    def tax_action(self):
        for task in self:
            return {
                "display_name": _("Taxes"),
                "view_type": "form",
                "view_mode": "tree,form",
                "res_model": "account.period.tax",
                "domain": [("task_id", "=", task.id)],
                "type": "ir.actions.act_window",
            }

    @api.multi
    def balance_action(self):
        for task in self:
            return {
                "display_name": _("Balance"),
                "view_type": "form",
                "view_mode": "tree,form",
                "res_model": "account.period.balance",
                "domain": [("task_id", "=", task.id)],
                "type": "ir.actions.act_window",
                "context": {'search_default_used_accounts': True}
            }

    @api.model
    @api.returns("self", lambda self: self.id)
    def create(self, vals):
        res = super(AccountPeriodTask, self).create(vals)
        res.res_model = self._name
        res.res_id = res.id
        return res

    @api.multi
    def action_queue(self):
        return self.task_id.action_queue()

    @api.multi
    def action_cancel(self):
        return self.task_id.action_cancel()

    @api.multi
    def action_refresh(self):
        return self.task_id.action_refresh()

    @api.multi
    def action_reset(self):
        return self.task_id.action_reset()

    @api.multi
    def unlink(self):
        cr = self._cr

        # remove entries
        for obj in self:
            obj._clean_entries()

        ids = self.ids
        cr.execute(
            "SELECT task_id FROM %s WHERE id IN %%s AND task_id IS NOT NULL"
            % self._table,
            (tuple(ids),),
        )
        task_ids = [r[0] for r in cr.fetchall()]
        res = super(AccountPeriodTask, self).unlink()
        self.env["automation.task"].browse(task_ids).unlink()
        return res

    def _run_options(self):
        return {"stages": 1, "singleton": True}

    def _clean_entries(self, check_valid=True):
        self.ensure_one()
        cr = self.env.cr

        # fetch autogenerated moves
        cr.execute("""SELECT
            e.move_id
        FROM account_period_entry e
        WHERE e.task_id = %s
          AND e.auto
        GROUP BY 1
        """, (self.id,))
        auto_move_ids = [r[0] for r in cr.fetchall()]

        # delete tax
        self.tax_ids.unlink()
        # delete balance
        self.balance_ids.unlink()

        # check for validated entries
        entry_obj = self.env["account.period.entry"]
        if check_valid:
            valid_entry_count =  entry_obj.search(
                [("task_id", "=", self.id), ("state", "=", "valid")], count=True
            )
            if valid_entry_count:
                raise Warning(_("Validated entries already exist."))

        # delete other entries
        entry_obj.search(
            [("task_id", "=", self.id)]
        ).unlink()

        # delete auto moves
        moves = self.env["account.move"].search([("id", "in", auto_move_ids)])
        moves.button_cancel()
        moves.unlink()

    def _get_st_line(self, move_line):
        st_line_obj = self.env["account.bank.statement.line"]
        st_line = None

        reconcile_lines = move_line.reconcile_partial_id and move_line.reconcile_partial_id.line_partial_ids
        if not reconcile_lines:
            reconcile_lines = move_line.reconcile_id and move_line.reconcile_id.line_id

        if reconcile_lines:
            for reconcile_line in reconcile_lines:
                st_line = st_line_obj.search([("journal_entry_id","=",reconcile_line.move_id.id)], limit=1)
                if st_line:
                    break

        return st_line

    def _create_payment_based(self, taskc, journals):
        """ search for invoices and receipts, which are in 
            the passed journal, and paid in this period """

        cr = self.env.cr

        receipt_journal_ids = tuple([j.id for j in journals if j.type in ("sale", "sale_refund", "purchase", "purchase_refund")])
        direct_journal_ids = tuple([j.id for j in journals if j.type in ("cash", "bank")])
        general_journal_ids = tuple([j.id for j in journals if j.type in ("general",)])

        period = self.period_id
        period_start = period.date_start
        period_end = period.date_stop
        entry_creator = PeriodEntryCreator(self, taskc)

        taskc.logd("Create payment based")

        if receipt_journal_ids:

            #######################################################################
            # search for invoice which has a payment
            # paid in this period
            # evaluate product an calculate
            # ... reverse charge, IGE (service or product)
            # ... incoming vat
            #######################################################################

            taskc.substage("Invoice Tax")

            # search for reconciled

            cr.execute(
            """SELECT
                i.id
            FROM account_move_reconcile r
            INNER JOIN account_move_line l ON (l.reconcile_id = r.id OR l.reconcile_partial_id = r.id)
            INNER JOIN account_invoice i ON i.move_id = l.move_id
            INNER JOIN account_move_line l2 on (l2.move_id != i.move_id AND (l2.reconcile_id = r.id OR l2.reconcile_id = r.id))
            WHERE i.journal_id IN %(journal_ids)s
              AND l2.date >= %(period_start)s 
              AND l2.date <= %(period_end)s 
            GROUP BY 1
        UNION 
            SELECT i.id FROM account_invoice i 
            INNER JOIN account_invoice_tax it ON it.invoice_id = i.id
            WHERE it.manual
              AND i.date_invoice >= %(period_start)s 
              AND i.date_invoice <= %(period_end)s
            """,
                {
                    "period_start": period_start,
                    "period_end": period_end,
                    "journal_ids": receipt_journal_ids,
                },
            )

            invoice_ids = [r[0] for r in cr.fetchall()]
            taskc.initLoop(len(invoice_ids), status="calc invoice tax")
            for invoice in self.env["account.invoice"].browse(invoice_ids):
                taskc.nextLoop()

                if not invoice.amount_total:
                    taskc.logw("Invoice is zero", ref="account.invoice,%s" % invoice.id)
                    continue

                sign = 1.0
                if invoice.type in ("out_refund", "in_invoice"):
                    sign = -1.0

                refund = False
                if invoice.type in ("in_refund", "out_refund"):
                    refund = True

                amount_paid = 0.0
                payment_date = None
                st_line = None

                for move_line in invoice.payment_ids:
                    if move_line.date >= period_start and move_line.date <= period_end:
                        amount_paid += move_line.credit - move_line.debit
                        payment_date = max(payment_date, move_line.date)

                        if not st_line:
                            st_line = self._get_st_line(move_line)


                if amount_paid:
                    if invoice.state == "paid":
                        payment_state = "paid"
                        payment_rate = 1.0
                    elif amount_paid > 0.0:
                        payment_state = "part"
                        payment_rate = abs((1 / invoice.amount_total) * amount_paid)
                    else:
                        payment_state = "open"
                        payment_rate = 0.0

                    for line in invoice.invoice_line:
                        price = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
                        tax = line.invoice_line_tax_id
                        
                       
                        taxes = tax.compute_all(
                            price, line.quantity, line.product_id, invoice.partner_id
                        )

                        # generated amounts
                        # and multiplicate with payment rate factor
                        # to get really paid part
                        amount = price * line.quantity * payment_rate * sign
                        amount_gross = taxes["total_included"] * payment_rate * sign
                        amount_net = taxes["total"] * payment_rate * sign
                        amount_tax = amount_gross - amount_net
                        
                        # ignore comment lines
                        if not tax and not amount and not amount_net and not amount_tax:
                            continue

                        tax_id = None
                        tax_base_id = None
                        tax_code_id = None
                        national_values = None
                        
                        if tax:
                            tax_id = tax.id
                            if invoice.type in ("in_refund", "in_invoice"):
                                tax_base_id = tax.ref_base_code_id.id
                                tax_code_id = tax.ref_tax_code_id.id
                            else:
                                tax_base_id = tax.base_code_id.id
                                tax_code_id = tax.tax_code_id.id

                            # book national tax
                            national_tax = tax.national_tax_id
                            if national_tax:
                                # calc tax                        
                                national_taxes = national_tax.compute_all(
                                    price, line.quantity, line.product_id, invoice.partner_id
                                )
                                national_gross = national_taxes["total_included"] * payment_rate * sign * -1.0
                                national_net = national_taxes["total"] * payment_rate * sign * -1.0
                                national_tax = national_gross - national_net
                                amount_tax = national_tax * -1.0

                                if invoice.type in ("in_refund", "in_invoice"):
                                    national_tax_base_id = tax.base_code_id.id
                                    national_tax_code_id = tax.tax_code_id.id
                                else:
                                    national_tax_base_id = tax.ref_base_code_id.id
                                    national_tax_code_id = tax.ref_tax_code_id.id

                                national_values = {
                                    "amount": 0.0,
                                    "amount_gross": 0.0,
                                    "amount_net": 0.0,                 
                                    "payment_amount": 0.0,
                                    "amount_tax": national_tax,
                                    "amount_base": national_net,
                                    "sign": sign*-1.0,                                
                                    "tax_code_id": national_tax_code_id,
                                    "tax_base_id": national_tax_base_id
                                }

                        account = line.account_id
                        values = entry_creator.add_move(
                            {
                                "date": payment_date,
                                "move_id": invoice.move_id.id,
                                "journal_id": invoice.journal_id.id,
                                "account_id": account.id,
                                "invoice_id": invoice.id,
                                "tax_id": tax_id,
                                "tax_code_id": tax_code_id,
                                "tax_base_id": tax_base_id,
                                "amount": amount,
                                "amount_gross": amount_gross,
                                "amount_net": amount_net,
                                "amount_tax": amount_tax,
                                "payment_rate": payment_rate,
                                "payment_amount": amount_paid,
                                "payment_state": payment_state,
                                "payment_date": payment_date,
                                "sign": sign,
                                "refund": refund,
                                "st_line_id": st_line and st_line.id or None
                            }
                        )

                        # add national tax reverse booking
                        if national_values:
                            values.update(national_values)
                            entry_creator.add_move(values)
               
            taskc.done()

            #######################################################################
            # search for receipts,
            # paid in this period which not belongs to invoices
            #######################################################################

            taskc.substage("Receipt Tax")

            cr.execute(
                """SELECT voucher_id, ARRAY_AGG(move_line_id) FROM
                (SELECT
                    v.id AS voucher_id, l2.id AS move_line_id
                FROM account_move_reconcile r
                INNER JOIN account_move_line l ON (l.reconcile_id = r.id OR l.reconcile_partial_id = r.id)
                INNER JOIN account_voucher v ON v.move_id = l.move_id
                INNER JOIN account_move_line l2 on (l2.move_id != v.move_id AND (l2.reconcile_id = r.id OR l2.reconcile_id = r.id))            
                WHERE v.type IN ('sale','purchase')
                GROUP BY 1,2) t
            GROUP BY 1""",
                {
                    "period_start": period_start,
                    "period_end": period_end,
                    "journal_ids": receipt_journal_ids,
                },
            )

            res = cr.fetchall()
            voucher_ids = [r[0] for r in res]
            voucher_payment_line_ids = dict((r[0], r[1]) for r in res)

            move_line_obj = self.env["account.move.line"]
            taskc.initLoop(len(voucher_ids), status="calc receipt tax")
            for voucher in self.env["account.voucher"].browse(voucher_ids):
                taskc.nextLoop()

                sign = 1.0
                if voucher.type == "purchase":
                    sign = -1.0

                amount = voucher.amount
                amount_paid = 0.0
                payment_date = None

                refund = False
                if (sign < 0.0 and amount > 0.0) or (sign > 0.0 and amount < 0.0):
                    refund = True

                move_line_ids = voucher_payment_line_ids.get(voucher.id)
                if not move_line_ids:
                    continue

                st_line = None
                for move_line in move_line_obj.browse(move_line_ids):
                    if move_line.date >= period_start and move_line.date <= period_end:
                        amount_paid += move_line.credit - move_line.debit
                        payment_date = max(payment_date, move_line.date)

                        if not st_line:
                            st_line = self._get_st_line(move_line)

                if amount_paid:
                    if voucher.paid:
                        payment_state = "paid"
                        payment_rate = 1.0
                    elif amount_paid > 0.0:
                        payment_state = "part"
                        payment_rate = abs((1 / voucher.amount) * amount_paid)
                    else:
                        payment_state = "open"
                        payment_rate = 0.0

                    tax = voucher.tax_id
                    tax_id = None
                    tax_base_id = None
                    tax_code_id = None
                    if tax:
                        if tax.national_tax_id:
                            taskc.loge("Foreign tax for local receipt", ref="account.voucher,%s" % voucher.id)
                            raise Warning(_("Foreign taxes not allowed for local receipts"))
                        
                        tax_id = tax.id
                        if voucher.type == "purchase":
                            tax_base_id = tax.ref_base_code_id.id
                            tax_code_id = tax.ref_tax_code_id.id
                        else:
                            tax_base_id = tax.base_code_id.id
                            tax_code_id = tax.tax_code_id.id

                    taxes = tax.compute_all(
                        amount, 1, product=None, partner=voucher.partner_id
                    )                
                    for line in voucher.line_ids:
                        # generated amounts
                        # and multiplicate with payment rate factor
                        # to get really paid part
                        amount = line.amount * payment_rate * sign
                        amount_gross = taxes["total_included"] * payment_rate * sign
                        amount_net = taxes["total"] * payment_rate * sign

                        account = line.account_id
                        entry_creator.add_move(
                            {
                                "date": payment_date,
                                "move_id": voucher.move_id.id,
                                "journal_id": voucher.journal_id.id,
                                "account_id": account.id,
                                "invoice_id": None,
                                "tax_id": tax_id,
                                "tax_code_id": tax_code_id,
                                "tax_base_id": tax_base_id,
                                "amount": amount,
                                "amount_gross": amount_gross,
                                "amount_net": amount_net,
                                "payment_rate": payment_rate,
                                "payment_amount": amount_paid,
                                "payment_state": payment_state,
                                "payment_date": payment_date,
                                "sign": sign,
                                "refund": refund,
                                "st_line_id": st_line and st_line.id or None
                            }
                        )

            taskc.done()

        #######################################################################
        # search direct booked move line (expense)
        #######################################################################

        if direct_journal_ids:

            taskc.substage("Expense/Income")

            cr.execute("""SELECT l.id, l.credit, l.debit, l.account_tax_id
                FROM account_move_line l
                INNER JOIN account_move m ON m.id = l.move_id 
                INNER JOIN account_account a ON a.id = l.account_id
                INNER JOIN account_account_type t on t.id = a.user_type
                WHERE m.date >= %(period_start)s 
                  AND m.date <= %(period_end)s
                  AND m.journal_id IN %(journal_ids)s
                  AND t.code IN ('expense','income')
            """,{
                    "period_start": period_start,
                    "period_end": period_end,
                    "journal_ids": direct_journal_ids,
            })


            lines = self.env["account.move.line"].browse([r[0] for r in cr.fetchall()])
            taskc.initLoop(len(lines))
            for line in lines:
                taskc.nextLoop()

                sign = -1.0
                if line.credit:
                    sign = 1.0
                    refund = True

                st_line = self._get_st_line(line)

                move = line.move_id
                amount = move.amount

                payment_state = "paid"
                payment_date = move.date
                payment_rate = 1.0

                tax = line.account_tax_id
                tax_id = None
                tax_base_id = None
                tax_code_id = None
                if tax:
                    if tax.national_tax_id:
                        taskc.loge("Foreign tax for local move", ref="account.move,%s" % move.id)
                        raise Warning(_("Foreign taxes not allowed for local moves"))
                        
                    tax_id = tax.id
                    if refund:
                        tax_base_id = tax.ref_base_code_id.id
                        tax_code_id = tax.ref_tax_code_id.id
                    else:
                        tax_base_id = tax.base_code_id.id
                        tax_code_id = tax.tax_code_id.id

                taxes = tax.compute_all(
                    amount, 1, product=None, partner=line.partner_id
                )

                # to get really paid part
                amount = amount * payment_rate * sign
                amount_gross = taxes["total_included"] * payment_rate * sign
                amount_net = taxes["total"] * payment_rate * sign
                amount_paid = amount_gross

                # add line
                account = line.account_id
                entry_creator.add_move(
                    {
                        "date": payment_date,
                        "move_id": move.id,
                        "journal_id": move.journal_id.id,
                        "account_id": account.id,
                        "invoice_id": None,
                        "tax_id": tax_id,
                        "tax_code_id": tax_code_id,
                        "tax_base_id": tax_base_id,
                        "amount": amount,
                        "amount_gross": amount_gross,
                        "amount_net": amount_net,
                        "payment_rate": payment_rate,
                        "payment_amount": amount_paid,
                        "payment_state": payment_state,
                        "payment_date": payment_date,
                        "sign": sign,
                        "refund": refund,
                        "st_line_id": st_line and st_line.id or None
                    }
                )

            taskc.done()

            #######################################################################
            # search tax move line (expense)
            #######################################################################

            taskc.substage("Tax")
            
            cr.execute("""SELECT l.id, l.credit, l.debit, l.account_tax_id
                FROM account_move_line l
                INNER JOIN account_move m ON m.id = l.move_id 
                INNER JOIN account_account a ON a.id = l.account_id                     
                LEFT  JOIN account_tax_code dt ON dt.id = a.debit_tax_code_id
                LEFT  JOIN account_tax_code ct ON ct.id = a.credit_tax_code_id
                WHERE m.date >= %(period_start)s 
                  AND m.date <= %(period_end)s
                  AND m.journal_id IN %(journal_ids)s
                  AND (    (l.debit  > 0 AND NOT dt.id IS NULL)
                        OR (l.credit > 0 AND NOT ct.id IS NULL) )

                        
            """,{
                    "period_start": period_start,
                    "period_end": period_end,
                    "journal_ids": general_journal_ids,
            })


            lines = self.env["account.move.line"].browse([r[0] for r in cr.fetchall()])
            taskc.initLoop(len(lines))
            for line in lines:
                taskc.nextLoop()

                move = line.move_id
                date = move.date
                journal = move.journal_id
                account = line.account_id

                if line.credit and account.credit_tax_code_id:
                    if "asset" in account.user_type.code:
                        sign = 1.0
                    else:
                        sign = -1.0

                    sign = 1.0
                    amount = 0.0
                    amount_base = line.credit * sign,
                    date = line.move_id.date

                    payment_amount = 0.0
                    payment_rate = 1.0
                    payment_state = "paid"
                    refund = False

                    entry_creator.add_move(
                        {
                            "date": date,
                            "move_id": move.id,
                            "journal_id": journal.id,
                            "account_id": account.id,
                            "invoice_id": None,
                            "tax_code_id": account.credit_tax_code_id.id,
                            "tax_base_id": account.credit_tax_code_id.id,
                            "amount_tax": amount,
                            "amount_base": amount_base,
                            "payment_rate": payment_rate,
                            "payment_amount": payment_amount,
                            "payment_state": payment_state,
                            "payment_date": date,
                            "sign": sign,
                            "refund": refund
                        }
                    )

                if line.debit and account.debit_tax_code_id:
                    if "liability" in account.user_type.code:
                        sign = -1.0
                    else:
                        sign = 1.0
                    
                    amount_base = 0.0
                    amount_tax = line.credit * sign
                    date = line.move_id.date

                    payment_amount = 0.0
                    payment_rate = 1.0
                    payment_state = "paid"
                    refund = False

                    entry_creator.add_move(
                        {
                            "date": date,
                            "move_id": move.id,
                            "journal_id": journal.id,
                            "account_id": account.id,
                            "invoice_id": None,
                            "tax_code_id": account.debit_tax_code_id.id,
                            "tax_base_id": None,
                            "amount_tax": amount_tax,
                            "amount_base": amount_base,
                            "payment_rate": payment_rate,
                            "payment_amount": payment_amount,
                            "payment_state": payment_state,
                            "payment_date": date,
                            "sign": sign,
                            "refund": refund
                        }
                    )

            taskc.done()


        #######################################################################
        # create moves
        #######################################################################

        entry_creator.flush()

        # all done
        taskc.done()

    def _create_private(self, taskc):
        taskc.substage("Create Private")

        cr = self._cr
        move_obj = self.env["account.move"]

        entry_creator = PeriodEntryCreator(self, taskc)
        period = self.period_id
        company = period.company_id
        journal = company.account_period_journal_id

        if not journal:
            raise Warning(_("No period booking journal was defined for company"))


        # search accounts with private option
        cr.execute("""SELECT
                e.id
            FROM account_period_entry e
            INNER JOIN account_account a ON a.id = e.account_id
            WHERE a.private_usage > 0
              AND a.private_account_id IS NOT NULL
              AND e.task_id = %s
        """, (self.id, ))
        entry_ids = [r[0] for r in cr.fetchall()]
        for entry in self.env["account.period.entry"].search([("id", "in", entry_ids)]):
            account = entry.account_id

            private_usage = account.private_usage
            private_account = account.private_account_id

            amount_gross = entry.amount_gross * entry.sign 
            amount_net = entry.amount_net * entry.sign
            amount_tax = entry.amount_tax * entry.sign

            private_amount = amount_gross * private_usage
            private_amount_net = amount_net * private_usage
            private_tax = private_amount - private_amount_net

            payment_rate = entry.payment_rate
            payment_state = entry.payment_state
            payment_date = entry.payment_date

            tax = entry.tax_id
            refund = entry.refund

            sign = entry.sign * -1.0

            field_from = "credit"
            field_to = "debit"

            if entry.amount > 0:
                field_from = "debit"
                field_to = "credit"

            # to/from private account
            private_line = {
                field_to: private_amount,
                "name": _("Private: %s") % entry.move_id.name,
                "account_id": private_account.id,
            }
            lines = [private_line]

            # to/from renevue/expense account
            calced_private_amount = 0.0
            for line in entry.move_id.line_id:
                field_amount = getattr(line, field_to)
                if field_amount > 0 and field_amount in (amount_tax, amount_gross, amount_net):
                    line_amount = round(field_amount * private_usage,2)
                    calced_private_amount += line_amount
                    lines.append({
                        field_from: line_amount,
                        "name": _("Private: %s") % line.name,
                        "account_id": line.account_id.id
                    })

            # correct rounding
            if abs(private_amount - calced_private_amount) <= 0.1:
                private_line[field_to] = calced_private_amount

            taskc.log("Create private move for %s" % entry.move_id.name,
                    ref="account.move,%s" % entry.move_id.id)

            # book to private
            move = move_obj.create({
                "ref": _("Private: %s" % entry.move_id.name),
                "period_id": period.id,
                "journal_id": journal.id,
                "line_id": [(0,0,l) for l in lines]
            })


            move.post()
            values = {
                "auto": True,
                "journal_id": journal.id,
                "account_id": account.id,
                "date": period.date_stop,
                "move_id": move.id,
                "payment_rate": payment_rate,
                "tax_id": tax.id,
                "tax_code_id": entry.tax_code_id.id,
                "tax_base_id": entry.tax_base_id.id,
                "amount_tax": private_tax,
                "amount_base": private_amount_net,
                "payment_state": payment_state,
                "payment_date": payment_date,
                "sign": sign,
                "refund": refund
            }
            entry_creator.add_move(values)

        entry_creator.flush()
        taskc.done()

    def _create_tax(self, taskc):
        taskc.substage("Create Tax")

        cr = self._cr
        tax_code_obj = self.env["account.tax.code"]
        period_tax_obj = self.env["account.period.tax"]

        period_tax_obj.search([("task_id","=",self.id)]).unlink()

        # tax calculation
        def calc_tax(tax_code, parent_id=None):
            entry_ids = set()

            # calc tax base

            cr.execute("""SELECT                               
                 COALESCE(SUM(e.amount_base*%s),0.0) AS amount_base
                ,ARRAY_AGG(e.id) AS entry_ids
            FROM account_period_entry e
            WHERE e.task_id = %%s
              AND e.tax_base_id = %%s              
            """ % tax_code.tax_sign,
                (self.id, tax_code.id)
            )

            amount_base = 0.0
            for (amount_base, base_entry_ids) in cr.fetchall():
                if base_entry_ids:
                    entry_ids |= set(base_entry_ids)


            # calc tax

            cr.execute("""SELECT                  
                 COALESCE(SUM(e.amount_tax*%s),0.0) AS amount_tax
                ,ARRAY_AGG(e.id) AS entry_ids
            FROM account_period_entry e
            WHERE e.task_id = %%s
              AND e.tax_code_id = %%s              
            """ % tax_code.tax_sign,
                (self.id, tax_code.id)
            )

            amount_tax = 0.0
            for (amount_tax, tax_entry_ids) in cr.fetchall():
                if tax_entry_ids:
                    entry_ids |= set(tax_entry_ids)


            # create tax

            period_tax = period_tax_obj.create(
                {
                    "task_id": self.id,
                    "sequence": tax_code.sequence,
                    "name": tax_code.name,
                    "code": tax_code.code,
                    "amount_base": amount_base,
                    "amount_tax": amount_tax,
                    "parent_id": parent_id,
                    "entry_ids": [(6, 0, list(entry_ids))],
                }
            )

            # process child
            childs = tax_code.child_ids
            if childs:
                for child in childs:
                    child_amount_base, child_amount_tax = calc_tax(
                        child, parent_id=period_tax.id
                    )
                    if child.sign:
                        amount_base += (child_amount_base * child.sign)
                        amount_tax += (child_amount_tax * child.sign)

                # update amount after
                # child processing
                period_tax.write({"amount_base": amount_base, "amount_tax": amount_tax})

            taskc.log(
                "Calculated tax | base: %s | tax: %s" % (amount_base, amount_tax),
                ref="account.tax.code,%s" % tax_code.id,
            )

            return (amount_base, amount_tax)

        # calc for root
        tax_total = 0.0
        for tax_code in tax_code_obj.search(
            [("company_id", "=", self.company_id.id), ("parent_id", "=", False)]
        ):
            (amount_base, amount_tax) = calc_tax(tax_code)
            tax_total += amount_tax

        self.tax_total = tax_total
        taskc.done()

    def _create_balance(self, taskc):
        """ Create account balance """
        taskc.substage("Create Balance")

        balance_obj = self.env["account.period.balance"]
        
        period = self.period_id
        periods = period.search([("fiscalyear_id","=",period.fiscalyear_id.id),
                                      ("date_stop","<=",period.date_stop)])
        sequence = 1

        accounts = self.env["account.account"].search([("company_id", "=", self.company_id.id)])
        taskc.substage("Create Balance")
        taskc.initLoop(len(accounts))

        for account in accounts:
            self._cr.execute("""SELECT COUNT(l), COALESCE(SUM(l.debit),0.0), COALESCE(SUM(l.credit),0.0)
                FROM account_move_line l
                WHERE l.account_id = %s
                  AND l.period_id IN %s
            """, (account.id, tuple(periods.ids,)))

            for (move_lines, debit, credit) in self._cr.fetchall():
                balance_obj.create({
                    "task_id": self.id,
                    "account_id": account.id,
                    "parent_account_id": account.parent_id.id,
                    "sequence": sequence,
                    "debit": debit,
                    "credit": credit,
                    "balance": debit-credit,
                    "move_lines": move_lines
                })

            sequence += 1
            taskc.nextLoop()

        taskc.done()

    def _check_unprocessed(self, taskc):
        for invoice in self.env["account.invoice"].search([("period_id","=",self.period_id.id),
                                            ("type","in",("in_invoice","in_refund")),
                                            ("state","not in",("paid","cancel"))]):
            taskc.logw("Invoice not reconciled",
                    ref="account.invoice,%s" % invoice.id,
                    code="NOT_RECONCILED")

    def _run(self, taskc):
        journals = self.env["account.journal"].search([("periodic", "=", True)])
        if not journals:
            taskc.logw("No journal for period processing specified.")
            return

        if self.period_id.company_id.taxation == "invoice":
            taskc.loge("**Tax on invoice** currently not supported.")
            return

        # save entry user
        taskc.log("Backup validated")

        entry_obj = self.env["account.period.entry"]
        valid_entries =  entry_obj.search(
                [("task_id", "=", self.id), ("state", "=", "valid")]
            )
        validated_by = dict([(e._get_key(), e.user_id.id) for e in valid_entries])


        # (re)create

        self._clean_entries(check_valid=False)
        self._create_payment_based(taskc, journals)
        self._create_private(taskc)
        self._create_tax(taskc)
        self._create_balance(taskc)
        self._check_unprocessed(taskc)

        # restore entry user
        taskc.log("Restore validated")

        entry_obj = self.env["account.period.entry"]
        for entry in  entry_obj.search(
                [("task_id", "=", self.id), ("state", "=", "draft")]
            ):
            user_id = validated_by.get(entry._get_key())
            if user_id:
                entry.user_id = user_id
                entry.state = "valid"


class AccountPeriodEntry(models.Model):
    _name = "account.period.entry"
    _description = "Period Entry"
    _order = "date, move_id"

    task_id = fields.Many2one(
        "account.period.task", "Task", required=True, index=True, readonly=True, ondelete="cascade"
    )

    name = fields.Char("Name", readonly=True, store=False, compute="_compute_name")
    date = fields.Date("Date", required=True, index=True, readonly=True)

    move_id = fields.Many2one(
        "account.move", "Move", index=True, required=True, readonly=True,
        ondelete="cascade"
    )
    st_line_id = fields.Many2one("account.bank.statement.line",
        "Statement Line",
        ondelete="cascade",
        index=True,
        readonly=True
    )
    journal_id = fields.Many2one(
        "account.journal", "Journal", index=True, required=True, readonly=True,
        ondelete="cascade"
    )
    account_id = fields.Many2one(
        "account.account", "Account", index=True, required=True, readonly=True,
        ondelete="cascade"
    )
    invoice_id = fields.Many2one(
        "account.invoice", "Invoice", index=True, readonly=True,
        ondelete="cascade"
    )
    voucher_id = fields.Many2one(
        "account.voucher", "Receipt", index=True, readonly=True,
        ondelete="cascade"
    )

    tax_id = fields.Many2one("account.tax", "Tax", index=True, readonly=True)
    tax_code_id = fields.Many2one("account.tax.code", "Tax Code", index=True, readonly=True)
    tax_base_id = fields.Many2one("account.tax.code", "Tax Base", index=True, readonly=True)
    
    sign = fields.Float("Sign", default=1.0)
    refund = fields.Boolean("Refund", default=False)
    
    amount = fields.Float("Amount", digits=dp.get_precision("Account"), readonly=True)
    amount_gross = fields.Float(
        "Gross Amount", digits=dp.get_precision("Account"), readonly=True
    )
    amount_net = fields.Float(
        "Net Amount", digits=dp.get_precision("Account"), readonly=True
    )
    amount_tax = fields.Float(
        "Tax Amount", digits=dp.get_precision("Account"), readonly=True
    )
    amount_base = fields.Float(
        "Tax Base", digits=dp.get_precision("Account"), readonly=True
    )

    payment_date = fields.Date("Payment Date", readonly=True)
    payment_amount = fields.Float(
        "Payment", digits=dp.get_precision("Account"), readonly=True
    )
    payment_rate = fields.Float("Payment Rate", readonly=True)
    payment_state = fields.Selection(
        [("open", "Open"), ("part", "Partly"), ("paid", "Done")],
        string="Payment State",
        index=True,
        required=True,
        readonly=True,
    )

    user_id = fields.Many2one("res.users", "Audited by", readonly=True)

    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("valid", "Validated"),
            ("wrong", "Wrong")
        ],
        string="Status",
        default="draft",
        readonly=True,
    )

    currency_id = fields.Many2one(
        "res.currency", "Currency", relation="company_id.currency_id", readonly=True
    )

    auto = fields.Boolean("Auto Generated",
                        readonly=True)

    @api.depends("move_id", "st_line_id")
    @api.multi
    def _compute_name(self):
        for obj in self:
            obj.name = obj.st_line_id.name or obj.move_id.ref or obj.move_id.name
    
    def _check_accountant(self):
        user = self.env.user
        if not user.has_group("account.group_account_user"):
            raise Warning(_("You must be an accountant to do that."))
        return user

    @api.multi
    def action_validate(self):
        user = self._check_accountant()
        for line in self.sudo():
            line.user_id = user
            line.state = "valid"
        return True

    @api.multi
    def action_wrong(self):
        user = self._check_accountant()
        for line in self.sudo():
            line.user_id = user
            line.state = "wrong"
        return True

    @api.multi
    def action_reset(self):
        user = self._check_accountant()
        for line in self.sudo():
            if line.user_id and line.user_id.id != user.id:
                if not user.has_group("account.group_account_manager"):
                    raise Warning(_("You must be an accountant manager to do that."))
            line.user_id = None
            line.state = "draft"
        return True

    @api.multi
    def action_print(self):
        for line in self:
            if line.invoice_id:
                return self.env["report"].get_action(self.invoice_id, 'account.report_invoice')
            elif line.st_line_id:
                return self.env["report"].get_action(self.st_line_id.statement_id.id, 'account.bank.statement.detail')
        return True

    @api.multi
    def action_open(self):
        for line in self:
            if line.invoice_id:
                return {
                    "display_name": _("Invoice"),
                    "view_type": "form",
                    "view_mode": "form",
                    "res_model": "account.invoice",
                    "res_id": self.invoice_id.id,
                    "type": "ir.actions.act_window",
                }
            elif line.voucher_id:
                return {
                    "display_name": _("Receipt"),
                    "view_type": "form",
                    "view_mode": "form",
                    "res_model": "account.voucher",
                    "res_id": self.voucher_id.id,
                    "type": "ir.actions.act_window",
                }
            elif line.st_line_id:
                return {
                    "display_name": _("Line"),
                    "view_type": "form",
                    "view_mode": "form",
                    "res_model": "account.bank.statement.line",
                    "res_id": self.st_line_id.id,
                    "type": "ir.actions.act_window",
                }
            return line.action_open_move()
        return True

    @api.multi
    def action_open_move(self):
        return {
            "display_name": _("Move"),
            "view_type": "form",
            "view_mode": "form",
            "res_model": "account.move",
            "res_id": self.move_id.id,
            "type": "ir.actions.act_window",
        }

    def _get_key(self):
        return (
            self.date,
            self.journal_id.id,
            self.move_id.id,
            self.account_id.id,
            self.invoice_id.id or 0,
            self.voucher_id.id or 0,
            self.tax_id.id or 0,
            self.tax_base_id.id or 0,
            self.tax_code_id.id or 0,
            self.sign,
            self.refund,
            self.amount,
            self.amount_gross,
            self.amount_net,
            self.amount_tax,
            self.payment_date,
            self.payment_amount,
            self.payment_rate,
            self.payment_state
        )


class AccountPeriodTax(models.Model):
    _name = "account.period.tax"
    _description = "Period Tax"
    _order = "sequence"

    task_id = fields.Many2one(
        "account.period.task", "Task", required=True, readonly=True, ondelete="cascade"
    )

    name = fields.Char("Name", required=True, readonly=True)
    code = fields.Char("Code", readonly=True, index=True)

    sequence = fields.Integer("Sequence", default=10, readonly=True)
    parent_id = fields.Many2one(
        "account.period.tax", "Parent", index=True, readonly=True, ondelete="cascade"
    )

    amount_base = fields.Float("Base Amount", help="Tax base amount.", readonly=True)
    amount_tax = fields.Float("Tax Amount", readonly=True)

    currency_id = fields.Many2one(
        "res.currency",
        "Currency",
        relation="task_id.company_id.currency_id",
        readonly=True,
    )
    entry_ids = fields.Many2many(
        "account.period.entry",
        "account_period_tax_entry_rel",
        "tax_id",
        "entry_id",
        string="Entries",
        readonly=True,
        ondelete="cascade"
    )

    entry_count = fields.Integer(
        "Entries", compute="_compute_entry_count", store=False, readonly=True
    )

    @api.multi
    def _compute_entry_count(self):
        for tax in self:
            tax.entry_count = len(tax.entry_ids)

    @api.multi
    def entry_action(self):
        for tax in self:
            entry_ids = tax.entry_ids.ids
            if entry_ids:
                return {
                    "display_name": _("Entries"),
                    "view_type": "form",
                    "view_mode": "tree,form",
                    "res_model": "account.period.entry",
                    "domain": [("id", "in", entry_ids)],
                    "type": "ir.actions.act_window",
                }
        return True


class AccoundPeriodBalance(models.Model):
    _name = "account.period.balance"
    _description = "Account Balance"
    _order = "sequence"
    _rec_name = "account_id"


    task_id = fields.Many2one(
        "account.period.task", "Task", required=True, readonly=True, ondelete="cascade"
    )

    account_id = fields.Many2one("account.account", "Account",
                required=True, index=True, ondelete="restrict", readonly=True)

    parent_account_id = fields.Many2one("account.account", "Parent Account",
                index=True, ondelete="cascade", readonly=True)

    sequence = fields.Integer("Sequence", readonly=True, default=10)

    debit = fields.Float("Debit", readonly=True, digits=dp.get_precision("Account"))
    credit = fields.Float("Credit", readonly=True, digits=dp.get_precision("Account"))
    balance = fields.Float("Balance", readonly=True, digits=dp.get_precision("Account"))

    move_lines = fields.Integer("Move Lines")

    @api.multi
    def action_move_lines(self):        
        for obj in self:
            period = obj.task_id.period_id
            periods =  period.search([("fiscalyear_id","=",period.fiscalyear_id.id),
                                      ("date_stop","<=",period.date_stop)])
            return {
                "display_name": _("Move Lines"),
                "view_type": "form",
                "view_mode": "tree,form",
                "res_model": "account.move.line",
                "domain": [("account_id", "=", obj.account_id.id),
                           ("period_id","in",periods.ids)],
                "type": "ir.actions.act_window",
            }
        return True
