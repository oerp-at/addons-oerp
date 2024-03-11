from odoo.tests.common import HttpCase


class TestAutomation(HttpCase):
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
        cron = task.cron_id
        action = task.action_id
        task.unlink()
        self.assertFalse(cron.exists(), "Check if cron was deleted")
        self.assertFalse(action.exists(), "Check if action was deleted")
