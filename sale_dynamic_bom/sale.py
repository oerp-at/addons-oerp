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
from openerp.exceptions import Warning
from openerp.tools.translate import _
from openerp import SUPERUSER_ID

from openerp.addons.at_base import format

class sale_order(osv.Model):
  _inherit = "sale.order"
  _columns = {
    "dynbom_location_id": fields.many2one("stock.location", "Production Location", readonly=True)
  }
   

  def _prepare_order_line_procurement(self, cr, uid, order, line, group_id=False, context=None):
    vals = super(sale_order, self)._prepare_order_line_procurement(cr, uid, order, line, group_id=group_id, context=context)    
    if order.dynbom_location_id:
      product = line.product_id
      if product:
        if product.dynbom:
          f = format.LangFormat(cr, uid, context=context, dp="Product UoS")
          name = vals.get("name") or ""
          line_names = []
          for mat_line in order.order_line:                    
            if mat_line.id != line.id:
              uom = mat_line.product_uos or mat_line.product_uom
              line_names.append("%s x %s %s" % (f.formatLang(mat_line.product_uos_qty),
                                          uom.name, 
                                          mat_line.name))
            
          if line_names:
            name = "%s\n\n%s\n\n" % (name,"\n\n".join(line_names))
            vals["name"] = name  
              
        else:
          vals["location_id"] = order.dynbom_location_id.id
          parent_loc = order.dynbom_location_id.location_id
          partner = parent_loc.partner_id
          if not partner:
            partner = parent_loc.company_id.partner_id
          vals["partner_dest_id"] = partner.id
          
    return vals
   
  def action_ship_create(self, cr, uid, ids, context=None):
    # search place for dynamic production
    location_obj = self.pool["stock.location"]
    production_obj = self.pool["mrp.production"]
    order_obj = self.pool["sale.order"]
    for order in self.browse(cr, uid, ids, context=context):
      dynbom_line = None
      for line in order.order_line:
        if line.product_id and line.product_id.dynbom:
          if dynbom_line:
            raise Warning(_("Only one dynamic production could added to sale order"))
          dynbom_line = line
      
      if dynbom_line:
        warehouse = order.warehouse_id
        location_ids = location_obj.search(cr, SUPERUSER_ID, [("usage","=","internal"),("id","child_of",warehouse.id),("dynbom","=",True)])
        available_location_id = None
        for location_id in location_ids:
          production_ids = production_obj.search(cr, SUPERUSER_ID, 
                                                 [("location_src_id","=",location_id),
                                                  ("state","in",["confirmed", 
                                                                 "ready", 
                                                                 "in_production"])], limit=1, context=context)
          
          if not production_ids:
            available_location_id = location_id
            break
          
        if not available_location_id:
          raise Warning(_("There is no free location for production"))
          
        order_obj.write(cr, uid, order.id, {
          "dynbom_location_id": available_location_id
        })
          
    return super(sale_order, self).action_ship_create(cr, uid, ids, context=context)