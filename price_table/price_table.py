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

class price_table(models.Model):
    _name = "price.table"
    _description = "Price Table"
    
    name = fields.Char("Name", required=True)
    line_ids = fields.One2many("price.table.line", "table_id", "Lines")
    version_id = fields.Many2one("product.pricelist.version", "Version", required=True)
    
    @api.one
    def _import_version(self, version):
        version_obj = self.env["product.pricelist.version"]
        pricelist_view = version_obj._pricelist_view(version)
        
        seq = 1
        products = {}
        lines = []
        
        for category_val in pricelist_view["categories"]:
            for product_val in category_val["products"]:
                product = product_val["product"]
                values = {
                    "product_id" : product.id,
                    "sequence" : seq,
                    "price" : product_val["price"]
                }
                products[product.id] = values
                seq += 1
                
        for line in self.line_ids:
            values = products.pop(line.product_id.id,None)
            if values:
                lines.append((1,line.id,values))
            
        for value in products.values():
            lines.append((0,0,value))
        
        self.write({
            "line_ids" : lines
        })
    
    @api.one
    def _build_pricelist(self):
        version = self.version_id
        pricelist = version.pricelist_id
    
        price_type_obj = self.env["product.price.type"]
        product_price_types = None
        if pricelist.type == "purchase":
            product_price_types =  price_type_obj.search([("field","=","standard_price")])
        elif pricelist.type == "sale":
            product_price_types =  price_type_obj.search([("field","=","list_price")])
        
        base = product_price_types and product_price_types[0].id or -1
                   
        # create price entries per product
        products = {}
        seq = 1
        for line in self.line_ids:
            vline = {
              "name" : line.product_id.name,
              "product_id" : line.product_id.id,
              "base" : base,
              "price_discount" : -1,
              "price_surcharge" : line.price,
              "sequence" : seq                          
            }
            products[line.product_id.id] = vline
            seq+=1
            
        # create update
        version_values = []
        for vline in version.items_id:
            if vline.product_id:
                try:
                  values = products.pop(vline.product_id.id)
                  # update
                  if values:
                      version_values.append((1,vline.id,values))
                except KeyError:
                  # remove                                
                  version_values.append((2,vline.id))        
        
        # insert new values         
        for values in products.values():
            version_values.append((0,0,values))
            
        # update price list
        
        pricelist_update = {
           "version_id" : [(1,version.id, {
                            "name" : self.name,
                            "items_id" : version_values            
                          })]
        }
        
        version.pricelist_id.write(pricelist_update)
        
    @api.multi
    def action_publish(self):
        for o in self:
            o._build_pricelist()
            
    @api.multi
    def action_import(self):
        for o in self:
            o._import_version(o.version_id)
        

class price_table_line(models.Model):
    _name = "price.table.line"
    _description = "Price Table Line"
    _rec_name = "product_id"
    _order = "category_id, sequence"
    
    table_id = fields.Many2one("price.table","Price Table")
    sequence = fields.Integer("Sequence")
    category_id = fields.Many2one("product.category","Category",compute="_compute_category", store=True)
    product_id = fields.Many2one("product.product", "Product", required=True)
    price = fields.Float("Price")
    
    @api.one
    @api.depends("product_id")
    def _compute_category(self):
        self.category_id = self.product_id.categ_id.id