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
    "name" : "oerp.at Expenses Alert",
    "summary" : "Expenses alert for analytic accounts",
    "description":"""
Expenses Alert
==============
Adds an option for automatically send an email to the customer,
after an time expense for the analytic account happens
""",
    "version" : "1.0",
    "author" :  "oerp.at",
    "website" : "http://oerp.at",
    "category" : "Sales Management/Project Management",
    "depends" : ["at_project_sale","account_analytic_analysis","analytic"],
    "data" : [
        "view/account_analytic_view.xml",
        "data/expense_alert_email_template.xml",
        "data/expense_alert_cron.xml"
    ],
    "auto_install" : False,
    "installable": True
}