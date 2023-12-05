from werkzeug.exceptions import BadRequest

import odoo
from odoo import models, SUPERUSER_ID
from odoo.http import request
from odoo.api import Environment


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _auth_method_automation_task(cls):
        token = request.params['token']
        dbname = request.params['db']

        #check header
        if not dbname:
            raise BadRequest("Database not specified.")
        if not token:
            raise BadRequest("Token not specified.")

        # check token
        registry = odoo.registry(dbname)
        with registry.cursor() as _cr:
            env = Environment(_cr, SUPERUSER_ID, {})
            token = env['automation.task.token'].sudo().search([('token', '=', token)], limit=1)
            if not token:
                raise BadRequest("Token not found.")    
            if request.session.uid:
                raise BadRequest("There should no user been set.")

        return True
