"""Convert the 19.0 working schedules for resource 20.0.

- break lines (``day_period = 'lunch'``) are gone in 20.0, a kept 12-13 line
  would count as working time (40 -> 45 hours a week)
- ``schedule_type``/``two_weeks_calendar`` became ``calendar_type``
- the time zone moved from the calendar to the company
"""
import logging

from odoo.upgrade import util

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if util.column_exists(cr, "resource_calendar_attendance", "day_period"):
        cond = "day_period = 'lunch'"
        if util.column_exists(cr, "resource_calendar_attendance", "display_type"):
            cond += " OR display_type IS NOT NULL"
        cr.execute(f"DELETE FROM resource_calendar_attendance WHERE {cond}")
        _logger.info("%s break/section lines removed from working schedules", cr.rowcount)

    if (not util.column_exists(cr, "resource_calendar", "calendar_type")
            and util.column_exists(cr, "resource_calendar", "schedule_type")):
        util.create_column(cr, "resource_calendar", "calendar_type", "varchar")
        cr.execute(
            """
            UPDATE resource_calendar SET calendar_type = CASE
                   WHEN schedule_type = 'flexible' THEN 'undefined'
                   WHEN two_weeks_calendar THEN 'variable'
                   ELSE 'fixed' END
            """
        )

    if not util.column_exists(cr, "res_company", "tz") and util.column_exists(cr, "resource_calendar", "tz"):
        util.create_column(cr, "res_company", "tz", "varchar")
        cr.execute(
            """
            UPDATE res_company c SET tz = rc.tz
              FROM resource_calendar rc WHERE rc.id = c.resource_calendar_id
            """
        )
