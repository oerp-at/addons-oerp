# -*- coding: utf-8 -*-

from odoo import http, SUPERUSER_ID
from odoo.http import request
from odoo.api import Environment
from odoo import registry as registry_get


class TaskLogController(http.Controller):
    """ task log controller """

    ALLOWED_FIELDS = {
        'name',
        'progress',
        'status',
        'task_id',
        'stage_id',
        'pri',
        'message',
        'ref',
        'code',
        'data',
        'total',
        'parent_id'
    }

    INT_FIELDS = {
        'task_id',
        'stage_id',
        'total',
        'parent_id'
    }

    def _get_values(self, **kwargs):
        for field in kwargs:
            if field not in self.ALLOWED_FIELDS:
                raise ValueError(f"Field {field} not allowed!")
            if field in self.INT_FIELDS:
                kwargs[field] = int(kwargs[field])
        return kwargs

    def _get_registry(self):
        return registry_get(request.httprequest.headers['X-Automation-DB'])

    @http.route(
        "/automation/log",
        type="http",
        auth="automation_task",
        csrf=False,
        methods=["POST"],
    )
    def log(self, progress=None, **kwargs):
        values = self._get_values(**kwargs)
        registry = self._get_registry()
        with registry.cursor() as cr:
            env = Environment(cr, SUPERUSER_ID, {})

            # check if progress passed
            # .. modify progress
            if progress:
                try:
                    progress = float(progress)
                    env["automation.task.stage"].browse(values["stage_id"]).write(
                        {"progress": progress}
                    )
                except ValueError:
                    pass
            # log
            return str(env["automation.task.log"].create(values).id)

    @http.route(
        "/automation/stage",
        type="http",
        auth="automation_task",
        csrf=False,
        methods=["POST"],
    )
    def stage(self, **kwargs):
        values = self._get_values(**kwargs)
        registry = self._get_registry()
        with registry.cursor() as cr:
            env = Environment(cr, SUPERUSER_ID, {})
            return str(env["automation.task.stage"].create(values).id)

    @http.route(
        "/automation/progress",
        type="http",
        auth="automation_task",
        csrf=False,
        methods=["POST"]
    )
    def progress(self, stage_id, **kwargs):
        stage_id = int(stage_id)
        values = self._get_values(**kwargs)
        registry = self._get_registry()
        with registry.cursor() as cr:
            env = Environment(cr, SUPERUSER_ID, {})
            env["automation.task.stage"].browse(stage_id).write(
                values
            )
        return ""