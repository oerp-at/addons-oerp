from odoo import fields, models


class IrCron(models.Model):
    _inherit = "ir.cron"
    _order = "priority, name"

    task_id = fields.Many2one("automation.task", "Task", store=False, readonly=True, compute="_compute_task_id")

    def _compute_task_id(self):
        tasks = self.env['automation.task'].search([('cron_id', 'in', self.ids)])
        task_by_cron_id = {task.cron_id.id: task.id for task in tasks}
        for cron in self:
            cron.task_id = task_by_cron_id.get(cron.id)
