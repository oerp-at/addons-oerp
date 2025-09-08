from werkzeug.exceptions import BadRequest

from odoo import models
from odoo.http import request
from odoo.modules.registry import Registry


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _auth_method_automation_task(cls):
        token = request.httprequest.headers['X-Automation-Token']
        dbname = request.httprequest.headers['X-Automation-DB']

        #  check header
        if not dbname:
            raise BadRequest('Database not specified')
        if not token:
            raise BadRequest('Token not specified')

        # check token
        registry = Registry(dbname)
        with registry.cursor() as cr:
            cr.execute('SELECT COUNT(id) FROM automation_task_token WHERE token = %s', (token,))
            token = cr.fetchall()
            if not token:
                raise BadRequest('Token not found')
            if request.session.uid:
                raise BadRequest('There should no user been set')

        return True
