# GitHub Actions

Reusable composite actions for Odoo CI/CD pipelines, provided by
[oerp-at/addons-oerp](https://github.com/oerp-at/addons-oerp).

## Available Actions

| Action | Description |
|--------|-------------|
| `odoo-detect-manifest-version` | Detects `__manifest__.py` version changes and calculates new app/chart versions |
| `docker-build-push` | Logs in to a container registry, builds and pushes a Docker image |
| `odoo-bump-chart-version` | Updates `Chart.yaml` versions and auto-commits the change |

---

## odoo-detect-manifest-version

Compares `__manifest__.py` versions between the current and previous commit.
When a version change is detected, the highest change level (major/minor/patch)
is used to bump the `appVersion` in `Chart.yaml` accordingly.

> **Important:** The repository must be checked out with `fetch-depth >= 2`,
> otherwise the action will fail with a clear error message.

### Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `chart-file` | no | `charts/odooi/Chart.yaml` | Path to the Helm `Chart.yaml` |

### Outputs

| Output | Description |
|--------|-------------|
| `changed` | `true` if any manifest version changed, `false` otherwise |
| `app_version` | New appVersion string (e.g. `19.0.1.3.0`) |
| `chart_version` | New chart version string (e.g. `19.0.3`) |
| `change_level` | Highest change level: `major`, `minor`, `patch`, or empty |

### Version Scheme

The Odoo module version format is `<OdooMajor>.<OdooMinor>.<Major>.<Minor>.<Patch>`.
The action compares the last three segments across all changed manifests and picks
the highest change level:

- **major** bump if `<Major>` changed in any manifest
- **minor** bump if `<Minor>` changed (and no major change)
- **patch** bump if `<Patch>` changed (and no major/minor change)

The chart `version` is bumped by incrementing its patch segment.

---

## docker-build-push

Handles container registry login, Docker metadata extraction, image build and push.

### Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `github-token` | **yes** | — | GitHub token for registry auth (pass `secrets.GITHUB_TOKEN`) |
| `registry` | no | `ghcr.io` | Container registry URL |
| `image` | no | `ghcr.io/${{ github.repository }}` | Full image name |
| `context` | no | `.` | Docker build context path |
| `push` | no | `true` | Whether to push the image |
| `version-tag` | no | — | Optional additional version tag |

### Outputs

| Output | Description |
|--------|-------------|
| `tags` | Generated image tags |
| `digest` | Image digest |

### Generated Tags

The action always generates:

- `type=ref,event=branch` — branch name tag (e.g. `production`)
- `type=sha` — short commit SHA tag

When `version-tag` is provided, an additional raw tag with that value is added.

---

## odoo-bump-chart-version

Updates `appVersion` and `version` in a Helm `Chart.yaml`, then commits and
pushes the change as `github-actions[bot]`.

### Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `chart-file` | no | `charts/odooi/Chart.yaml` | Path to the Helm `Chart.yaml` |
| `app-version` | **yes** | — | New `appVersion` value |
| `chart-version` | **yes** | — | New chart `version` value |

### Permissions

The workflow job must have `contents: write` permission for the commit and push
to succeed.

---

## Full Workflow Example

A complete workflow combining all three actions:

```yaml
name: Build Image

on:
  push:
    paths-ignore:
      - 'charts/**'
    branches:
      - production

jobs:
  docker:
    runs-on: ubuntu-latest

    permissions:
      contents: write
      packages: write

    steps:
      - name: Checkout repository
        uses: actions/checkout@v5
        with:
          fetch-depth: 2

      - name: Detect manifest version changes
        id: version
        uses: oerp-at/addons-oerp/.github/actions/odoo-detect-manifest-version@19.0
        with:
          chart-file: charts/odooi/Chart.yaml

      - name: Build and push Docker image
        uses: oerp-at/addons-oerp/.github/actions/docker-build-push@19.0
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
          version-tag: ${{ steps.version.outputs.app_version }}

      - name: Bump Chart.yaml versions
        if: steps.version.outputs.changed == 'true'
        uses: oerp-at/addons-oerp/.github/actions/odoo-bump-chart-version@19.0
        with:
          app-version: ${{ steps.version.outputs.app_version }}
          chart-version: ${{ steps.version.outputs.chart_version }}
```
