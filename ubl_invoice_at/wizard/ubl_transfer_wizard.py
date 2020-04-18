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


from suds.client import Client
from suds.wsse import *
import os

from openerp.osv import fields, osv
from openerp.tools.translate import _
from openerp.exceptions import Warning

#import logging
#__logger__ = logging.getLogger(__name__)

class ubl_transfer_wizard(osv.osv_memory):
    
    def _send_invoice(self, cr, uid, wizard, context=None):
        if wizard.profile_id.ws_type_id.code == "usp.gv.at":
            if wizard.invoice_id.state in ("draft","cancel"):
                raise Warning(_("Invoice is in draft or cancel state"))
            
            # prepare client
            wsdl_file = "file:%s/erb-invoicedelivery-200.wsdl" % os.path.dirname(__file__) 
            client = Client(wsdl_file)
            security = Security()
            token = UsernameToken(wizard.profile_id.ws_user,wizard.profile_id.ws_password)
            security.tokens.append(token)
            client.set_options(wsse=security)
            
            #settings
            settings =  client.factory.create("DeliverySettingsType")
            settings.test = wizard.test
            
            if wizard.email:
                settings.EmailSettings.AlternateResponseEmail = [wizard.email]
                settings.EmailSettings.SubjectPrefix = _("Invoice %s Transfer ") % wizard.invoice_id.number
            
            #invoice
            invoice = client.factory.create("DeliveryInvoiceType")
            invoice.value = wizard.xml_data
            
            # attachments
            embedded_attachments = []
            for attach in wizard.att_ids:
                embedded_attachment = client.factory.create("DeliveryEmbeddedAttachmentType")
                embedded_attachment.value = attach.datas
                embedded_attachment._name = attach.datas_fname or attach.name 
                embedded_attachments.append(embedded_attachment)
            
            #deliver invoice
            res = None
            try:
                res = client.service.deliverInvoice(invoice,embedded_attachments)
            except Exception,e:
                if hasattr(e, "message"):
                    if e.message == "syntax error":
                        raise Warning(_("Invalid Login"))
                    else:
                        raise Warning(e.message)
                else:
                    raise e
            
            #handle error
            error = res and hasattr(res,"Error") and res.Error or None
            error_messages = []
            if error:
                for detail in error.ErrorDetail:
                    if hasattr(detail,"ErrorCode"):
                        error_messages.append("Error Code: %s\nField: %s\nMessage: %s" % (detail.ErrorCode,detail.Field,detail.Message))
                    elif hasattr(detail,"Field"):
                        error_messages.append("Field: %s\nMessage: %s" % (detail.Field,detail.Message))
                    elif hasattr(detail,"Message"):
                        error_messages.append(detail.Message)    
            
            if error_messages:
                raise Warning("\n\n".join(error_messages))
                
        return super(ubl_transfer_wizard, self)._send_invoice(cr, uid, wizard=wizard, context=context)
                        
    
    _inherit = "ubl.transfer.wizard"    
    _name = "ubl.transfer.wizard"
