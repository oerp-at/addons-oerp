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
            "payment_amount"        
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

        key = (move_id,
                journal_id,
                account_id,
                invoice_id,
                voucher_id,
                tax_id,
                tax_base_id,
                tax_code_id,
                sign,
                refund)

        # calculate tax if it is not passed
        if not "amount_tax" in values:
            values["amount_tax"] = values["amount_gross"] - values["amount_net"]                

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
        domain=[('state','=','draft')],
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

    def _clean_entries(self):
        self.ensure_one()

        cr = self.env.cr
        entry_obj = self.env["account.period.entry"]

        # fetch autogenerated moves
        cr.execute("""SELECT
            e.move_id
        FROM account_period_entry e
        WHERE e.task_id = %s
          AND e.auto
        GROUP BY 1
        """, (self.id,))

        auto_move_ids = [r[0] for r in cr.fetchall()]

        # check for validated entries
        valid_entry_count =  entry_obj.search(
            [("task_id", "=", self.id), ("state", "=", "valid")], count=True
        )
        if valid_entry_count:
            raise Warning(_("Validated entries already exist."))

        # delete tax
        self.env["account.period.tax"].search([("task_id", "=", self.id)]).unlink()

        # delete other entries
        entry_obj.search(
            [("task_id", "=", self.id), ("state", "!=", "valid")]
        ).unlink()

        # delete auto moves
        moves = self.env["account.move"].search([("id", "in", auto_move_ids)])
        moves.button_cancel()
        moves.unlink()
        
    def _create_payment_based(self, taskc, journals):
        """ search for invoices and receipts, which are in 
            the passed journal, and paid in this period """

        cr = self.env.cr
                
        receipt_journal_ids = tuple([j.id for j in journals if j.type in ("sale", "sale_refund", "purchase", "purchase_refund")])
        direct_journal_ids = tuple([j.id for j in journals if j.type in ("cash", "bank")])
        
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

                for move_line in invoice.payment_ids:
                    if move_line.date >= period_start and move_line.date <= period_end:
                        amount_paid += move_line.credit - move_line.debit
                        payment_date = max(payment_date, move_line.date)
                
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
                        taxes = line.invoice_line_tax_id.compute_all(
                            price, line.quantity, line.product_id, invoice.partner_id
                        )
                        
                        # generated amounts
                        # and multiplicate with payment rate factor
                        # to get really paid part
                        amount = price * line.quantity * payment_rate * sign
                        amount_gross = taxes["total_included"] * payment_rate * sign
                        amount_net = taxes["total"] * payment_rate * sign                    

                        tax_id = None
                        tax_base_id = None
                        tax_code_id = None
                        tax = line.invoice_line_tax_id
                        if tax:                       
                            if invoice.type in ("in_refund", "in_invoice"):
                                tax_base_id = tax.ref_base_code_id.id
                                tax_code_id = tax.ref_tax_code_id.id
                            else:
                                tax_base_id = tax.base_code_id.id
                                tax_code_id = tax.tax_code_id.id

                        account = line.account_id
                        entry_creator.add_move(
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
                                "payment_rate": payment_rate,
                                "payment_amount": amount_paid,
                                "payment_state": payment_state,
                                "payment_date": payment_date,
                                "sign": sign,
                                "refund": refund
                            }                
                        )

                        
                # add manual tax entries

                for invoice_tax in invoice.tax_line:
                    if invoice_tax.manual:
                        amount = invoice_tax.amount * sign
                        payment_amount = amount                        
                        entry_creator.add_move(
                            {
                                "date": invoice_tax.date_invoice,
                                "move_id": invoice.move_id.id,
                                "journal_id": invoice.journal_id.id,
                                "account_id": invoice_tax.account_id,
                                "invoice_id": invoice.id,                                
                                "tax_code_id": invoice_tax.tax_code_id,
                                "tax_base_id": invoice_tax.base_code_id,
                                "amount_tax": amount,
                                "payment_rate": payment_rate,
                                "payment_amount": payment_amount,
                                "payment_state": payment_state,
                                "payment_date": payment_date,
                                "sign": sign,
                                "refund": refund
                            }
                        )

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

                for move_line in move_line_obj.browse(move_line_ids):
                    if move_line.date >= period_start and move_line.date <= period_end:
                        amount_paid += move_line.credit - move_line.debit
                        payment_date = max(payment_date, move_line.date)

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
                        tax_id = tax.id
                        if voucher.type == "purchase":
                            tax_base_id = tax.ref_base_code_id.id
                            tax_code_id = tax.ref_tax_code_id.id
                        else:
                            tax_base_id = tax.base_code_id.id
                            tax_code_id = tax.tax_code_id.id

                    taxes = voucher.tax_id.compute_all(
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
                                "amount": amount,
                                "amount_gross": amount_gross,
                                "amount_net": amount_net,                        
                                "payment_rate": payment_rate,
                                "payment_amount": amount_paid,
                                "payment_state": payment_state,
                                "payment_date": payment_date,
                                "sign": sign,
                                "refund": refund
                            }
                        )

            taskc.done()

        #######################################################################
        # search direct booked move line (expense)
        #######################################################################

        if direct_journal_ids:

            taskc.substage("Direct Tax")

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
                
                move = line.move_id
                amount = move.amount 
                
                payment_state = "paid"                                                      
                payment_date = move.date
                payment_rate = 1.0
                
                tax = line.account_tax_id
                if tax:
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
                
                # calc private amount
                account = line.account_id
                entry_creator.add_move(
                    {
                        "date": payment_date,
                        "move_id": move.id,
                        "journal_id": move.journal_id.id,
                        "account_id": account.id,
                        "invoice_id": None,
                        "tax_id": tax_id,
                        "amount": amount,
                        "amount_gross": amount_gross,
                        "amount_net": amount_net,                        
                        "payment_rate": payment_rate,
                        "payment_amount": amount_paid,
                        "payment_state": payment_state,
                        "payment_date": payment_date,
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
        taskc.logd("Create Private")

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
        """)        
        entry_ids = [r[0] for r in cr.fetchall()]
        for entry in self.env["account.period.entry"].search([("id", "in", entry_ids)]):
            account = entry.account_id
            
            private_usage = account.private_usage
            private_account = account.private_account_id

            private_amount = entry.amount_gross * entry.sign * private_usage
            private_tax = entry.amount_tax * entry.sign * private_usage
            private_amount_net = private_amount - private_tax
            
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
                "account_id": account.id,                    
            }
            lines = [private_line]

            # to/from renevue/expense account
            calced_private_amount = 0.0
            for line in entry.move_id.line_id:
                field_amount = getattr(line, field_to)             
                if field_amount > 0:
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
                "amount": private_amount * sign,
                "amount_gross": private_amount * sign,
                "amount_net": private_amount_net * sign,                
                "payment_state": payment_state,
                "payment_date": payment_date,
                "sign": sign,
                "refund": refund
            }

            if tax:
                values.update({
                    "tax_code_id": tax.tax_code_id.id,
                    "tax_base_id": tax.base_code_id.id,
                    "amount_tax": private_tax
                })

            entry_creator.add_move(values)

        entry_creator.flush()

    def _create_tax(self, taskc):
        taskc.logd("Create tax")

        cr = self._cr
        tax_code_obj = self.env["account.tax.code"]
        period_tax_obj = self.env["account.period.tax"]

        taskc.substage("Create Tax")
        period_tax_obj.search([("task_id","=",self.id)]).unlink()

        # tax calculation
        def calc_tax(tax_code, parent_id=None):
            entry_ids = set()            
            
            # calc tax base

            cr.execute("""SELECT                               
                 COALESCE(SUM(e.amount_net*e.sign*e.refund_sign),0.0) AS amount_base
                ,ARRAY_AGG(e.id) AS entry_ids
            FROM account_period_entry e
            WHERE e.task_id = %s
              AND e.tax_base_id = %s              
            """,
                (self.id, tax_code.id)
            )

            amount_base = 0.0            
            for (amount_base, base_entry_ids) in cr.fetchall():
                if base_entry_ids:
                    entry_ids |= set(base_entry_ids)


            # calc tax

            cr.execute("""SELECT                  
                 COALESCE(SUM(e.amount_tax*e.sign*e.refund_sign),0.0) AS amount_tax
                ,ARRAY_AGG(e.id) AS entry_ids
            FROM account_period_entry e
            WHERE e.task_id = %s
              AND e.tax_code_id = %s              
            """,
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

    def _run(self, taskc):
        journals = self.env["account.journal"].search([("periodic", "=", True)])
        if not journals:
            taskc.logw("No journal for period processing specified.")
            return

        if self.period_id.company_id.taxation == "invoice":
            taskc.loge("**Tax on invoice** currently not supported.")
            return

        self._clean_entries()
        self._create_payment_based(taskc, journals)       
        self._create_private(taskc)
        self._create_tax(taskc)

        cr = self._cr
        cr.execute("UPDATE account_period_entry SET uid")


class AccountPeriodEntry(models.Model):
    _name = "account.period.entry"
    _description = "Period Entry"

    _rec_name = "move_id"
    _order = "date, move_id"

    task_id = fields.Many2one(
        "account.period.task", "Task", required=True, index=True, readonly=True, ondelete="cascade"
    )
    move_id = fields.Many2one(
        "account.move", "Move", index=True, required=True, readonly=True, 
        ondelete="restrict"
    )

    date = fields.Date("Date", required=True, index=True, readonly=True)

    journal_id = fields.Many2one(
        "account.journal", "Journal", index=True, required=True, readonly=True,
        ondelete="restrict"
    )
    account_id = fields.Many2one(
        "account.account", "Account", index=True, required=True, readonly=True,
        ondelete="restrict"
    )
    invoice_id = fields.Many2one(
        "account.invoice", "Invoice", index=True, readonly=True,
        ondelete="restrict"
    )
    voucher_id = fields.Many2one(
        "account.voucher", "Receipt", index=True, readonly=True,
        ondelete="restrict"
    )

    tax_id = fields.Many2one("account.tax", "Tax", index=True, readonly=True)
    tax_code_id = fields.Many2one("account.tax.code", "Tax Code", index=True, readonly=True)
    tax_base_id = fields.Many2one("account.tax.code", "Tax Base", index=True, readonly=True)

    sign = fields.Float("Sign", default=1.0)
    refund = fields.Boolean("Refund", default=False)

    refund_sign = fields.Float("Refund Sign", compute="_compute_refund_sign", store=True)

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

    @api.depends("refund")
    @api.multi
    def _compute_refund_sign(self):
        for obj in self:            
            obj.refund_sign = -1.0 if obj.refund else 1.0

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

    amount_base = fields.Float("Base Amount", readonly=True)
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
