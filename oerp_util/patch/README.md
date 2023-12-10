# Odoo {{ odoo_version }} Distribution

This is an all-in-one repository with all Odoo modules for development and
distribution. It should make fast start easy and simple.

For linking/including the additional modules, git subtree is used. Therefore, it's easy to push back changes.

# Dependencies

For the package management **pipenv** is used. Therefore, all dependencies (also for development) are tracked in the `Pipfile` and the resulting `Pipfile.lock`.

But some Python packages also have native dependencies, here the packagelist for Ubuntu 22.04:

    apt install --no-install-recommends build-essential git virtualenv pipenv poppler-utils bzip2 curl fonts-freefont-ttf fonts-ubuntu fontconfig python3-dev libcairo2-dev libcups2-dev libffi-dev libfontconfig-dev libfreetype6-dev libssl-dev libldap2-dev libxml2-dev libxslt1-dev libpq-dev libhttp-parser-dev libsasl2-dev libmagickwand-dev xfonts-75dpi xfonts-base xfonts-encodings xfonts-utils wkhtmltopdf


# Development

## Commit Messages

Please use the commit message format described in the [OCA Guidlines](https://github.com/OCA/odoo-community.org/blob/master/website/Contribution/CONTRIBUTING.rst#commit-message) or described in the [Odoo Development Guidlines](https://www.odoo.com/documentation/16.0/developer/misc/other/guidelines.html)

## Commands

For simplifying the Odoo development/handling a smart/small extension was made to Odoo source.
The command line extension `odoo/odoo/cli/config.py` and the odoo start/entry point `odoo/odoo-bin`.

This extend the odoo for simple tasks like update and serve the odoo server or export/import and clean translations.

### Prerequesites

* Create `.venv` in your distribution directory
* Call `pipenv install` and `pipenv install --dev` for additional development packages.
* Execute `./odoo/odoo-bin assemble` that every command can be executed just with `odoo`.
  If you have new modules, call again `./odoo/odoo-bin assemble`

### Server Update

Following command updates the whole server:

    odoo update -d <database>

But also a module update is possible:

    odoo update -d <database> <module>

### Server Run

To run the server simply execute:

    odoo serve -d <database>

### Translation Export

This command exports translation (default de_DE):

    odoo po_export -d <database> <module>


### Translation Import

And with this command you can import/update all translations

    odoo po_import -d <database> <module>

### Testing

Testing is important, therefore you can start individual module tests
with

    odoo test -d <database> --test-prefix=<test> <module>

### Further Help

    ./odoo <cmd> --help


## Profiles

You can define a profile with the name of your project checkout folder. For example if I checkout an Odoo distribution with name `{{ profile }}`, then the profile name is `{{ profile }}`, it's simple.

For this profile you can define default parametesr for commands which are automatically passed, like database and default language, test database download and more.

The `odoo-profile.yml` can be defined in:

* `/etc/odoo/odoo-profile.yml`
* `~/.odoo-profile.yml`
* `<project-dir>/odoo-profile.yml`

```
---

# default for all
default:

    # general definition
    # of parameter database
    db: {{ database }}

    # special definition
    # only for po_export function
    po_export:
        lang: de_DE

{{ profile }}:
    db: {{ database }}

```

After you defined the profiles, you can don't need to pass always the database, just use ...

    odoo test oerp_util

... for example. This makes the daily work easier.

## VSCode

This repository already provide a workspace configuration with for vscode.

### Start Developing

1. Checkout the source
2. Open VSCode workspace
3. Install OS (Ubuntu) packages
4. Setup python environment (open terminal create **.venv** and enter **pipenv install**)

#### .vscode/launch.json (example)

```
{
    // Use IntelliSense to learn about possible attributes.
    // Hover to view descriptions of existing attributes.
    // For more information, visit: https://go.microsoft.com/fwlink/?linkid=830387
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Odoo: Server",
            "type": "python",
            "request": "launch",
            "program": "${workspaceFolder}/odoo/odoo-bin",
            "console": "integratedTerminal",
            "args": ["serve"]
        },
        {
            "name": "Odoo: Test",
            "type": "python",
            "request": "launch",
            "program": "${workspaceFolder}/odoo/odoo-bin",
            "console": "integratedTerminal",
            "args": ["test"
                "--config=${workspaceFolder}/.config/odoo-test.conf",
                "<module>"
            ]
        }
    ]
}
```