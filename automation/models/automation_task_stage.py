import uuid

from odoo import fields, models
from .automation_task import _list_all_models


class AutomationTaskStage(models.Model):
    _name = 'automation.task.stage'
    _description = 'Task Stage'
    _order = 'id asc'
    _rec_name = 'complete_name'

    complete_name = fields.Char('Title', compute='_compute_name')
    complete_progress = fields.Float('Process %', readonly=True, compute='_compute_progress')

    name = fields.Char(readonly=True, required=True)
    progress = fields.Float('Progress %', readonly=True)
    status = fields.Char()

    task_id = fields.Many2one(
        'automation.task',
        'Task',
        readonly=True,
        index=True,
        required=True,
        ondelete='cascade',
    )
    parent_id = fields.Many2one('automation.task.stage', 'Parent Stage', readonly=True, index=True)
    total = fields.Integer(readonly=True)

    child_ids = fields.One2many('automation.task.stage', 'parent_id', string='Substages', copy=False)

    def _compute_name(self):
        exclude_root = self._context.get('display_exclude_root')
        for obj in self:
            name = []
            stage = obj
            while stage:
                if not exclude_root or stage.parent_id:
                    name.append(stage.name)
                stage = stage.parent_id
            complete_name = ' / '.join(reversed(name)) or '/'
            obj.complete_name = complete_name

    def _get_progress(self):
        self.ensure_one()
        progress = self.progress

        # if there is progress
        # return the progress
        if progress > 0:
            return min(progress, 100.0)

        # otherwise, return the overall progress
        # for the childs
        childs = self.child_ids
        total = 1.0 / (max(self.total, len(childs)) or 1)
        for child in childs:
            progress += (child._get_progress() * total)
        return min(round(progress), 100.0)

    def _compute_progress(self):
        for obj in self:
            obj.complete_progress = obj._get_progress()


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


class TaskToken(models.Model):
    _name = 'automation.task.token'
    _description = 'Task Token'
    _rec_name = 'task_id'

    task_id = fields.Many2one('automation.task', 'Task', required=True, ondelete='cascade', index=True)
    token = fields.Char(required=True, default=lambda self: str(uuid.uuid4()), index=True)
