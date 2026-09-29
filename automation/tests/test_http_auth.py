from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestAutomationHttpAuth(HttpCase):
    ''' The automation_task auth method guards the /automation routes '''

    def setUp(self):
        super().setUp()
        example = self.env['automation.task.example'].create({'name': 'Auth Test'})
        self.task = example.task_id
        self.stage = self.env['automation.task.stage'].create({'task_id': self.task.id, 'name': 'Auth Test'})
        self.token = self.env['automation.task.token'].create({'task_id': self.task.id}).token

    def _post_log(self, token):
        headers = {'X-Automation-DB': self.env.cr.dbname}
        if token:
            headers['X-Automation-Token'] = token
        return self.url_open('/automation/log', data={
            'task_id': self.task.id,
            'stage_id': self.stage.id,
            'message': 'auth probe',
        }, headers=headers)

    def _probe_logs(self):
        return self.env['automation.task.log'].search([
            ('task_id', '=', self.task.id),
            ('message', '=', 'auth probe'),
        ])

    def test_valid_token(self):
        res = self._post_log(self.token)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(self._probe_logs()), 1)

    def test_unknown_token(self):
        res = self._post_log('not-a-token')
        self.assertEqual(res.status_code, 400)
        self.assertFalse(self._probe_logs())

    def test_missing_token(self):
        res = self._post_log(None)
        self.assertEqual(res.status_code, 400)
        self.assertFalse(self._probe_logs())
