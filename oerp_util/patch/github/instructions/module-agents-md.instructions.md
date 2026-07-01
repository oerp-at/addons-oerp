---
name: 'Module AGENTS.md'
description: 'Keep AGENTS.md in the module root updated with every change'
applyTo: 'custom-addons-*/**/AGENTS.md, custom-addons-*/**/__manifest__.py, custom-addons-*/**/models/**, custom-addons-*/**/views/**'
---

# Module AGENTS.md

Every Odoo module **must** have an `AGENTS.md` in its **root directory** (next to `__manifest__.py`). This file is the **first thing an agent reads** when starting work on the module.

## Location

```
custom-addons-<subproject>/
  <addon_repo>/
    <module_name>/
      __manifest__.py
      AGENTS.md          ← here, in the module root
      models/
      views/
      ...
```

## Mandatory Update

Update `AGENTS.md` with **every change** to the module – no exceptions. If the file does not exist yet, create it.

## Content

Keep it **short and scannable** (aim for 30–80 lines). Use this structure:

```markdown
# <Module Technical Name>

> One-sentence purpose of the module.

## Dependencies

- `dependency_a`, `dependency_b`

## Models

| Model | Purpose |
|-------|---------|
| `model.name` | Brief description |

## Key Fields & Logic

- `field_name` on `model.name` – what it does / how it's computed.
- Cron / scheduled actions, if any.
- Important constraints or business rules.

## Views & Menus

- Which views exist (form, list, pivot, …) and where they are registered.
- Menu path if relevant.

## Configuration

- Settings or config keys the module introduces.

## File Layout

- Quick reference of the module's file structure (models, views, migrations, tests).

## Known Pitfalls / Notes

- Anything non-obvious a developer should know (migration quirks, performance considerations, external API dependencies, …).
```

## Rules

1. **English only** – all text in `AGENTS.md` must be in English.
2. **No prose** – bullet points and tables, not paragraphs.
3. **Accurate** – reflect the current code, not aspirations. Remove entries for deleted models/fields.
4. **Minimal diffs** – when updating, change only what is affected by the current change; don't rewrite unrelated sections.
