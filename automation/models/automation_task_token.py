import uuid

from odoo import fields, models


class TaskToken(models.Model):
    _name = 'automation.task.token'
    _description = 'Task Token'
    _rec_name = 'task_id'

    task_id = fields.Many2one('automation.task', 'Task', required=True, ondelete='cascade', index=True)
    token = fields.Char(required=True, default=lambda self: str(uuid.uuid4()), index=True)
