from odoo import api, fields, models


class AutomationTaskMixin(models.AbstractModel):
    _name = 'automation.task.mixin'
    _description = 'Automation Task Proxy'
    _inherits = {'automation.task': 'task_id'}

    task_id = fields.Many2one('automation.task', 'Task', required=True, index=True, ondelete='cascade')

    @api.model_create_multi
    @api.returns('self', lambda value: value.id)
    def create(self, vals_list):
        tasks = super(AutomationTaskMixin, self).create(vals_list)
        for task in tasks:
            task.res_model = self._name
            task.res_id = task.id
        return tasks

    def unlink(self):
        # search inherited
        ids = self.ids
        task_ids = None
        if ids:
            self._cr.execute(f'SELECT task_id FROM {self._table} WHERE id IN %s AND task_id IS NOT NULL', (tuple(ids),))
            task_ids = [r[0] for r in self._cr.fetchall()]

        # unlink self
        res = super(AutomationTaskMixin, self).unlink()

        # unlink inherited
        if ids and task_ids:
            self.env['automation.task'].browse(task_ids).unlink()

        return res

    def action_queue(self):
        return self.task_id.action_queue()

    def action_restart(self):
        return self.task_id.action_restart()

    def action_cancel(self):
        return self.task_id.action_cancel()

    def action_refresh(self):
        return self.task_id.action_refresh()

    def action_reset(self):
        return self.task_id.action_reset()

    def action_stage(self):
        return self.task_id.action_stage()

    def action_log(self):
        return self.task_id.action_log()

    def action_warning(self):
        return self.task_id.action_warning()

    def action_error(self):
        return self.task_id.action_error()

    def _test_task(self):
        return self.task_id._test_task()

    def _run(self, taskc):
        """ Test Task """
        pass
