"""res.country ``zip_required`` (boolean) is ``zip_applicability`` in 20.0.

Country data is noupdate, so every country would stay 'required'. Countries
still on the 19.0 shipped value get the 20.0 shipped value (many are
'not_applicable' now); countries changed by the tenant keep their choice
(True -> required, False -> optional).
"""
import logging

from lxml import etree

from odoo.tools.misc import file_open
from odoo.upgrade import util

_logger = logging.getLogger(__name__)

#: base xml ids of the countries 19.0 shipped with zip_required = False
NOT_REQUIRED_19 = {"ao", "bj", "bz", "cl", "ec", "hk", "ie", "mo", "pe", "vn"}


def _shipped_20():
    with file_open("base/data/res_country_data.xml", "rb") as f:
        tree = etree.parse(f)
    return {
        rec.get("id"): rec.findtext("field[@name='zip_applicability']") or "required"
        for rec in tree.iterfind(".//record[@model='res.country']")
    }


def migrate(cr, version):
    if not util.column_exists(cr, "res_country", "zip_required"):
        return
    shipped = _shipped_20()
    cr.execute(
        """
        SELECT c.id, d.name, c.zip_required
          FROM res_country c
     LEFT JOIN ir_model_data d ON d.model = 'res.country' AND d.module = 'base' AND d.res_id = c.id
        """
    )
    changed = 0
    for country_id, xmlid, zip_required in cr.fetchall():
        unchanged = xmlid and bool(zip_required) == (xmlid not in NOT_REQUIRED_19)
        if unchanged and xmlid in shipped:
            value = shipped[xmlid]
        else:
            value = "required" if zip_required else "optional"
        cr.execute("UPDATE res_country SET zip_applicability = %s WHERE id = %s AND zip_applicability IS DISTINCT FROM %s",
                   [value, country_id, value])
        changed += cr.rowcount
    _logger.info("zip_applicability set on %s countries", changed)
