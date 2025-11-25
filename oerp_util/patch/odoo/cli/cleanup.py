import os
from operator import itemgetter
import logging
import psycopg2

import odoo
from odoo.tools import unique, groupby
from odoo.addons.base.models.ir_model import MODULE_UNINSTALL_FLAG
from odoo.models import LOG_ACCESS_COLUMNS

from . import Command
from .assemble import CommandMixin, DatabaseMixin

ODOO_RELEASE = odoo.release
ADDON_API = ODOO_RELEASE.version

_logger = logging.getLogger(__name__)


class CleanUp(CommandMixin, Command, DatabaseMixin):
    """ CleanUp Database """

    def __init__(self):
        super(CleanUp, self).__init__()

        self.parser.add_argument("--fix",
                                action="store_true",
                                name="fix",
                                help="Do/Fix all offered cleanup(s)")

        self.parser.add_argument("--no-drop",
                                action="store_true",
                                name="nodrop",
                                help="Do not drop columns and tables")

        self.parser.add_argument("--uninstall",
                                type=str,
                                name="uninstall",
                                nargs="+",
                                help="Modules which should be uninstall during cleanup")

        self.parser.add_argument("--only-raw",
                                action="store_true",
                                name="raw",
                                help="Only raw fixes without module update")

        self.addons_paths = None



    def _module_data_uninstall_no_drop(self, env, modules_to_remove):
        """ Deletes all not available modules, but did not drop any columns for tables
        """
        from odoo.addons.base.models.ir_model import IrModelFields, IrModel
        drop_column_fct = IrModelFields._drop_column
        drop_table_fct = IrModel._drop_table
        try:
            IrModelFields._drop_column = lambda *args, **kwargs: True
            IrModel._drop_table = lambda *args, **kwargs: True
            self._module_data_uninstall(env, modules_to_remove)
        finally:
            IrModelFields._drop_column = drop_column_fct
            IrModel._drop_table = drop_table_fct


    def _module_data_uninstall(self, env, modules_to_remove):
        """Deletes all the records referenced by the ir.model.data entries
        ``ids`` along with their corresponding database backed (including
        dropping tables, columns, FKs, etc, as long as there is no other
        ir.model.data entry holding a reference to them (which indicates that
        they are still owned by another module).
        Attempts to perform the deletion in an appropriate order to maximize
        the chance of gracefully deleting all records.
        This step is performed as part of the full uninstallation of a module.
        """

        # enable model/field deletion
        # we deactivate prefetching to not try to read a column that has been deleted
        env = env(context={MODULE_UNINSTALL_FLAG: True, 'prefetch_fields': False})

        # determine records to unlink
        records_items = []              # [(model, id)]
        model_ids = []
        field_ids = []
        selection_ids = []
        constraint_ids = []

        # delete orphaned assets
        cr = env.cr
        for module_name in modules_to_remove:
            # pylint: disable=sql-injection
            cr.execute(f"DELETE FROM ir_asset WHERE path LIKE '/{module_name}/%'")

        # search for model data
        ModelData = env['ir.model.data']
        module_data = ModelData.search([('module', 'in', modules_to_remove)], order='id DESC')
        for data in module_data:
            if data.model == 'ir.model':
                model_ids.append(data.res_id)
            elif data.model == 'ir.model.fields':
                field_ids.append(data.res_id)
            elif data.model == 'ir.model.fields.selection':
                selection_ids.append(data.res_id)
            elif data.model == 'ir.model.constraint':
                constraint_ids.append(data.res_id)
            else:
                records_items.append((data.model, data.res_id))

        # avoid prefetching fields that are going to be deleted: during uninstall, it is
        # possible to perform a recompute (via flush) after the database columns have been
        # deleted but before the new registry has been created, meaning the recompute will
        # be executed on a stale registry, and if some of the data for executing the compute
        # methods is not in cache it will be fetched, and fields that exist in the registry but not
        # in the database will be prefetched, this will of course fail and prevent the uninstall.
        for ir_field in env['ir.model.fields'].browse(field_ids):
            if not ir_field.exists():
                field_ids.remove(ir_field.id)
                continue
            if ir_field.model in env:
                model = env[ir_field.model]
                field = model._fields.get(ir_field.name)
                if field is not None:
                    field.prefetch = False

        # to collect external ids of records that cannot be deleted
        undeletable_ids = []

        def delete(records):
            # do not delete records that have other external ids (and thus do
            # not belong to the modules being installed)
            ref_data = ModelData.search([
                ('model', '=', records._name),
                ('res_id', 'in', records.ids),
            ])
            records -= records.browse((ref_data - module_data).mapped('res_id'))
            if not records:
                return

            # special case for ir.model.fields
            if records._name == 'ir.model.fields':
                missing = records - records.exists()
                if missing:
                    # delete orphan external ids right now;
                    # an orphan ir.model.data can happen if the ir.model.field is deleted via
                    # an ONDELETE CASCADE, in which case we must verify that the records we're
                    # processing exist in the database otherwise a MissingError will be raised
                    orphans = ref_data.filtered(lambda r: r.res_id in missing._ids)
                    _logger.info('Deleting orphan ir_model_data %s', orphans)
                    orphans.unlink()
                    # /!\ this must go before any field accesses on `records`
                    records -= missing
                # do not remove LOG_ACCESS_COLUMNS unless _log_access is False
                # on the model
                records -= records.filtered(lambda f: f.name == 'id' or (
                    f.name in LOG_ACCESS_COLUMNS and
                    f.model in env and env[f.model]._log_access
                ))

            # now delete the records
            _logger.info('Deleting %s', records)
            try:
                with ModelData.env.cr.savepoint():
                    records.unlink()
            # pylint: disable=broad-exception-caught
            except Exception:
                if len(records) <= 1:
                    undeletable_ids.extend(ref_data._ids)
                else:
                    # divide the batch in two, and recursively delete them
                    half_size = len(records) // 2
                    delete(records[:half_size])
                    delete(records[half_size:])

        # remove non-model records first, grouped by batches of the same model
        for model, items in groupby(unique(records_items), itemgetter(0)):
            if model in env:
                delete(env[model].browse(item[1] for item in items))

        # Remove copied views. This must happen after removing all records from
        # the modules to remove, otherwise ondelete='restrict' may prevent the
        # deletion of some view. This must also happen before cleaning up the
        # database schema, otherwise some dependent fields may no longer exist
        # in database.
        modules = env['ir.module.module'].search([('name', 'in', modules_to_remove)])
        modules._remove_copied_views()

        # remove constraints
        delete(env['ir.model.constraint'].browse(unique(constraint_ids)))
        constraints = env['ir.model.constraint'].search([('module', 'in', modules.ids)])
        constraints.unlink()

        # If we delete a selection field, and some of its values have ondelete='cascade',
        # we expect the records with that value to be deleted. If we delete the field first,
        # the column is dropped and the selection is gone, and thus the records above will not
        # be deleted.
        delete(env['ir.model.fields.selection'].browse(unique(selection_ids)).exists())
        delete(env['ir.model.fields'].browse(unique(field_ids)))

        if not self.params.no_drop:
            # drop releations
            relations = env['ir.model.relation'].search([('module', 'in', modules.ids)])
            relations._module_data_uninstall()

        # remove models
        delete(env['ir.model'].browse(unique(model_ids)))

        # log undeletable ids
        _logger.info("ir.model.data could not be deleted (%s)", undeletable_ids)

        # sort out which undeletable model data may have become deletable again because
        # of records being cascade-deleted or tables being dropped just above
        for data in ModelData.browse(undeletable_ids).exists():
            if data.model in env:
                record = env[data.model].browse(data.res_id)
                try:
                    with env.cr.savepoint():
                        if record.exists():
                            # record exists therefore the data is still undeletable,
                            # remove it from module_data
                            module_data -= data
                            continue
                # pylint: disable=except-pass
                except psycopg2.ProgrammingError:
                    # This most likely means that the record does not exist, since record.exists()
                    # is rougly equivalent to `SELECT id FROM table WHERE id=record.id` and it may raise
                    # a ProgrammingError because the table no longer exists (and so does the
                    # record), also applies to ir.model.fields, constraints, etc.
                    pass
        # remove remaining module data records
        module_data.unlink()

    def _cleanup_modules(self, env):
        cr = env.cr
        cr.execute("SELECT name, latest_version FROM ir_module_module WHERE name != 'studio_customization'")
        rows = cr.fetchall()
        invalid_modules = []
        uninstall_set = set(self.params.uninstall) if self.params.uninstall else set()
        for name, latest_version in rows:
            info = odoo.modules.module.get_manifest(name)
            # add modules which are not available or installable
            if not info or not info.get('installable', True) or name in uninstall_set:
                invalid_modules.append(name)

        # uninstall invalid modules
        invalid_modules = tuple(invalid_modules)
        if invalid_modules:
            for module_name in invalid_modules:
                if self.params.fix:
                    module = env['ir.module.module'].search([('name', '=', module_name)], limit=1)
                    if module:
                        _logger.warning("[FIX] Uninstall module: %s", module_name)

                        # remove module user group relation
                        cr.execute("""DELETE FROM ir_model_data WHERE
                            id IN (
                            SELECT d.id FROM ir_model_data d
                            INNER JOIN res_groups_users_rel rel ON rel.gid = d.res_id
                            WHERE d.model='res.groups'
                            AND d.module = %s
                            )""", (module_name,))

                        if self.params.no_drop:
                            self._module_data_uninstall_no_drop(env, [module_name])
                        else:
                            self._module_data_uninstall(env, [module_name])

                        cr.execute('DELETE FROM ir_module_module WHERE name = %s', (module_name, ))
                else:
                    _logger.warning("[FOUND] Unavailable module: %s", module_name)

            if self.params.fix:
                _logger.warning("[FIX] cleanup module state and dependencies")
                # remove invalid modules from dependency lists
                cr.execute('DELETE FROM ir_module_module_dependency WHERE name in %s', (tuple(invalid_modules), ))
                # reset module state
                cr.execute("UPDATE ir_module_module SET state = 'installed' WHERE state = 'to upgrade'")

        # check unreferenced
        cr.execute("""SELECT d.name FROM ir_model_data d
                    LEFT JOIN ir_module_module m ON m.id = d.res_id
                    WHERE d.model = 'ir.module.module'
                    AND m.id IS NULL""")
        unref_modules = [r[0] for r in cr.fetchall()]
        if unref_modules:
            if self.params.fix:
                # remove unreferenced
                _logger.warning("[FIX] unreferenced modul data: %s", ', '.join(unref_modules))
                cr.execute("""DELETE FROM ir_model_data WHERE id IN (
                    SELECT d.id FROM ir_model_data d
                    LEFT JOIN ir_module_module m ON m.id = d.res_id
                    WHERE d.model = 'ir.module.module'
                    AND m.id IS NULL
                )""")
            else:
                _logger.warning("[FOUND] unreferenced modul data: %s", ', '.join(unref_modules))

    def run_config(self):
        self.addons_paths = self.get_addons_paths()
        self.call_with_cr(self.pre_cleanup)
        if not self.params.only_raw:
            self.setup_env()

    def get_file_path(self, relative_file_path):
        for addon_path in self.addons_paths:
            file_path = os.path.join(addon_path, relative_file_path)
            if os.path.exists(file_path):
                return file_path
        return None

    def pre_cleanup(self, cr):
        self.pre_cleanup_assets(cr)
        self.pre_cleanup_views(cr)

    def pre_cleanup_assets(self, cr):
        cr.execute('SELECT id, path FROM ir_asset WHERE active')
        commit = False
        for asset_id, asset_path in cr.fetchall():
            if not self.get_file_path(asset_path):
                if self.params.fix:
                    _logger.info('[FIX] delete invalid asset %s', asset_path)
                    cr.execute('DELETE FROM ir_asset WHERE id = %s', (asset_id,))
                    commit = True
                else:
                    _logger.info("[FOUND] Invalid asset %s", asset_path)

        if commit:
            cr.execute('COMMIT')

    def pre_cleanup_views(self, cr):
        # cleanup not available views
        cr.execute("""SELECT v.id, v.arch_fs, v.inherit_id, m.latest_version FROM ir_ui_view v
            LEFT JOIN ir_model_data d ON d.res_id = v.id AND d.model = 'ir.ui.view'
            LEFT JOIN ir_module_module m ON m.name = d.module
            WHERE v.arch_prev IS NOT NULL
            AND m.name != 'studio_customization'
            AND v.arch_fs IS NOT NULL
            AND v.active""")

        delete_view_ids = {}
        commit = False

        for view_id, arch_fs, inherit_id, module_version in cr.fetchall():
            if not self.get_file_path(arch_fs) or (module_version and module_version < ADDON_API):
                if self.params.fix:
                    delete_view_ids[view_id] = (inherit_id, arch_fs)
                    commit = True
                else:
                    _logger.warning('[FOUND] invalid view %s', arch_fs)

        # get report layout view ids
        cr.execute("SELECT view_id FROM report_layout")
        report_layout_view_ids = set([r[0] for r in cr.fetchall()])

        while delete_view_ids:
            # delete views which have not dependency
            deleted_views = []
            for view_id, (inherit_id, arch_fs) in delete_view_ids.items():
                _logger.warning('[FIX] Removing invalid view %s', arch_fs)
                child_views = [k for k, (child_inherit_id, child_arch_fs) in delete_view_ids.items() if child_inherit_id == view_id]
                if not child_views:
                    # special case for openupgrade_scripts
                    if arch_fs.startswith('openupgrade_scripts'):
                        cr.execute("DELETE FROM ir_ui_view WHERE inherit_id = %s", (view_id,))
                    else:
                        cr.execute("DELETE FROM ir_ui_view WHERE inherit_id = %s AND NOT active", (view_id,))

                    # delete report layout if view is used
                    if view_id in report_layout_view_ids:
                        _logger.warning('[FIX] Deactivate report layout view %s', arch_fs)
                        cr.execute("DELETE FROM report_layout WHERE view_id = %s", (view_id,))

                    cr.execute("DELETE FROM ir_ui_view WHERE id = %s", (view_id,))
                    deleted_views.append(view_id)

            # remove view from dict
            for view_id in deleted_views:
                delete_view_ids.pop(view_id)

            # check if there wehre something to delete
            if not deleted_views and delete_view_ids:
                _logger.error('Unable to delete views with IDs %s', delete_view_ids.keys())
                break

        if commit:
            cr.execute("COMMIT")

    def run_config_env(self, env):
        # check full cleanup
        cr = env.cr
        try:
            self._cleanup_modules(env)
            if self.params.fix:
                # pylint: disable=invalid-commit
                cr.commit()
        # pylint: disable=broad-exception-caught
        except Exception as e:
            if self.params.debug:
                _logger.exception(e)
            else:
                _logger.error(e)
            return
        finally:
            cr.rollback()