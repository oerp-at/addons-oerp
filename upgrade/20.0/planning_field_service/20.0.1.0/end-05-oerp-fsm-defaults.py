"""Field Service defaults after the install of planning_field_service.

base pre-70 installs planning_field_service_worksheet and
planning_field_service_sale_timesheet without their post_init hooks, this
script does their part:

- worksheets (customer report) and products on shifts are on, 19.0 had them
  on all FSM projects
- the companies plan their field service time in the Field Service project
  (19.0 "Außendienst") and invoice travel with the travel fees product

base pre-70 also moved the xml ids of the 19.0 default records to the 20.0
modules. Should a 20.0 data file have been loaded over them (init mode ignores
noupdate), the columns these files set get their 19.0 values back, by SQL, so
no compute runs.
"""
import json
import logging

from odoo.upgrade import util

_logger = logging.getLogger(__name__)

#: model -> columns the 20.0 data files of planning_field_service_sale_timesheet write
RESTORED_COLUMNS = {
    "project.project": ["name", "label_tasks", "user_id", "allow_timesheets", "allow_billable"],
    "project.task.type": ["name", "sequence", "fold"],
    "product.template": [
        "name", "type", "service_tracking", "categ_id", "list_price", "uom_id", "invoice_policy",
        "service_type", "planning_enabled", "planning_role_id", "purchase_ok", "sale_ok",
    ],
}


def migrate(cr, version):
    if not util.table_exists(cr, "_oerp_fsm_record"):
        return
    env = util.env(cr)
    features = [
        ("planning_field_service_worksheet", "planning.group_field_service_allow_customer_report"),
        ("planning_field_service_sale_timesheet", "planning.group_field_service_allow_material"),
    ]
    for module, xmlid in features:
        group = env.ref(xmlid, raise_if_not_found=False)
        if group and util.module_installed(cr, module):
            env.ref("base.group_user")._apply_group(group)
    project = env.ref("planning_field_service_sale_timesheet.fsm_project", raise_if_not_found=False)
    travel = env.ref("planning_field_service_sale_timesheet.field_service_product_travel_invoice",
                     raise_if_not_found=False)
    if project and travel:
        env["res.company"].search([]).write({
            "planning_project_id": project.id,
            "travel_time_invoicing_product_id": travel.id,
        })

    cr.execute("SELECT xmlid, model, res_id, vals FROM _oerp_fsm_record ORDER BY xmlid")
    for xmlid, model, res_id, vals in cr.fetchall():
        table = util.table_of_model(cr, model)
        columns = [c for c in RESTORED_COLUMNS.get(model, ()) if c in vals and util.column_exists(cr, table, c)]
        if not columns:
            continue
        cr.execute(
            util.format_query(cr, "SELECT to_jsonb(r) FROM {} r WHERE r.id = %s", table), [res_id]
        )
        row = cr.fetchone()
        if not row:
            _logger.warning("Field Service: %s (%s %s) is gone, not restored", xmlid, model, res_id)
            continue
        changed = [c for c in columns if row[0].get(c) != vals[c]]
        if not changed:
            continue
        for column in changed:
            value = vals[column]
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            cr.execute(
                util.format_query(cr, "UPDATE {} SET {} = %s WHERE id = %s", table, column), [value, res_id]
            )
        _logger.info("Field Service: restored 19.0 values of %s (%s): %s", xmlid, res_id, ", ".join(changed))
    env.invalidate_all()
