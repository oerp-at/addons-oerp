from odoo import fields, models
from .automation_task import _list_all_models


class AutomationTaskLog(models.Model):
    _name = 'automation.task.log'
    _description = 'Task Log'
    _order = 'id asc'
    _rec_name = 'create_date'

    task_id = fields.Many2one(
        'automation.task',
        'Task',
        required=True,
        readonly=True,
        index=True,
        ondelete='cascade',
    )
    stage_id = fields.Many2one(
        'automation.task.stage',
        'Stage',
        required=True,
        readonly=True,
        index=True,
        ondelete='cascade',
    )

    pri = fields.Selection(
        [
            ('x', 'Emergency'),
            ('a', 'Alert'),
            ('e', 'Error'),
            ('w', 'Warning'),
            ('n', 'Notice'),
            ('i', 'Info'),
            ('d', 'Debug'),
        ],
        string='Priority',
        default='i',
        index=True,
        required=True,
        readonly=True,
    )

    message = fields.Text(readonly=True)
    ref = fields.Reference(_list_all_models, readonly=True, index=True)
    safe_ref = fields.Reference(
        _list_all_models, string='Reference', compute='_compute_safe_ref', store=False,
        readonly=True)
    code = fields.Char(index=True, readonly=True)
    data = fields.Json(readonly=True)

    def _compute_safe_ref(self):
        ids = self.ids
        cr = self.env.cr
        if ids:
            objs = dict([(o.id, o) for o in self])
            cr.execute('SELECT id, ref FROM automation_task_log WHERE id IN %s', (tuple(ids),))
            for obj_id, ref in cr.fetchall():
                ref_obj = None
                if ref:
                    res_model, res_id = ref.split(',')
                    ref_obj = self.env[res_model].browse(int(res_id))
                    if not ref_obj.exists():
                        ref_obj = None
                objs[obj_id]['safe_ref'] = ref_obj
