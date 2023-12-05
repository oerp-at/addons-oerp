# -*- coding: utf-8 -*--
# License LGPL-3 or later (http://www.gnu.org/licenses/lgpl).

from odoo import api, fields, models


class TransSyncTask(models.Model):
    _name = 'automation.task.sample'
    _description = 'Automation Task Sample'
    _inherit = "automation.task.mixin"