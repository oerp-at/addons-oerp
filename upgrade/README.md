# upgrade – migration scripts for `odoo migrate`

Scripts that migrate a database one major version up without touching the Odoo
core. `odoo migrate` (and `odoo update` when it detects an older database) puts
these directories on Odoo's `--upgrade-path`:

- `upgrade-util/src` – subtree of https://github.com/odoo/upgrade-util (helpers
  as `odoo.upgrade.util`, plus its own `base/0.0.0` scripts)
- `<target version>/` – our scripts for the core modules, laid out like a
  module's `migrations/` folder: `<module>/<version>/{pre,post,end}-*.py`

Our own modules keep their scripts in `<module>/migrations/<version>/`.

Only one major version per run: a 19.0 database can be migrated with the 20.0
code base, an 18.0 database first needs the 19.0 one.

## Usage

Run it in the environment of the new version, e.g. `odoo-20.0-enterprise`.
First check the database without changing anything:

    pipenv run odoo migrate --source odoo19_x -d odoo20_x --dry-run

The dry run logs the version of base, the upgrade path and every installed
module that is

- renamed, merged or removed by the upgrade scripts (`oerp_module_moves.py`),
- without source code and therefore kept installed (Studio, imported modules),
- not available in the new version, so the cleanup will uninstall it together
  with the modules depending on it (warning).

Then migrate a copy. The source database and its filestore stay unchanged:

    pipenv run odoo migrate --source odoo19_x -d odoo20_x

Options:

- `--source` – database to migrate, copied with its filestore to `-d`
- `-d` / `--database` – target database (the profile default applies)
- `--dry-run` – only check versions and modules, change nothing
- `--force-drop-db` – drop an existing target database before the copy, needed
  for every further run on the same target
- `--in-place` – migrate `-d` itself instead of a copy, make a backup first
- `--upgrade-source` – `auto` (default), `odoo` or `oerp`, see below
- `--upgrade-aim` – `auto` (default), `test` or `production`, see below
- `--extra-upgrade-path` – additional script directories, comma separated, e.g.
  scripts of a customer repository
- `--no-cleanup` – run the first step only (no cleanup, no final update)
- `--no-drop` – keep tables and columns of the modules the cleanup uninstalls,
  see below

`odoo update` migrates by itself: if the database is still on the previous
major version, it runs `odoo migrate --in-place` instead of the update. This is
how an image of the new version migrates a customer database, so the backup has
to exist before the first update. It takes `--upgrade-source`, `--upgrade-aim`
and `--extra-upgrade-path` as well.

## Upgrade source: our scripts or upgrade.odoo.com

- `auto` (default) – a Community database (no `web_enterprise`) is migrated
  with our scripts. An Enterprise database with subscription code
  (`database.enterprise_code`) goes to upgrade.odoo.com; if Odoo refuses the
  request (unknown subscription, version not offered yet) or there is no
  subscription code, our scripts migrate it with a warning
- `odoo` – always upgrade.odoo.com, stops if the subscription code is missing

`odoo restore --neutralize` removes `database.enterprise_code`, so the copy does
not report to the subscription. It keeps the code in
`oerp.upgrade.enterprise_code`, which only `odoo migrate` reads: a neutralized
copy still goes to upgrade.odoo.com, as `test` request.
- `oerp` – always our scripts, e.g. an Enterprise database whose scripts we
  maintain ourselves (Field Service of ATTRIA)

The request type on upgrade.odoo.com is `--upgrade-aim`:

- `auto` (default) – `test` for a neutralized database
  (`database.is_neutralized`), `production` otherwise
- `test` / `production` – set it explicitly

Note: a local copy that is not neutralized counts as production. `--dry-run`
logs the source, the request type and the reason and sends nothing.

With `odoo` a dump of the database goes to Odoo (`pg_dump`, rsync over ssh),
the upgraded database comes back as `-d` (in place: restored next to it as
`<db>_odoo_upgraded`, then renamed), the files Odoo created are merged into the
filestore. Then our steps `cleanup` and `update` run as usual, for the
migrations of our own modules and the Studio views. `addons-oerp/upgrade/<version>`
stays off the upgrade path then, otherwise it would migrate a second time;
upgrade-util and `--extra-upgrade-path` stay on it.

The work directory is `<data_dir>/filestore/.odoo-upgrade/<db>` (in the image on
the filestore volume). It keeps the token of the request: a job that is
restarted resumes the request instead of sending the database again. In the end
only `upgrade-report.html` and `upgrade.log` of Odoo stay there.

The three settings work in the same way as parameter, as key in
`odoo-profile.yml` (`upgrade_source`, `upgrade_aim`, `extra_upgrade_path`) or as
environment variable (`ODOO_UPGRADE_SOURCE`, `ODOO_UPGRADE_AIM`,
`ODOO_EXTRA_UPGRADE_PATH`). The odoo chart sets the environment variables of the
update job from `odooinit.upgrade.source`, `.aim` and `.extraPath`.

Afterwards check the log, the exit code alone does not show the warnings. Each
step reports its numbers (`Step cleanup: 0 error(s), 12 warning(s)`) and every
warning left after the final update is listed as `Left after update: ...`.

## Layout of `<target version>/`

- `oerp_module_moves.py` – core modules that were renamed, merged or removed.
  Read by `base/<version>/pre-10-oerp-module-moves.py` and by
  `odoo migrate --dry-run`.
- `<module>/<version>/` – the version folder must be greater than the installed
  version and not greater than the new one, e.g. `base/20.0.1.3` for 19.0 → 20.0.
  A folder not greater than the installed version is skipped without a message.

Each script starts with a docstring that says what it migrates and why. Larger
topics of 19.0 → 20.0:

- `base/20.0.1.3/` – module moves, unavailable modules, countries and states,
  partner banks, access rights, columns of base models
- `base/20.0.1.3/pre-70-oerp-fsm.py` and `planning_field_service/20.0.1.0/` –
  Field Service: the `industry_fsm*` modules are gone, each FSM task becomes a
  `planning.slot` linked to its task and project; worksheet templates become
  properties of the slot, recurrences and sale order links are kept
- `mail/20.0.1.19/end-20-oerp-template-config-param.py` – mail templates still
  calling the removed `get_param` are reset to their 20.0 definition
- `account`, `point_of_sale`, `pos_hr`, `stock`, `sale`, `purchase`, `hr`, … –
  renamed fields and models, changed selections

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

Modules without source code that only live in the database – Studio
customizations (`studio_customization`) and imported modules – are no missing
modules: they stay installed, and neither migrate nor cleanup uninstalls them.

## Studio and custom views

Extension views without a file (Studio, views created in the UI) often point
to fields or anchors that no longer exist in the new version. The cleanup does
not drop such a view as a whole: it checks the views one after the other and
only removes the parts (`xpath`, `field`, …) that no longer resolve. Each
removed part is logged as warning with the view, the old arch stays in
`arch_prev`. A view is only removed when its model is gone or none of its parts
is valid any more. With `--no-drop` the views are left untouched.

## Migration marker

`odoo migrate` writes the state to the system parameters of the target
database:

- `oerp.migration.state` – `running` during the migration, then `done` or
  `failed`
- `oerp.migration.info` – versions, start time, duration, number of errors or
  warnings left

A database with `running` or `failed` is not served: `odoo serve` stops
(`--ignore-migration-state` to override), `--wait-for-database` keeps waiting.
A failed migration is not resumed: fix the cause and migrate again from the
source with `--force-drop-db`. After a failed `--in-place` migration restore
the backup first.

## `odoo cleanup`

The second step of the migration, also usable on its own, e.g. after removing
modules from the addons path. Without `--fix` it only reports (`[FOUND]`) and
changes nothing:

    pipenv run odoo cleanup -d odoo20_x
    pipenv run odoo cleanup -d odoo20_x --fix

- `--fix` – apply the fixes (`[FIX]`): uninstall unavailable modules, clean up
  module states and orphaned module data, prune Studio and custom views,
  remove invalid views and assets
- `--no-drop` – uninstall without dropping tables and columns
- `--uninstall <module> …` – uninstall these modules as well
- `--only-raw` – only the SQL fixes (assets, views, unaccent), no module
  uninstall and no view pruning
