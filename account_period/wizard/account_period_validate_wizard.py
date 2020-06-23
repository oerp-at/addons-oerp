# -*- coding: utf-8 -*--
# © 2017 Funkring.net (Martin Reisenhofer <martin.reisenhofer@funkring.net>)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from openerp import api, fields, models


class AccountPeriodValidateWizard(models.TransientModel):
    _name = 'account.period.validate.wizard'
    _description = 'Validate Wizard'

    #name = fields.Char(string='Name', default="/")

    def _get_period_entries(self):        
        return self.env["account.period.entry"].browse(
            self._context.get("active_model") == "account.period.entry" and self._context.get("active_ids") or []
        )

    @api.multi
    def action_validate(self):
        self._get_period_entries().action_validate()
        return True

    @api.multi
    def action_reset(self):
        self._get_period_entries().action_reset()
        return True

