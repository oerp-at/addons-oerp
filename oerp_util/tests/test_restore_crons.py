from odoo.cli.restore import deactivate_crons
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestRestoreCrons(TransactionCase):
    """A defused copy keeps its crons off after the module update (14007).

    ``odoo restore --neutralize --update`` neutralizes, then updates all
    modules - and the update switches crons of the module data on again.
    """

    def test_every_cron_off_but_the_autovacuum(self):
        crons = self.env['ir.cron'].with_context(active_test=False).search([])
        autovacuum = self.env.ref('base.autovacuum_job')
        crons.write({'active': True})
        crons.flush_recordset()
        self.assertEqual(deactivate_crons(self.env.cr), len(crons) - 1)
        self.env.invalidate_all()
        self.assertTrue(autovacuum.active)
        self.assertFalse((crons - autovacuum).filtered('active'))
        # Nothing left to switch off the second time.
        self.assertEqual(deactivate_crons(self.env.cr), 0)
