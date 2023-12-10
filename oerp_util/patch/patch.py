#!/usr/bin/env python3

import sys
import os
import shutil
import re
import logging

_logger = logging.getLogger(__name__)


class PatchError(Exception):
    pass


def content_from_template(template, template_ctx):
    """ Replace {{var}} in template with values from template_ctx """
    pattern = re.compile(r'\{\{\s*([a-z0-9]+)\s*\}\}')
    def replace(match):
        var_name = match.group(1)
        return template_ctx.get(var_name, '')
    return pattern.sub(replace, template)

def patch(dst_path, src_path=None, directory=False, template_ctx=None, patch_back=False, add_init=False, copy_tree=False):
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

        if not os.path.exists(src_path):
            _logger.info('copy %s', file_name)
            shutil.copy(dst_path, src_path)
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
                    if not 'from . import config' in init_content:
                        _logger.warning('Patch %s', dst_init_path)
                        with open(dst_init_path, 'w', encoding='utf-8') as f:
                            init_content = init_content + f'\n{import_line}\n'
                            f.write(init_content)
            return True
        else:
            # compare with current and write only if different
            with open(src_path, 'r', encoding='utf-8') as f:
                src_content = f.read()
            with open(dst_path, 'r', encoding='utf-8') as f:
                dst_content = f.read()
            if src_content == dst_content:
                return False

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
            content = content_from_template(tmpl, template_ctx)

        # write new file
        if not os.path.exists(dst_path):
            _logger.info('copy %s', file_name)
            with open(dst_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        else:
            # compare with current and write only if different
            with open(dst_path, 'r', encoding='utf-8') as f:
                current_content = f.read()
            # update readme
            if content != current_content:
                _logger.warning('update %s', file_name)
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
            _logger.info('Copy %s', file_name)
            shutil.copy(src_path, dst_path)
            return True

        return False

def patch_dist():
    """
    Patch(back) the current cli/config.py to the current odoo distribution.
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

    patch(
        os.path.join(odoo_path, 'odoo', 'cli', 'config.py'),
        os.path.join(src_path, 'odoo', 'cli', 'config.py'),
        patch_back=True,
        add_init=True)

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

    ## setup development
    #

    # setup directories
    patch(os.path.join(workspace_path, '.test'), directory=True)
    patch(os.path.join(workspace_path, '.venv'), directory=True)

    # copy Pipfile
    patch(os.path.join(workspace_path, 'Pipfile'),
          os.path.join(src_path, 'Pipfile'),
          template_ctx=template_ctx)

    # setup vscode config
    if not patch(os.path.join(workspace_path, '.vscode'),
          os.path.join(src_path, 'dev', '.vscode'), copy_tree=True):
        # if vscode directory exists, patch (back) snippets
        patch(os.path.join(workspace_path, '.vscode', 'odoo.code-snippets'),
              os.path.join(src_path, 'dev', '.vscode', 'odoo.code-snippets'),
              patch_back=True)

    # copy test config
    if patch(os.path.join(workspace_path, '.config'), directory=True):
        patch(os.path.join(workspace_path, '.config', 'odoo-test.conf'),
              os.path.join(src_path, 'dev', '.config', 'odoo-test.conf'),
              template_ctx=template_ctx)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        patch_dist()
    except PatchError as e:
        _logger.error(e)
        sys.exit(1)
