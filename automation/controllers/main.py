# -*- coding: utf-8 -*-

from odoo import http, SUPERUSER_ID
from odoo.http import request
from odoo.api import Environment
from odoo import registry as registry_get

class TaskLogController(http.Controller):
    """ task log controller """

    def _get_registry(self):
        return registry_get(request.header['Log-DB'])

    @http.route(
        "/web/automation/log",
        type="http",
        auth="automation_task",
        csrf=False,
        methods=["POST"],
    )
    def log(self, progress=None, **kwargs):
        registry = self._get_registry()
        with registry.cursor() as cr:
            env = Environment(cr, SUPERUSER_ID, {})

            # check if progress passed
            # .. modify progress
            if progress:
                try:
                    progress = float(progress)
                    env["automation.task.stage"].browse(int(kwargs["stage_id"])).write(
                        {"progress": progress}
                    )
                except ValueError:
                    pass
            # log
            return str(env["automation.task.log"].create(kwargs).id)

    @http.route(
        "/web/automation/stage",
        type="http",
        auth="automation_task",
        csrf=False,
        methods=["POST"],
    )
    def stage(self, **kwargs):
        registry = self._get_registry()
        with registry.cursor() as cr:
            env = Environment(cr, SUPERUSER_ID, {})
            return str(env["automation.task.stage"].create(kwargs).id)

    @http.route(
        "/web/automation/progress",
        type="http",
        auth="automation_task",
        csrf=False,
        methods=["POST"]
    )
    def progress(self, stage_id, **kwargs):
        stage_id = int(stage_id)
        registry = self._get_registry()
        with registry.cursor() as cr:
            env = Environment(cr, SUPERUSER_ID, {})
            env["automation.task.stage"].browse(stage_id).write(
                kwargs
            )
        return ""