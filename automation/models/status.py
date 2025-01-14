import json
import logging
import requests
from odoo import tools, exceptions, _

_logger = logging.getLogger(__name__)


class TaskStatus(object):
    """ This class is used to log the progress of a task. """

    def __init__(self, task, total=1, local=False, logger=None, log=False, options=None, token=None, test=False):
        """ construct a new task status object
            :param task: The related task
            :param int total: The stage count
            :param bool local: Write all transaction within one transaction
            :param logger: The logger to use
            :param bool log: Log to logger also
        """
        # init options
        self.options = options if not options is None else {}

        # if test then enable log and test
        if tools.config.get('test_enable'):
            test = True
            log = True
            local = True

        # init stack
        self.token = token
        self.stage_stack = []
        self.last_status = None
        self.errors = 0
        self.warnings = 0
        self.test = test
        self.uid = task.env.uid

        # init loop
        self._loop_inc = 0.0
        self._loop_progress = 0.0

        # init task
        self.task = task
        self.env = task.env

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
            if token:
                self.token = token
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
            else:
                # set paths
                self.log_path = "log"
                self.stage_path = "stage"
                self.progress_path = "progress"

        # setup root stage
        # first call to remote
        self.root_stage_id = self._create_stage({"name": task.name, "total": total})
        self.parent_stage_id = self.root_stage_id
        self.stage_id = self.root_stage_id

        # first log
        # second call to remote
        self.log(_("Started"))


    def _post_data(self, url, data, result_parser=lambda res: None):
        if self.token:
            with requests.post(url, data=data, headers=self.headers, timeout=120) as res:
                res.raise_for_status()
                return result_parser(res)
        else:
            # copy data for local push
            data = data.copy()

            # write data to database
            def write_data(cr):

                def update_progress():
                    progress = data.pop("progress", None)
                    status = data.pop("status", None)
                    stage_id = data["stage_id"]
                    if status and progress:
                        cr.execute('UPDATE automation_task_stage SET progress = %s, status = %s WHERE id = %s', (progress, status, stage_id))
                    elif progress:
                        cr.execute('UPDATE automation_task_stage SET progress = %s WHERE id = %s', (progress, stage_id))
                    elif status:
                        cr.execute('UPDATE automation_task_stage SET status = %s WHERE id = %s', (status, stage_id))
                    return stage_id

                if url == "log":
                    update_progress()
                    # create log
                    cr.execute("""
                        INSERT INTO automation_task_log(create_date, write_date, create_uid, write_uid, task_id, stage_id, pri, message, ref, code, data)
                        VALUES (NOW() at time zone 'UTC', NOW() at time zone 'UTC', %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING ID
                    """, (self.uid,
                        self.uid,
                        data["task_id"],
                        data["stage_id"],
                        data["pri"],
                        data.get('message') or '',
                        data.get('ref') or '',
                        data.get('code') or '',
                        data.get('data') or None
                    ))
                    log_id = cr.fetchone()[0]
                    return log_id
                elif url == "stage":
                    # create stage
                    cr.execute("""
                        INSERT INTO automation_task_stage(create_date, write_date, create_uid, write_uid, task_id, name, parent_id, progress, status, total)
                        VALUES (NOW() at time zone 'UTC', NOW() at time zone 'UTC', %s, %s, %s, %s, %s, %s, %s, %s) RETURNING ID
                    """, (self.uid,
                        self.uid,
                        data["task_id"],
                        data["name"],
                        data.get('parent_id', None),
                        data.get('progress', 0),
                        data.get('status', ''),
                        data.get('total', None)
                    ))
                    stage_id = cr.fetchone()[0]
                    return stage_id
                elif url == "progress":
                    return update_progress()

            if not self.test:
                # create second cursor for commit
                with self.task.pool.cursor() as cr:
                    return write_data(cr)
            else:
                # write data straight ahead for testing
                return write_data(self.task.env.cr)

    def _post_progress(self, data):
        if self.local:
            self.stage_obj.browse(data["stage_id"]).write({
                "task_id": self.task.id,
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
            return self._post_data(self.stage_path,
                                   data,
                                   result_parser=lambda res: int(res.text))

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

        if not data is None and not isinstance(data, str):
            data = json.dumps(data)

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
            ref = f"{obj.name},{obj.id}"
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

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        # only close if there is no error
        if exc_type is None:
            self.close()


class TaskLogger:
    """ Tasklogger is a helper class for logging to python logger,
        especially for use in tests. """
    def __init__(self, name, options=None):
        self.logger = logging.getLogger(name)
        self.name = name
        self._status = None
        self._progress = 0
        self._loop_inc = 0.0
        self._loop_progress = 0.0
        self.errors = 0
        self.warnings = 0
        self.options = options if not options is None else {}

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