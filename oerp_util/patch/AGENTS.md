# Agent Instructions – Odoo {{ odoo_version }}

Dieses Projekt ist eine **Odoo {{ odoo_version }} Distribution**: ein Monorepo mit Odoo-Core, Standard-Addons und lokal ausgecheckten Unterprojekten.

## Projektstruktur

- **`odoo/`** – Odoo-Core und -Binaries (`odoo-bin`, CLI). Nicht als „eigenes Addon" behandeln; Änderungen hier nur für CLI-Erweiterungen (via `patch_back`).
- **`addons-oerp/`** – Utilities und CLI-Erweiterungen (BSD-2-Clause). Enthält `oerp_util/patch/` als Quelle für die CLI-Patches in `odoo/odoo/cli/`. Dateien dort werden per `patch_back` bidirektional synchronisiert – Änderungen in `odoo/odoo/cli/` werden automatisch nach `addons-oerp/` zurückgeschrieben und umgekehrt.
- **`addons-design-themes/`** – Odoo Design-Themes.
- **`custom-addons-*`** – Eigene Unterprojekte mit Odoo-Modulen. Jedes Verzeichnis kann mehrere Addon-Repositories enthalten (verschachtelte Struktur, siehe unten).
- **`assembly/`** – **Generiert, nicht manuell bearbeiten.** Enthält einen Symlink-Baum, der alle Module unter `assembly/odoo/addons/` zusammenführt. Wird von `odoo assemble` erstellt und dient der IDE (Pyright/Pylance) zur Auflösung von `odoo.addons.*`-Imports.
- **`docker/`**, **`kubernetes/`**, **`odoo-gitops/`** – Deployment-Konfiguration.
- **`.venv/`** – Virtuelle Python-Umgebung (pipenv).
- **`.vscode/`** – VSCode/Cursor Debug-Konfiguration (`launch.json`), Snippets.
- **`odoo.code-workspace`** – Workspace-Datei mit Pylint- und Pyright-Konfiguration. Definiert `assembly/` als `extraPaths` für die Code-Analyse.

### Verzeichnisstruktur in `custom-addons-*`

Unterprojekte haben eine verschachtelte Struktur. Addon-Repositories liegen als Unterordner, die wiederum einzelne Module enthalten:

```
custom-addons-<name>/
├── odoo-profile.yml          # Subprofil (optional)
├── Dockerfile                # Deployment
├── charts/                   # Helm Charts
├── woa_addons/               # Generelle Weboffice-Module (projektübergreifend)
│   ├── module_a/
│   │   ├── __manifest__.py
│   │   └── ...
│   └── module_b/
├── woa_custom/               # Kundenspezifische Module (nur für dieses Projekt)
│   └── custom_module/
├── woa_orderjim/             # Weiteres projektspezifisches Addon-Repository
│   └── l10n_at_orderjim_pos/
├── oca_l10n-austria/         # OCA-Repository
└── oca_network/              # OCA-Repository
```

Beim Bearbeiten von Modulen immer prüfen, in welchem **`custom-addons-*`**-Baum das Modul liegt; Abhängigkeiten und Imports beziehen sich auf diese Addon-Pfade.

### Nicht bearbeiten

Folgende Verzeichnisse/Dateien sind generiert oder extern und sollen nicht manuell geändert werden:
- **`assembly/`** – generiert durch `odoo assemble`
- **`odoo/`** – Odoo-Core (Ausnahme: `odoo/odoo/cli/` wird per `patch_back` synchronisiert)
- **`.venv/`** – virtuelle Umgebung

## Technologie

- **Odoo:** Version **{{ short_version }}**
- **Python:** 3.12 (virtuelle Umgebung unter `.venv`)
- **Abhängigkeiten:** Pipenv (`pipenv install` / `pipenv install --dev`)
- **Patch:** Mit `./addons-oerp/oerp_util/patch/patch.py` wird das lokale Checkout einmalig vorbereitet (CLI-Erweiterungen, Workspace-Dateien, Docker-Setup).
- **Assembly:** Nach `./odoo/odoo-bin assemble` stehen Befehle wie `odoo serve`, `odoo update`, `odoo test` zur Verfügung und der `assembly/`-Symlink-Baum wird aktualisiert. **Nach dem Anlegen neuer Module muss `odoo assemble` erneut ausgeführt werden.**

## CLI-Befehle

Alle Befehle können mit `odoo <cmd>` aufgerufen werden (nach `assemble`). Die wichtigsten:

| Befehl | Beschreibung |
|--------|-------------|
| `odoo serve` | Server starten |
| `odoo update [-d <db>] [<module>]` | Alle oder einzelne Module aktualisieren |
| `odoo test [-d <db>] [<module>]` | Tests ausführen (siehe [Tests](#tests)) |
| `odoo po_export [-d <db>] <module>` | Übersetzungen exportieren |
| `odoo po_import [-d <db>] <module>` | Übersetzungen importieren |
| `odoo restore` | Datenbank wiederherstellen |
| `odoo backup` | Datenbank sichern |
| `odoo assemble` | Assembly-Symlinks und IDE-Konfiguration aktualisieren |
| `odoo cleanup` | Bereinigung |
| `odoo install` | Modul installieren |
| `odoo updatelist` | Modulliste aktualisieren |
| `odoo autoenv` | Umgebung automatisch einrichten |

Datenbank `-d <database>` kann entfallen, wenn per Profil vorkonfiguriert.

## Konventionen für Addons

- Ein Modul = ein Verzeichnis mit `__manifest__.py` (und typisch `__init__.py`, Models, Views, etc.).
- Imports folgen dem Schema `from odoo.addons.<module> import ...` – der `assembly/`-Ordner stellt sicher, dass die IDE diese auflösen kann.
- Commit-Messages: OCA- oder Odoo-Entwicklerrichtlinien (z. B. [OCA](https://github.com/OCA/odoo-community.org/blob/master/website/Contribution/CONTRIBUTING.rst#commit-message), [Odoo Guidelines](https://www.odoo.com/documentation/16.0/developer/misc/other/guidelines.html)).
- Übersetzungen: Export `odoo po_export -d <database> <module>`, Import `odoo po_import -d <database> <module>` (Standardsprache z. B. in `odoo-profile.yml`, z. B. `de_DE`).

### Tests

- Standardaufruf: `odoo test -d <database> --test-prefix=<test> <module>`
- `odoo test` startet bei HTTP-/Tour-Tests einen internen Test-Server. Der Port kommt aus `test.test_server_port` in `odoo-profile.yml` (Default `10069`).
- **Port-Konflikte:** Läuft bereits ein anderer Odoo-Server auf dem konfigurierten Port (z. B. ein zweiter Test- oder Entwicklungs-Server), den Tests einen freien Port mitgeben:

  ```bash
  odoo test -d <database> --test-server-port <port> <module>
  ```

  So lassen sich Tests parallel zu einem laufenden `odoo serve` starten, ohne dass sich die Ports gegenseitig blockieren.

## Konventionen für Unterprojekte

- Die Verzeichnisse **`custom-addons-*`** sind Unterprojekte (jedes kann mehrere Addon-Repositories enthalten).
- Jedes Unterprojekt kann ein eigenes Profil haben: **`odoo-profile.yml`** bzw. **`.odoo-profile.yml`** im Unterprojektordner.

### Unterprojekt wechseln mit `odoo assemble`

Wird `odoo assemble` **innerhalb** eines `custom-addons-<name>/`-Verzeichnisses aufgerufen, bewirkt das einen Wechsel des aktiven Unterprojekts. Konkret passiert dabei:

1. **Profil wird geladen:** Das `odoo-profile.yml` / `.odoo-profile.yml` des Unterprojekts wird eingelesen. Dadurch gelten die dort definierten Defaults (z. B. eigene Datenbank) für alle CLI-Befehle.
2. **Module werden verlinkt:** Die Addon-Repositories des Unterprojekts werden als zusätzliche Symlinks in `assembly/odoo/addons/` angelegt – die Module des Unterprojekts sind damit für die IDE und den Server auflösbar.
3. **`launch.json` wird angepasst:** Das `cwd` aller Odoo-Debug-Konfigurationen in `.vscode/launch.json` wird automatisch auf `${workspaceFolder}/custom-addons-<name>` umgestellt. Dadurch verwenden Server-Start und Tests das korrekte Unterprojekt-Profil.

Um zurück zum Basisprojekt zu wechseln, `odoo assemble` im Wurzelverzeichnis ausführen.

## Profil & Konfiguration

Profile definieren Standardwerte (Datenbank, Sprache, etc.) und werden in dieser Reihenfolge geladen (spätere überschreiben frühere):

1. `/etc/odoo/odoo-profile.yml`
2. `<projekt>/odoo-profile.yml`
3. `<projekt>/custom-addons-<name>/odoo-profile.yml` (wenn im Unterprojekt)
4. `<projekt>/custom-addons-<name>/.odoo-profile.yml` (lokales Override)
5. `~/.odoo-profile.yml` (benutzerspezifisch)

Der Profilname leitet sich vom Verzeichnisnamen ab: `{{ profile }}` bzw. `{{ profile }}-<subprojekt>`.

Bei Befehlen wie `odoo update`, `odoo serve`, `odoo test` die passende Datenbank angeben (`-d <database>`), sofern nicht durch Profil vorkonfiguriert.
