---
name: 'Odoo 19 – Common AI Pitfalls'
description: 'Odoo 19 – common AI errors to avoid (XML, Python, model structure)'
applyTo: '**/*.xml, **/*.py'
---

# Odoo 19 – Common AI Pitfalls

## Search View `<group>` (Group By)

The `<group>` element inside `<search>` is a **plain container** for `group_by` filters. It takes **no attributes**.

```xml
<!-- ✅ GOOD -->
<group>
    <filter name="customer" string="Customer" context="{'group_by': 'partner_id'}"/>
</group>

<!-- ❌ BAD – expand and string do NOT exist on search <group> -->
<group expand="1" string="Group By">
    <filter name="customer" string="Customer" context="{'group_by': 'partner_id'}"/>
</group>
```

## No `attrs=` in Odoo 18+

The `attrs` attribute was **removed** in Odoo 17+. Use inline Python expressions directly.

```xml
<!-- ✅ GOOD (Odoo 18+) -->
<field name="amount" invisible="state != 'done'" readonly="state == 'done'"/>

<!-- ❌ BAD – attrs is removed -->
<field name="amount" attrs="{'invisible': [('state', '!=', 'done')], 'readonly': [('state', '=', 'done')]}"/>
```

## Inline `invisible` / `readonly` / `required` Expressions

These attributes take **Python-like boolean expressions**, not domain lists.

```xml
<!-- ✅ GOOD -->
<field name="date" invisible="not show_date"/>
<field name="ref" readonly="state in ('done', 'cancel')"/>
<field name="partner_id" required="type == 'out_invoice'"/>

<!-- ❌ BAD – domain syntax in inline attributes -->
<field name="date" invisible="[('show_date', '=', False)]"/>
<field name="ref" readonly="[('state', 'in', ('done', 'cancel'))]"/>
```

## `_()` Translation in Models (Odoo 18+)

In model code use `self.env._()` instead of bare `_()`.

```python
# ✅ GOOD (Odoo 18+)
raise UserError(self.env._("Record not found."))

# ❌ BAD
raise UserError(_("Record not found."))
```

## Search View Date Filters: Use `date=` Attribute

For period-based filtering (month, quarter, year) on date fields, use the built-in `date=` attribute on `<filter>`. It generates an automatic dropdown with all periods. Do **not** build manual domains with `context_today()` and `relativedelta`.

```xml
<!-- ✅ GOOD – built-in date filter with automatic period dropdown -->
<filter name="date_filter" string="Date" date="date"/>

<!-- ❌ BAD – manual quarter calculation with context_today() -->
<filter name="current_quarter" string="Current Quarter"
        domain="[('date', '>=', (context_today() + relativedelta(day=1, month=...)).strftime('%Y-%m-%d')),
                 ('date', '&lt;', ...)]"/>
```

### Preselect a Period: `default_period="<id>"` (Odoo 19)

To have a specific period preselected when the date filter is active, set `default_period` on the filter. Combine with `search_default_<filter_name>` in the action context to activate the filter by default.

Generator ids follow the format `unit` or `unit<sign><offset>` (see `web/static/src/search/utils/dates.js`):

| Period | id |
|---|---|
| This month | `month` |
| Last month | `month-1` |
| Month before last | `month-2` |
| This quarter | `quarter` |
| Last quarter | `quarter-1` |
| This year | `year` |
| Last year | `year-1` |

Multiple ids can be combined with commas (e.g. `month-1,year-1`).

```xml
<!-- ✅ GOOD – declarative preselection with default_period -->
<filter name="date_filter" string="Date" date="date" default_period="month-1"/>
```
