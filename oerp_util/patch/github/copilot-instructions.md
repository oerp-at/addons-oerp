# Coding Standards – Odoo 19.0

Always-on coding conventions for this project. These apply to all code changes.

---

## 1. English in Code

All **field names**, **string labels**, **help texts**, and **descriptions** in source code must be written in **English**.

### Scope

- **Python:** `string=` and `help=` on field definitions, `_description` on models, user-facing messages in code (e.g. `UserError`, wizard messages).
- **XML:** `string=` and `help=` on field and view elements, button/label texts, menu titles, action names and descriptions.
- **Manifest:** `name`, `description`, `summary` in `__manifest__.py` – in English.

### Rationale

- English is the standard language for code and identifiers; translations are handled via `po_export` / `po_import` and language modules.
- Keeps the codebase consistent and easier to maintain and review.

### Examples

```python
# ✅ GOOD
name = fields.Char(string="Internal Reference", help="Unique internal reference.")
description = fields.Text(string="Description")

# ❌ BAD (German in code)
name = fields.Char(string="Interne Referenz", help="Eindeutige interne Referenz.")
```

```xml
<!-- ✅ GOOD -->
<field name="date_start" string="Start Date" help="Start date of the period."/>

<!-- ❌ BAD -->
<field name="date_start" string="Startdatum" help="Startdatum des Zeitraums."/>
```

User-facing text that is only ever shown in the UI and is translated via `.po` files can stay in the default language (e.g. German) in the PO files; the rule applies to the **source code** (Python/XML/manifest), which must use English.

---

## 2. WOA Coding Style – Naming

All names (variables, fields, methods, classes, modules, XML IDs, filenames) must be **descriptive, short, and as simple as possible**.

### Rules

1. **Descriptive** – The name clearly conveys what it represents. No guessing required.
2. **Short** – Omit unnecessary words. Don't repeat context already implied by the model or module.
3. **Simple** – Prefer commonly understood terms. Avoid abbreviations that aren't immediately obvious.

### Examples

```python
# ❌ BAD – too long, redundant, unclear
has_active_employee_contract_flag = fields.Boolean()
compute_total_amount_of_all_lines_in_order = ...
tmp_val = ...
x = ...

# ✅ GOOD – descriptive, short, simple
is_contracted = fields.Boolean(string="Contracted")
_compute_total = ...
remaining_qty = ...
line_count = ...
```

```xml
<!-- ❌ BAD -->
<record id="action_open_all_sale_order_records_list" ...>
<field name="very_long_redundant_description_field_name" .../>

<!-- ✅ GOOD -->
<record id="sale_order_action" ...>
<field name="description" .../>
```

### Quick Reference

| Element | Style | Example |
|---------|-------|---------|
| Field | `snake_case`, no model name prefix | `start_date`, `total` |
| Method | `_compute_*`, `action_*` – keep short | `_compute_total`, `action_confirm` |
| Model class | `UpperCamelCase` | `SaleOrder` |
| Model name | `dot.notation`, singular | `sale.order` |
| XML ID | `model_view_type` | `sale_order_view_form` |
| Module | `snake_case`, singular | `sale_subscription` |

---

## 3. Keep Agent Rules in Sync (Cursor · Copilot · Claude)

This project drives **three** AI assistants from one shared rule set. Whenever you add, change, or remove a rule/convention, mirror it across **all three** targets:

- **Cursor** → `.cursor/rules/<name>.mdc`
- **GitHub Copilot** → `.github/instructions/<name>.instructions.md` (always-on rules also summarized here in `copilot-instructions.md`)
- **Claude** → `CLAUDE.md` (root; long-form context in `AGENTS.md`)

A new convention is not finished until it exists in all three. Reuse the same base name and scope, keep the content equivalent, and edit the files in the workspace — `addons-oerp/oerp_util/patch/patch.py` distributes them to new projects and keeps them in sync (`patch_back`). See `.github/instructions/agent-rules-sync.instructions.md`.
