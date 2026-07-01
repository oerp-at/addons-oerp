---
name: 'OCA Coding Style'
description: 'Follow OCA coding style conventions when writing code'
---

# OCA Coding Style

When writing code, follow the **OCA Coding Style**. Reference: [OCA Guidelines](https://github.com/OCA/odoo-community.org/blob/master/website/Contribution/CONTRIBUTING.rst).

**Python:** PEP8/Flake8; Imports: stdlib → third party → odoo → local imports (alphabetical). Black/isort for formatting. Strings with `%(name)s`, Exceptions from `odoo.exceptions` (e.g. `UserError`). Method names: `_compute_<field>`, `_inverse_<field>`, `_search_<field>`, `_onchange_<field>`, `_check_*`, actions `action_*` + `self.ensure_one()`. Models: UpperCamelCase, model name e.g. `sale.order` (singular). No `cr.commit()`, no raw SQL when ORM suffices; SQL only with placeholders `%s`. Since Odoo 18 in models: `self.env._()` instead of `_()`.

**Module/Manifest:** Module name singular, `base_`/`l10n_CC_`/extension name as prefix. Version `19.0.x.y.z`, `author` includes ", Odoo Community Association (OCA)", `license`, `website` (OCA repo). No empty keys.

**Structure:** `models/`, `views/`, `controllers/`, `security/`, `data/`, `demo/`, `tests/`. Filenames only `[a-z0-9_]`: e.g. `models/res_partner.py`, `views/res_partner_views.xml`, `data/res_partner_data.xml`; Controllers individually: `main.py`.

**XML:** 4 spaces; `id` before `model`; Fields: `name` first. xml_id without module prefix; Pattern: `model_view_form`, `model_menu`, `model_action`. Demo IDs with suffix `_demo`. Boolean/Numeric with `eval="True"`/`eval="100"`. No `<openerp>`/deprecated nodes; Odoo 18+ new chatter tag.

**File Header:** Avoid placing comments in the file header.
