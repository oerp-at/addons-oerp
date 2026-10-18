"""Column changes in base that the ORM would convert wrongly.

- ir.actions.client ``params_store``: bytea -> text; a plain cast yields hex
  ('\\x7b...') and breaks the client actions (e.g. the POS menus)
- res.device.log: ``user_agent`` is required in 20.0 (19.0 had platform and
  browser), ``user_id`` is a plain integer without foreign key
"""
from odoo.upgrade import util


def migrate(cr, version):
    if util.column_type(cr, "ir_act_client", "params_store") == "bytea":
        util.alter_column_type(cr, "ir_act_client", "params_store", "text",
                               using="convert_from({0}, 'UTF8')")

    if util.table_exists(cr, "res_device_log"):
        if not util.column_exists(cr, "res_device_log", "user_agent"):
            util.create_column(cr, "res_device_log", "user_agent", "varchar")
        if util.column_exists(cr, "res_device_log", "platform"):
            cr.execute(
                """
                UPDATE res_device_log
                   SET user_agent = COALESCE(NULLIF(concat_ws(' ', platform, browser), ''), 'unknown')
                 WHERE user_agent IS NULL
                """
            )
        cr.execute("ALTER TABLE res_device_log DROP CONSTRAINT IF EXISTS res_device_log_user_id_fkey")
