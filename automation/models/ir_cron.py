from odoo import fields, models


class IrCron(models.Model):
    _inherit = "ir.cron"
    _order = "priority, name"

    task_id = fields.Many2one("automation.task", "Task", ondelete="cascade", readonly=True)
