import time
import uuid
import logging
from odoo import api, fields, models, SUPERUSER_ID, _, exceptions, tools
from .status import TaskStatus

_logger = logging.getLogger(__name__)


def _list_all_models(self):
    """ show all available odoo models """
    self._cr.execute("SELECT model, name FROM ir_model ORDER BY name")
    return self._cr.fetchall()


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
        default=lambda self: self._uid,
        index=True,
        readonly=True,
    )

    res_model = fields.Char("Resource Model", index=True, readonly=True)
    res_id = fields.Integer("Resource ID", index=True, readonly=True)
    res_ref = fields.Reference(_list_all_models, string="Resource", compute="_compute_res_ref", readonly=True)
    cron_id = fields.Many2one(
        "ir.cron",
        "Scheduled Job",
        index=True,
        ondelete="set null",
        copy=False,
        readonly=True,
    )

    total_logs = fields.Integer(compute="_compute_total_logs")
    total_stages = fields.Integer(compute="_compute_total_stages")
    total_warnings = fields.Integer(compute="_compute_total_warnings")
    total_errors = fields.Integer(compute="_compute_total_errors")

    task_id = fields.Many2one("automation.task", "Task", compute="_compute_task_id")

    start_after_task_id = fields.Many2one(
        "automation.task",
        "Start after task",
        readonly=True,
        index=True,
        ondelete="restrict",
        help="Start *this* task after the specified task, was set to null after run state is set.")
    start_after = fields.Datetime(help="Start *this* task after the specified date/time.")

    parent_id = fields.Many2one("automation.task",
                                "Parent",
                                readonly=True,
                                index=True,
                                ondelete="set null",
                                help="The parent task, after *this* task was started")

    post_task_ids = fields.One2many("automation.task",
                                    "start_after_task_id",
                                    "Post Tasks",
                                    help="Tasks which are started after this task.",
                                    readonly=True)

    child_task_ids = fields.One2many("automation.task",
                                     "parent_id",
                                     "Child Tasks",
                                     help="Tasks which already started after this task.",
                                     readonly=True)

    action_id = fields.Many2one("ir.actions.server", "Server Action", ondelete="restrict", index=True, readonly=True)

    def _compute_task_id(self):
        for obj in self:
            self.task_id = obj

    def _compute_progress(self):
        if not self.ids:
            self.progress = 0.0
            return

        res = dict.fromkeys(self.ids, 0.0)

        # search stages
        self._cr.execute(
            "SELECT id FROM automation_task_stage WHERE task_id IN %s AND parent_id IS NULL",
            (tuple(self.ids), ),
        )

        # get progress
        stage_ids = [r[0] for r in self._cr.fetchall()]
        for stage in self.env["automation.task.stage"].browse(stage_ids):
            res[stage.task_id.id] = stage.complete_progress

        # assign
        for obj in self:
            obj.progress = res[obj.id]

    def _compute_res_ref(self):
        if not self.ids:
            self.res_ref = None
            return

        self._cr.execute(
            """SELECT res_model, ARRAY_AGG(id)
            FROM automation_task
            WHERE id IN %s
            GROUP BY 1
        """, (tuple(self.ids), ))

        values = {}
        for res_model, task_ids in self._cr.fetchall():
            model_obj = self.env.get(res_model)
            if model_obj:
                table_name = model_obj._table
                self._cr.execute(
                    """SELECT
                        t.id, r.id
                    FROM automation_task t
                    LEFT JOIN %s r ON r.id = t.res_id
                    WHERE t.id IN %%s
                """ % table_name, (task_ids, ))

                values.update(dict([(i, "%s,%s" % (res_model, r)) for (i, r) in self._cr.fetchall()]))

        for obj in self:
            obj.res_ref = values.get(obj.id, None)

    def _compute_total_logs(self):
        if not self.ids:
            self.total_logs = 0
            return

        self._cr.execute("SELECT task_id, COUNT(*) FROM automation_task_log WHERE task_id IN %s GROUP BY 1",
                    (tuple(self.ids), ))
        values = dict(self._cr.fetchall())
        for obj in self:
            obj.total_logs = values.get(obj.id) or 0

    def _compute_total_warnings(self):
        if not self.ids:
            self.total_warnings = 0
            return

        self._cr.execute(
            """SELECT task_id, COUNT(*) FROM automation_task_log
            WHERE pri = 'w'
              AND task_id IN %s
            GROUP BY 1
            """, (tuple(self.ids), ))
        values = dict(self._cr.fetchall())
        for obj in self:
            obj.total_warnings = values.get(obj.id) or 0

    def _compute_total_errors(self):
        if not self.ids:
            self.total_errors = 0
            return

        self._cr.execute(
            """SELECT task_id, COUNT(*) FROM automation_task_log
            WHERE pri IN ('a','e','x')
              AND task_id IN %s GROUP BY 1
            """, (tuple(self.ids), ))
        values = dict(self._cr.fetchall())
        for obj in self:
            obj.total_errors = values.get(obj.id) or 0

    def _compute_total_stages(self):
        if not self.ids:
            self.total_stages = 0
            return

        res = dict.fromkeys(self.ids, 0)
        self._cr.execute(
            "SELECT task_id, COUNT(*) FROM automation_task_stage WHERE task_id IN %s GROUP BY 1",
            (tuple(self.ids), ),
        )
        for task_id, stage_count in self._cr.fetchall():
            res[task_id] = stage_count
        for r in self:
            r.total_stages = res[r.id]

    def _run(self, taskc):
        """ Test Task """
        self.ensure_one()
        for stage in range(1, 10):
            taskc.stage("Stage %s" % stage)

            for proc in range(1, 100, 10):
                taskc.log("Processing %s", stage)
                taskc.progress(f"Processing {stage}", proc)
                time.sleep(1)

            taskc.done()

    def _stage_count(self):
        self.ensure_one()
        return 10

    def _task_get_list(self):
        self.ensure_one()

        task_id = self.id
        self._cr.execute(
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

        task_ids = [r[0] for r in self._cr.fetchall()]
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
        if self.owner_id.id != self._uid and not self.user_has_groups(
                "automation.group_automation_manager,base.group_system"):
            raise exceptions.UserError(_("Not allowed. You have to be the owner or an automation manager"))

    def action_cancel(self):
        for task in self:
            # check rights
            task._check_execution_rights()
            if task.state == "queued":
                task.state = "cancel"
                if task.cron_id:
                    task.cron_id.active = False
        return True

    def action_stage(self):
        return {
            "display_name": _("Stages"),
            "res_model": "automation.task.stage",
            "type": "ir.actions.act_window",
            "view_mode": "tree,form",
            "domain": [("task_id", "=", self.id)],
            "context": {'display_exclude_root':True}
        }

    def action_log(self):
        return {
            "display_name": _("Logs"),
            "res_model": "automation.task.log",
            "type": "ir.actions.act_window",
            "view_mode": "tree,form",
            "domain": [("task_id", "=", self.id)],
            "context": {'display_exclude_root':True}
        }

    def action_warning(self):
        return {
            "display_name": _("Logs"),
            "res_model": "automation.task.log",
            "type": "ir.actions.act_window",
            "view_mode": "tree,form",
            "domain": [("task_id", "=", self.id), ("pri", "=", "w")],
            "context": {'display_exclude_root':True}
        }

    def action_error(self):
        return {
            "display_name": _("Logs"),
            "res_model": "automation.task.log",
            "type": "ir.actions.act_window",
            "view_mode": "tree,form",
            "domain": [("task_id", "=", self.id), ("pri", "in", ("e", "a", "x"))],
            "context": {'display_exclude_root':True}
        }

    def action_refresh(self):
        return True

    def action_reset(self):
        return True

    def _get_cron_values(self):
        self.ensure_one()

        # setup next call
        nextcall = fields.Datetime.now()
        if self.start_after and nextcall < self.start_after:
            nextcall = self.start_after

        # new cron entry
        return {
            "name": f"Task: {self.name}",
            "user_id": SUPERUSER_ID,
            "interval_type": "minutes",
            "interval_number": 1,
            "nextcall": nextcall,
            "numbercall": 1,
            "active": True,
            "priority": 100000 + self.id,
            "task_id": self.id,
            "ir_actions_server_id": self.action_id.id
        }

    def _get_task_values(self):
        self.ensure_one()
        return {
            "name": f"Automation Action ({self.id})",
            "state": "task",
            "sequence": 100000 + self.id,
            "model_id": self.env["ir.model"].search([("model", "=", "automation.task")], limit=1).id,
            "usage": "ir_cron",
            "task_id": self.id
        }

    def _task_enqueue(self):
        """ queue task """

        # remove stages
        self._cr.execute(
            "DELETE FROM automation_task_stage WHERE task_id=%s",
            (self.id, ),
        )

        # (re)create token
        token_obj = self.env["automation.task.token"]
        token_obj.search([("task_id", "=", self.id)]).unlink()
        token_obj.create({
            "task_id": self.id
        })

        # set queued
        self.write({
            "state": "queued",
            "parent_id": self.start_after_task_id.id,
            "start_after_task_id": None,
            "start_after": None,
        })

        # create action on the fly
        if not self.action_id:
            self.action_id = self.env["ir.actions.server"].create(self._get_task_values())

        # (re)create cron entry
        old_cron = self.cron_id
        self.cron_id = self.env["ir.cron"].create(self._get_cron_values())
        # cleanup old cron entry
        old_cron.unlink()

    def action_queue(self):
        for task in self:
            # check rights
            task._check_execution_rights()
            if task.state in ("draft", "cancel", "failed", "done"):
                # sudo task, and check if it is not active already
                sudo_task = task.sudo()
                if not sudo_task.cron_id or not sudo_task.cron_id.active:
                    task.sudo()._task_enqueue()
        return True

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
            self._cr.commit()

    def _process_task(self):
        self.ensure_one()
        task = self

        if task and task.state == "queued":
            try:
                task_options = task._task_options()
                stage_count = task_options["stages"]
                resource = task_options["resource"]

                # check if it is a singleton task
                # if already another task run, requeue
                # don't process this task
                if task_options.get("singleton"):
                    # check concurrent
                    self._cr.execute(
                        "SELECT MIN(id) FROM automation_task WHERE res_model=%s AND state IN ('queued','run')",
                        (resource._model._name, ),
                    )

                    active_task_id = self._cr.fetchone()[0]
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
                    "start_after_task_id": None,
                    "parent_id": task.start_after_task_id.id
                })
                # commit after start
                self._commit_state()

                # run task
                taskc = TaskStatus(task, stage_count)
                resource._run(taskc)

                # check fail on errors
                if task_options.get("fail_on_errors"):
                    if taskc.errors:
                        raise exceptions.UserError(_("Task finished with errors"))

                # close
                taskc.close()

                # update status and commit
                task.write({"state_change": fields.Datetime.now(), "state": "done", "error": None})
                # pylint: disable=invalid-commit
                self._commit_state()

            except Exception as e:
                # rollback on error
                self._cr.rollback()

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
                })

                # finally commit current state after
                # rollback
                self._commit_state()

        return True


class AutomationTaskMixin(models.AbstractModel):
    _name = "automation.task.mixin"
    _description = "Automation Task Proxy"
    _inherits = {"automation.task": "task_id"}

    task_id = fields.Many2one("automation.task", "Task", required=True, index=True, ondelete="cascade")

    @api.model_create_multi
    @api.returns('self', lambda value: value.id)
    def create(self, vals_list):
        res = super(AutomationTaskMixin, self).create(vals_list)
        res.res_model = self._name
        res.res_id = res.id
        return res

    def unlink(self):
        # search inherited
        ids = self.ids
        self._cr.execute("SELECT task_id FROM %s WHERE id IN %%s AND task_id IS NOT NULL" % self._table, (tuple(ids),))
        task_ids = [r[0] for r in self._cr.fetchall()]
        # unlink task
        res = super(AutomationTaskMixin, self).unlink()
        # unlink inherited
        self.env["automation.task"].browse(task_ids).unlink()
        return res

    def action_queue(self):
        return self.task_id.action_queue()

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

    def _run(self, taskc):
        """ Test Task """
        self.ensure_one()
        for stage in range(1, 2):
            taskc.stage(f"Stage {stage}")

            for proc in range(1, 100, 10):
                taskc.log(f"Processing {stage}")
                taskc.progress(f"Processing {stage}", proc)
                time.sleep(1)

            taskc.done()


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
        exclude_root = self._context.get('display_exclude_root')
        for obj in self:
            name = []
            stage = obj
            while stage:
                if not exclude_root or stage.parent_id:
                    name.append(stage.name)
                stage = stage.parent_id
            obj.complete_name = " / ".join(reversed(name))

    def _calc_progress(self):
        self.ensure_one()
        progress = self.progress
        if progress >= 100.0:
            return progress

        childs = self.child_ids
        total = max(self.total, len(childs)) or 1

        for child in childs:
            progress += child._calc_progress() / total

        return min(round(progress), 100.0)

    def _compute_progress(self):
        for obj in self:
            self.complete_progress = obj._calc_progress()


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
    code = fields.Char(index=True)
    data = fields.Json()

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
