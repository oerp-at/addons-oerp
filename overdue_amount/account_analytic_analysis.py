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

from openerp.osv import fields, osv

class account_analytic_analysis(osv.Model):
    
    def _is_overdue_quantity(self, cr, uid, ids, fieldnames, args, context=None):
        result = dict.fromkeys(ids, 0)
        for record in self.browse(cr, uid, ids, context=context):
            if record.quantity_max > 0.0:
                result[record.id] = int(record.hours_quantity > record.quantity_max)
            elif record.check_overdue_amount:
                result[record.id] = int(record.balance < record.overdue_amount_max)
            else:
                result[record.id] = 0
        return result
    
    def _get_analytic_account(self, cr, uid, ids, context=None):
        cr.execute("SELECT l.account_id FROM account_analytic_line l WHERE l.id IN %s GROUP BY 1", (tuple(ids),))
        account_ids = [r[0] for r in cr.fetchall()]
        return account_ids
    
    _inherit = "account.analytic.account"
    _columns = {
        "check_overdue_amount" : fields.boolean("Check Overdue"),
        "overdue_amount_max" : fields.float("Overdue Line", help="Define max overdue amount, normally it is an negative value or null"),
        "is_overdue_quantity" : fields.function(_is_overdue_quantity, method=True, type='boolean', string='Overdue Quantity',
                                                store={
                                                    'account.analytic.line' : (_get_analytic_account, None, 20),
                                                    'account.analytic.account': (lambda self, cr, uid, ids, c=None: ids, ["quantity_max","overdue_amount_max","check_overdue_amount"], 10),
                                                }),
    
    }