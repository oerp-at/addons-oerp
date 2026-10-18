"""Write the 19.0 tracking values into the message body, as 20.0 does when posting.

mail 20.0 no longer has the model mail.tracking.value (it is in the optional
module mail_tracking) and renders tracked changes into ``mail.message.body``
with ``message_type = 'tracking'``. 19.0 tracking messages have an empty body
and would show up as empty notes in the chatter. The table stays in place.
"""
import logging

from markupsafe import Markup

from odoo import fields
from odoo.tools import format_amount, format_date, format_datetime, formatLang
from odoo.upgrade import util

_logger = logging.getLogger(__name__)

#: field type -> suffix of the value columns of mail_tracking_value (default char)
COLUMNS = {
    "boolean": "integer", "integer": "integer", "float": "float", "monetary": "float",
    "date": "datetime", "datetime": "datetime", "text": "text",
}


def _to_datetime(value):
    return fields.Datetime.to_datetime(value.replace("T", " ")[:19])


def _format(env, ftype, value, currency):
    if ftype == "boolean":
        return env._("Yes") if value else env._("No")
    if value in (None, False, ""):
        return "None"
    if ftype == "monetary" and currency:
        return format_amount(env, value, currency)
    if ftype in ("float", "monetary"):
        return formatLang(env, value)
    if ftype == "integer":
        return formatLang(env, value, digits=0)
    if ftype == "date":
        return format_date(env, value)
    if ftype == "datetime":
        return format_datetime(env, value, tz=env.user.tz or "UTC")
    return value


def migrate(cr, version):
    if not util.table_exists(cr, "mail_tracking_value"):
        return
    env = util.env(cr)
    lang = env.ref("base.user_admin").lang or "en_US"
    env = env(context=dict(env.context, lang=lang))
    has_currency = util.column_exists(cr, "mail_tracking_value", "currency_id")
    cr.execute(
        f"""
        SELECT t.mail_message_id, COALESCE(f.ttype, t.field_info->>'type', 'char'),
               COALESCE(f.field_description->>%s, f.field_description->>'en_US',
                        t.field_info->>'desc', 'Unknown'),
               to_jsonb(t), {"t.currency_id" if has_currency else "NULL"}
          FROM mail_tracking_value t
          JOIN mail_message m ON m.id = t.mail_message_id
     LEFT JOIN ir_model_fields f ON f.id = t.field_id
         WHERE COALESCE(m.body, '') IN ('', '<p></p>')
      ORDER BY t.mail_message_id, t.id
        """,
        [lang],
    )
    by_message = {}
    for message_id, ftype, label, row, currency_id in cr.fetchall():
        column = COLUMNS.get(ftype, "char")
        currency = env["res.currency"].browse(currency_id) if currency_id else None
        old, new = row[f"old_value_{column}"], row[f"new_value_{column}"]
        if column == "datetime":
            old, new = old and _to_datetime(old), new and _to_datetime(new)
        by_message.setdefault(message_id, []).append({
            "field_label": label,
            "old_value": _format(env, ftype, old, currency),
            "new_value": _format(env, ftype, new, currency),
        })
    for message_id, values in by_message.items():
        body = env["ir.qweb"]._render("mail.mail_tracking_template", {"trackingValues": values})
        cr.execute("UPDATE mail_message SET body = %s, message_type = 'tracking' WHERE id = %s",
                   [Markup(body).strip(), message_id])
    _logger.info("tracking values written into %s message bodies", len(by_message))
