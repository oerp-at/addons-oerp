from unittest.mock import patch

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

    def _patch_singleton(self):
        ''' Turn the example into a quick singleton task '''
        example = type(self.env['automation.task.example'])
        for name, method in (
            ('_run_options', lambda task: {'singleton': True}),
            ('_run', lambda task, taskc: taskc.log('Singleton run')),
        ):
            patcher = patch.object(example, name, method, create=True)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_singleton_task_runs(self):
        ''' The concurrency check of a singleton task crashed on Odoo 19,
        resource._model is gone (12450) '''
        self._patch_singleton()
        task = self.env['automation.task.example'].create({
            'name': 'Singleton Task'
        })

        task.action_queue()
        task.task_id._process_task()

        self.assertEqual(task.state, 'done')
        self.assertFalse(task.error)
