import argparse
import importlib.util
import logging
import os
import shutil
import subprocess
import time

import odoo
from odoo.modules.module import get_manifest, get_modules, initialize_sys_path
from odoo.tools.config import config

from . import Command
from .assemble import CommandMixin, DatabaseMixin, get_base_dir, update_database
from .cleanup import CleanUp, imported_modules
from .odoo_upgrade import UPGRADE_SERVER, OdooUpgrade, OdooUpgradeError

_logger = logging.getLogger(__name__)

MARKER_STATE = 'oerp.migration.state'
MARKER_INFO = 'oerp.migration.info'
INSTALLED_STATES = ('installed', 'to upgrade', 'to remove')
UPGRADE_SOURCES = ('auto', 'odoo', 'oerp')
UPGRADE_AIMS = ('auto', 'test', 'production')
DUMP_JOBS = 4
#: in place, Odoo's result is restored next to the database and then swapped
UPGRADED_SUFFIX = '_odoo_upgraded'
REPLACED_SUFFIX = '_odoo_replaced'


class MigrationError(Exception):
    pass


def major_version(version):
    """ '19.0.1.3' -> '19.0', None for versions without a major part """
    parts = (version or '').split('.')
    if len(parts) < 2 or not parts[0].isdigit():
        return None
    return f'{parts[0]}.{parts[1]}'


def previous_major_version(version):
    """ the major version a database must have to be migrated to ``version`` """
    major = int(version.split('.')[0])
    return f'{major - 1}.0'


def get_upgrade_dir():
    """ addons-oerp/upgrade, next to the odoo checkout (also in the image) """
    return os.path.join(get_base_dir(), 'addons-oerp', 'upgrade')


def get_upgrade_paths(target_version, extra_paths=None, scripts=True):
    """ upgrade-util and our scripts of the target version; without
    ``scripts`` after an upgrade by Odoo, they would migrate a second time """
    upgrade_dir = get_upgrade_dir()
    paths = [os.path.join(upgrade_dir, 'upgrade-util', 'src')]
    if scripts:
        paths.append(os.path.join(upgrade_dir, target_version))
    paths.extend(p for p in (extra_paths or []) if p)
    return [p for p in paths if os.path.isdir(p)]


def load_module_moves(target_version):
    """ oerp_module_moves.py of the target version, None if there is none """
    path = os.path.join(get_upgrade_dir(), target_version, 'oerp_module_moves.py')
    if not os.path.exists(path):
        return None
    spec = importlib.util.spec_from_file_location('oerp_module_moves', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_database_state(cr):
    """ version of base, installed modules and migration marker of a database """
    cr.execute("SELECT latest_version FROM ir_module_module WHERE name = 'base'")
    row = cr.fetchone()
    cr.execute("SELECT name FROM ir_module_module WHERE state IN %s ORDER BY name", [INSTALLED_STATES])
    modules = [r[0] for r in cr.fetchall()]
    cr.execute("SELECT value FROM ir_config_parameter WHERE key = %s", [MARKER_STATE])
    marker = cr.fetchone()
    return {
        'base_version': row[0] if row else None,
        'modules': modules,
        'imported': imported_modules(cr),
        'marker': marker[0] if marker else None,
    }


def get_upgrade_workdir(database):
    """ next to the filestores: on the filestore volume in the image, so dumps
    fit and an interrupted request is found again after a restart """
    return os.path.join(os.path.dirname(config.filestore(database)), '.odoo-upgrade', database)


def read_upgrade_facts(cr):
    """ what decides between our scripts and the upgrade platform of Odoo """
    cr.execute("SELECT 1 FROM ir_module_module WHERE name = 'web_enterprise' AND state IN %s",
               [INSTALLED_STATES])
    enterprise = bool(cr.fetchone())
    cr.execute("SELECT key, value FROM ir_config_parameter WHERE key IN %s",
               [('database.enterprise_code', 'database.is_neutralized')])
    params = dict(cr.fetchall())
    return {
        'enterprise': enterprise,
        'contract': (params.get('database.enterprise_code') or '').strip() or None,
        'neutralized': (params.get('database.is_neutralized') or '').lower() == 'true',
    }


def choose_upgrade(facts, source=None, aim=None):
    """ :return: dict with source (odoo/oerp), aim (test/production, only for
    odoo), the requested source, the contract and the reasons for the log """
    requested, aim = source or 'auto', aim or 'auto'
    if requested not in UPGRADE_SOURCES:
        raise MigrationError(f"Unknown upgrade source {requested!r}, use one of {UPGRADE_SOURCES}")
    if aim not in UPGRADE_AIMS:
        raise MigrationError(f"Unknown upgrade aim {aim!r}, use one of {UPGRADE_AIMS}")
    choice = {'requested': requested, 'contract': facts['contract'], 'aim': None}
    if requested == 'oerp':
        return dict(choice, source='oerp', reason="upgrade source set to oerp")
    if requested == 'auto' and not facts['enterprise']:
        return dict(choice, source='oerp', reason="Community database (web_enterprise not installed)")
    if not facts['contract']:
        if requested == 'odoo':
            raise MigrationError("Upgrade source odoo needs the subscription code of the database "
                                 "(system parameter database.enterprise_code)")
        return dict(choice, source='oerp', warning=True,
                    reason="Enterprise database without subscription code (database.enterprise_code)")
    if aim == 'auto':
        aim = 'test' if facts['neutralized'] else 'production'
        aim_reason = 'neutralized' if facts['neutralized'] else 'not neutralized'
    else:
        aim_reason = 'set'
    reason = ("upgrade source set to odoo" if requested == 'odoo' else
              "Enterprise database with subscription code")
    return dict(choice, source='odoo', aim=aim, reason=f"{reason}, aim {aim} ({aim_reason})")


def split_unavailable(state, handled=()):
    """ installed modules without an installable manifest: (moved by the upgrade
    scripts, missing, kept without source code like Studio) """
    moved, missing, kept = [], [], []
    for name in state['modules']:
        if name in state['imported']:
            kept.append(name)
            continue
        manifest = get_manifest(name)
        if manifest and manifest.get('installable', True):
            continue
        (moved if name in handled else missing).append(name)
    return moved, missing, kept


def migration_needed(cr):
    """ source major version if the database has to be migrated, else None

    Raises MigrationError for databases this code base cannot migrate.
    """
    state = read_database_state(cr)
    source = major_version(state['base_version'])
    target = odoo.release.major_version
    if not source or source == target:
        return None
    if source == previous_major_version(target):
        return source
    raise MigrationError(
        f"Database is on {source}, this code base is {target}: only a migration from "
        f"{previous_major_version(target)} is possible. Migrate step by step with the "
        f"image of each version in between.")


def set_marker(cr, state, info=None):
    for key, value in ((MARKER_STATE, state), (MARKER_INFO, info)):
        if value is None:
            continue
        cr.execute("UPDATE ir_config_parameter SET value = %s WHERE key = %s", [value, key])
        if not cr.rowcount:
            cr.execute("INSERT INTO ir_config_parameter (key, value) VALUES (%s, %s)", [key, value])


def missing_dependencies():
    """ dependencies of modules on the addons path that are nowhere on it,
    e.g. Enterprise modules required by a module of a shared repository """
    available = set(get_modules())
    missing = set()
    for module in available:
        manifest = get_manifest(module)
        if manifest:
            missing.update(set(manifest.get('depends', ())) - available)
    return missing


class UnknownModulesFilter(logging.Filter):
    """ upgrade-util registers every module of the addons path; a dependency
    that is not available anywhere only makes that module uninstallable, so
    its "Unknown modules" error is logged as warning """

    logger_name = 'odoo.upgrade.util.modules'

    def __init__(self, unavailable):
        super().__init__()
        self.unavailable = set(unavailable)

    def filter(self, record):
        if record.levelno >= logging.ERROR and record.msg == "Unknown modules: %s":
            names = {n.strip() for n in str(record.args[0]).split(',')}
            if names <= self.unavailable:
                record.levelno, record.levelname = logging.WARNING, 'WARNING'
        return True


def unloadable_dependents(installed, removed):
    """ installed modules that cannot be loaded any more because one of their
    dependencies (direct or indirect) is removed """
    removed = set(removed)
    dependents = set()
    changed = True
    while changed:
        changed = False
        for name in installed:
            if name in removed or name in dependents:
                continue
            manifest = get_manifest(name)
            if manifest and set(manifest.get('depends', ())) & (removed | dependents):
                dependents.add(name)
                changed = True
    return dependents


class LogCollector(logging.Handler):
    """ collects WARNING and above per step; the exit code of an update hides them """

    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.step = None
        self.records = []

    def emit(self, record):
        self.records.append((self.step, record))

    def errors(self, step=None):
        return [r for s, r in self.records
                if r.levelno >= logging.ERROR and (step is None or s == step)]

    def warnings(self, step=None):
        return [r for s, r in self.records
                if r.levelno == logging.WARNING and (step is None or s == step)]


def add_upgrade_arguments(parser):
    """ the same settings for odoo migrate and odoo update (migration in place):
    parameter, key in odoo-profile.yml or environment variable ODOO_<KEY> """
    parser.add_argument(
        "--upgrade-source", metavar="UPGRADE_SOURCE", name="upgrade_source", envvar=True,
        help="auto (default): a Community database with our scripts (addons-oerp/upgrade), "
             "an Enterprise database with subscription code on upgrade.odoo.com if Odoo "
             "accepts the request, otherwise with our scripts. odoo: always upgrade.odoo.com. "
             "oerp: always our scripts")
    parser.add_argument(
        "--upgrade-aim", metavar="UPGRADE_AIM", name="upgrade_aim", envvar=True,
        help="Request type on upgrade.odoo.com. auto (default): test for a neutralized "
             "database (database.is_neutralized), production otherwise. Or test, production")
    parser.add_argument(
        "--extra-upgrade-path", metavar="EXTRA_UPGRADE_PATH", name="extra_upgrade_path",
        envvar=True, help="Additional upgrade script directories, comma separated")


class Migrate(CommandMixin, Command, DatabaseMixin):
    """ Migrate a database to the major version of this code base """

    def __init__(self):
        super().__init__()
        self.parser.add_argument(
            "--source", metavar="SOURCE",
            help="Database to migrate. It is copied to --database (database and filestore) "
                 "and stays unchanged. Default: --database itself with --in-place")
        self.parser.add_argument(
            "--in-place", action="store_true", name="in_place",
            help="Migrate --database itself (used by odoo update, the backup has to exist)")
        self.parser.add_argument(
            "--dry-run", action="store_true", name="dry_run",
            help="Only check versions and modules, change nothing")
        self.parser.add_argument(
            "--force-drop-db", action="store_true", name="force_drop_db",
            help="Drop an existing target database before copying")
        add_upgrade_arguments(self.parser)
        self.parser.add_argument(
            "--no-cleanup", action="store_true", name="no_cleanup",
            help="Skip the cleanup and the final update after the migration")
        self.parser.add_argument(
            "--no-drop", action="store_true", name="no_drop",
            help="Keep the tables and columns of the modules the cleanup uninstalls (installed "
                 "but not available, and the modules depending on them), e.g. for a partial "
                 "migration in local tests")

    # ------------------------------------------------------------------
    # checks
    # ------------------------------------------------------------------

    def precheck(self, database):
        """ log a report and return (source major version, missing modules, their dependents);
        the chosen way (our scripts or Odoo) is kept in ``self.upgrade`` """
        con = self.connect_database(database=database)
        try:
            with con.cursor() as cr:
                state = read_database_state(cr)
                source = migration_needed(cr)
                facts = read_upgrade_facts(cr)
        finally:
            con.close()

        target = odoo.release.major_version
        _logger.info("Database %s: base %s, %s installed modules, marker %s",
                     database, state['base_version'], len(state['modules']), state['marker'])
        if not source:
            _logger.info("Database %s is already on %s, nothing to migrate", database, target)
            return None, [], []

        self.upgrade = choose_upgrade(facts, self.params.upgrade_source, self.params.upgrade_aim)
        via_odoo = self.upgrade['source'] == 'odoo'
        (_logger.warning if self.upgrade.get('warning') else _logger.info)(
            "Upgrade source %s: %s", self.upgrade['source'], self.upgrade['reason'])
        if via_odoo:
            _logger.info("A dump of %s goes to %s as %s request, the result comes back as %s",
                         database, UPGRADE_SERVER, self.upgrade['aim'], self.params.database)

        moves = None if via_odoo else load_module_moves(target)
        handled = moves.handled_modules() if moves else set()
        # Studio/imported modules have no source code, they stay installed
        moved, missing, kept = split_unavailable(state, handled)

        _logger.info("Migration %s -> %s, upgrade path%s: %s", source, target,
                     ' after the upgrade by Odoo' if via_odoo else '',
                     ', '.join(get_upgrade_paths(target, self.extra_upgrade_paths(),
                                                 scripts=not via_odoo)))
        dependents = sorted(unloadable_dependents(state['modules'], missing))
        if moved:
            _logger.info("Renamed/merged/removed by the upgrade scripts: %s", ', '.join(moved))
        if kept:
            _logger.info("Without source code (Studio/imported), kept installed: %s",
                         ', '.join(kept))
        if missing and via_odoo:
            # Odoo renames and merges its own modules, only what is left is uninstalled
            _logger.warning("Not available for %s, uninstalled by the cleanup unless the upgrade "
                            "by Odoo replaces them (%s): %s", target,
                            'data kept' if self.params.no_drop else 'data dropped',
                            ', '.join(missing + dependents))
        elif missing:
            _logger.warning("Not available for %s, uninstalled by the cleanup (%s): %s",
                            target, 'data kept' if self.params.no_drop else 'data dropped',
                            ', '.join(missing + dependents))
        if state['marker'] in ('running', 'failed'):
            _logger.warning("Migration marker of %s is %r", database, state['marker'])
        return source, missing, dependents

    def extra_upgrade_paths(self):
        extra = self.params.extra_upgrade_path
        return [p.strip() for p in extra.split(',')] if extra else []

    # ------------------------------------------------------------------
    # steps
    # ------------------------------------------------------------------

    def execute_admin(self, *statements):
        """ statements on the postgres database, outside a transaction """
        con = self.connect_database_admin(database='postgres')
        con.autocommit = True
        try:
            with con.cursor() as cr:
                for statement in statements:
                    if isinstance(statement, tuple):
                        cr.execute(*statement)
                    else:
                        cr.execute(statement)
                return cr.fetchall() if cr.description else None
        finally:
            con.close()

    def database_exists(self, database):
        return bool(self.execute_admin(("SELECT 1 FROM pg_database WHERE datname = %s", [database])))

    def drop_target(self, target):
        """ an existing target database is only dropped with --force-drop-db """
        if not self.database_exists(target):
            return
        if not self.params.force_drop_db:
            raise MigrationError(f"Database {target} exists, use --force-drop-db")
        _logger.warning("Drop database %s", target)
        self.execute_admin(f'DROP DATABASE "{target}" WITH (FORCE)')

    def copy_database(self, source, target):
        self.drop_target(target)
        _logger.info("Copy database %s to %s", source, target)
        self.execute_admin(f'CREATE DATABASE "{target}" WITH TEMPLATE "{source}"')
        self.copy_filestore(source, target)

    def copy_filestore(self, source, target):
        src_store = config.filestore(source)
        dst_store = config.filestore(target)
        if os.path.isdir(dst_store):
            shutil.rmtree(dst_store)
        if os.path.isdir(src_store):
            _logger.info("Copy filestore %s to %s", src_store, dst_store)
            shutil.copytree(src_store, dst_store, symlinks=True)

    # ------------------------------------------------------------------
    # upgrade by Odoo
    # ------------------------------------------------------------------

    def dump_database(self, database, path):
        """ directory format, as the upgrade platform expects it """
        if os.path.isdir(path):
            shutil.rmtree(path)
        _logger.info("Dump %s to %s", database, path)
        OdooUpgrade.run(['pg_dump', '--no-owner', '--format', 'd', '--jobs', str(DUMP_JOBS),
                         '--file', path, database], env=self.get_db_env())

    def restore_upgraded(self, database, dump):
        """ restore the result of Odoo, it has to be on the target version """
        if self.database_exists(database):
            _logger.warning("Drop database %s", database)
            self.execute_admin(f'DROP DATABASE "{database}" WITH (FORCE)')
        _logger.info("Restore the upgraded database as %s", database)
        self.createdb(database)
        # --no-comments: see DatabaseMixin.restore_database
        res = subprocess.run(['pg_restore', '--no-owner', '--no-comments', '--format', 'd',
                              '--jobs', str(DUMP_JOBS), '--dbname', database, dump],
                             check=False, capture_output=True, text=True, env=self.get_db_env())
        if res.stderr:
            _logger.log(logging.WARNING if res.returncode else logging.INFO,
                        "pg_restore output:\n%s", res.stderr.strip()[-4000:])
        con = self.connect_database(database=database)
        try:
            with con.cursor() as cr:
                version = major_version(read_database_state(cr)['base_version'])
        finally:
            con.close()
        if version != odoo.release.major_version:
            raise MigrationError(f"The database restored from Odoo is on {version}, "
                                 f"not on {odoo.release.major_version}")

    def merge_filestore(self, source, target, upgraded):
        """ the filestore of the source plus the files Odoo created """
        if source != target:
            self.copy_filestore(source, target)
        if os.path.isdir(upgraded):
            dst_store = config.filestore(target)
            os.makedirs(dst_store, exist_ok=True)
            _logger.info("Merge the filestore of the upgrade into %s", dst_store)
            OdooUpgrade.run(['rsync', '-a', upgraded + '/', dst_store + '/'])

    def replace_database(self, database, upgraded):
        """ in place: the upgraded database takes the name of the original one """
        replaced = database + REPLACED_SUFFIX
        _logger.warning("Replace database %s by %s", database, upgraded)
        self.execute_admin(
            f'DROP DATABASE IF EXISTS "{replaced}" WITH (FORCE)',
            ("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
             "WHERE datname = %s AND pid <> pg_backend_pid()", [database]),
            f'ALTER DATABASE "{database}" RENAME TO "{replaced}"',
            f'ALTER DATABASE "{upgraded}" RENAME TO "{database}"',
            f'DROP DATABASE "{replaced}" WITH (FORCE)',
        )

    def upgrade_by_odoo(self, source_db, target_db, source_version):
        """ upgrade on upgrade.odoo.com, restore the result as target_db.
        Returns False if Odoo refused the request and auto falls back to our scripts """
        target = odoo.release.major_version
        client = OdooUpgrade(self.upgrade['contract'], target, self.upgrade['aim'],
                             get_upgrade_workdir(target_db))
        restore_db = target_db + UPGRADED_SUFFIX if self.params.in_place else target_db
        try:
            state = client.resume()
            if not state:
                try:
                    client.create()
                except OdooUpgradeError as e:
                    if self.upgrade['requested'] != 'auto':
                        raise
                    _logger.warning("Odoo refused the upgrade request, migrating with our "
                                    "scripts instead: %s", e)
                    return False
                self.dump_database(source_db, client.upload_path)
                client.upload()
            if state != 'done':
                client.wait()
            dump, filestore = client.download()
            self.restore_upgraded(restore_db, dump)
            self.merge_filestore(source_db, target_db, filestore)
            self.write_marker(restore_db, 'running', f"{source_version} -> {target} restored "
                              f"from upgrade.odoo.com ({self.upgrade['aim']})")
            if restore_db != target_db:
                self.replace_database(target_db, restore_db)
            client.finish()
        except OdooUpgradeError as e:
            raise MigrationError(str(e)) from e
        return True

    def write_marker(self, database, state, info=None):
        con = self.connect_database(database=database)
        try:
            with con.cursor() as cr:
                set_marker(cr, state, info)
            con.commit()
        finally:
            con.close()

    def skip_modules(self, database, modules):
        """ the update must not touch modules that cannot be
        loaded, the cleanup uninstalls them afterwards """
        con = self.connect_database(database=database)
        try:
            with con.cursor() as cr:
                cr.execute("UPDATE ir_module_module SET state = 'uninstalled' WHERE name IN %s",
                           [tuple(modules)])
            con.commit()
        finally:
            con.close()

    def cleanup(self, database, uninstall=None):
        """ the fixes of odoo cleanup: unavailable modules, views, assets """
        cleanup = CleanUp()
        cleanup.params = argparse.Namespace(
            fix=True, no_drop=self.params.no_drop, uninstall=uninstall or None, only_raw=False,
            debug=self.params.debug, exit_error=True, database=database)
        cleanup.addons_paths = cleanup.get_addons_paths()
        cleanup.call_with_cr(cleanup.pre_cleanup)
        cleanup.setup_env(database)

    def report(self, collector, steps):
        """ log what each step left behind, the final update has to be clean """
        for step in steps:
            errors, warnings = collector.errors(step), collector.warnings(step)
            _logger.info("Step %s: %s error(s), %s warning(s)", step, len(errors), len(warnings))
        final = steps[-1]
        remaining = collector.errors(final) + collector.warnings(final)
        for message in sorted({f"{r.levelname} {r.name}: {r.getMessage()}"[:300] for r in remaining}):
            _logger.warning("Left after %s: %s", final, message)

    def migrate(self, database, source_version, skipped=None, via_odoo=False):
        """ the steps here; after an upgrade by Odoo only cleanup and update """
        target = odoo.release.major_version
        via = f" via upgrade.odoo.com ({self.upgrade['aim']})" if via_odoo else ""
        info = f"{source_version} -> {target}{via}, started {time.strftime('%Y-%m-%d %H:%M:%S')}"
        self.write_marker(database, 'running', info)
        if skipped:
            self.skip_modules(database, skipped)

        config['upgrade_path'] = get_upgrade_paths(target, self.extra_upgrade_paths(),
                                                   scripts=not via_odoo)
        initialize_sys_path()

        # log unknown dependencies instead of aborting, see ErrorCounter
        os.environ['UPG_RAISE_ON_UNEXISTING_MODULES'] = '0'
        unavailable = missing_dependencies()
        if unavailable:
            _logger.warning("Dependencies not on the addons path, their modules stay "
                            "uninstallable: %s", ', '.join(sorted(unavailable)))

        unknown_filter = UnknownModulesFilter(unavailable)
        logging.getLogger(unknown_filter.logger_name).addFilter(unknown_filter)
        collector = LogCollector()
        logging.getLogger().addHandler(collector)
        steps = ['migrate'] if self.params.no_cleanup else ['migrate', 'cleanup', 'update']
        if via_odoo:
            steps.remove('migrate')
        if not steps:
            self.write_marker(database, 'done', f"{info}, without cleanup and update")
            return
        started = time.time()
        try:
            _logger.info("Migrate %s: %s", database, info)
            for step in steps:
                collector.step = step
                if step == 'migrate':
                    update_database(database, modules=['base'])
                elif step == 'cleanup':
                    # the missing modules are found by the cleanup itself
                    dependents = [m for m in skipped or () if get_manifest(m)]
                    self.cleanup(database, uninstall=dependents)
                else:
                    # a regular odoo update (base = all modules) on the cleaned database
                    _logger.info("Final update of %s", database)
                    update_database(database)
                odoo.modules.registry.Registry.delete(database)
                if collector.errors(step):
                    break
        except Exception:
            _logger.exception("Migration of %s failed", database)
        finally:
            logging.getLogger().removeHandler(collector)
            logging.getLogger(unknown_filter.logger_name).removeFilter(unknown_filter)

        duration = f"{time.time() - started:.0f}s"
        self.report(collector, steps)
        errors = collector.errors()
        if errors:
            self.write_marker(database, 'failed', f"{info}, {len(errors)} errors")
            raise MigrationError(f"Migration of {database} logged {len(errors)} "
                                 f"error(s) after {duration}, marker set to failed")
        left = len(collector.warnings(steps[-1]))
        self.write_marker(database, 'done', f"{info}, done after {duration}, "
                                            f"{left} warning(s) in step {steps[-1]}")
        _logger.info("Migration of %s done after %s, %s warning(s) left after %s",
                     database, duration, left, steps[-1])

    # ------------------------------------------------------------------

    def run_config(self):
        self.setup_db_env()
        target_db = self.params.database
        source_db = target_db if self.params.in_place else (self.params.source or None)
        if not source_db:
            raise MigrationError("Give --source (copy) or --in-place")
        if not self.params.in_place and source_db == target_db:
            raise MigrationError("--source and --database are the same, use --in-place")

        source_version, missing, dependents = self.precheck(source_db)
        if self.params.dry_run or not source_version:
            return

        if self.upgrade['source'] == 'odoo':
            if not self.params.in_place and not self.params.force_drop_db \
                    and self.database_exists(target_db):
                # before anything goes to Odoo
                raise MigrationError(f"Database {target_db} exists, use --force-drop-db")
            if self.upgrade_by_odoo(source_db, target_db, source_version):
                con = self.connect_database(database=target_db)
                try:
                    with con.cursor() as cr:
                        state = read_database_state(cr)
                finally:
                    con.close()
                # what Odoo did not replace is uninstalled by the cleanup
                missing = split_unavailable(state)[1]
                dependents = sorted(unloadable_dependents(state['modules'], missing))
                self.migrate(target_db, source_version, skipped=missing + dependents,
                             via_odoo=True)
                return

        if not self.params.in_place:
            self.copy_database(source_db, target_db)
        self.migrate(target_db, source_version, skipped=missing + dependents)

    def run(self, args):
        try:
            super().run(args)
        except MigrationError as e:
            _logger.error(str(e))
            raise SystemExit(1)


def run_migration_if_needed(database, debug=False, upgrade_source=None, upgrade_aim=None,
                            extra_upgrade_path=None):
    """ called by odoo update: migrate in place when the database is on the
    previous major version. Returns True if a migration ran. """
    command = Migrate()
    command.params = argparse.Namespace(
        database=database, source=None, in_place=True, dry_run=False,
        force_drop_db=False, upgrade_source=upgrade_source, upgrade_aim=upgrade_aim,
        extra_upgrade_path=extra_upgrade_path, no_cleanup=False, no_drop=False,
        debug=debug, exit_error=True)
    command.setup_db_env()
    con = command.connect_database(database=database)
    try:
        with con.cursor() as cr:
            source_version = migration_needed(cr)
    finally:
        con.close()
    if not source_version:
        return False
    _logger.warning("Database %s is on %s, migrating to %s instead of updating",
                    database, source_version, odoo.release.major_version)
    command.run_config()
    return True
