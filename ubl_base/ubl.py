# -*- coding: utf-8 -*-
# -*- encoding: utf-8 -*-

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

from openerp.osv import fields,osv
from openerp.tools.translate import _

class ubl_profile(osv.osv):
    
    def _get_ubl(self, cr, uid, context=None):
        profile_id = self.search_id(cr, uid, [], 0, context=context)
        if profile_id:
            return self.browse(cr, uid, profile_id, context=context)
        return None
    
    _name = "ubl.profile"
    _decription = "UBL Profile"
    _columns = {
        "name" : fields.char("Name"),        
        "code" : fields.char("ID",select=True),
        "ubl_ref" : fields.char("UBL Reference Pattern", help="A Python evaluated string.\n"
                                                             "* 'partner' browseable passed as global variable\n"
                                                             "* 'invoice' browseable passed as global variable\n"
                                                             "* 'profile' browseable passed as global variable\n"),
        "ws_type_id" : fields.many2one("ubl.ws.type", "Webservice Type"),
        "ws_user" : fields.char("Webservice User"),
        "ws_password" : fields.char("Webservice Password"),
        "uom_ids" : fields.one2many("ubl.uom", "profile_id", "UBL Unit of Measures"),
        "partner_rule_ids" : fields.one2many("ubl.rule.partner", "profile_id", "Partner Rules")
    }


class ubl_rule_partner(osv.osv):
    
    def _get_rule(self, cr, uid, profile_id, partner_id, context=None):
        partner = self.pool.get("res.partner").browse(cr, uid, partner_id, context=context)
        if not partner:
            return None
        
        state = partner.state_id
        if not state:
            return None
        
        rule_id = self.search_id(cr, uid, [("profile_id","=",profile_id),("state_id","=",state.id)])
        if rule_id:
            return self.browse(cr, uid, rule_id, context=context)
        return None
    
    _name = "ubl.rule.partner"
    _decription = "UBL Partner Rule"
    _columns = {
        "profile_id" : fields.many2one("ubl.profile", "Profile", required=True, select=True),
        "name" : fields.many2one("res.partner","Partner", required=True, select=True),
        "state_id" : fields.many2one("res.country.state","State", select=True),
        "no_delivery_address" : fields.boolean("No Delivery Address")
    }    


class ubl_uom(osv.osv):
    _name = "ubl.uom"
    _description = "UBL Unit of Measures"
    _columns = {                
        "profile_id" : fields.many2one("ubl.profile","Profile", required=True, select=True),
        "uom_id" : fields.many2one("product.uom", "Unit of Measure", select=True),
        "name" : fields.char("Name", select=True)         
    }


class ubl_ws_type(osv.osv):
    _name = "ubl.ws.type"
    _description = "UBL WebService Type"
    _columns = {
        "name" : fields.char("Name"),
        "code" : fields.char("Code")        
    }
