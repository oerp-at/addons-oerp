# CLAUDE.md — Odoo 19.0 Distribution

Monorepo einer **Odoo-19.0-Distribution**: Odoo-Core, Standard-Addons und lokal ausgecheckte Unterprojekte.
Vollständige Doku in [AGENTS.md](AGENTS.md); Coding-Regeln unter [.cursor/rules/](.cursor/rules/).

## Struktur

- `odoo/` — Odoo-Core + CLI. **Nicht bearbeiten**, außer `odoo/odoo/cli/` (wird per `patch_back` mit `addons-oerp/` synchronisiert).
- `addons-enterprise/`, `addons-design-themes/` — Standard-/Theme-Addons (nicht bearbeiten).
- `custom-addons-<name>/` — **Kundenprojekt (Unterprojekt)**. Module liegen entweder direkt (`custom-addons-<name>/<module>`) oder in einem Repo-Ordner (`custom-addons-<name>/<repo>/<module>`) — die Verschachtelung ist **nicht fix**, nur lose konventioniert:
  - `woa_custom/<module>` — Repo für Kundenanpassungen (nur dieses Projekt)
  - `woa_submodules/<module|repo>` — als git-Submodule ausgecheckte Repos/Module
  - `woa_<xxx>/…` — üblicherweise ein einzelnes Repo
  - Vor dem Bearbeiten immer prüfen, in welchem Baum ein Modul tatsächlich liegt (ein Modul = Ordner mit `__manifest__.py`).
- `assembly/` — **generiert** (Symlink-Baum, via `odoo assemble`). Nur Symlinks, nie dort editieren — Quelle ist `custom-addons-<name>/`.
- `.venv/` — pipenv-Umgebung (nicht bearbeiten).

## CLI (immer über pipenv)

CLI-Befehle **immer** mit `pipenv run odoo <cmd>` aufrufen (blankes `.venv/bin/odoo` bricht mit lxml-Fehler ab).

- `pipenv run odoo serve` — Server starten
- `pipenv run odoo update [<module>]` — Module aktualisieren
- `pipenv run odoo test <module>` — Tests (siehe unten)
- `pipenv run odoo assemble` — Symlinks + IDE-Config aktualisieren. **Nach neuen Modulen erneut ausführen.**
- `pipenv run odoo po_export|po_import <module>` — Übersetzungen (Default `de_DE`)

**Unterprojekt-Wechsel:** `pipenv run odoo assemble` **innerhalb** `custom-addons-<name>/` ausführen — lädt dessen `odoo-profile.yml`, verlinkt dessen Module und setzt `launch.json`-`cwd`. Zurück zum Basisprojekt: `assemble` im Wurzelverzeichnis.

**`-d <db>` kann entfallen**, wenn per Profil (`odoo-profile.yml`) vorkonfiguriert. Kommandos im Unterprojekt-Ordner nutzen automatisch dessen Datenbank.

## Tests

Aus dem Unterprojekt-Ordner (`custom-addons-<name>/`) heraus in der pipenv-Umgebung:

```bash
cd custom-addons-<name>/
pipenv run odoo test <module> [--test-case=<Class>] [--test-prefix=<method>]
```

- Port-Konflikt (paralleler Server): `--test-server-port <port>` mitgeben.
- **Kunden-Module** (`woa_custom/woa_<customer>_*`): laufen auf fixer DB → dürfen bestehende DB-Records direkt nutzen. `@tagged('-standard', 'custom')`, `TransactionCase`, keine Migrationen laden. Ausführen mit `--test-tags=custom`.
- **Test-Partner-Defaults**: Land Österreich (`env.ref("base.at")`), gültige UID z. B. `ATU12345675` / `ATU66994005` (EC-Sales-Szenarien: passende EU-VAT wie `DE123456788`).

## Coding-Regeln

**Immer gültig:**
- **English in code**: Feldnamen, `string=`, `help=`, `_description`, Manifest-`name/summary/description`, User-Errors — alles Englisch. UI-Übersetzungen laufen über `.po`.
- **Naming (WOA)**: beschreibend, kurz, einfach. Felder `snake_case` ohne Modell-Präfix; Methoden `_compute_*`, `action_*`; Modellname `dot.notation` singular; XML-ID `model_view_type`.

**Odoo 19 – häufige Fehler vermeiden** (siehe [odoo-code-pitfalls.mdc](.cursor/rules/odoo-code-pitfalls.mdc)):
- Kein `attrs=` mehr → inline `invisible="state != 'done'"` (Python-Ausdruck, keine Domain-Liste).
- Kein `t-esc` → `t-out`. Kein `_()` in Models → `self.env._()`.
- Search-`<group>` nimmt **keine** Attribute. Datumsfilter über `date="<field>"` / `default_period=`.
- `string=` weglassen, wenn es dem Auto-Label entspricht. `help=` in Endnutzer-Sprache (keine technischen Feldnamen).
- `__init__.py` importiert **nie** `tests`. Imports am Dateikopf. HTTP via `requests`.
- Wizards liegen unter `wizards/`, XML als `<name>_wizard.xml`.

**Struktur & Manifest:**
- OCA Coding Style (PEP8, Import-Reihenfolge, `models/ views/ controllers/ security/ data/ demo/ tests/`, Dateinamen `[a-z0-9_]`).
- **Manifest-Version** bei jeder Änderung anpassen: `19.0.<Major>.<Minor>.<Patch>` — Code-only → Patch; neue Felder/Views → Minor (Patch=0); entfernt/umbenannt → Major (Minor/Patch=0, Major startet bei 1).
- **Neue Module** aus Template `.cursor/templates/woa_addon` (beide Icons kopieren).
- **Modul-`AGENTS.md`**: jedes Modul hat eine im Root (neben `__manifest__.py`), bei jeder Änderung aktuell halten (kurz, Englisch, Bullet/Tabellen).
- **readme/**: neue Features unter `readme/` dokumentieren (DESCRIPTION.md, USAGE.md, CONFIGURE.md …).

## Agent-Regeln synchron halten (Cursor · Copilot · Claude)

Dieses Projekt steuert **drei** KI-Assistenten aus einem gemeinsamen Regelsatz. Wird eine Regel/Konvention neu angelegt, geändert oder entfernt, **muss** sie in allen drei Zielen gespiegelt werden:

- **Cursor** → `.cursor/rules/<name>.mdc`
- **GitHub Copilot** → `.github/instructions/<name>.instructions.md` (immer aktive Regeln zusätzlich in `.github/copilot-instructions.md`)
- **Claude** → `CLAUDE.md` (Root; Langform in `AGENTS.md`)

Eine neue Konvention ist erst fertig, wenn sie in allen drei existiert (gleicher Basisname/Scope, inhaltlich äquivalent). Bearbeitet wird im Workspace — `addons-oerp/oerp_util/patch/patch.py` verteilt die Dateien in neue Projekte und hält sie per `patch_back` synchron.