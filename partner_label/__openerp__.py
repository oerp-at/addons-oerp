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
    "name" : "oerp.at Partner Label",
    "summary" : "Partner mail label report",
    "description":"""
Partner Label
=============

* adds an report for printing partner mail labels

""",
    "version" : "1.0",
    "author" :  "oerp.at",
    "website" : "http://oerp.at",
    "category" : "Sales",
    "depends" : ["at_base"],
    "data" : ["report/partner_label_report.xml"],
    "auto_install" : False,
    "installable": True
}