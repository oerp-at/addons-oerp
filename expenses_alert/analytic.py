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

import logging

from openerp.osv import fields, osv
from openerp.addons.at_base import util

_logger = logging.getLogger(__name__)


class account_analytic_account(osv.Model):
    
    def _expense_alert_line_ids(self, cr, uid, ids, field_name, arg, context=None):
        res = dict.fromkeys(ids, None)
        alert_date = context and context.get("alert_date") or util.lastDay()
        
        cr.execute("SELECT a.id, al.id FROM account_analytic_account a "
                "      INNER JOIN account_analytic_line al ON al.account_id=a.id " 
                "             AND ( (a.expense_alert_date IS NULL AND al.date=%s) " 
                "                OR (a.expense_alert_date IS NOT NULL AND al.date > a.expense_alert_date AND al.date<=%s) ) "
                "      INNER JOIN resource_resource r ON r.user_id = al.user_id "      
                "      INNER JOIN hr_employee e ON e.resource_id = r.id AND e.journal_id = al.journal_id "  
                "      WHERE a.expense_alert AND a.id IN %s AND NOT a.partner_id IS NULL AND (al.to_invoice IS NOT NULL OR a.to_invoice IS NULL) " 
                "      GROUP BY 1,2 "
                "      ORDER BY a.id, al.date ",
                (alert_date, alert_date, tuple(ids)))
        
        for account_id, line_id in cr.fetchall():
            line_ids = res[account_id]
            if line_ids is None:
                res[account_id] = line_ids = []
            line_ids.append(line_id)

        return res
    
    _inherit = "account.analytic.account"
    _columns = {
        "expense_alert" : fields.boolean("Expense Alert", help="Expense alert should be done"),
        "expense_alert_date" : fields.date("Alert Date"),
        "expense_alert_line_ids" : fields.function(_expense_alert_line_ids, type="many2many", obj="account.analytic.line", string="Expense Alert Lines")
    }
    
    def _expense_alert(self, cr, uid, context=None):
        alert_date = context and context.get("alert_date") or util.lastDay()
       
        # env
        email_obj = self.pool["email.template"]
        data_obj = self.pool["ir.model.data"]
        template_id = data_obj.xmlid_to_res_id(cr, uid, "expenses_alert.email_template_expense_alert", raise_if_not_found=True)
          
        # query alerts
        cr.execute("SELECT a.id FROM account_analytic_account a " 
                    "      INNER JOIN account_analytic_line al ON al.account_id=a.id " 
                    "             AND ( (a.expense_alert_date IS NULL AND al.date=%s) " 
                    "                OR (a.expense_alert_date IS NOT NULL AND al.date > a.expense_alert_date AND al.date<=%s) ) "
                    "      INNER JOIN resource_resource r ON r.user_id = al.user_id "      
                    "      INNER JOIN hr_employee e ON e.resource_id = r.id AND e.journal_id = al.journal_id "  
                    "      WHERE a.expense_alert AND NOT a.partner_id IS NULL AND (al.to_invoice IS NOT NULL OR a.to_invoice IS NULL)" 
                    "      GROUP BY 1 ",
                   (alert_date, alert_date))
        
        # send alerts
        report_ctx = context and dict(context) or {}
        report_ctx["alert_date"] = alert_date
        for (account_id, ) in cr.fetchall():
            _logger.debug("Sending expense alert for account %s" % account_id)
            email_obj.send_mail(cr, uid, template_id, account_id, force_send=True, context=report_ctx)
            self.write(cr, uid, [account_id], {"expense_alert_date" : alert_date}, context=context) 
    
        return True
