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
