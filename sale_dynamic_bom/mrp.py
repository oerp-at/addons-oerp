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

class mrp_bom(osv.Model):
  _inherit = "mrp.bom"
  _columns = {
      "sale_order_bom" : fields.boolean("Sale Order is BoM")
  }
    
    
class mrp_production(osv.Model):
  _inherit = "mrp.production"
  
  def action_confirm(self, cr, uid, ids, context=None):
    # create dynamic bom if it should be created 
    procurement_obj = self.pool["procurement.order"]
    for production in self.browse(cr, uid, ids, context=context):
      procurement_ids = procurement_obj.search(cr, uid, [("production_id","=",production.id)])
      if procurement_ids:
        procurement = procurement_obj.browse(cr, uid, procurement_ids[0], context=context)
        if production:
          sale_order_line = procurement.sale_line_id
          if sale_order_line:      
            # check dynamic bom product
            product = sale_order_line.product_id
            if product and product.dynbom:
              
              # check dynamic bom order
              order = sale_order_line.order_id
              if order.dynbom_location_id:
                prod_obj = self.pool["mrp.production"]
                prod_line_obj = self.pool["mrp.production.product.line"]
                  
                # update src 
                prod_obj.write(cr, uid, production.id, 
                               { "location_src_id": order.dynbom_location_id.id }, context=context)
                
                # add production line
                for line in order.order_line:              
                  product = line.product_id              
                  if line.id != sale_order_line.id:                
                      prod_line_obj.create(cr, uid, {
                          "production_id": production.id,
                          "name": line.name,
                          "product_id": product.id,
                          "product_qty": line.product_uom_qty,
                          "product_uom": line.product_uom.id,
                          "product_uos_qty": line.product_uos_qty,
                          "product_uos": line.product_uos.id
                        }, context=context)    
                      
    return super(mrp_production, self).action_confirm(cr, uid, ids, context=context)
  
  
  def _get_raw_material_procure_method(self, cr, uid, product, location_id=False, location_dest_id=False, context=None):
    """ location for dynbom production is principal make_to_stock """
    if location_id:
      location = self.pool["stock.location"].browse(cr, uid, location_id, context=context)
      if location and location.dynbom:
        return "make_to_stock"
    return super(mrp_bom, self)._get_raw_material_procure_method(cr, uid, product, location_id=location_id, location_dest_id=location_dest_id, context=context)
  
  def _procurement_info(self, cr, uid, ids, field_name, arg, context=None):
    res = dict.fromkeys(ids)
    
    cr.execute("SELECT p.id, po2.name, ol.procurement_note FROM procurement_order po"
                " INNER JOIN mrp_production p ON p.id = po.production_id "
                " INNER JOIN stock_move m ON m.id = po.move_dest_id "
                " INNER JOIN procurement_order po2 ON po2.id = m.procurement_id "
                " LEFT JOIN sale_order_line ol ON ol.id = po2.sale_line_id "
                " WHERE p.id IN %s ", (tuple(ids),))
    
    for production_id, name, note in cr.fetchall():
      if note:
        name = "%s\n\n%s" % (note,name)
      res[production_id] = name
      
    return res
  
  _columns = {
    "procurement_info": fields.function(_procurement_info, type="text", string="Procurement Information")
  }