from odoo import fields, models


class IrActionsServer(models.Model):
    _inherit = "ir.actions.server"

    state = fields.Selection(selection_add=[("task", "Automation Task")], ondelete={"task": "cascade"})
    task_id = fields.Many2one("automation.task", "Task", ondelete="cascade", readonly=True)

    def _run_action_task_multi(self, eval_context):
        for act in self:
            act.task_id._process_task()
        return False
