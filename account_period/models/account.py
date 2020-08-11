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


class AccountJournal(models.Model):
    _inherit = "account.journal"

    periodic = fields.Boolean("Periodic Processing")


class AccountAccount(models.Model):
    _inherit = "account.account"

    private_account_id = fields.Many2one("account.account", "Private Account")

    private_usage = fields.Float(
        "Private Usage",
        help="Define private usage between 0.0 - 1.0.\n"
        "0.0 means no private usage.\n"
        "1.0 means 100% private usage",
    )

    credit_tax_code_id = fields.Many2one("account.tax.code", "Credit Tax Code")
    debit_tax_code_id = fields.Many2one("account.tax.code", "Debit Tax Codd")


class AccountTax(models.Model):
    _inherit = "account.tax"

    national_tax_id = fields.Many2one("account.tax", "National Tax", oncascade="delete")
    import_tax = fields.Selection([("eu","EU"),
                                   ("third","Third Country")],
                                   string="Import Tax")    


class AccountTaxCode(models.Model):
    _inherit = "account.tax.code"

    tax_sign = fields.Float("Coefficent for Tax", 
        help="Coefficent for Tax: 1.0 is a tax levy addition, -1.0 is a tax levy reduction.",
        default=1.0)