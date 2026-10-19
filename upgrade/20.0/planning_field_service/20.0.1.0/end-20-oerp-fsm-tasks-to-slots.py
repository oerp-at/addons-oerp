"""Field Service tasks (19.0) become planning slots (20.0).

One slot per task staged by base pre-70 (``_oerp_fsm_task``), linked to the
task and its project (project_forecast); the task keeps its stage, chatter
and description. Per slot:

- window: planned_date_begin -> date_deadline as in 19.0 (often a maintenance
  period of 2 weeks or 3 months); only a deadline: the day before it; no
  dates: an unscheduled draft slot
- allocated hours: those of the task, also 0, so the window does not book the
  technician for all of it
- resources: the employees of the assigned users; users without an employee
  get one (an unlinked employee of the same name is linked instead)
- state: done tasks are completed, open ones with resources and dates are
  scheduled, the rest are drafts
- customer, worksheet template and worksheet values, sales order line as on
  the task; the technician role
- recurrence: a planning.recurrency per task recurrence takes over; the task
  recurrences are removed, otherwise both would create the next occurrence.
  ``last_generated_end_datetime`` is the end of the latest slot.

Sales orders created from a task point to its slot. Every slot gets the note
"Migrated from task #id". No tracking, no mails.
"""
import logging
from collections import defaultdict
from datetime import datetime, time, timedelta

from markupsafe import Markup

from odoo.tools import html2plaintext

from odoo.upgrade import util

_logger = logging.getLogger(__name__)

CONTEXT = {
    "tracking_disable": True,
    "mail_create_nolog": True,
    "mail_create_nosubscribe": True,
    "mail_notrack": True,
    "mail_auto_subscribe_no_notify": True,
    "no_reset_password": True,
    "active_test": False,
}


def _resources(env, user_ids_by_company):
    """resource of each (user, company); creates missing employees"""
    Employee = env["hr.employee"]
    result = {}
    for company_id, user_ids in user_ids_by_company.items():
        for user in env["res.users"].browse(sorted(user_ids)):
            employee = Employee.search(
                [("user_id", "=", user.id), ("company_id", "=", company_id)], limit=1, order="active desc, id"
            )
            if not employee:
                employee = Employee.search(
                    [("name", "=ilike", user.name), ("user_id", "=", False), ("company_id", "=", company_id),
                     ("active", "=", True)],
                )
                if len(employee) == 1:
                    employee.user_id = user
                    _logger.info("Field Service: employee %s %r linked to its user %s for the planning",
                                 employee.id, employee.name, user.login)
                else:
                    employee = Employee.create({"name": user.name, "user_id": user.id, "company_id": company_id})
                    _logger.info("Field Service: employee %s created for user %s for the planning",
                                 employee.id, user.login)
            result[user.id, company_id] = employee.resource_id.id
    return result


def _window(task):
    start, end = task["planned_date_begin"], task["date_deadline"]
    if start and end and start < end:
        return start, end
    if end:
        return end - timedelta(days=1), end
    if start:
        return start, start + timedelta(days=1)
    return False, False


def migrate(cr, version):
    if not util.table_exists(cr, "_oerp_fsm_task"):
        return
    env = util.env(cr)(context=dict(util.env(cr).context, **CONTEXT))

    cr.execute("SELECT * FROM _oerp_fsm_task WHERE slot_id IS NULL ORDER BY task_id")
    columns = [d[0] for d in cr.description]
    tasks = [dict(zip(columns, row)) for row in cr.fetchall()]
    if not tasks:
        return
    Task = env["project.task"]
    tasks = [t for t in tasks if Task.browse(t["task_id"]).exists()]

    users_by_company = defaultdict(set)
    for task in tasks:
        users_by_company[task["company_id"]].update(task["user_ids"] or [])
    resources = _resources(env, users_by_company)

    role = env.ref("planning_field_service_sale_timesheet.field_service_technician_role", raise_if_not_found=False)

    # worksheet values: slot property name of each staged x_ field
    cr.execute("SELECT template_id, name, prop_name FROM _oerp_fsm_ws_field WHERE prop_name IS NOT NULL")
    prop_names = defaultdict(dict)
    for template_id, name, prop_name in cr.fetchall():
        prop_names[template_id][name] = prop_name
    cr.execute("SELECT template_id, task_id, vals FROM _oerp_fsm_ws_row WHERE task_id IS NOT NULL")
    worksheets = {task_id: (template_id, vals) for template_id, task_id, vals in cr.fetchall()}

    # recurrences: one planning.recurrency per task recurrence with scheduled slots
    windows = {t["task_id"]: _window(t) for t in tasks}
    recurrencies = {}
    by_recurrence = defaultdict(list)
    for task in tasks:
        if task["recurrence_id"] and windows[task["task_id"]][0]:
            by_recurrence[task["recurrence_id"]].append(task)
    for recurrence_id, rec_tasks in sorted(by_recurrence.items()):
        first = rec_tasks[0]
        until = first["repeat_until"]
        repeat_type = first["repeat_type"] if first["repeat_type"] in ("forever", "until") else "forever"
        if repeat_type == "until" and not until:
            repeat_type = "forever"
        recurrencies[recurrence_id] = env["planning.recurrency"].create({
            "repeat_interval": first["repeat_interval"] or 1,
            "repeat_unit": first["repeat_unit"] or "year",
            "repeat_type": repeat_type,
            "repeat_until": datetime.combine(until, time.max) if repeat_type == "until" else False,
            "company_id": first["company_id"],
        })

    vals_list = []
    for task in tasks:
        start, end = windows[task["task_id"]]
        resource_ids = [resources[u, task["company_id"]] for u in task["user_ids"] or [] if (u, task["company_id"]) in resources]
        resource_ids = [r for r in resource_ids if r]
        if task["state"] == "1_done" or task["fsm_done"]:
            state = "4_completed" if start else "1_draft"
        elif resource_ids and start:
            state = "2_published"
        else:
            state = "1_draft"
        name = task["name"] or ""
        description = html2plaintext(task["description"] or "").strip()
        if description:
            name = f"{name}\n\n{description}"
        template_id = task["worksheet_template_id"]
        worksheet = worksheets.get(task["task_id"])
        if worksheet:
            template_id = worksheet[0]
        vals = {
            "name": name,
            "task_id": task["task_id"],
            "project_id": task["project_id"],
            "company_id": task["company_id"],
            "partner_id": task["partner_id"] or False,
            "resource_ids": [(6, 0, resource_ids)],
            "start_datetime": start,
            "end_datetime": end,
            "allocated_hours": task["allocated_hours"] or 0.0,
            "state": state,
            "worksheet_template_id": template_id or False,
            "role_id": role.id if role else False,
        }
        if not start:
            vals["allocated_percentage"] = 0.0
        if task["recurrence_id"] in recurrencies and start:
            vals["recurrency_id"] = recurrencies[task["recurrence_id"]].id
        if task["sale_line_id"]:
            vals["sale_line_id"] = task["sale_line_id"]
        vals_list.append(vals)

    # sale_planning 19.0 only allowed unscheduled slots with a sales order line,
    # 20.0 dropped that constraint; it goes at the end of the update (_process_end)
    cr.execute("ALTER TABLE planning_slot DROP CONSTRAINT IF EXISTS planning_slot_check_datetimes_set_or_plannable_slot")

    # small batches of close windows: the resource calendars are read for the
    # whole period of a batch (one task is dated in the year 2607)
    Slot = env["planning.slot"]
    slots = Slot
    batches = defaultdict(list)
    for vals in vals_list:
        batches[vals["start_datetime"].year if vals["start_datetime"] else 0].append(vals)
    for year in sorted(batches):
        batch = batches[year]
        for index in range(0, len(batch), 100):
            slots |= Slot.create(batch[index:index + 100])

    for slot in slots:
        cr.execute("UPDATE _oerp_fsm_task SET slot_id = %s WHERE task_id = %s", [slot.id, slot.task_id.id])

    # values the create computes may have changed: the 19.0 values win
    by_task = {s.task_id.id: s for s in slots}
    for vals in vals_list:
        slot = by_task[vals["task_id"]]
        fix = {
            key: vals[key] for key in ("project_id", "partner_id", "worksheet_template_id", "allocated_hours")
            if (slot[key].id if hasattr(slot[key], "id") else slot[key]) != vals[key]
        }
        if fix:
            slot.write(fix)

    # worksheet values
    for task_id, (template_id, row) in worksheets.items():
        slot = by_task.get(task_id)
        if not slot:
            _logger.warning("Field Service: worksheet of task %s without slot, not migrated", task_id)
            continue
        values = {}
        for field_name, prop_name in prop_names[template_id].items():
            value = row.get(field_name)
            if value in (None, False, "", [], {}):
                value = False
            values[prop_name] = value
        slot.worksheet_properties = values

    # recurrences: no backfill by the cron, the task recurrences end here
    for recurrency in recurrencies.values():
        ends = [s for s in recurrency.slot_ids.mapped("end_datetime") if s]
        if ends:
            recurrency.write({"last_generated_end_datetime": max(ends)})
    cr.execute(
        """
        UPDATE project_task t
           SET recurring_task = false, recurrence_id = NULL
          FROM _oerp_fsm_task s
         WHERE s.task_id = t.id
           AND (t.recurring_task OR t.recurrence_id IS NOT NULL)
        """
    )
    cr.execute(
        """
        DELETE FROM project_task_recurrence r
         WHERE r.id IN (SELECT recurrence_id FROM _oerp_fsm_task)
           AND NOT EXISTS (SELECT 1 FROM project_task t WHERE t.recurrence_id = r.id)
        """
    )
    removed = cr.rowcount

    # sales orders created from a task
    if util.column_exists(cr, "sale_order", "planning_slot_id"):
        cr.execute(
            """
            UPDATE sale_order o
               SET planning_slot_id = s.slot_id
              FROM _oerp_fsm_sale_order f
              JOIN _oerp_fsm_task s ON s.task_id = f.task_id
             WHERE o.id = f.sale_order_id
               AND s.slot_id IS NOT NULL
            """
        )
    env.invalidate_all()

    for slot in slots:
        slot.message_post(
            body=Markup("Migrated from task %s") % slot.task_id._get_html_link(title=f"#{slot.task_id.id}"),
            message_type="comment",
            subtype_xmlid="mail.mt_note",
        )

    _logger.info(
        "Field Service: %s tasks -> %s planning slots, %s recurrences (%s task recurrences removed), %s worksheets",
        len(tasks), len(slots), len(recurrencies), removed, len(worksheets),
    )
