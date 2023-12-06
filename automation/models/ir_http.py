from werkzeug.exceptions import BadRequest

import odoo
from odoo import models
from odoo.http import request


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _auth_method_automation_task(cls):
        token = request.header['Log-Token']
        dbname = request.header['Log-DB']

        #check header
        if not dbname:
            raise BadRequest("Database not specified.")
        if not token:
            raise BadRequest("Token not specified.")

        # check token
        registry = odoo.registry(dbname)
        with registry.cursor() as cr:
            cr.execute("SELECT COUNT(id) FROM automation_task_token WHERE token = %s", (token,))
            token = cr.fetchall()
            if not token:
                raise BadRequest("Token not found.")
            if request.session.uid:
                raise BadRequest("There should no user been set.")

        return True
