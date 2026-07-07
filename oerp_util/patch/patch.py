#!/usr/bin/env python3

import sys
import os
import shutil
import re
import logging

_logger = logging.getLogger(__name__)

PLACEHOLDER_PATTERN = re.compile(r'\{\{(\{\{)?\s*([A-Za-z0-9_]+)\s*(\}\})?\}\}')


class PatchError(Exception):
    pass


def replace_placeholders(value, context):
    """
    Replace all placeholders in the format {{ placeholder }} with values from context dictionary.
    """
    def replace_match(match):
        placeholder = match.group(2).strip()
        if match.group(1) == '{{' and match.group(3) == '}}':
            return '{{ ' + placeholder + ' }}'
        elif placeholder not in context:
            return placeholder
        return str(context.get(placeholder) or '')

    value = PLACEHOLDER_PATTERN.sub(replace_match, value)
    return value

def patch(dst_path, src_path=None, directory=False, template_ctx=None, patch_back=False, add_init=False, copy_tree=False, update=True, force=False):
    """ A simple patch function with less library dependencies that it runs if python3 is installed."""
    if directory:
        if not os.path.exists(dst_path):
            os.mkdir(dst_path)
            return True
        return False

    file_name = os.path.basename(dst_path)
    name = os.path.splitext(file_name)[0]

    # file patch
    # with patch back option
    if patch_back:

        if not src_path:
            raise PatchError('patch_back requires src_path')

        if not os.path.exists(dst_path):
            _logger.info('copy %s', file_name)
            shutil.copy(src_path, dst_path)
            if add_init:
                dst_dir = os.path.dirname(dst_path)
                dst_init_path = os.path.join(dst_dir, '__init__.py')

                # check if init file exists
                if not os.path.exists(dst_init_path):
                    raise PatchError(f'__init__.py not found at {dst_init_path} for patching')

                # patch init file
                with open(dst_init_path, 'r', encoding='utf-8') as f:
                    init_content = f.read()
                    import_line = f'from . import {name}'
                    if not 'from . import {name}' in init_content:
                        _logger.warning('Patch %s', dst_init_path)
                        with open(dst_init_path, 'w', encoding='utf-8') as f:
                            init_content = init_content + f'\n{import_line}\n'
                            f.write(init_content)
            return True
        else:
            # compare with current and write only if different
            # (read binary so the same code path also syncs non-text files)
            with open(src_path, 'rb') as f:
                src_content = f.read()
            with open(dst_path, 'rb') as f:
                dst_content = f.read()
            if src_content == dst_content:
                return False

            # force: always take the source, never patch back
            if force:
                _logger.warning('force update %s', file_name)
                shutil.copy(src_path, dst_path)
                return True

            src_mtime = os.path.getmtime(src_path)
            dst_mtime = os.path.getmtime(dst_path)

            # check of update
            if src_mtime > dst_mtime:
                _logger.warning('update %s', file_name)
                shutil.copy(src_path, dst_path)
                return True
            # check for patch back
            elif src_mtime < dst_mtime:
                _logger.warning('patch back to %s', src_path)
                shutil.copy(dst_path, src_path)
                return True

            return False

    # copy template
    elif template_ctx:

        if not src_path:
            raise PatchError('template requires src_path')

        # get file content
        with open(src_path, 'r', encoding='utf-8') as f:
            tmpl = f.read()
            content = replace_placeholders(tmpl, template_ctx)

        # write new file
        if not os.path.exists(dst_path):
            _logger.info('copy %s from template', file_name)
            with open(dst_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        elif update:
            # compare with current and write only if different
            with open(dst_path, 'r', encoding='utf-8') as f:
                current_content = f.read()
            # check if content is to update
            if content != current_content:
                _logger.warning('update %s from template', file_name)
                with open(dst_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                return True

        return False

    # copy tree if not exists
    elif copy_tree:
        if not os.path.exists(dst_path):
            _logger.info('copy tree %s', file_name)
            shutil.copytree(src_path, dst_path)
            return True
        return False

    # simple copy if file not exists
    else:

        if not os.path.exists(dst_path):
            _logger.info('copy %s', file_name)
            shutil.copy(src_path, dst_path)
            return True

        return False

def patch_tree(dst_dir, src_dir, patch_back=False, template_ctx=None, update=True, force=False):
    """
    Recursively patch every file of src_dir into dst_dir.

    Directories are created as needed. Files that only exist in dst_dir are
    left untouched, so project-local additions (e.g. an extra rule) survive.
    With patch_back each file is kept in bidirectional sync just like patch().
    """
    if not os.path.isdir(src_dir):
        raise PatchError(f'source tree not found: {src_dir}')

    changed = False
    if not os.path.exists(dst_dir):
        os.makedirs(dst_dir)
        changed = True

    for root, _dirs, files in os.walk(src_dir):
        rel = os.path.relpath(root, src_dir)
        target_root = dst_dir if rel == '.' else os.path.join(dst_dir, rel)
        if not os.path.exists(target_root):
            os.makedirs(target_root)
            changed = True
        for file_name in files:
            if patch(
                    os.path.join(target_root, file_name),
                    os.path.join(root, file_name),
                    patch_back=patch_back,
                    template_ctx=template_ctx,
                    update=update,
                    force=force):
                changed = True

    return changed

def patch_dist(force=False):
    """
    Patch(back) the current cli/*.py to the current odoo distribution.

    With force the source (addons-oerp) always wins: files are patched
    into the workspace but never patched back.
    """

    # determine and check paths
    #

    src_path = os.path.abspath(os.path.dirname(__file__))
    workspace_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
    odoo_path = os.path.join(workspace_path, 'odoo')

    # check if odoo source exists
    if not os.path.exists(odoo_path):
        raise PatchError(f'Odoo source not found at {odoo_path}')


    ## get distribution info
    #

    m = re.match(r'^(odoo\-(([0-9]+)\.([0-9]+))\-([a-z0-9_]+))(\-.*)?$', os.path.basename(workspace_path))
    if not m:
        raise PatchError(f'Invalid distribution name {workspace_path}, should be something like odoo-16.0-<name>')

    profile = m.group(1)
    odoo_version = m.group(2)
    short_version = m.group(3)
    short_name = m.group(5)
    database = f'odoo{short_version}_{short_name}'

    template_ctx = {
        'profile': profile,
        'odoo_version': odoo_version,
        'short_version': short_version,
        'short_name': short_name,
        'database': database,
        'workspace_path': workspace_path
    }
    _logger.info("patch %s", template_ctx)

    ## setup distribution
    #

    for cli_cmd in ('assemble',
                    'install',
                    'serve',
                    'test',
                    'restore',
                    'update',
                    'po_export',
                    'po_import',
                    'updatelist',
                    'cleanup',
                    'backup',
                    'autoenv'):
        patch(
            os.path.join(odoo_path, 'odoo', 'cli', f'{cli_cmd}.py'),
            os.path.join(src_path, 'odoo', 'cli', f'{cli_cmd}.py'),
            patch_back=True, force=force)

    patch(
        os.path.join(odoo_path, 'odoo-bin'),
        os.path.join(src_path, 'odoo-bin')
    )

    patch(
        os.path.join(workspace_path, 'README.md'),
        os.path.join(src_path, 'README.md'),
        template_ctx=template_ctx
    )

    patch(
        os.path.join(workspace_path, '.gitignore'),
        os.path.join(src_path, '.gitignore'),
    )

    ## setup AI assistant rules (Cursor, GitHub Copilot, Claude)
    #
    # One shared rule set drives three assistants. All of these are kept in
    # bidirectional sync (patch_back): edit them in the workspace and the
    # changes are written back to this patch source, and vice versa.

    # Claude: root context + long-form agent instructions
    patch(
        os.path.join(workspace_path, 'CLAUDE.md'),
        os.path.join(src_path, 'CLAUDE.md'),
        patch_back=True, force=force)

    patch(
        os.path.join(workspace_path, 'AGENTS.md'),
        os.path.join(src_path, 'AGENTS.md'),
        patch_back=True, force=force)

    # Cursor: rule files (.mdc) – kept in sync per file
    patch_tree(
        os.path.join(workspace_path, '.cursor', 'rules'),
        os.path.join(src_path, 'cursor', 'rules'),
        patch_back=True, force=force)

    # Cursor: addon templates – copied once (contains binary assets), not synced
    patch(
        os.path.join(workspace_path, '.cursor', 'templates'),
        os.path.join(src_path, 'cursor', 'templates'),
        copy_tree=True)

    # GitHub: Copilot instructions (copilot-instructions.md + instructions/) and
    # CI workflows – bootstrapped and kept in sync per file (see final block).

    ## setup development
    #

    # setup directories
    patch(os.path.join(workspace_path, '.test'), directory=True)
    patch(os.path.join(workspace_path, '.venv'), directory=True)
    patch(os.path.join(workspace_path, '.restore'), directory=True)

    # copy Pipfile
    patch(os.path.join(workspace_path, 'Pipfile'),
          os.path.join(src_path, 'Pipfile'))

    # copy odoo-profile.yml
    patch(os.path.join(workspace_path, 'odoo-profile.yml'),
          os.path.join(src_path, 'odoo-profile.yml'),
          template_ctx=template_ctx, update=False)

    # setup vscode workspace
    patch(os.path.join(workspace_path, 'odoo.code-workspace'),
          os.path.join(src_path, 'dev', 'odoo.code-workspace'),
          patch_back=True, force=force)

    # setup vscode config
    if not patch(os.path.join(workspace_path, '.vscode'),
          os.path.join(src_path, 'dev', '.vscode'), copy_tree=True):
        # if vscode directory exists check if launch.json exists
        patch(os.path.join(workspace_path, '.vscode', 'launch.json'),
              os.path.join(src_path, 'dev', '.vscode', 'launch.json'))
        # if vscode directory exists, patch (back) snippets
        patch(os.path.join(workspace_path, '.vscode', 'odoo.code-snippets'),
              os.path.join(src_path, 'dev', '.vscode', 'odoo.code-snippets'),
              patch_back=True, force=force)

    # copy test config
    patch(os.path.join(workspace_path, '.config'), directory=True)
    patch(os.path.join(workspace_path, '.config', 'odoo-test.conf'),
              os.path.join(src_path, 'dev', '.config', 'odoo-test.conf'),
              template_ctx=template_ctx)

    # copy docker
    patch(os.path.join(workspace_path, 'docker'),
              os.path.join(src_path, 'docker'),
              copy_tree=True)

    patch(os.path.join(workspace_path, 'Dockerfile'),
              os.path.join(src_path, 'Dockerfile'))

    # setup github: CI workflows + Copilot instructions
    # (kept in sync per file so new instruction files propagate both ways)
    patch_tree(os.path.join(workspace_path, '.github'),
              os.path.join(src_path, 'github'),
              patch_back=True, force=force)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        patch_dist(force='--force' in sys.argv[1:])
    except PatchError as e:
        _logger.error(e)
        sys.exit(1)
