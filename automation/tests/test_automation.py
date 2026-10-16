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

    def test_automation_retrying_lifecycle(self):
        task = self.env['automation.task.example'].create({
            'name': 'Test Task'
        })

        # queue task
        task.action_queue()
        self.assertEqual(task.state, 'queued')

        # process task
        task.task_id.with_context(max_duration_s=5)._test_task()

        # check if task is requeued
        self.assertEqual(task.state, 'queued')

    def _log_messages(self, task):
        return self.env['automation.task.log'].search([('task_id', '=', task.task_id.id)]).mapped('message')

    def test_task_runs_in_the_language_of_its_owner(self):
        """The cron has no language: the log follows the owner (13795)."""
        self.env['res.lang']._activate_lang('de_DE')
        owner = self.env['res.users'].create({
            'name': 'German Owner', 'login': 'german_owner_13795', 'lang': 'de_DE',
            'group_ids': [(6, 0, self.env.user.group_ids.ids)],
        })
        task = self.env['automation.task.example'].create({'name': 'Test Task', 'owner_id': owner.id})
        task.action_queue()
        # the cron runs without language, like in production
        task.task_id.with_context(lang=None)._process_task()

        self.assertEqual(task.state, 'done')
        self.assertIn('Gestartet', self._log_messages(task))
        self.assertNotIn('Started', self._log_messages(task))

    def test_task_without_owner_language_stays_english(self):
        owner = self.env['res.users'].create({
            'name': 'English Owner', 'login': 'english_owner_13795', 'lang': 'en_US',
            'group_ids': [(6, 0, self.env.user.group_ids.ids)],
        })
        task = self.env['automation.task.example'].create({'name': 'Test Task', 'owner_id': owner.id})
        task.action_queue()
        task.task_id.with_context(lang=None)._process_task()

        self.assertIn('Started', self._log_messages(task))
