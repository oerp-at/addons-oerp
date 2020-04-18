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
from openerp.addons.at_base import util

class purchase_order(models.Model):
  _inherit = "purchase.order"
  _track = {
    "recv_confirm": {},
  }
  
  recv_confirm = fields.Boolean("Received Confirmation", states={'done':[('readonly',True)]}, track_visibility='always')
  
  @api.model
  def _check_recv_confirm(self):    
    deadline = util.getDate(days=-4)
    orders = self.search([("state","=","approved"),("recv_confirm","=",False),("date_order","<",deadline)])
    if orders:
      data_obj = self.env["ir.model.data"]     
      monitor_group = self.env["mail.group"].browse(data_obj.xmlid_to_res_id("purchase_monitor.group_purchase_monitor", raise_if_not_found=True))
      
      subject = _("No confirmation for %s orders") % len(orders)
      names = ["<li>%s</li>" % n[1] for n in orders.name_get()]
      body = "<ul>\n%s\n</ul>" % "\n".join(names)
      
      monitor_group.message_post(subject=subject, 
                                body=body,
                                subtype="mt_comment")
      
    return True
      
  