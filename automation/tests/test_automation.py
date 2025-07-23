from odoo.tests.common import TransactionCase
from odoo.tests import tagged


@tagged('post_install', '-at_install')
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
        # check if logs are created
        self.assertTrue(task.total_logs, 'Check if logs are created')

        # delete task
        task.unlink()
        # check delete of empty set
        self.env['automation.task.example'].unlink()
