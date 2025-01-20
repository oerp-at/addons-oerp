import time
from odoo import models


class AutomationTaskExample(models.Model):
    _name = 'automation.task.example'
    _description = 'Automation Task Example'
    _inherit = "automation.task.mixin"


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

        taskc.stage("Another Loop to show percentage progress")
        taskc.loop_init(10)
        for i in range(10):
            taskc.loop_next()
            taskc.log("Processing %s", i)
            time.sleep(1)

        taskc.log('Generall Log with reference and json data', ref='account.move,13', data={'a': 1, 'b': 2})
        taskc.logd('Debug log')
        taskc.logw('Warning log')
        taskc.logi('Info log')
        taskc.logx('Fatal Error')
        taskc.loga('Critical Error')
        taskc.done()
