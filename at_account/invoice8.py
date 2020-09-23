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

from openerp import models, fields, api, _
import openerp.addons.decimal_precision as dp


class account_invoice(models.Model):
    _inherit = "account.invoice"

    discount = fields.Float(
        "Discount %",
        compute="_calc_discount",
        store=False,
        digits_compute=dp.get_precision("Discount"),
    )
    discount_amount = fields.Float(
        "Discount",
        compute="_calc_discount",
        store=False,
        digits_compute=dp.get_precision("Account"),
    )

    @api.one
    def _calc_discount(self):
        discount_amount = 0.0
        for line in self.invoice_line:
            discount_amount += line.discount_amount

        if not discount_amount:
            self.discount = 0.0
            self.discount_amount = 0.0
        else:
            total_nodisc = self.amount_untaxed + discount_amount
            self.discount_amount = discount_amount
            self.discount = 100.0 / total_nodisc * discount_amount

    @api.multi
    def invoice_send(self, force=False):
        # get template
        template = self.env.ref("account.email_template_edi_invoice", False)
        message_obj = self.env["mail.compose.message"]
        # send all unsent
        for inv in self:
            if not inv.sent or force:
                message = message_obj.with_context(
                    default_template_id=template.id,
                    default_model="account.invoice",
                    default_res_id=inv.id,
                    mark_invoice_as_sent=True,
                    default_partner_ids=[inv.partner_id.id],
                    default_composition_mode="comment",
                    default_notify=True,
                ).create({})
                # finally sent
                message.send_mail()

    @api.model
    def send_all_draft(self, inv_type="out_invoice"):
        for invoice in self.search([("state", "=", "draft"), ("type", "=", inv_type)]):
            invoice.signal_workflow("invoice_open")
            invoice.invoice_send()
        return True


class account_invoice_line(models.Model):
    _inherit = "account.invoice.line"

    @api.multi
    def _line_format(self):
        res = dict.fromkeys(self.ids, "")
        for line in self:
            if not line.product_id and not line.price_unit and not line.quantity:
                res[line.id] = "s"
        return res
