from odoo import models


class AutomationTaskExample(models.Model):
    _name = 'automation.task.example'
    _description = 'Automation Task Example'
    _inherit = "automation.task.mixin"
