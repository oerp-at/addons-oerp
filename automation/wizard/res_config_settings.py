from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    automation_task_unqueued_run = fields.Boolean(
        string='Unqueued Run',
        config_parameter='automation.task_unqueued_run',
        default=False,
        help='Allow tasks to run without queueing'
    )
