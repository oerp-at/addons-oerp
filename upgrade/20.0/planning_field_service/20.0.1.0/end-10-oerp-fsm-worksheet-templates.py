"""Worksheet templates of project.task (19.0) become templates of planning.slot.

19.0 generated a model x_project_task_worksheet_template_<id> per template; in
20.0 a template holds a properties definition and the values are stored in
planning.slot ``worksheet_properties``. The definition is built from the fields
staged by base pre-70, in the order of the template's form view (Studio
included): every notebook page and every group with a title becomes a
separator. Fields that are not on the form only come along when a worksheet
holds a value for them. The custom QWeb layout of a template is not ported:
20.0 prints the properties with its generic worksheet report.

Templates that nothing uses (no worksheet, task, project or product) are
archived, e.g. the demo template "Device Installation and Maintenance".
"""
import json
import logging

from lxml import etree

from odoo.tools.template_inheritance import apply_inheritance_specs

from odoo.upgrade import util

_logger = logging.getLogger(__name__)

#: field types with the same property type
SAME_TYPES = {
    "boolean", "integer", "float", "char", "text", "html", "date", "datetime",
    "selection", "many2one", "many2many",
}

#: fields of the generated model that are no worksheet content
SKIPPED_FIELDS = {"id", "x_project_task_id", "x_name", "display_name"}
SKIPPED_PREFIXES = ("message_", "activity_", "my_activity_", "rating_", "website_message", "has_message")


def _combined_arch(views):
    """form arch of the generated model with its extension views applied"""
    primary = [v for v in views if v["mode"] == "primary" and not v["inherit_id"]]
    if not primary:
        return None
    arch = etree.fromstring(primary[0]["arch"])
    ids = {primary[0]["view_id"]}
    pending = sorted((v for v in views if v["inherit_id"]), key=lambda v: (v["priority"], v["view_id"]))
    progress = True
    while pending and progress:
        progress = False
        for view in list(pending):
            if view["inherit_id"] in ids:
                arch = apply_inheritance_specs(arch, etree.fromstring(view["arch"]))
                ids.add(view["view_id"])
                pending.remove(view)
                progress = True
    return arch


def _skipped(field):
    name = field["name"]
    return (
        name in SKIPPED_FIELDS
        or name in ("create_uid", "create_date", "write_uid", "write_date")
        or name.startswith(SKIPPED_PREFIXES)
        or field["ttype"] in ("one2many", "many2one_reference")
    )


def _label(field, arch_string=None):
    if arch_string and arch_string.strip():
        return arch_string.strip()
    label = field["label"] or {}
    return (label.get("de_DE") or label.get("en_US") or field["name"]).strip() or field["name"]


def _property(field, arch_string=None):
    """property definition of a staged field, None if it has no equivalent"""
    ttype = field["ttype"]
    if ttype == "binary":
        ptype = "signature"
    elif ttype == "monetary":
        ptype = "float"
    elif ttype in SAME_TYPES:
        ptype = ttype
    else:
        return None
    name = field["name"]
    if ptype == "html" and not name.endswith("_html"):
        name += "_html"
    elif ptype != "html" and name.endswith("_html"):
        name = name[: -len("_html")] + "_value"
    prop = {"name": name, "type": ptype, "string": _label(field, arch_string)}
    if ptype in ("many2one", "many2many"):
        prop["comodel"] = field["relation"]
        prop["domain"] = False
    if ptype == "selection":
        prop["selection"] = [list(s) for s in field["selection"] or []]
    default = field["default_value"]
    if default not in (None, False, "") and ptype not in ("many2one", "many2many", "signature"):
        prop["default"] = json.loads(default) if isinstance(default, str) else default
    return prop


def _definition(arch, fields, rows):
    definition, used = [], {}
    if arch is not None:
        sep = 0
        for node in arch.iter("page", "group", "field"):
            if node.tag in ("page", "group"):
                title = node.get("string")
                if title and title.strip():
                    sep += 1
                    definition.append({
                        "name": f"separator_{sep}", "type": "separator",
                        "string": title.strip(), "fold_by_default": False,
                    })
                continue
            field = fields.get(node.get("name"))
            if not field or field["name"] in used or _skipped(field):
                continue
            # fields inside a relational field's subview do not belong to the worksheet
            if any(parent.tag == "field" for parent in node.iterancestors()):
                continue
            prop = _property(field, node.get("string"))
            if prop:
                definition.append(prop)
                used[field["name"]] = prop["name"]
    # fields Studio removed from the form, kept when a worksheet has a value
    extra = []
    for field in fields.values():
        if field["name"] in used or _skipped(field):
            continue
        if any(row.get(field["name"]) not in (None, False, "", [], {}) for row in rows):
            prop = _property(field)
            if prop:
                extra.append(prop)
                used[field["name"]] = prop["name"]
    if extra:
        definition.append({"name": "separator_more", "type": "separator", "string": "Weitere Felder", "fold_by_default": True})
        definition.extend(extra)
    # separators without a property behind them are dropped
    cleaned = []
    for index, prop in enumerate(definition):
        if prop["type"] == "separator":
            following = definition[index + 1] if index + 1 < len(definition) else None
            if not following or following["type"] == "separator":
                continue
        cleaned.append(prop)
    return cleaned, used


def migrate(cr, version):
    if not util.table_exists(cr, "_oerp_fsm_ws_template"):
        return
    env = util.env(cr)
    Template = env["worksheet.template"].with_context(active_test=False)

    cr.execute("SELECT template_id, name FROM _oerp_fsm_ws_template ORDER BY template_id")
    for template_id, name in cr.fetchall():
        template = Template.browse(template_id).exists()
        if not template:
            _logger.warning("Field Service: worksheet template %s %r is gone", template_id, name)
            continue
        cr.execute(
            "SELECT view_id, inherit_id, mode, priority, arch FROM _oerp_fsm_ws_view WHERE template_id = %s",
            [template_id],
        )
        views = [dict(zip(("view_id", "inherit_id", "mode", "priority", "arch"), r)) for r in cr.fetchall()]
        cr.execute(
            """
            SELECT field_id, name, ttype, label, relation, selection, default_value
              FROM _oerp_fsm_ws_field WHERE template_id = %s
            """,
            [template_id],
        )
        keys = ("field_id", "name", "ttype", "label", "relation", "selection", "default_value")
        fields = {r[1]: dict(zip(keys, r)) for r in cr.fetchall()}
        cr.execute("SELECT vals FROM _oerp_fsm_ws_row WHERE template_id = %s", [template_id])
        rows = [r[0] for r in cr.fetchall()]

        definition, used = _definition(_combined_arch(views), fields, rows)
        for field_name, prop_name in used.items():
            cr.execute(
                "UPDATE _oerp_fsm_ws_field SET prop_name = %s WHERE template_id = %s AND name = %s",
                [prop_name, template_id, field_name],
            )
        skipped = sorted(
            f["name"] for f in fields.values() if f["name"] not in used and not _skipped(f)
        )

        vals = {"res_model": "planning.slot", "worksheet_properties_definition": definition}
        cr.execute(
            """
            SELECT EXISTS(SELECT 1 FROM _oerp_fsm_ws_row WHERE template_id = %(t)s)
                OR EXISTS(SELECT 1 FROM _oerp_fsm_task WHERE worksheet_template_id = %(t)s)
                OR EXISTS(SELECT 1 FROM ir_model_data WHERE model = 'worksheet.template' AND res_id = %(t)s)
            """,
            {"t": template_id},
        )
        used_anywhere = cr.fetchone()[0]
        if not used_anywhere and util.column_exists(cr, "project_project", "worksheet_template_id"):
            cr.execute("SELECT 1 FROM project_project WHERE worksheet_template_id = %s LIMIT 1", [template_id])
            used_anywhere = bool(cr.rowcount)
        if not used_anywhere:
            cr.execute(
                "SELECT 1 FROM product_template WHERE worksheet_template_id::text ~ %s LIMIT 1",
                [rf'":\s*{template_id}\b'],
            )
            used_anywhere = bool(cr.rowcount)
        if not used_anywhere:
            vals["active"] = False
        template.write(vals)
        cr.execute("UPDATE _oerp_fsm_ws_template SET converted = true WHERE template_id = %s", [template_id])
        _logger.info(
            "Field Service: worksheet template %s %r now on planning.slot, %s properties%s%s",
            template_id, name, len(definition), "" if used_anywhere else ", archived (unused)",
            f", fields without a place on the form or a value skipped: {', '.join(skipped)}" if skipped else "",
        )
