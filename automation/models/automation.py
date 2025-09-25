import uuid
import logging
import psycopg2
from odoo import api, fields, models, _, exceptions, tools
from .status import TaskStatus

_logger = logging.getLogger(__name__)


def _list_all_models(self):
    """ show all available odoo models """
    self.env.cr.execute("SELECT model, name FROM ir_model ORDER BY name")
    return self.env.cr.fetchall()


class AutomationTask(models.Model):
    _name = "automation.task"
    _description = "Automation Task"
    _order = "id asc"

    name = fields.Char(required=True)
    state_change = fields.Datetime(
        required=True,
        readonly=True,
        copy=False,
        default=lambda self: fields.Datetime.now(),
    )

    state = fields.Selection([
        ("draft", "Draft"),
        ("queued", "Queued"),
        ("run", "Running"),
        ("cancel", "Canceled"),
        ("failed", "Failed"),
        ("done", "Done"),
    ], required=True, index=True,
    readonly=True, default="draft", copy=False)

    progress = fields.Float(readonly=True, compute="_compute_progress")
    error = fields.Text(readonly=True, copy=False)
    group_id = fields.Many2one('res.groups', 'Group', ondelete="set null")
    owner_id = fields.Many2one(
        "res.users",
        required=True,
        default=lambda self: self.env.uid,
        index=True,
        readonly=True,
    )

    res_model = fields.Char("Resource Model", index=True, readonly=True)
    res_id = fields.Integer("Resource ID", index=True, readonly=True)
    res_ref = fields.Reference(_list_all_models, string="Resource", compute="_compute_res_ref", readonly=True)

    total_logs = fields.Integer(compute="_compute_total_logs")
    total_stages = fields.Integer(compute="_compute_total_stages")
    total_warnings = fields.Integer(compute="_compute_total_warnings")
    total_errors = fields.Integer(compute="_compute_total_errors")

    task_id = fields.Many2one("automation.task", "Task", compute="_compute_task_id")

    error_count = fields.Integer(readonly=True)
    warning_count = fields.Integer(readonly=True)


    def _compute_task_id(self):
        for obj in self:
            self.task_id = obj

    def _compute_progress(self):
        if not self.ids:
            self.progress = 0.0
            return

        #  get progress from stages
        res = dict.fromkeys(self.ids, 0.0)
        self.env.cr.execute(
            "SELECT id FROM automation_task_stage WHERE task_id IN %s AND parent_id IS NULL",
            (tuple(self.ids), ),
        )
        stage_ids = [r[0] for r in self.env.cr.fetchall()]
        for stage in self.env["automation.task.stage"].browse(stage_ids):
            res[stage.task_id.id] = stage._get_progress()
        # assign
        for obj in self:
            obj.progress = res.get(obj.id, 0.0)

    def _compute_res_ref(self):
        if not self.ids:
            self.res_ref = None
            return

        self.env.cr.execute(
            """SELECT res_model, ARRAY_AGG(id)
            FROM automation_task
            WHERE id IN %s
            GROUP BY 1
        """, (tuple(self.ids), ))

        values = {}
        for res_model, task_ids in self.env.cr.fetchall():
            model_obj = self.env.get(res_model)
            if model_obj:
                table_name = model_obj._table
                self.env.cr.execute(
                    """SELECT
                        t.id, r.id
                    FROM automation_task t
                    LEFT JOIN %s r ON r.id = t.res_id
                    WHERE t.id IN %%s
                """ % table_name, (task_ids, ))

                values.update(dict([(i, "%s,%s" % (res_model, r)) for (i, r) in self.env.cr.fetchall()]))

        for obj in self:
            obj.res_ref = values.get(obj.id, None)

    def _compute_total_logs(self):
        if not self.ids:
            self.total_logs = 0
            return

        self.env.cr.execute("SELECT task_id, COUNT(*) FROM automation_task_log WHERE task_id IN %s GROUP BY 1",
                    (tuple(self.ids), ))
        values = dict(self.env.cr.fetchall())
        for obj in self:
            obj.total_logs = values.get(obj.id) or 0

    def _compute_total_warnings(self):
        if not self.ids:
            self.total_warnings = 0
            return

        self.env.cr.execute(
            """SELECT task_id, COUNT(*) FROM automation_task_log
            WHERE pri = 'w'
              AND task_id IN %s
            GROUP BY 1
            """, (tuple(self.ids), ))
        values = dict(self.env.cr.fetchall())
        for obj in self:
            obj.total_warnings = values.get(obj.id) or 0

    def _compute_total_errors(self):
        if not self.ids:
            self.total_errors = 0
            return

        self.env.cr.execute(
            """SELECT task_id, COUNT(*) FROM automation_task_log
            WHERE pri IN ('a','e','x')
              AND task_id IN %s GROUP BY 1
            """, (tuple(self.ids), ))
        values = dict(self.env.cr.fetchall())
        for obj in self:
            obj.total_errors = values.get(obj.id) or 0

    def _compute_total_stages(self):
        if not self.ids:
            self.total_stages = 0
            return

        res = dict.fromkeys(self.ids, 0)
        self.env.cr.execute(
            "SELECT task_id, COUNT(*) FROM automation_task_stage WHERE task_id IN %s GROUP BY 1",
            (tuple(self.ids), ),
        )
        for task_id, stage_count in self.env.cr.fetchall():
            res[task_id] = stage_count
        for r in self:
            r.total_stages = res[r.id]

    def _run(self, taskc):
        pass

    def _stage_count(self):
        self.ensure_one()
        return 10

    def _task_get_list(self):
        self.ensure_one()

        task_id = self.id
        self.env.cr.execute(
            """WITH RECURSIVE task(id) AS (
                SELECT
                    id
                FROM automation_task t
                WHERE
                    t.id = %s
                UNION
                    SELECT
                        st.id
                    FROM automation_task st
                    INNER JOIN task pt ON st.start_after_task_id = pt.id
            )
            SELECT id FROM task
            """, (task_id, ))

        task_ids = [r[0] for r in self.env.cr.fetchall()]
        return self.browse(task_ids)

    def _task_get_after_tasks(self):
        self.ensure_one()
        return self.search([("start_after_task_id", "=", self.id)])

    def _task_add_after_last(self, task):
        """ Add task after this, if it is already
            queued it will be not queued twice """
        self.ensure_one()
        if task:
            tasklist = self._task_get_list()
            if not task in tasklist:
                task.write({"start_after_task_id": tasklist[-1].id})

    def _task_insert_after(self, task):
        """ Insert task after this """
        self.ensure_one()
        if task:
            task.start_after_task_id = task
            self.search([("start_after_task_id", "=", task.id)]).write({"start_after_task_id": self.id})

    def _check_execution_rights(self):
        # check rights
        if self.owner_id.id != self.env.uid and not self.env.user.has_groups(
                "automation.group_automation_manager,base.group_system"):
            raise exceptions.UserError(_("Not allowed. You have to be the owner or an automation manager"))

    def action_cancel(self):
        for task in self:
            # check rights
            task._check_execution_rights()
            if task.state == "queued":
                task.state = "cancel"

        return True

    def action_stage(self):
        return {
            "display_name": _("Stages"),
            "res_model": "automation.task.stage",
            "type": "ir.actions.act_window",
            "view_mode": "list,form",
            "domain": [("task_id", "=", self.id)],
            "context": {'display_exclude_root':True}
        }

    def action_log(self):
        return {
            "display_name": _("Logs"),
            "res_model": "automation.task.log",
            "type": "ir.actions.act_window",
            "view_mode": "list,form",
            "domain": [("task_id", "=", self.id)],
            "context": {'display_exclude_root':True}
        }

    def action_warning(self):
        return {
            "display_name": _("Logs"),
            "res_model": "automation.task.log",
            "type": "ir.actions.act_window",
            "view_mode": "list,form",
            "domain": [("task_id", "=", self.id), ("pri", "=", "w")],
            "context": {'display_exclude_root':True}
        }

    def action_error(self):
        return {
            "display_name": _("Logs"),
            "res_model": "automation.task.log",
            "type": "ir.actions.act_window",
            "view_mode": "list,form",
            "domain": [("task_id", "=", self.id), ("pri", "in", ("e", "a", "x"))],
            "context": {'display_exclude_root':True}
        }

    def action_refresh(self):
        return True

    def action_reset(self):
        return True

    def _is_run_unqueued(self):
        """ Check task should be run unqueued """

        if self.env.context.get('task_unqueued_run'):
            return True

        param = self.env['ir.config_parameter'].sudo().get_param('automation.task_unqueued_run')
        if not param:
            return False
        return param.lower() in ('true', '1', 'yes', 'on')

    def _task_enqueue(self):
        """ queue task """

        # remove stages
        self.env.cr.execute(
            "DELETE FROM automation_task_stage WHERE task_id=%s",
            (self.id, ),
        )

        # set queued and trigger cron
        self.write({
            "state": "queued"
        })
        if self._is_run_unqueued():
            self._process_task()
        else:
            self.env.ref('automation.ir_cron_automation_task')._trigger()

    def action_queue(self):
        for task in self:
            # check rights
            task._check_execution_rights()
            if task.state in ("draft", "cancel", "failed", "done"):
                # sudo task, and check if it is not active already
                task.sudo()._task_enqueue()
        return True

    def action_restart(self):
        return self.action_queue()

    def _task_options(self):
        self.ensure_one()
        # get instance
        if self.res_model and self.res_id:
            model_obj = self.env[self.res_model]
            resource = model_obj.browse(self.res_id)
        else:
            resource = self

        # prepare options
        options = {"stages": 1, "resource": resource}

        # fetch custom options
        if hasattr(resource, "_run_options"):
            res_options = getattr(resource, "_run_options")
            if callable(res_options):
                res_options = resource._run_options()
            options.update(res_options)
        return options

    def _commit_state(self):
        """ ugly hack but needed to commit changes """
        if not tools.config.get('test_enable'):
            # pylint: disable=invalid-commit
            self.env.cr.commit()

    def _rollback_state(self):
        if not tools.config.get('test_enable'):
            self.env.cr.rollback()

    def _test_task(self):
        self.ensure_one()
        if tools.config.get('test_enable'):
            self.action_queue()
            # if queued run task
            if self.state == 'queued':
                self._process_task()

    def _process_task(self):
        self.ensure_one()
        task = self

        if task and task.state == "queued":
            error_count = 0
            warning_count = 0
            try:
                task_options = task._task_options()
                stage_count = task_options["stages"]
                resource = task_options["resource"]

                # check if it is a singleton task
                # if already another task run, requeue
                # don't process this task
                if task_options.get("singleton"):
                    # check concurrent
                    self.env.cr.execute(
                        "SELECT MIN(id) FROM automation_task WHERE res_model=%s AND state IN ('queued','run')",
                        (resource._model._name, ),
                    )

                    active_task_id = self.env.cr.fetchone()[0]
                    if active_task_id and active_task_id < task.id:
                        # queue task after running
                        task.write({"start_after_task_id": active_task_id})
                        return True

                # change task state
                # and commit
                task.write({
                    "state_change": fields.Datetime.now(),
                    "state": "run",
                    "error": None,
                    "error_count": 0,
                    "warning_count": 0,
                })
                # commit after start
                self._commit_state()

                # run task
                with TaskStatus(task, stage_count, options=task_options) as taskc:
                    try:
                        resource._run(taskc)
                    finally:
                        error_count = taskc.errors
                        warning_count = taskc.warnings

                    # check fail on errors
                    if task_options.get("fail_on_errors"):
                        if error_count:
                            raise exceptions.UserError(_("Task finished with errors"))

                # update status and commit
                task.write({"state_change": fields.Datetime.now(),
                            "state": "done",
                            "error": None,
                            "error_count": error_count,
                            "warning_count": warning_count
                    })

                # pylint: disable=invalid-commit
                self._commit_state()

            except Exception as e:
                # rollback on error
                self._rollback_state()

                _logger.exception("Task execution failed")
                task = self.browse(task.id)  # reload task after rollback

                # securely try to get message
                error = None
                try:
                    error = str(e)
                    if not error and hasattr(e, "message"):
                        error = e.message
                except:
                    _logger.exception("Parsing failed")

                #if there is no message
                if not error:
                    error = "Unexpected error, see logs"

                # write error
                task.write({
                    "state_change": fields.Datetime.now(),
                    "state": "failed",
                    "error": error,
                    "error_count": error_count,
                    "warning_count": warning_count
                })

                # finally commit current state after
                # rollback
                self._commit_state()

        return True


    @api.model
    def _cron_run(self):
        # get available tasks
        ids = None
        try:
            self.env.cr.execute("""SELECT id FROM automation_task WHERE state = 'queued' FOR UPDATE NOWAIT LIMIT 1""")
            ids = [r[0] for r in self.env.cr.fetchall()]
        except psycopg2.OperationalError:
            # return if there is a concurrency error
            self.env.cr.rollback()
            return

        # return if no tasks available
        if not ids:
            return

        # process task
        self.env["automation.task"].browse(ids[0])._process_task()



class AutomationTaskMixin(models.AbstractModel):
    _name = "automation.task.mixin"
    _description = "Automation Task Proxy"
    _inherits = {"automation.task": "task_id"}

    task_id = fields.Many2one("automation.task", "Task", required=True, index=True, ondelete="cascade")

    @api.model_create_multi
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
            self.env.cr.execute(f"SELECT task_id FROM {self._table} WHERE id IN %s AND task_id IS NOT NULL", (tuple(ids),))
            task_ids = [r[0] for r in self.env.cr.fetchall()]

        # unlink self
        res = super(AutomationTaskMixin, self).unlink()

        # unlink inherited
        if ids and task_ids:
            self.env["automation.task"].browse(task_ids).unlink()

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


class AutomationTaskStage(models.Model):
    _name = "automation.task.stage"
    _description = "Task Stage"
    _order = "id asc"
    _rec_name = "complete_name"

    complete_name = fields.Char("Title", compute="_compute_name")
    complete_progress = fields.Float("Progess %", readonly=True, compute="_compute_progress")

    name = fields.Char(readonly=True, required=True)
    progress = fields.Float("Progress %", readonly=True)
    status = fields.Char()

    task_id = fields.Many2one(
        "automation.task",
        "Task",
        readonly=True,
        index=True,
        required=True,
        ondelete="cascade",
    )
    parent_id = fields.Many2one("automation.task.stage", "Parent Stage", readonly=True, index=True)
    total = fields.Integer(readonly=True)

    child_ids = fields.One2many("automation.task.stage", "parent_id", string="Substages", copy=False)

    def _compute_name(self):
        exclude_root = self.env.context.get('display_exclude_root')
        for obj in self:
            name = []
            stage = obj
            while stage:
                if not exclude_root or stage.parent_id:
                    name.append(stage.name)
                stage = stage.parent_id
            complete_name = " / ".join(reversed(name)) or '/'
            obj.complete_name = complete_name

    def _get_progress(self):
        self.ensure_one()
        progress = self.progress

        # if there is a progress
        # return the progress
        if progress > 0:
            return min(progress, 100.0)

        # otherwise return the overall progress
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
    _name = "automation.task.log"
    _description = "Task Log"
    _order = "id asc"
    _rec_name = "create_date"

    task_id = fields.Many2one(
        "automation.task",
        "Task",
        required=True,
        readonly=True,
        index=True,
        ondelete="cascade",
    )
    stage_id = fields.Many2one(
        "automation.task.stage",
        "Stage",
        required=True,
        readonly=True,
        index=True,
        ondelete="cascade",
    )

    pri = fields.Selection(
        [
            ("x", "Emergency"),
            ("a", "Alert"),
            ("e", "Error"),
            ("w", "Warning"),
            ("n", "Notice"),
            ("i", "Info"),
            ("d", "Debug"),
        ],
        string="Priority",
        default="i",
        index=True,
        required=True,
        readonly=True,
    )

    message = fields.Text(readonly=True)
    ref = fields.Reference(_list_all_models, readonly=True, index=True)
    safe_ref = fields.Reference(_list_all_models, string="Reference", compute="_compute_safe_ref", store=False, readonly=True)
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
    _name = "automation.task.token"
    _description = "Task Token"
    _rec_name = "task_id"

    task_id = fields.Many2one("automation.task", "Task", required=True, ondelete="cascade", index=True)
    token = fields.Char(required=True, default=lambda self: str(uuid.uuid4()), index=True)
