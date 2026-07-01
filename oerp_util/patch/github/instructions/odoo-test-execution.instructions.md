---
name: 'Odoo Test Execution'
description: 'Running Odoo tests from the CLI'
applyTo: 'custom-addons-*/**/tests/**'
---

# Odoo Test Execution

Tests must be run inside the **pipenv environment** and from the **subproject directory** (`custom-addons-<subproject>/`).

## Setup

```bash
cd custom-addons-<subproject>/
pipenv run odoo test <module> ...
```

If `odoo assemble` was already run in the subproject, `pipenv run odoo test` is available.

## Commands

```bash
# Run all tests for a module
pipenv run odoo test <module>

# Run a specific test class
pipenv run odoo test <module> --test-case=<TestCaseClass>

# Run a specific test method
pipenv run odoo test <module> --test-case=<TestCaseClass> --test-prefix=<test_method>
```

## Example

```bash
cd custom-addons-flexiskin/
pipenv run odoo test woa_l10n_at_accountant --test-case=TestFaonATUpload --test-prefix=test_submit_creates_activity
```
