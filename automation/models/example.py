import time
from odoo import models


class AutomationTaskExample(models.Model):
    _name = 'automation.task.example'
    _description = 'Automation Task Example'
    _inherit = 'automation.task.mixin'

    def _run(self, taskc):
        """ Test Task """
        self.ensure_one()
        counter = 0
        for stage in range(1, 2):
            taskc.stage('Stage %s' % stage)

            for proc in range(1, 100, 10):
                counter += 1
                taskc.log('Processing %s' % counter)
                taskc.progress(f'Processing {stage}', proc)
                time.sleep(1)

            taskc.done()

        taskc.stage('Another Loop to show percentage progress')
        taskc.loop_init(10)
        counter = 0
        for i in range(10):
            taskc.loop_next()
            counter += 1
            taskc.log('Processing %s' % counter)
            time.sleep(1)

        taskc.log('Generall Log with reference and json data', ref='account.move,13', data={'a': 1, 'b': 2})
        taskc.logd('Debug log')
        taskc.logw('Warning log')
        taskc.log('Info log')
        taskc.logx('Fatal Error')
        taskc.loga('Critical Error')
        taskc.done()
