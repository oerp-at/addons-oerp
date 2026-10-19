"""Reset mail templates that still call ``ir.config_parameter.get_param``.

20.0 removed ``get_param`` (now ``get_str``/``get_int``/...). Standard
templates are noupdate, so they keep their 19.0 body and fail to render, e.g.
``auth_signup.set_password_email`` on every new user. Templates of an
installed module are reset to their 20.0 definition (body, subject and their
translations); a template without one is only reported.
"""
import logging

from odoo.upgrade import util

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute(
        """
        SELECT t.id, d.module || '.' || d.name, m.state
          FROM mail_template t
          LEFT JOIN ir_model_data d ON d.model = 'mail.template' AND d.res_id = t.id
          LEFT JOIN ir_module_module m ON m.name = d.module
         WHERE t.body_html::text LIKE '%%get_param(%%'
            OR t.subject::text LIKE '%%get_param(%%'
        """
    )
    for template_id, xmlid, state in cr.fetchall():
        if xmlid and state == "installed":
            util.update_record_from_xml(
                cr, xmlid, fields=("body_html", "subject"), reset_translations={"body_html", "subject"}
            )
            _logger.info("mail template %s (%s) reset to its 20.0 version", template_id, xmlid)
        else:
            _logger.warning(
                "mail template %s (%s) still calls ir.config_parameter.get_param, adapt it by hand",
                template_id, xmlid or "no xml id",
            )
