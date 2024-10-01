import json
from odoo.tests.common import TransactionCase


class TestAutomation(TransactionCase):
    ''' Automation Test Case especially the log '''

    def test_automation_lifecycle(self):

        task = self.env['automation.task.example'].create({
            'name': 'Test Task'
        })

        # queue task
        task.action_queue()
        self.assertEqual(task.state, 'queued')

        # process task
        task.task_id._process_task()

        # check if done
        self.assertEqual(task.state, 'done')
        # check if logs are createds
        self.assertTrue(task.total_logs, 'Check if logs are created')

        # check test log
        log = self.env['automation.task.log'].search([('task_id', '=', task.task_id.id), ('code', '=', 'TEST')], limit=1)
        self.assertTrue(log, 'Check if log exist')
        data = json.loads(log.data)
        self.assertTrue(data, 'Check if log has data')
        self.assertTrue(data.get('test'), 'Check if test property was set in jsons')

