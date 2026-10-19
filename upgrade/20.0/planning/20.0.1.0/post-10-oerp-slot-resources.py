"""planning.slot ``resource_id`` (one resource) is ``resource_ids`` in 20.0.

The 19.0 column is still there after the update of planning; the cleanup
drops it afterwards.
"""
from odoo.upgrade import util


def migrate(cr, version):
    if not util.column_exists(cr, "planning_slot", "resource_id"):
        return
    cr.execute(
        """
        INSERT INTO planning_slot_resource_resource_rel (planning_slot_id, resource_resource_id)
             SELECT id, resource_id FROM planning_slot WHERE resource_id IS NOT NULL
        ON CONFLICT DO NOTHING
        """
    )
