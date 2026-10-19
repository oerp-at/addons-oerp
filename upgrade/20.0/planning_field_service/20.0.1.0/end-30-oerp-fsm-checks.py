"""Check the converted Field Service data against the staging of base pre-70.

Logs the number of slots per state next to the expected split of the staged
tasks, and a warning for every task whose slot has no resource (open shift) or
no dates (unscheduled).
"""
import logging

from odoo.upgrade import util

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not util.table_exists(cr, "_oerp_fsm_task"):
        return
    cr.execute(
        """
        SELECT CASE WHEN t.state = '1_done' OR t.fsm_done THEN '4_completed' ELSE 'open' END AS expected,
               s.state, count(*)
          FROM _oerp_fsm_task t
     LEFT JOIN planning_slot s ON s.id = t.slot_id
      GROUP BY 1, 2
      ORDER BY 1, 2
        """
    )
    split = cr.fetchall()
    _logger.info("Field Service: staged task state -> slot state: %s",
                 ", ".join(f"{e} -> {s or 'no slot'}: {n}" for e, s, n in split))
    for expected, state, count in split:
        if not state:
            _logger.error("Field Service: %s staged tasks (%s) have no planning slot", count, expected)
        elif expected == "4_completed" and state != "4_completed":
            _logger.warning("Field Service: %s done tasks are %s slots", count, state)
        elif expected == "open" and state == "4_completed":
            _logger.warning("Field Service: %s open tasks are completed slots", count)

    cr.execute(
        """
        SELECT t.task_id, t.name, s.id,
               NOT EXISTS (SELECT 1 FROM planning_slot_resource_resource_rel r WHERE r.planning_slot_id = s.id),
               s.start_datetime IS NULL
          FROM _oerp_fsm_task t
          JOIN planning_slot s ON s.id = t.slot_id
         WHERE s.start_datetime IS NULL
            OR NOT EXISTS (SELECT 1 FROM planning_slot_resource_resource_rel r WHERE r.planning_slot_id = s.id)
         ORDER BY t.task_id
        """
    )
    for task_id, name, slot_id, no_resource, no_dates in cr.fetchall():
        _logger.warning(
            "Field Service: task %s %r -> slot %s %s", task_id, name, slot_id,
            " and ".join(m for m, c in (("without resource (open shift)", no_resource),
                                        ("without dates (unscheduled)", no_dates)) if c),
        )

    cr.execute(
        """
        SELECT (SELECT count(*) FROM _oerp_fsm_ws_row WHERE task_id IS NOT NULL),
               (SELECT count(*) FROM planning_slot s JOIN _oerp_fsm_task t ON t.slot_id = s.id
                 WHERE s.worksheet_properties IS NOT NULL AND s.worksheet_properties::text NOT IN ('{}', 'null')),
               (SELECT count(DISTINCT recurrence_id) FROM _oerp_fsm_task),
               (SELECT count(DISTINCT s.recurrency_id) FROM planning_slot s JOIN _oerp_fsm_task t ON t.slot_id = s.id)
        """
    )
    rows, worksheets, recurrences, recurrencies = cr.fetchone()
    _logger.info("Field Service: worksheets %s staged / %s on slots, recurrences %s staged / %s planning",
                 rows, worksheets, recurrences, recurrencies)
    if worksheets < rows:
        _logger.warning("Field Service: %s of %s worksheets were not moved to their slot", rows - worksheets, rows)
