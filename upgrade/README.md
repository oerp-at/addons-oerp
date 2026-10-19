# upgrade – migration scripts for `odoo migrate`

Scripts that migrate a database one major version up without touching the Odoo
core. `odoo migrate` (and `odoo update` when it detects an older database) puts
these directories on Odoo's `--upgrade-path`:

- `upgrade-util/src` – subtree of https://github.com/odoo/upgrade-util (helpers
  as `odoo.upgrade.util`, plus its own `base/0.0.0` scripts)
- `<target version>/` – our scripts for the core modules, laid out like a
  module's `migrations/` folder: `<module>/<version>/{pre,post,end}-*.py`

Our own modules keep their scripts in `<module>/migrations/<version>/`.

## Layout of `<target version>/`

- `oerp_module_moves.py` – core modules that were renamed, merged or removed.
  Read by `base/<version>/pre-10-oerp-module-moves.py` and by
  `odoo migrate --dry-run`.
- `<module>/<version>/` – the version folder must be greater than the installed
  version and not greater than the new one, e.g. `base/20.0.1.3` for 19.0 → 20.0.

Update upgrade-util:

    git subtree pull --squash --prefix=addons-oerp/upgrade/upgrade-util upgrade-util master

## Steps of `odoo migrate`

1. `migrate` – `odoo update` of base with the upgrade path above
2. `cleanup` – the fixes of `odoo cleanup --fix`: unavailable modules are
   uninstalled, invalid views and assets removed
3. `update` – a regular `odoo update` on the cleaned database

Any error in a step stops the migration and sets the marker
`oerp.migration.state` to `failed`. At the end every step reports its errors
and warnings, and each warning left after the final update is listed.
`--no-cleanup` runs step 1 only.

Installed modules that are not available (and the modules depending on them)
do not stop the migration: the update skips them and the cleanup uninstalls
them, tables and columns included. `--no-drop` keeps their tables and columns,
e.g. for a partial migration in local tests, so the data is still there once
the module is ported:

    pipenv run odoo migrate --source odoo19_x -d odoo20_x --force-drop-db --no-drop \
        --addons-path <paths without the modules to leave out>
