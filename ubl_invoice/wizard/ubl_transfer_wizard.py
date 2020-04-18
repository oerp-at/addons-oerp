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

from StringIO import StringIO
import base64

from openerp.osv import fields, osv
from openerp.tools.translate import _
from openerp.addons.at_base import util
from openerp.addons.at_base import tuple2xml

from openerp.tools.safe_eval import safe_eval

class ubl_transfer_wizard(osv.osv_memory):
    
    def _get_partner(self, cr, uid, invoice, context=None):
        return invoice.partner_id
    
    def _get_invoice_partner(self, cr, uid, invoice, context=None):
        return invoice.partner_id
    
    def default_get(self, cr, uid, fields_list, context=None):
        res = super(ubl_transfer_wizard, self).default_get(cr, uid, fields_list, context)
        invoice_obj = self.pool.get("account.invoice")
        partner_rule_obj = self.pool.get("ubl.rule.partner")
                
        active_ids = util.active_ids(context, "account.invoice")        
        if active_ids:               
            invoice = invoice_obj.browse(cr, uid, active_ids[0], context)
        if invoice:
            # create invoice report          
            report = self.pool["ir.actions.report.xml"]._lookup_report(cr, "account.report_invoice")
            if report:
                report_context = context.copy()
                report_context["report_title"]=invoice.number
                report.create(cr, uid, [invoice.id], {"model": "account.invoice"}, report_context)
                   
            if "invoice_id" in fields_list:
                res["invoice_id"]=invoice.id        
                if "att_ids" in fields_list:
                    attach_obj = self.pool.get("ir.attachment")
                    attach_ids = attach_obj.search(cr, uid, [("res_model","=","account.invoice"),("res_id","=",invoice.id)])
                    res["att_ids"] = attach_ids
                
            if "profile_id" in fields_list:
                ubl_profile = invoice_obj._ubl_profile(cr, uid, invoice, context)
                if ubl_profile:
                    res["profile_id"] = ubl_profile.id
                    res["ubl_action"] = "sent"
                    
                    no_delivery_address = False
                    partner = self._get_partner(cr, uid, invoice, context=context)
                    rule = partner_rule_obj._get_rule(cr, uid, ubl_profile.id, partner.id)

                    invoice_partner = self._get_invoice_partner(cr, uid, invoice, context=context)
                    if rule and rule.name:
                        invoice_partner = rule.name
                        
                    if "partner_id" in fields_list:
                        if invoice_partner:
                            res["partner_id"] = invoice_partner.id
                    if "no_delivery_address" in fields_list:
                        if rule:                            
                            no_delivery_address = rule.no_delivery_address         
                            res["no_delivery_address"] = no_delivery_address               
                    if "ubl_ref" in fields_list:
                        if invoice.ubl_ref:
                            res["ubl_ref"] = invoice.ubl_ref  
                        elif ubl_profile.ubl_ref:                            
                            res["ubl_ref"] = safe_eval(ubl_profile.ubl_ref, locals_dict={ "partner" : partner, "invoice" : invoice, "profile" : ubl_profile } ) or invoice.number
            
                    if "xml_data" in fields_list:               
                        res["xml_data"] = self._get_xml_data(cr, uid, invoice, res.get("partner_id"), res.get("ubl_ref"), no_delivery_address, ubl_profile, context)
                 
                    
        return res
    
    def _get_xml_data(self, cr, uid, invoice, customer_id, ubl_ref, no_delivery_address, profile=None, context=None):
        invoice_obj = self.pool.get("account.invoice")
        inv_context = context and dict(context) or {}
        inv_context["customer_id"]=customer_id
        inv_context["ubl_ref"]=ubl_ref
        inv_context["no_delivery_address"]=no_delivery_address
        ubl = invoice_obj._ubl_invoice(cr, uid, invoice, profile=profile, context=inv_context)
        return base64.encodestring(tuple2xml.translate(StringIO(), ubl).getvalue())
    
    def _send_invoice(self, cr, uid, wizard, context=None):
        self.pool["account.invoice"].write(cr, uid, wizard.invoice_id.id, {"ubl_status" : "sent"}, context=context)            
        return True
        
    def action_ok(self, cr, uid, ids, context=None):
        invoice_obj = self.pool.get("account.invoice")
        for wizard in self.browse(cr, uid, ids, context):
            self.write(cr, uid, [wizard.id], {"xml_data" : self._get_xml_data(cr, uid, wizard.invoice_id, wizard.partner_id.id, wizard.ubl_ref, wizard.no_delivery_address, wizard.profile_id, context)}, context)
            invoice_obj.write(cr, uid, wizard.invoice_id.id, {"ubl_ref": wizard.ubl_ref, "ubl_status": wizard.ubl_action}, context=context)
        return { "type" : "ir.actions.act_window_close" }
        
    def action_transfer(self, cr, uid, ids, context=None):
        self.action_ok(cr, uid, ids, context)
        for wizard in self.browse(cr, uid, ids, context):
            if not wizard.profile_id.ws_type_id:
                raise osv.except_osv(_("Error"), _("No webservice defined for sending the invoice"))
            self._send_invoice(cr, uid, wizard, context)
            self.pool["account.invoice"].message_post(cr, uid, wizard.invoice_id.id, context=context, 
                                                      body=_("UBL Invoice %s with reference %s transfered") % (wizard.invoice_id.number or "", wizard.ubl_ref))
        return { "type" : "ir.actions.act_window_close" }
    
    _name = "ubl.transfer.wizard"
    _description = "Transfer Wizard"
    _columns = {
        "ubl_action" : fields.selection([("prepare","Prepare"),
                                         ("sent","Send"),
                                         ("except","Except")], string="Action", required=True),
        "xml_data" : fields.binary("XML Data"),
        "invoice_id" : fields.many2one("account.invoice","Invoice",required=True),
        "profile_id" : fields.many2one("ubl.profile","UBL Profile",required=True),
        "partner_id" : fields.many2one("res.partner","Partner",required=True),
        "att_ids" : fields.many2many("ir.attachment", "ubl_transfer_wizard_att_rel", "wizard_id", "att_id", string="Attachments"),
        "no_delivery_address" : fields.boolean("No Delivery Address"),
        "ubl_ref" : fields.char("UBL Reference"),
        "email" : fields.char("E-Mail"),
        "test" : fields.boolean("Test")
    }    
