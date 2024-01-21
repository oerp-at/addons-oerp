import logging
import requests
from odoo import exceptions, _

_logger = logging.getLogger(__name__)


class TaskStatus(object):
    """ This class is used to log the progress of a task. """

    def __init__(self, task, total=1, local=False, logger=None, log=False):
        """ construct a new task status object
            :param task: The related task
            :param int total: The stage count
            :param bool local: Write all transaction within one transaction
            :param logger: The logger to use
            :param bool log: Log to logger also
        """


        # init stack
        self.stage_stack = []
        self.last_status = None
        self.errors = 0
        self.warnings = 0

        # init loop
        self._loop_inc = 0.0
        self._loop_progress = 0.0

        # init task
        self.task = task

        # init stage name
        self.parent_stage_name = ""
        self.stage_name = task.name

        # init logger
        self.logger = logger
        if not self.logger and log:
            self.logger = _logger

        # init db
        self.db = task.env.cr.dbname

        # init remote/local
        self.local = local
        if self.local:
            self.stage_obj = self.task.env["automation.task.stage"]
            self.log_obj = self.task.env["automation.task.log"]
            self.log_obj.search([("task_id", "=", self.task.id)]).unlink()
            self.stage_obj.search([("task_id", "=", self.task.id)]).unlink()

            self.log_path = ""
            self.stage_path = ""
            self.progress_path = ""
            self.headers = {}
            self.token = None

        else:
            self.token = self.task.env["automation.task.token"].search([("task_id", "=", task.id)], limit=1).token
            if not self.token:
                raise exceptions.UserError(_("No token for task %(task_name)s [%(task_id)s] was generated"
                                            ,{'task_name': self.task.name, 'task_id': self.task.id}))

            baseurl = self.task.get_base_url()
            if not baseurl:
                raise exceptions.UserError(_("Cannot determine Base-Url"))

            self.log_path = f"{baseurl}/automation/log"
            self.stage_path = f"{baseurl}/automation/stage"
            self.progress_path = f"{baseurl}/automation/progress"

            # prepare header
            self.headers = {
                'Accept': 'application/form',
                'X-Automation-Token': self.token,
                'X-Automation-DB': self.db
            }

        # setup root stage
        # first call to remote
        self.root_stage_id = self._create_stage({"name": task.name, "total": total})
        self.parent_stage_id = self.root_stage_id
        self.stage_id = self.root_stage_id

        # first log
        # second call to remote
        self.log(_("Started"))

    def _post_data(self, url, data):
        res = requests.post(url, data=data, headers=self.headers, timeout=120)
        res.raise_for_status()
        return res

    def _post_progress(self, data):
        if self.local:
            self.stage_obj.browse(data["stage_id"]).write({
                "task_id": data["task_id"],
                "status": data["status"],
                "progress": data["progress"],
            })
        else:
            self._post_data(self.progress_path, data)

    def _post_stage(self, data):
        if self.logger:
            self.logger.info("= Stage %s", data["name"])
        data["task_id"] = self.task.id
        if self.local:
            return self.stage_obj.create(data).id
        else:
            res = self._post_data(self.stage_path, data)
            return int(res.text)

    def _post_log(self, data):
        # check for local logging
        data["task_id"] = self.task.id
        if self.local:

            ref = data.get("ref")
            if ref:
                ref_parts = ref.split(",")
                ref_obj = ref_parts[0]
                ref_id = int(ref_parts[1])
                obj = self.log_obj.env[ref_obj].browse(ref_id).exists()
                if obj:
                    data["message"] = f"{data['message']} ({obj.id}, '{obj.display_name}')"
                else:
                    data["message"] = f"{data['message']} ({ref})"

            # add progress
            if "progress" in data:
                progress = data.pop("progress", 0.0)
                self.task.env["automation.task.stage"].browse(self.stage_id).write({"progress": progress})

            self.log_obj.create(data)

        # otherwise forward log to server
        else:
            self._post_data(self.log_path, data)

        # log message
        if self.logger:
            pri = data["pri"]
            message = data["message"]
            if pri == "i":
                self.logger.info(message)
            elif pri == "e":
                self.errors += 1
                self.logger.error(message)
            elif pri == "w":
                self.warnings += 1
                self.logger.warning(message)
            elif pri == "d":
                self.logger.debug(message)
            elif pri == "x":
                self.logger.fatal(message)
            elif pri == "a":
                self.logger.critical(message)

    def log(self, message, pri="i", obj=None, ref=None, progress=None, code=None, data=None):
        if pri == "e":
            self.errors += 1
        elif pri == "w":
            self.warnings += 1

        values = {
            "stage_id": self.stage_id,
            "pri": pri,
            "message": message,
            "code": code,
            "data": data,
        }
        if progress:
            values["progress"] = progress
        if obj:
            ref = "%s,%s" % (obj._name, obj.id)
        if ref:
            values["ref"] = ref

        self._post_log(values)

    def loge(self, message, pri="e", **kwargs):
        self.log(message, pri=pri, **kwargs)

    def logw(self, message, pri="w", **kwargs):
        self.log(message, pri=pri, **kwargs)

    def logd(self, message, pri="d", **kwargs):
        self.log(message, pri=pri, **kwargs)

    def logn(self, message, pri="n", **kwargs):
        self.log(message, pri=pri, **kwargs)

    def loga(self, message, pri="a", **kwargs):
        self.log(message, pri=pri, **kwargs)

    def logx(self, message, pri="x", **kwargs):
        self.log(message, pri=pri, **kwargs)

    def loop_init(self, loop_count, status=None):
        self._loop_progress = 0.0
        if not loop_count:
            self._loop_progress = 100.0
            self._loop_inc = 0.0
        else:
            self._loop_inc = 100.0 / loop_count
            self._loop_progress = 0.0
        self.progress(status, self._loop_progress)

    def loop_next(self, status=None, step=1):
        self._loop_progress += self._loop_inc * step
        self.progress(status, self._loop_progress)

    def progress(self, status, progress):
        values = {
            "stage_id": self.stage_id,
            "task_id": self.task.id,
            "status": status,
            "progress": min(round(progress), 100),
        }
        if self.last_status is None or self.last_status != values:
            self.last_status = values
            self._post_progress(values)

    def _create_stage(self, values):
        return self._post_stage(values)

    def stage(self, subject, total=None):
        values = {"parent_id": self.parent_stage_id, "name": subject}
        if total:
            values["total"] = total
        self.stage_stack.append((self.parent_stage_id, self.stage_id))
        self.stage_id = self._create_stage(values)

    def substage(self, subject, total=None):
        values = {"parent_id": self.stage_id, "name": subject}
        if total:
            values["total"] = total
        self.stage_stack.append((self.parent_stage_id, self.stage_id))
        self.parent_stage_id = self.stage_id
        self.stage_id = self._create_stage(values)

    def done(self):
        self.progress(_("Done"), 100.0)
        if self.stage_stack:
            self.parent_stage_id, self.stage_id = self.stage_stack.pop()

    def close(self):
        self._post_progress({"stage_id": self.root_stage_id, "status": _("Done"), "progress": 100.0})


class TaskLogger:
    """ Tasklogger is a helper class for logging to python logger,
        especially for use in tests. """
    def __init__(self, name):
        self.logger = logging.getLogger(name)
        self.name = name
        self._status = None
        self._progress = 0
        self._loop_inc = 0.0
        self._loop_progress = 0.0
        self.errors = 0
        self.warnings = 0

    # pylint: disable=unused-argument
    def log(self, message, pri="i", obj=None, ref=None, progress=None, code=None, data=None):
        if pri == "i":
            self.logger.info(message)
        elif pri == "e":
            self.errors += 1
            self.logger.error(message)
        elif pri == "w":
            self.warnings += 1
            self.logger.warning(message)
        elif pri == "d":
            self.logger.debug(message)
        elif pri == "x":
            self.logger.fatal(message)
        elif pri == "a":
            self.logger.critical(message)

    def loge(self, message, pri="e", **kwargs):
        self.log(message, pri=pri, **kwargs)

    def logw(self, message, pri="w", **kwargs):
        self.log(message, pri=pri, **kwargs)

    def logd(self, message, pri="d", **kwargs):
        self.log(message, pri=pri, **kwargs)

    def logn(self, message, pri="n", **kwargs):
        self.log(message, pri=pri, **kwargs)

    def loga(self, message, pri="a", **kwargs):
        self.log(message, pri=pri, **kwargs)

    def logx(self, message, pri="x", **kwargs):
        self.log(message, pri=pri, **kwargs)

    def loop_init(self, loopCount, status=None):
        self._loop_progress = 0.0
        if not loopCount:
            self._loop_progress = 100.0
            self._loop_inc = 0.0
        else:
            self._loop_inc = 100.0 / loopCount
            self._loop_progress = 0.0
        self.progress(status, self._loop_progress)

    def loop_next(self, status=None, step=1):
        self._loop_progress += self._loop_inc * step
        self.progress(status, self._loop_progress)

    def progress(self, status, progress):
        progress = min(round(progress), 100)
        if not status:
            status = "Progress"
        if self._status != status or self._progress != progress:
            self._status = status
            self._progress = progress
            self.log("%s: %s", self._status, self._progress)

    def stage(self, subject, total=None):
        self.log("= %s", subject)

    def substage(self, subject, total=None):
        self.log("== %s", subject)

    def done(self):
        self.progress("Done", 100.0)

    def close(self):
        pass