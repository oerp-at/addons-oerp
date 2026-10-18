"""Free the xml ids of 19.0 access rights and record rules for ir.access.

Odoo 20.0 replaces ``ir.model.access`` and ``ir.rule`` by one model
``ir.access``. The modules define the new records under the old xml ids
(``ir.access.csv``), so the 19.0 ``ir.model.data`` rows still pointing at the
old models make the data import fail ("found record of different model").

Records owned by a module are dropped from ``ir.model.data`` here; every
module re-creates them as ``ir.access`` while it is upgraded. The old rows stay
in ``ir_model_access``/``ir_rule`` until base removes those models.

Custom records (no xml id or ``__export__``/``__custom__``) are not converted,
19.0 rules and 20.0 accesses differ in meaning. They are counted and logged
as warning so they can be recreated by hand.
"""
import logging

_logger = logging.getLogger(__name__)

OLD_MODELS = {"ir.model.access": "ir_model_access", "ir.rule": "ir_rule"}
CUSTOM_MODULES = ("__export__", "__custom__", "studio_customization")


def migrate(cr, version):
    for model, table in OLD_MODELS.items():
        cr.execute("SELECT to_regclass(%s)", [table])
        if not cr.fetchone()[0]:
            continue

        cr.execute(
            f"""
            SELECT t.id, t.name
              FROM {table} t
             WHERE NOT EXISTS (SELECT 1 FROM ir_model_data d
                                WHERE d.model = %s AND d.res_id = t.id
                                  AND d.module NOT IN %s)
            """,
            [model, CUSTOM_MODULES],
        )
        custom = cr.fetchall()
        if custom:
            _logger.warning(
                "%s custom %s records are not converted to ir.access, recreate them: %s",
                len(custom), model, ", ".join(f"{name} ({rid})" for rid, name in custom),
            )

        cr.execute(
            "DELETE FROM ir_model_data WHERE model = %s AND module NOT IN %s",
            [model, CUSTOM_MODULES],
        )
        _logger.info("%s: %s xml ids released for ir.access", model, cr.rowcount)
