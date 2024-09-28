#!/usr/bin/python3

import argparse
import re
import os
from git import Repo


# "Merge branch 'feature/ERP-277' into '14.0-xyz-stage'"
MERGE_PATTERN = re.compile("Merge branch '([^']*)' into '([^']*)'")
# 14.0.1.0.0 or 14.0.1.0
RELEASE_PATTERN = re.compile(r"release/([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+(\.[0-9]+)?)")


def to_version(version_str):
    res = [0,0,0,0,0]
    version_ints = [int(v) for v in version_str.split(".")]
    for i in range(0, min(len(version_ints), len(res))):
        res[i] = version_ints[i]
    return tuple(res)

def inc_patch(version):
    odoo_major, odoo_minor, major, minor, patch = version
    return (odoo_major, odoo_minor, major, minor, patch+1)

def inc_minor(version):
    odoo_major, odoo_minor, major, minor, patch = version
    return (odoo_major, odoo_minor, major, minor+1, 0)

def version_to_str(version):
    return ".".join([str(v) for v in version])

def get_next_release(work_dir, commit_id=None):
    version_file = os.path.join(work_dir, 'VERSION')
    if not os.path.exists(version_file):
        raise Exception(f"{version_file} not found")

    version_str = None
    with open(version_file, "r") as f:
        version_str = str(f.read()).strip()

    if not version_str:
        raise Exception(f'No version found in {version_file}')

    version = to_version(version_str)
    version_prefix = f'release/{version_str}'
    repo = Repo(work_dir)
    active_branch = repo.active_branch

    # get current version
    current_version = version
    version_exist = False
    for remote in repo.remotes:
        for r in remote.refs:
            ref_name = r.name[len(remote.name)+1:]
            if ref_name.startswith(version_prefix):
                m = RELEASE_PATTERN.match(ref_name)
                if m:
                    v = to_version(m.group(1))
                    version_exist = True
                    if v > current_version:
                        current_version = v

    if version_exist:
        # check if source is a hotfix
        c = repo.commit(commit_id) if commit_id else active_branch.commit
        m = MERGE_PATTERN.match(c.summary)
        if m and m.group(1).startswith('hotfix'):
            current_version = inc_patch(current_version)
        else:
            current_version = inc_minor(current_version)

    return f"release/{version_to_str(current_version)}"


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir",help="Git working directory.", required=False, default=".")
    parser.add_argument("--commit",help="Extract information from specified commit.", required=False)
    args = parser.parse_args()

    print(get_next_release(args.work_dir, commit_id=args.commit))