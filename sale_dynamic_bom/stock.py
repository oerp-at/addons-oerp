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

class stock_location(osv.Model):
  _inherit = "stock.location"
  _columns = {
    "dynbom" : fields.boolean("Dynamic Production", help="Location for dynamic BoM production")
  }
  

class stock_move(osv.Model):
  _inherit = "stock.move"
  
  def action_done(self, cr, uid, ids, context=None):
    res = super(stock_move, self).action_done(cr, uid, ids, context=context)
    
    cr.execute("SELECT l.id FROM stock_move m "
               " INNER JOIN stock_location l ON l.id = m.location_dest_id AND l.dynbom "
               " WHERE m.id IN %s ", (tuple(ids),))
    
    dynbom_location_ids = [r[0] for r in cr.fetchall()]
    if dynbom_location_ids:
      production_obj = self.pool["mrp.production"]
      dynbom_production_ids = production_obj.search(cr, uid, 
            [("location_src_id","in",dynbom_location_ids),
             ("state","=","confirmed")], context=context)
          
      if dynbom_production_ids:
        # assign again
        production_obj.action_assign(cr, uid, dynbom_production_ids, context=context)
    
    return res
  
  
class stock_picking(osv.Model):
  _inherit = "stock.picking"
  
  def _invoice_create_line(self, cr, uid, moves, journal_id, inv_type='out_invoice', context=None):
    forward_moves = []
    invoice_ids = []
    sale_obj = self.pool["sale.order"]
    move_obj = self.pool["stock.move"]
    for move in moves:
      if move.product_id.dynbom:
        # check if to invoice
        if move.invoice_state == "2binvoiced":
          procurement = move.procurement_id
          if procurement and procurement.sale_line_id:
            sale_order = procurement.sale_line_id.order_id
            invoice_id = sale_obj.action_invoice_create(cr, uid, [sale_order.id], grouped=True, context=context)
            if invoice_id:
              invoice_ids.append(invoice_id)
              move_obj.write(cr, uid, move.id, {"invoice_state": "invoiced"}, context=context)
          else:
            forward_moves.append(move)
      else:
        forward_moves.append(move)
    
    res = invoice_ids.extend(super(stock_picking, self)._invoice_create_line(cr, uid, forward_moves, journal_id, inv_type=inv_type, context=context))
    if res:
      invoice_ids.extend(res)
    return invoice_ids
    
    