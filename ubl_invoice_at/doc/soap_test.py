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
import base64
import os

if __name__ == '__main__':
    with open('xml_data.xml', 'r') as xml_file:
        xml_data = xml_file.read()
    
    client = Client("file:erb-invoicedelivery-200.wsdl")
    security = Security()
    token = UsernameToken('s000n003n412', '')
    security.tokens.append(token)
    client.set_options(wsse=security)
      
    
    #settings
    settings =  client.factory.create("DeliverySettingsType")
    settings._test = True
    settings.EmailSettings.AlternateResponseEmail = ["martin.reisenhofer@funkring.net"]
    
    #invoice
    invoice = client.factory.create("DeliveryInvoiceType")
    invoice.value = base64.encodestring(xml_data)
   
    attachmentType =  client.factory.create("DeliveryEmbeddedAttachmentType")
    print attachmentType
    print client
    print settings
    
    try:
        res =  client.service.deliverInvoice(invoice)
        error = res and hasattr(res,"Error") and res.Error or None
        error_messages = []        
        if error:
            for detail in error.ErrorDetail:
                if hasattr(detail,"ErrorCode"):
                    error_messages.append("Error Code: %s\nField: %s\nMessage: %s" % (detail.ErrorCode,detail.Field,detail.Message))
                else:
                    error_messages.append("Field: %s\nMessage: %s" % (detail.Field,detail.Message))
        if error_messages:
            print "\n\n".join(error_messages)
    except Exception,e:
        print e.message
    