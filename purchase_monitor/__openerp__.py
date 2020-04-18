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

{
    "name" : "Purchase Monitor",
    "summary" : "Send an email if no answer to pruchase was received",
    "description":"""
Purchase Monitor
================

* Sends an E-Mail if there exist no purchase confirmation 

    """,
    "version" : "1.0",
    "author" :  "oerp.at",
    "website" : "http://oerp.at",
    "category" : "Purchase",
    "depends" : ["at_base","purchase"],
    "data" : ["view/purchase_view.xml",
              "data/cron.xml",
              "data/group.xml"],
    "auto_install" : False,
    "installable": True
}