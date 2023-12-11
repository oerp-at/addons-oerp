from odoo.tests.common import TransactionCase


class TestTask(TransactionCase):
    """ Test automation task """

    def test_task(self):
        task = self.env["automation.task"].create({
            "name": "Test"
        })
        task.action_queue()

        self.assertTrue(task.cron_id, "Check if cron was set")
        self.assertTrue(task.action_id, "Check if action was set")

        task.action_cancel()
        self.assertFalse(task.cron_id.active, "Check if cron was unset")

