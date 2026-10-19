"""planning.slot ``state``: 'draft'/'published' are '1_draft'/'2_published' in 20.0."""
from odoo.upgrade import util


def migrate(cr, version):
    util.change_field_selection_values(
        cr, "planning.slot", "state", {"draft": "1_draft", "published": "2_published"})
