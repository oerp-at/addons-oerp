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
    "name" : "oerp.at UBL Invoice",
    "description":"""
Universal Business Language Support
===================================

* Supports sending invoice
* XML Reports with UBL 2.1

""",
    "version" : "1.0",
    "author" :  "oerp.at",
    "category" : "EDI",
    "depends" : ["ubl_base",
                 "at_account",
                 "account"],
    "data" : ["wizard/ubl_transfer_wizard.xml",
              "view/invoice_view.xml",
              "view/ubl_profile.xml"],
    "auto_install" : False,
    "installable": True
}
