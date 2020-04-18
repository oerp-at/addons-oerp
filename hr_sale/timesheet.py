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
from openerp.addons.at_base import util
import openerp.addons.decimal_precision as dp

class hr_timesheet_sheet(osv.Model):
    
    def _service_sale(self, cr, uid, date_from, date_to, context=None):
        res = 0.0
        line_obj = self.pool["account.analytic.line"]
        pricelist_obj = self.pool["product.pricelist"]
        order_stats = {}
        
        def get_total(line):
            product = line.product_id
            pricelist = account.pricelist_id
            price = product.list_price
            hours = line.unit_amount
            partner = account.partner_id
            
            if pricelist:
                price = pricelist_obj.price_get(cr, uid, 
                                                [pricelist.id], 
                                                product.id, 
                                                partner and partner.id or None,  
                                                {"date":line.date})[pricelist.id]
            to_invoice = line.to_invoice
            discount = to_invoice and to_invoice.factor or 0.0
            line_total = price*hours*(1.0-(discount/100.0))
            return line_total
       
        
        cr.execute("SELECT l.id FROM hr_analytic_timesheet tl "
                   " INNER JOIN account_analytic_line l ON l.id = tl.line_id "
                   " WHERE l.unit_amount > 0 AND l.product_id IS NOT NULL AND l.user_id = %s AND l.date >= %s AND l.date <= %s ", (uid, date_from, date_to))
        
          
        
        for line in line_obj.browse(cr, uid, [r[0] for r in cr.fetchall()], context=context):
            account = line.account_id
            order = account.order_id            
            
            line_total = 0.0     

            if line.to_invoice:
                line_total = get_total(line)
            elif order and not order.state in ("cancel","draft","sent"):
                line_total = get_total(line)
                
                # get sold hours
                sold_hours = 0.0
                if not order.id in order_stats:
                    for oline in order.order_line:
                        oprod = oline.product_id
                        if oprod and oprod.type == "service":
                            sold_hours += (oline.price_unit*oline.product_uom_qty*(1.0-oline.discount))
                    
                    # search all other analytic lines and correct stat                           
                    cr.execute("SELECT l.id FROM hr_analytic_timesheet tl "
                              " INNER JOIN account_analytic_line l ON l.id = tl.line_id "
                              " WHERE l.account_id = %s " 
                              "   AND l.product_id IS NOT NULL "
                              "   AND ( (l.date <= %s AND l.user_id != %s) OR (l.date < %s AND l.user_id = %s) ) ", (account.id, date_to, uid, date_from, uid))
                    
                    
                    for line2 in line_obj.browse(cr, uid, [r[0] for r in cr.fetchall()], context=context):
                        line2_total = get_total(line2)   
                        sold_hours -= line2_total  
                        
                else:
                    sold_hours = order_stats.get(order.id,0.0)

                # correct line total                
                if sold_hours <= 0.0:
                    line_total = 0
                else:
                    sold_hours -= line_total
                    if sold_hours < 0.0:
                        line_total -= min(line_total,abs(sold_hours))
                        
                order_stats[order.id] = sold_hours
       
            # sumup
            res += line_total
            
        return res
    
    def _total_service_sale(self, cr, uid, ids, field_name, arg, context=None):
        res = dict.fromkeys(ids)
        for sheet in self.browse(cr, uid, ids, context):
            user = sheet.user_id
            if user:
                res[sheet.id]=self._service_sale(cr, user.id, sheet.date_from, sheet.date_to, context=context)
        return res
    
    _inherit = "hr_timesheet_sheet.sheet"
    _columns = {
        "total_service_sale" : fields.function(_total_service_sale, type="float", digits_compute=dp.get_precision("Account"), string="Total Service Sale"),
        "currency_id": fields.related("company_id", "currency_id", type="many2one", relation="res.currency", string="Currency", readonly=True)
    }
    

class hr_timesheet_sheet_sheet_day(osv.Model):
    
    def _total_service_sale(self, cr, uid, ids, field_name, arg, context=None):        
        res = dict.fromkeys(ids)
        time_obj = self.pool["hr_timesheet_sheet.sheet"]
        for sheet_day in self.browse(cr, uid, ids, context):
            sheet = sheet_day.sheet_id
            res[sheet_day.id]=time_obj._service_sale(cr, sheet.user_id.id, sheet_day.name, sheet_day.name, context=context)
        return res
    
    _inherit = "hr_timesheet_sheet.sheet.day"
    _columns = {
        "total_service_sale" : fields.function(_total_service_sale, type="float", digits_compute=dp.get_precision("Account"), string="Service Sale")
    }
    