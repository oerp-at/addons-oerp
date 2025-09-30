# addons-oerp

It is a tiny set of utils and modules which does not fit exactly in the OCA concept, but make the live much easier. This repository will keep minimal because the big stuff should happen at the OCA.
To avoid any licence issues, everything is published with the BSD-2-Clause and free to copy and change without copy left.


| Module            | Description                                                                     |
|-------------------|---------------------------------------------------------------------------------|
| oerp_util         | Utils for testing, and CLI patch for Odoo in oerp_util/dist.                    |
| automation        | An automation framework which used Odoo standard (scheduled) background tasks.  |


# Odoo Environment Setup

With the patch in `oerp_util/patch/patch.py` you can setup easily a full working Odoo environment, general IDE independend, but preconfigured for VSCode. The prefered OS is *Ubuntu 24.04 LTS.*

The following steps will describe the setup.

## Install native dependencies on Ubuntu

    sudo apt install --no-install-recommends build-essential git virtualenv poppler-utils bzip2 curl fonts-freefont-ttf fonts-ubuntu fontconfig python3-dev libcairo2-dev libcups2-dev libffi-dev libfontconfig-dev libfreetype6-dev libssl-dev libldap2-dev libxml2-dev libxslt1-dev libpq-dev libhttp-parser-dev libsasl2-dev libmagickwand-dev xfonts-75dpi xfonts-base xfonts-encodings xfonts-utils postgresql pipenv postgresql-16-pgvector

## Create a Database User

Before we start you need a working database user, after installing all the prerequesites, just create
a superuser like that...

    $ sudo su - postgres
    $ createuser -s <myuser>
    $ exit

## The Environment Folder

The environment folder, where you setup your working environment, use a special form/syntax: `odoo-<version>-<environment name>`.

An folder named like odoo-18.0-sh has following information:

    Odoo
    Version: x.y
    Environment: sh

For our following example setup we use odoo-18.0-test

    Odoo
    Version: 18.0
    Environment: test


## Creating the Environment

Creating the manually is just that easy, that don't want to write a script for it.
We are starting with creating our environment and entering the folder:

    $ mkdir odoo-18.0-test
    $ cd odoo-18

As next step we checkout all our needed code base for the desired Odoo (in our case 18.0) version:

    $ git clone -b 18.0 https://github.com/odoo/odoo.git odoo
    $ git clone -b 18.0 git@github.com:odoo/design-themes.git addons-design-themes
    $ git clone -b 18.0 git@github.com:odoo/enterprise.git addons-enterprise
    $ git clone -b 18.0 git@github.com:oerp-at/addons-oerp.git addons-oerp

if you only want community version you can skip the enterprise checkout.

## Patching the Environment

After preparing your environment, just patch it ...

    $ ./addons-oerp/oerp_util/patch/patch.py

Now you have an working environment prepared for kubernetes, docker etc. Fantastic!
Odoo checkout is changed, so I recommend to create a seperate branch to make updates easy.

    $ cd odoo
    $ git checkout -b odoo-oerp ; git add -A . ; git commit -m "patched with oerp additional cli tools"
    $ git pull origin 18.0 # (for updating later)

## Ready to Install Python

Finally we need to install the python dependencies we need for our project. Do it just with ..

    $ pipenv install

If you need additional libraries just install it with ´pipenv install <library name>´.
Dependencies are tracked in Pipefile and they are specific to your working environment, so feel free to change.

## Final Perperation before the Run

Everything is ready now, but to make it simpler, and add resolution support for your preferred IDE,
use following command to setup all links...

    $ ./odoo/odoo-bin assemble

After this command, you only have to type `odoo` to call the odoo-cli.
Look below to find the full list of commands, but if you want to try, you can just run the server with
`odoo serve`

## Multiple Profiles for Odoo Databases

Normally you work on different Odoo implementations.
So it is useful, to switch easily between them without peparing new environments for every Odoo database.
Good news, it works easily with profiles. After the patch you see a file ´odoo-profile.yml` in your workspace. This file configures the commandline defaults for all added cli-commands.
What does this mean, maybe you look and checkout the following, for better understanding.

    default:
      db: {{ database }}
      po_export:
        lang: de_DE

### Create a new (Sub)Profile

For creating a new profile, just create a new folder that following following convention:
`custom-addons-<odoo-instance-name>` like custom-addons-*myinstance*.

  $ mkdir custom-addons-myinstance
  $ cd custom-addons-myinstance

After you created your custom folder, we use in the test *custom-addons-myinstance*,
you are able to checkout your instance specific modules, and also configure a specific test db.

If you edit now the `odoo-profile.yml` you can add an (sub)profile specific entry like that.

    default:
      db: odoo18_test
      po_export:
        lang: de_DE

    odoo-18.0-test-myinstance:
      db: odoo18_myinstance


I am in the folder `./custom-addons-myinstance` and add now a custom repostory for my from the oca like https://github.com/OCA/mail .
For that I simple checkout the module (or add is as submodule, if custom-addons-myinstance is already a git repository)

    $ git clone -b 18.0 git@github.com:OCA/mail.git addons-mail

Do make it resolvable in my IDE, I can just call ..

    $ odoo assemble

... directly in the `./custom-addons-myinstance` folder, now all modules linked automatically.
If I use VSCode, also the working directory path is automatically changed to my instance directory.


## VSCode

After patching the directory, automatically a workspace file `ooo.code-workspace` is created in the
root directory. Just open it, and you have already the full preconfigured environment.


## Addinal CLI

All additional commands you can start from your root workspace folder or if you working in a (sub)profile, from your (sub)profile folder. No configuration is needed, jsut work right away.


### Odoo Server

Starting the Odoo server:

    $ odoo serve

### Module Update

Updating all modules:

    $ odoo update

Updating only a single module:

    $ odoo update <module name>

### Run Tests

For test driven development, you normally implement tests upfront and then debug your implementation.
With extended odoo cli it is just easy. It also starts a local test server for javascript tours.

Running all module tests:

    $ odoo test <module name>

Running a specific test case:

    $ odoo test <module name> --test-case=<TestCaseName>

Running a specific test case function

    $ odoo test <module name> --test-prefix=<test function prefix>

Standard parameters for tests like tags etc, are all supported.

### And More ###

... **following documentation will comming soon** ..

