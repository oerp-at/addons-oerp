---
name: 'Keep Agent Rules in Sync'
description: 'New rules must be added for Cursor, GitHub Copilot and Claude alike'
---

# Keep Agent Rules in Sync (Cursor · Copilot · Claude)

This project drives **three** AI assistants from one shared rule set. Whenever you add, change, or remove a rule/convention, you **must** mirror it across all three targets.

| Assistant | Location | Format |
|-----------|----------|--------|
| **Cursor** | `.cursor/rules/<name>.mdc` | Front-matter (`description`, `globs`, `alwaysApply`) + Markdown |
| **GitHub Copilot** | `.github/instructions/<name>.instructions.md` (always-on rules also summarized in `.github/copilot-instructions.md`) | Front-matter (`name`, `description`, `applyTo`) + Markdown |
| **Claude** | `CLAUDE.md` (root); long-form context in `AGENTS.md` | Plain Markdown |

## Rules

1. **One rule = three targets.** A new convention is not finished until it exists as a Cursor `.mdc`, a Copilot `.instructions.md`, and an entry in `CLAUDE.md`.
2. **Same base name, same scope.** Reuse the same file base name and the same glob / `applyTo` / section across targets so a rule stays traceable.
3. **Content stays equivalent.** Wording may be condensed per format (`CLAUDE.md` is a summary), but the rule itself must not diverge between assistants.
4. **Always-on rules** (no `applyTo` in Copilot / `alwaysApply: true` in Cursor) also belong in `.github/copilot-instructions.md` and the "Coding-Regeln" section of `CLAUDE.md`.
5. **Single source of truth.** All of these files are distributed to new projects and kept in sync (`patch_back`) by `addons-oerp/oerp_util/patch/patch.py`. Edit them in the workspace — the patch tooling writes changes back to the source.