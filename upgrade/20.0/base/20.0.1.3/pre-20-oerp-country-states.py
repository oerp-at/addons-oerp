"""Follow renamed XML ids of country states.

Odoo renames state XML ids between versions (e.g. Odisha: base.state_in_or ->
base.state_in_od). Loading the new CSV would then try to create the state a
second time and fail on the unique (country, code) constraint. Every base
state whose XML id is no longer in the CSV, but whose country and code are,
gets the new XML id instead.
"""
import csv
import logging

from odoo.tools.misc import file_open

from odoo.upgrade import util

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    with file_open("base/data/res.country.state.csv") as f:
        rows = list(csv.DictReader(f))
    new_by_key = {(row["country_id:id"], row["code"]): row["id"] for row in rows}
    new_ids = set(new_by_key.values())

    cr.execute(
        """
        SELECT d.name, cd.name, s.code
          FROM ir_model_data d
          JOIN res_country_state s ON s.id = d.res_id
          JOIN ir_model_data cd ON cd.model = 'res.country' AND cd.module = 'base'
                               AND cd.res_id = s.country_id
         WHERE d.model = 'res.country.state' AND d.module = 'base'
        """
    )
    for old_name, country, code in cr.fetchall():
        if old_name in new_ids:
            continue
        new_name = new_by_key.get((country, code))
        if new_name:
            _logger.info("state %s/%s: base.%s -> base.%s", country, code, old_name, new_name)
            util.rename_xmlid(cr, f"base.{old_name}", f"base.{new_name}", on_collision="merge")
