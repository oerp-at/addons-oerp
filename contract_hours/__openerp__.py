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
    "name" : "oerp.at Contract Hours",
    "summary" : "Define contract hours per month",
    "description":"""
Contract Hours
==============

* Adds a field for defining the hours per month on an analytic contract
* Adds a function field to show the used hours per year
 
    """,
    "version" : "1.0",
    "author" :  "oerp.at",
    "website" : "http://oerp.at",
    "category" : "Contracts Management",
    "depends" : ["project_timesheet","analytic","account_analytic_analysis","at_project_sale"],
    "data" : ["view/account_analytic_analysis_view.xml",
              "view/project_view.xml"],
    "auto_install" : False,
    "installable": True
}