import os
import shutil
from datetime import datetime
import logging
import polib

import odoo
from odoo.tools import misc
from odoo.tools.translate import (PoFileReader,
                                  PoFileWriter,
                                  TranslationModuleReader)

from . import Command
from .assemble import CommandMixin


_logger = logging.getLogger(__name__)

ODOO_RELEASE = odoo.release


class PoIgnoreFileWriter(PoFileWriter):
    def __init__(self, target, modules, lang, ignore, ignore_empty=False, only_empty=False):
        super(PoIgnoreFileWriter, self).__init__(target, lang)
        self.modules = modules
        self.ignore = ignore
        self.ignore_empty = ignore_empty
        self.only_empty = only_empty

    def write_rows(self, rows):
        # we now group the translations by source. That means one translation per source.
        grouped_rows = {}
        for module, type, name, res_id, src, trad, comments in rows:
            row = grouped_rows.setdefault(src, {})
            row.setdefault('modules', set()).add(module)
            if not row.get('translation') and trad != src:
                row['translation'] = trad
            row.setdefault('tnrs', []).append((type, name, res_id))
            row.setdefault('comments', set()).update(comments)

        for src, row in sorted(grouped_rows.items()):
            if not self.lang:
                # translation template, so no translation value
                row['translation'] = ''
            elif not row.get('translation'):
                row['translation'] = ''

            # check if translations should ignored
            write_translation = True
            if self.ignore or self.ignore_empty or self.only_empty:
                for tnr in row["tnrs"]:
                    comments = row['comments']
                    if not comments:
                        comments = ['']
                    for comment in comments:
                        # type, name, imd_name, src, value, comments
                        value = row['translation']
                        key = (tnr[0], tnr[1], str(tnr[2]), src,
                               value, comment)
                        if self.ignore and key in self.ignore:
                            write_translation = False
                        elif self.ignore_empty and not value:
                            write_translation = False
                        elif self.only_empty and value:
                            write_translation = False

            if write_translation:
                self.add_entry(row['modules'], row['tnrs'], src,
                               row['translation'], row['comments'])

        self.po.header = "Translation of %s.\n" \
                    "This file contains the translation of the following modules:\n" \
                    "%s" % (ODOO_RELEASE.description, ''.join("\t* %s\n" % m for m in self.modules))
        now = datetime.utcnow().strftime('%Y-%m-%d %H:%M+0000')
        self.po.metadata = {
            'Project-Id-Version': f'{ODOO_RELEASE.description} {ODOO_RELEASE.version}',
            'Report-Msgid-Bugs-To': '',
            'POT-Creation-Date': now,
            'PO-Revision-Date': now,
            'Last-Translator': '',
            'Language-Team': '',
            'MIME-Version': '1.0',
            'Content-Type': 'text/plain; charset=UTF-8',
            'Content-Transfer-Encoding': '',
            'Plural-Forms': '',
        }

        # buffer expects bytes
        self.buffer.write(str(self.po).encode())


class Po_Export(CommandMixin, Command):

    def __init__(self):
        super().__init__()
        self.lang = None
        self.langfile = None
        self.pot = False
        self.modpath = None
        self.langdir = None
        self.export_backup_file = None
        self.export_file = None

        self.parser.add_argument(
            "--merge",
            nargs='+',
            name="merge",
            help="*.po files to merge into export file, if the translation is empty"
        )
        self.parser.add_argument(
            "--force-merge",
            nargs='+',
            name="force_merge",
            help="*.po files to merge into export file"
        )
        self.parser.add_argument(
            "--no-merge",
            name="no_merge",
            action="store_true",
            help="No merge of backup file"
        )
        self.parser.add_argument(
            "--ignore-empty",
            name="ignore_empty",
            action="store_true",
            help="Ignore empty translations"
        )
        self.parser.add_argument(
            "--ignore-file",
            name="ignore_file",
            action="store_true",
            help="Export empty into ignore file"
        )
        self.parser.add_argument(
            "--pot",
            name="pot",
            action="store_true",
            help="Export translation template"
        )
        self.parser.add_argument(
            "--lang",
            name="lang",
            metavar="LANG",
            help="Language to export"
        )
        self.parser.add_argument(
            "--keep-inherited",
            name="keep_inherited",
            action="store_true",
            help="Keep translations of inherited/mixin fields and inherited model "
                 "names (e.g. 'Created by', 'Messages')"
        )

    def _is_inherited_term(self, env, module, ttype, name, res_id):
        """Check if a translation term originates from another module.

        Fields introduced by another module (magic columns, mail mixin, etc.)
        have their _modules set to that source module, not the current one.
        Likewise, model names inherit from the module that first defined them.
        """
        if ttype not in ('model', 'model_terms') or not res_id or '.' not in res_id:
            return False
        record = env.ref(res_id, raise_if_not_found=False)
        if not record:
            return False
        record_model = record._name
        if record_model == 'ir.model.fields':
            # Magic fields (create_uid, write_date, id, display_name, etc.)
            # are inherited from BaseModel by every model.
            from odoo.orm.models import MAGIC_COLUMNS
            MAGIC_FIELD_NAMES = frozenset(list(MAGIC_COLUMNS) + ['display_name', '__last_update'])
            if record.name in MAGIC_FIELD_NAMES:
                return True
            field = env[record.model]._fields.get(record.name)
            # _modules contains the mixin module for mixin fields
            # (e.g. message_ids._modules == ('mail',)).
            if field and field._modules and module not in field._modules:
                return True
            return False
        if record_model == 'ir.model.fields.selection':
            field_model = record.field_id.model
            field = env[field_model]._fields.get(record.field_id.name)
            return bool(field and field._modules) and module not in field._modules
        if record_model == 'ir.model':
            target = env.get(record.model)
            return bool(target is not None and target._original_module) \
                and target._original_module != module
        return False

    def run_config(self):
        # check module
        if not self.params.module:
            _logger.error("No module defined for export!")
            return
        # check path
        self.modpath = odoo.modules.get_module_path(self.params.module)
        if not self.modpath:
            _logger.error("No module %s not found in path!",
                          self.params.module)
            return

        # check if it should be a template
        if (self.params.pot
            or not self.params.lang
            or self.params.lang == "pot"):
            self.lang = None
            self.langfile = self.params.module + ".pot"
            self.pot = True
        else:
            self.lang = self.params.lang
            self.pot = False
            self.langfile = self.lang.split("_")[0] + ".po"

        self.langdir = os.path.join(self.modpath, "i18n")
        if not os.path.exists(self.langdir):
            _logger.warning("Created language directory %s", self.langdir)
            os.mkdir(self.langdir)

        # run with env
        self.setup_env()

    def trans_export(self, lang, modules, buffer, cr, ignore, ignore_empty=False, only_empty=False):
        translations = TranslationModuleReader(cr, modules=modules, lang=lang)
        rows = list(translations)
        if not self.params.keep_inherited:
            from odoo import SUPERUSER_ID
            from odoo.api import Environment
            env = Environment(cr, SUPERUSER_ID, {})
            rows = [r for r in rows if not self._is_inherited_term(env, r[0], r[1], r[2], r[3])]
        export_modules = set(r[0] for r in rows)
        writer = PoIgnoreFileWriter(buffer, export_modules, lang, ignore, ignore_empty=ignore_empty, only_empty=only_empty)
        writer.write_rows(rows)
        del translations

    def load_ignore(self):
        ignore = None
        ignore_filename = f'{self.export_file}.ignore'
        if os.path.exists(ignore_filename):
            _logger.info("Load ignore file %s", ignore_filename)
            ignore = set()
            with misc.file_open(ignore_filename, mode="rb") as fileobj:
                reader = PoFileReader(fileobj)
                for row in reader:
                    if not row.get("value"):
                        # type, name, imd_name, src, value, comments
                        imd_name = row.get("imd_name")
                        module = row.get("module") or ""
                        if imd_name and module and not imd_name.find(
                                ".") > 0:
                            imd_name = f'{module}.{imd_name}'
                        ignore.add(
                            (row["type"], row["name"], imd_name,
                                row["src"], row["value"], row["comments"]))
        return ignore

    def create_backup(self):
        if not self.export_backup_file:
            return False

        _logger.info('Create backup %s', self.export_backup_file)
        shutil.copy(self.export_file, self.export_backup_file)
        return True

    def remove_backup(self):
        if not self.export_backup_file:
            return False
        os.remove(self.export_backup_file)
        return True

    def restore_backup(self):
        if not self.export_backup_file:
            return False
        _logger.warning("Restore previous %s", self.export_file)
        shutil.copy(self.export_backup_file, self.export_file)
        return True

    def merge(self, file_to_merge, force=False):
        """ merge translations from backup to untranslated entries """
        if not file_to_merge:
            return False
        _logger.info('Merge translations with %s', file_to_merge)
        po_file = polib.pofile(self.export_file)

        # merge key function
        def fuzzy_key(entry):
            return entry.msgid_with_context

        # load translations to merge
        po_file_to_merge = polib.pofile(file_to_merge)
        po_fuzzy_merge_entry_set = dict(
            (fuzzy_key(entry), entry) for entry in po_file_to_merge if entry.msgstr.strip()
        )

        # build translation set
        po_merge_entry_set = {
            str(m) for m in po_file_to_merge
        }

        # merge translations
        po_entry_count = 0
        changed = False
        for po_entry in po_file:
            po_entry_count += 1

            if not self.pot and not po_entry.msgstr or force:
                po_merge_entry = po_fuzzy_merge_entry_set.get(fuzzy_key(po_entry))
                if po_merge_entry and po_merge_entry.msgstr:
                    po_entry.msgstr = po_merge_entry.msgstr

            # check if entry is in the translation set
            if str(po_entry) not in po_merge_entry_set:
                changed = True

        # check amount of entries
        if po_entry_count != len(po_merge_entry_set):
            changed = True

        # write po file
        po_file.save(self.export_file)
        return changed

    def run_config_env(self, env):
        # check module installed
        if not env["ir.module.module"].search(
            [("state", "=", "installed"), ("name", "=", self.params.module)]):
            _logger.error("No module %s installed!", self.params.module)
            return
        # set export file
        self.export_file = os.path.join(self.langdir, self.langfile)
        self.export_backup_file = (f'{self.export_file}.backup'
                                    if os.path.exists(self.export_file) else None)
        # preprocessing
        self.create_backup()

        # write ignore file if enabled
        if self.params.ignore_file:
            with open(f'{self.export_file}.ignore', "wb") as export_stream:
                _logger.info('Writing %s', self.export_file)
                self.trans_export(self.lang, [self.params.module], export_stream,
                                env.cr, None, only_empty=True)

        # load ignore file
        ignore = self.load_ignore()

        # write translations
        with open(self.export_file, "wb") as export_stream:
            _logger.info('Writing %s', self.export_file)
            self.trans_export(self.lang, [self.params.module], export_stream,
                              env.cr, ignore, ignore_empty=self.params.ignore_empty)

        # merge with other files
        if self.params.merge:
            for merge_file in self.params.merge:
                self.merge(merge_file)
        if self.params.force_merge:
            for merge_file in self.params.merge:
                self.merge(merge_file, force=True)

        # merge empty translations with backup file (if exists)
        # and delete backup file afterwards
        if not self.params.no_merge and self.export_backup_file:
            if not self.merge(self.export_backup_file):
                # if no change, restore backup file
                # to keep timestamp
                _logger.warning('No translations changes')
                self.restore_backup()
        # remove backup
        self.remove_backup()
