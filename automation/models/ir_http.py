from werkzeug.exceptions import BadRequest

from odoo import models
from odoo.http import request
from odoo.modules.registry import Registry


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _auth_method_automation_task(cls, routing):
        headers = request.httprequest.headers
        token = headers.get('X-Automation-Token')
        dbname = headers.get('X-Automation-DB')

        # check header
        if not dbname:
            raise BadRequest("Database not specified")
        if not token:
            raise BadRequest("Token not specified")
        if request.session.uid:
            raise BadRequest("There should no user been set")

        # check token; a COUNT() always returns a row, so select the token itself
        with Registry(dbname).cursor() as cr:
            cr.execute("SELECT 1 FROM automation_task_token WHERE token = %s LIMIT 1", (token,))
            if not cr.fetchone():
                raise BadRequest("Token not found")
