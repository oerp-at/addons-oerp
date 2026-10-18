"""Neutralise the 19.0 inheriting views of all modules before they load.

While a module upgrades, Odoo validates each of its views together with all
views inheriting from it. Inheriting views of modules that load later still
carry their 19.0 arch and fail on fields removed in 20.0 (e.g. the mail server
action extension on ``mail_post_method`` breaks loading the mail cron view).

The arch of every module-owned inheriting view is replaced by an empty
``<data/>``; each module writes its 20.0 arch back while it upgrades, views
dropped in 20.0 are removed with their xml id at the end of the update.
noupdate and custom views (no xml id, ``__export__``, ...) are kept as they
are and only counted, they have to be checked after the migration.
"""
import json
import logging

_logger = logging.getLogger(__name__)

CUSTOM_MODULES = ("__export__", "__custom__", "studio_customization")
EMPTY_ARCH = json.dumps({"en_US": "<data/>"})


def migrate(cr, version):
    cr.execute(
        """
        UPDATE ir_ui_view v
           SET arch_db = %s::jsonb
          FROM ir_model_data d
         WHERE d.model = 'ir.ui.view' AND d.res_id = v.id
           AND d.module NOT IN %s AND NOT COALESCE(d.noupdate, false)
           AND v.inherit_id IS NOT NULL
        """,
        [EMPTY_ARCH, CUSTOM_MODULES],
    )
    _logger.info("%s inheriting views neutralised until their module upgrades", cr.rowcount)

    cr.execute(
        """
        SELECT v.id, v.name
          FROM ir_ui_view v
         WHERE v.inherit_id IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM ir_model_data d
                            WHERE d.model = 'ir.ui.view' AND d.res_id = v.id
                              AND d.module NOT IN %s AND NOT COALESCE(d.noupdate, false))
        """,
        [CUSTOM_MODULES],
    )
    kept = cr.fetchall()
    if kept:
        _logger.warning(
            "%s custom/noupdate inheriting views kept with their 19.0 arch, check them: %s",
            len(kept), ", ".join(f"{name} ({vid})" for vid, name in kept),
        )
