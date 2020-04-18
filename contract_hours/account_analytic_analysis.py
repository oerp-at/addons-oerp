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

class account_analytic_account(osv.Model):
    
    def _ct_year_hours(self, cr, uid, ids, fieldnames, args, context=None):
        res = dict.fromkeys(ids, 0)
        cr.execute("SELECT a.id, a.ct_month_hours * 12 FROM account_analytic_account a WHERE id IN %s ", (tuple(ids),))
        for rec_id, rec_hours in cr.fetchall():
            res[rec_id] = rec_hours
        return res 

    def _ct_remaining_hours(self, cr, uid, ids, fieldnames, args, context=None):
        res = dict.fromkeys(ids, 0)
        
        # assign all hours
        for account in self.browse(cr, uid, ids, context=context):
            res[account.id] = account.ct_year_hours
        
        # calc used
        cr.execute("SELECT a.id, (a.ct_month_hours * 12)-SUM(l.unit_amount) FROM account_analytic_line l " 
                   " INNER JOIN account_analytic_account a ON a.id = l.account_id AND a.id IN %s AND a.ct_month_hours > 0 "  
                   " INNER JOIN account_analytic_journal j ON j.id = l.journal_id AND j.type = 'general' " 
                   " INNER JOIN res_company c ON c.id = a.company_id " 
                   " WHERE l.product_uom_id = c.project_time_mode_id AND a.recurring_invoices AND l.date <= a.recurring_next_date AND l.date >= (a.recurring_next_date - INTERVAL '1 year') "
                   " GROUP BY 1 ",(tuple(ids),))
        for rec_id, rec_used_hours in cr.fetchall():
            res[rec_id] = rec_used_hours
            
        return res 
   
    def _get_analytic_account_used_hours_rel(self, cr, uid, ids, context=None):
        cr.execute("SELECT l.account_id FROM account_analytic_line l  "
                   " INNER JOIN account_analytic_account a ON a.id = l.account_id AND a.ct_month_hours > 0 "
                   " WHERE l.id IN %s GROUP BY 1 ", (tuple(ids),))
        account_ids = [r[0] for r in cr.fetchall()]
        return account_ids
    
    def on_change_template(self, cr, uid, ids, template_id, date_start=False, context=None):
        res = super(account_analytic_account, self).on_change_template(cr, uid, ids, template_id, date_start=date_start, context=context)
        if template_id:
          template = self.browse(cr, uid, template_id, context=context)
          if not ids:
            res["value"]["ct_month_hours"] = template.ct_month_hours
        return res
    
    _inherit = "account.analytic.account"
    _columns = {
        "ct_month_hours" : fields.float("Hours per month"),
        "ct_year_hours" : fields.function(_ct_year_hours, string="Hours per Year", store=True),
        "ct_remaining_hours" : fields.function(_ct_remaining_hours, string="Remaining hours", help="Remaining hours this year",  store={
                                                    'account.analytic.line' : (_get_analytic_account_used_hours_rel, None, 20),
                                                    'account.analytic.account': (lambda self, cr, uid, ids, c=None: ids, ["ct_year_hours","ct_month_hours"], 10),
                                          })
    }