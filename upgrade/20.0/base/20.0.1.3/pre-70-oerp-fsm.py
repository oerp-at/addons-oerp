"""Field Service 19.0 (industry_fsm*) -> 20.0 (planning_field_service*).

20.0 has no FSM projects and no generated worksheet models: an intervention is
a planning.slot and the worksheet values are properties of the slot. No module
ships a migration, ``odoo migrate`` leaves the industry_fsm* modules to the
cleanup, which drops their columns, the x_ worksheet tables and the records
they own by xml id.

This script runs while all 19.0 data is still there and only prepares:

- stages the FSM tasks, the worksheet templates (fields, views, rows) and the
  sale order links into ``_oerp_fsm_*`` tables; they are kept after the
  migration for comparison
- moves the xml ids of the default records (project, stages, product, mail
  alias, worksheet template) to the 20.0 modules, so the cleanup keeps them
- moves product.template ``worksheet_template_id`` to its 20.0 module
- installs planning_field_service, its worksheet module and project_forecast
  (slot <-> task/project link) and makes the planning_field_service scripts
  run (``planning_field_service/20.0.1.0/end-*``), which convert the data;
  two bridge modules are installed without their post_init hook
- keeps website_planning_field_service (public service request form) from
  being auto installed

Nothing happens on databases that never had industry_fsm installed.
"""
import logging

from odoo.upgrade import util

_logger = logging.getLogger(__name__)

#: the Field Service modules of 19.0, uninstalled by the cleanup
FSM_MODULES = [
    "industry_fsm", "industry_fsm_report", "industry_fsm_sale", "industry_fsm_sale_report",
    "industry_fsm_sale_subscription", "industry_fsm_sms", "industry_fsm_stock",
    "l10n_din5008_industry_fsm", "documents_fsm",
]

#: 20.0 modules installed in place of industry_fsm; the bridges auto install
SUCCESSORS = ["planning_field_service", "planning_field_service_worksheet", "project_forecast"]

#: installed like an upgrade, without init mode and post_init hook: the hooks
#: save all settings, which fails while modules are 'to upgrade' (hr wants to
#: install hr_attendance); planning_field_service end-05 does their part.
#: Without init mode their noupdate data also leaves the moved records alone.
NO_POST_INIT = ["planning_field_service_worksheet", "planning_field_service_sale_timesheet"]

#: auto install modules of 20.0 that FSM databases do not get
NO_AUTO_INSTALL = ["website_planning_field_service"]

#: default records owned by the industry_fsm modules: old xml id -> 20.0 xml id
MOVED_XMLIDS = {
    "industry_fsm.fsm_project": "planning_field_service_sale_timesheet.fsm_project",
    "industry_fsm.fsm_project_mail_alias": "planning_field_service_sale_timesheet.fsm_project_mail_alias",
    **{
        f"industry_fsm.planning_project_stage_{i}": f"planning_field_service_sale_timesheet.planning_project_stage_{i}"
        for i in range(5)
    },
    "industry_fsm_sale.field_service_product": "planning_field_service_sale_timesheet.field_service_product",
    "industry_fsm_sale.field_service_product_product_template":
        "planning_field_service_sale_timesheet.field_service_product_product_template",
    "industry_fsm_report.fsm_worksheet_template": "planning_field_service_worksheet.fsm_worksheet_template",
}


def fsm_installed(cr):
    """industry_fsm was installed in 19.0

    ``odoo migrate`` resets the state of unavailable modules to 'uninstalled'
    before the update, the version and the FSM columns stay.
    """
    cr.execute("SELECT 1 FROM ir_module_module WHERE name = 'industry_fsm' AND latest_version IS NOT NULL")
    return bool(cr.rowcount) and util.column_exists(cr, "project_project", "is_fsm")


def _col(cr, table, column, cast, alias="t"):
    """``alias.column`` if the column exists, else a typed NULL"""
    if util.column_exists(cr, table, column):
        return f"{alias}.{column}"
    return f"NULL::{cast}"


def _stage_tasks(cr):
    cr.execute("DROP TABLE IF EXISTS _oerp_fsm_task")
    cr.execute(
        f"""
        CREATE TABLE _oerp_fsm_task AS
        SELECT t.id AS task_id,
               t.project_id,
               t.company_id,
               t.name,
               t.description,
               t.partner_id,
               t.active,
               {_col(cr, "project_task", "planned_date_begin", "timestamp")} AS planned_date_begin,
               t.date_deadline,
               t.allocated_hours,
               t.state,
               {_col(cr, "project_task", "fsm_done", "boolean")} AS fsm_done,
               {_col(cr, "project_task", "worksheet_template_id", "integer")} AS worksheet_template_id,
               {_col(cr, "project_task", "sale_line_id", "integer")} AS sale_line_id,
               t.recurring_task,
               t.recurrence_id,
               r.repeat_interval,
               r.repeat_unit,
               r.repeat_type,
               r.repeat_until,
               ARRAY(SELECT u.user_id FROM project_task_user_rel u WHERE u.task_id = t.id ORDER BY u.user_id)
                   AS user_ids,
               NULL::integer AS slot_id
          FROM project_task t
          JOIN project_project p ON p.id = t.project_id
     LEFT JOIN project_task_recurrence r ON r.id = t.recurrence_id
         WHERE p.is_fsm
           AND NOT COALESCE(t.is_template, false)
        """
    )
    count = cr.rowcount
    cr.execute("ALTER TABLE _oerp_fsm_task ADD PRIMARY KEY (task_id)")
    return count


def _stage_worksheets(cr):
    for table in ("_oerp_fsm_ws_template", "_oerp_fsm_ws_view", "_oerp_fsm_ws_field", "_oerp_fsm_ws_row"):
        cr.execute(f"DROP TABLE IF EXISTS {table}")
    cr.execute(
        """
        CREATE TABLE _oerp_fsm_ws_template AS
        SELECT w.id AS template_id, w.name, w.res_model, w.company_id, w.sequence, w.active,
               m.model, NULL::boolean AS converted
          FROM worksheet_template w
     LEFT JOIN ir_model m ON m.id = w.model_id
         WHERE w.res_model = 'project.task'
        """
    )
    # the form view of the generated model, Studio adds its fields by extension views
    cr.execute(
        """
        CREATE TABLE _oerp_fsm_ws_view AS
        SELECT w.template_id, v.id AS view_id, v.inherit_id, v.mode, v.priority,
               v.arch_db->>'en_US' AS arch
          FROM _oerp_fsm_ws_template w
          JOIN ir_ui_view v ON v.model = w.model AND v.type = 'form' AND v.active
        """
    )
    cr.execute(
        """
        CREATE TABLE _oerp_fsm_ws_field AS
        SELECT w.template_id, f.id AS field_id, f.name, f.ttype, f.field_description AS label,
               f.relation, f.related, f.store,
               (SELECT jsonb_agg(jsonb_build_array(s.value, COALESCE(s.name->>'de_DE', s.name->>'en_US'))
                                 ORDER BY s.sequence, s.id)
                  FROM ir_model_fields_selection s WHERE s.field_id = f.id) AS selection,
               (SELECT d.json_value FROM ir_default d
                 WHERE d.field_id = f.id AND d.user_id IS NULL AND d.company_id IS NULL
                   AND d.condition IS NULL
                 LIMIT 1) AS default_value,
               NULL::varchar AS prop_name
          FROM _oerp_fsm_ws_template w
          JOIN ir_model_fields f ON f.model = w.model
        """
    )
    cr.execute("CREATE TABLE _oerp_fsm_ws_row (template_id integer, task_id integer, vals jsonb)")
    cr.execute("SELECT template_id, model FROM _oerp_fsm_ws_template WHERE model IS NOT NULL")
    rows = 0
    for template_id, model in cr.fetchall():
        table = util.table_of_model(cr, model)
        if not util.table_exists(cr, table):
            continue
        cr.execute(
            util.format_query(
                cr,
                "INSERT INTO _oerp_fsm_ws_row SELECT %s, x.x_project_task_id, to_jsonb(x) FROM {} x",
                table,
            ),
            [template_id],
        )
        rows += cr.rowcount
    return rows


def _stage_records(cr):
    """19.0 values of the default records, init mode of the 20.0 modules overwrites them"""
    cr.execute("DROP TABLE IF EXISTS _oerp_fsm_record")
    cr.execute("CREATE TABLE _oerp_fsm_record (xmlid varchar, model varchar, res_id integer, vals jsonb)")
    for xmlid in MOVED_XMLIDS:
        module, name = xmlid.split(".", 1)
        cr.execute(
            "SELECT model, res_id FROM ir_model_data WHERE module = %s AND name = %s", [module, name]
        )
        row = cr.fetchone()
        if not row:
            continue
        model, res_id = row
        table = util.table_of_model(cr, model)
        cr.execute(
            util.format_query(
                cr,
                "INSERT INTO _oerp_fsm_record SELECT %s, %s, %s, to_jsonb(r) FROM {} r WHERE r.id = %s",
                table,
            ),
            [MOVED_XMLIDS[xmlid], model, res_id, res_id],
        )


def _stage_sale_orders(cr):
    cr.execute("DROP TABLE IF EXISTS _oerp_fsm_sale_order")
    if not util.column_exists(cr, "sale_order", "task_id"):
        cr.execute("CREATE TABLE _oerp_fsm_sale_order (sale_order_id integer, task_id integer)")
        return
    cr.execute(
        """
        CREATE TABLE _oerp_fsm_sale_order AS
        SELECT id AS sale_order_id, task_id FROM sale_order WHERE task_id IS NOT NULL
        """
    )


def _free_action_paths(cr):
    """the 20.0 actions reuse the paths of the 19.0 ones (e.g. field-service-worksheet-templates),
    which stay until the cleanup uninstalls their modules"""
    cr.execute(
        "SELECT DISTINCT model FROM ir_model_data WHERE module IN %s AND model LIKE 'ir.actions.%%'",
        [tuple(FSM_MODULES)],
    )
    for (model,) in cr.fetchall():
        table = util.table_of_model(cr, model)
        if not util.column_exists(cr, table, "path"):
            continue
        cr.execute(
            util.format_query(
                cr,
                """
                UPDATE {} a
                   SET path = NULL
                  FROM ir_model_data d
                 WHERE d.model = %s AND d.res_id = a.id AND d.module IN %s AND a.path IS NOT NULL
                """,
                table,
            ),
            [model, tuple(FSM_MODULES)],
        )


def migrate(cr, version):
    if not fsm_installed(cr):
        return

    tasks = _stage_tasks(cr)
    rows = _stage_worksheets(cr)
    _stage_records(cr)
    _stage_sale_orders(cr)
    _free_action_paths(cr)
    _logger.info("Field Service: staged %s tasks and %s worksheet rows for planning_field_service", tasks, rows)

    for old, new in MOVED_XMLIDS.items():
        if util.ref(cr, old) and not util.ref(cr, new):
            util.rename_xmlid(cr, old, new)

    util.move_field_to_module(
        cr, "product.template", "worksheet_template_id",
        "industry_fsm_sale_report", "planning_field_service_sale_worksheet",
    )

    for module in SUCCESSORS:
        util.force_install_module(cr, module, reason="it replaces industry_fsm (Field Service)")
    util.force_upgrade_of_fresh_module(cr, "planning_field_service")
    for module in NO_POST_INIT:
        util.force_upgrade_of_fresh_module(cr, module, init=False)
    util.ENVIRON["__modules_to_skip_autoinstall"].update(NO_AUTO_INSTALL)
