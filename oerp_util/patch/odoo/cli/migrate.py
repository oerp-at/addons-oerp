import argparse
import importlib.util
import logging
import os
import shutil
import time

import odoo
from odoo.modules.module import get_manifest, get_modules, initialize_sys_path
from odoo.tools.config import config

from . import Command
from .assemble import CommandMixin, DatabaseMixin, get_base_dir, update_database
from .cleanup import CleanUp

_logger = logging.getLogger(__name__)

MARKER_STATE = 'oerp.migration.state'
MARKER_INFO = 'oerp.migration.info'
INSTALLED_STATES = ('installed', 'to upgrade', 'to remove')


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


def get_upgrade_paths(target_version, extra_paths=None):
    upgrade_dir = get_upgrade_dir()
    paths = [
        os.path.join(upgrade_dir, 'upgrade-util', 'src'),
        os.path.join(upgrade_dir, target_version),
    ]
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
        'marker': marker[0] if marker else None,
    }


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
        self.parser.add_argument(
            "--extra-upgrade-path", metavar="EXTRA_UPGRADE_PATH", name="extra_upgrade_path",
            help="Additional upgrade script directories, comma separated")
        self.parser.add_argument(
            "--no-cleanup", action="store_true", name="no_cleanup",
            help="Skip the cleanup and the final update after the migration")
        self.parser.add_argument(
            "--no-drop", action="store_true", name="no_drop",
            help="Partial migration for local tests: installed modules that are not available "
                 "(and the modules depending on them) are uninstalled instead of stopping the "
                 "migration. The cleanup keeps their tables and columns")

    # ------------------------------------------------------------------
    # checks
    # ------------------------------------------------------------------

    def precheck(self, database):
        """ log a report and return (source major version, missing modules, their dependents) """
        con = self.connect_database(database=database)
        try:
            with con.cursor() as cr:
                state = read_database_state(cr)
                source = migration_needed(cr)
        finally:
            con.close()

        target = odoo.release.major_version
        _logger.info("Database %s: base %s, %s installed modules, marker %s",
                     database, state['base_version'], len(state['modules']), state['marker'])
        if not source:
            _logger.info("Database %s is already on %s, nothing to migrate", database, target)
            return None, [], []

        moves = load_module_moves(target)
        handled = moves.handled_modules() if moves else set()
        missing, moved = [], []
        for name in state['modules']:
            manifest = get_manifest(name)
            if manifest and manifest.get('installable', True):
                continue
            (moved if name in handled else missing).append(name)

        _logger.info("Migration %s -> %s, upgrade path: %s", source, target,
                     ', '.join(get_upgrade_paths(target, self.extra_upgrade_paths())))
        dependents = sorted(unloadable_dependents(state['modules'], missing))
        if moved:
            _logger.info("Renamed/merged/removed by the upgrade scripts: %s", ', '.join(moved))
        if missing and self.params.no_drop:
            _logger.warning("Partial migration, uninstalled with their data kept: %s",
                            ', '.join(missing + dependents))
        elif missing:
            _logger.error("Installed but not available for %s (port, add to oerp_module_moves.py "
                          "or --no-drop for a partial migration): %s", target, ', '.join(missing))
        if state['marker'] in ('running', 'failed'):
            _logger.warning("Migration marker of %s is %r", database, state['marker'])
        return source, missing, dependents

    def extra_upgrade_paths(self):
        extra = self.params.extra_upgrade_path
        return [p.strip() for p in extra.split(',')] if extra else []

    # ------------------------------------------------------------------
    # steps
    # ------------------------------------------------------------------

    def copy_database(self, source, target):
        con = self.connect_database_admin(database='postgres')
        con.autocommit = True
        try:
            with con.cursor() as cr:
                cr.execute("SELECT 1 FROM pg_database WHERE datname = %s", [target])
                if cr.fetchone():
                    if not self.params.force_drop_db:
                        raise MigrationError(f"Database {target} exists, use --force-drop-db")
                    _logger.warning("Drop database %s", target)
                    cr.execute(f'DROP DATABASE "{target}" WITH (FORCE)')
                _logger.info("Copy database %s to %s", source, target)
                cr.execute(f'CREATE DATABASE "{target}" WITH TEMPLATE "{source}"')
        finally:
            con.close()

        src_store = config.filestore(source)
        dst_store = config.filestore(target)
        if os.path.isdir(dst_store):
            shutil.rmtree(dst_store)
        if os.path.isdir(src_store):
            _logger.info("Copy filestore %s to %s", src_store, dst_store)
            shutil.copytree(src_store, dst_store, symlinks=True)

    def write_marker(self, database, state, info=None):
        con = self.connect_database(database=database)
        try:
            with con.cursor() as cr:
                set_marker(cr, state, info)
            con.commit()
        finally:
            con.close()

    def skip_modules(self, database, modules):
        """ partial migration: the update must not touch modules that cannot be
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

    def migrate(self, database, source_version, skipped=None):
        target = odoo.release.major_version
        info = f"{source_version} -> {target}, started {time.strftime('%Y-%m-%d %H:%M:%S')}"
        self.write_marker(database, 'running', info)
        if skipped:
            self.skip_modules(database, skipped)

        config['upgrade_path'] = get_upgrade_paths(target, self.extra_upgrade_paths())
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
        if missing and not self.params.no_drop:
            raise MigrationError("Installed modules are not available, see above")

        if not self.params.in_place:
            self.copy_database(source_db, target_db)
        self.migrate(target_db, source_version, skipped=missing + dependents)

    def run(self, args):
        try:
            super().run(args)
        except MigrationError as e:
            _logger.error(str(e))
            raise SystemExit(1)


def run_migration_if_needed(database, debug=False):
    """ called by odoo update: migrate in place when the database is on the
    previous major version. Returns True if a migration ran. """
    command = Migrate()
    command.params = argparse.Namespace(
        database=database, source=None, in_place=True, dry_run=False,
        force_drop_db=False, extra_upgrade_path=None, no_cleanup=False, no_drop=False,
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
