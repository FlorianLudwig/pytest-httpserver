#!/usr/bin/env python3

import pdb
import sys
import os
import argparse
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
import atexit
import shutil
import urllib.request
import json
import configparser


class UserError(Exception):
    pass


@dataclass
class CLIArgs:
    remote: str
    branch: str
    work_dir: Path
    debug: bool
    release_type: str


class Travis:
    BASE_URL = "https://api.travis-ci.org"

    def url_for(self, uri: str):
        return self.BASE_URL.rstrip("/") + "/" + uri.lstrip("/")

    def get_branch(self, branch: str):
        url = self.url_for("repos/csernazs/pytest-httpserver/branches/wip-zsolt")
        response = urllib.request.urlopen(url).read().decode("utf-8")
        return json.loads(response)


class BumpVersion:
    def __init__(self, work_dir: Path):
        self.work_dir = work_dir

    def read_bump_version_config(self):
        config = configparser.ConfigParser()
        config.read(str(self.work_dir.joinpath(".bumpversion.cfg")))
        return config

    def get_current_version(self) -> str:
        config = self.read_bump_version_config()
        return config["bumpversion"]["current_version"]


class Application:
    def run_in_workspace(self, args, **kwargs):
        new_args = []
        for arg in args:
            if isinstance(arg, Path):
                new_args.append(str(arg))
            else:
                new_args.append(arg)
        args = new_args
        print(" ".join(args))
        kwargs["cwd"] = str(self.work_dir)
        return subprocess.run(args, **kwargs)

    def parse_args(self) -> CLIArgs:
        parser = argparse.ArgumentParser()
        parser.add_argument("-r", "--remote", help="Git remote to use", required=True)
        parser.add_argument("-b", "--branch", help="Branch to use", required=True)
        parser.add_argument("-w", "--work-dir", help="Work directory to use, default: temp dir")
        parser.add_argument(
            "-d", "--debug", action="store_true", help="Debug mode. Temp directory will not be deleted."
        )
        parser.add_argument("release_type", help="Type of the release", choices=("major", "minor", "patch"))
        args = parser.parse_args()

        if not args.work_dir:
            args.work_dir = tempfile.mkdtemp(prefix="release_py_")
            if not args.debug:
                atexit.register(shutil.rmtree, args.work_dir)
        else:
            try:
                Path(args.work_dir).mkdir()
            except FileExistsError:
                if not args.debug:
                    raise UserError(f"Directory already exists: {args.work_dir}")

        return CLIArgs(
            remote=args.remote,
            branch=args.branch,
            work_dir=Path(args.work_dir),
            debug=args.debug,
            release_type=args.release_type,
        )

    def check_ci_build(self):
        commit_id = (
            self.run_in_workspace(["git", "rev-parse", self.args.branch], stdout=subprocess.PIPE)
            .stdout.decode("utf-8")
            .strip()
        )

        print(f"Current HEAD is {commit_id}")
        travis = Travis()
        resp = travis.get_branch(self.args.branch)

        if resp["commit"]["sha"] != commit_id:
            raise UserError("ci-check: latest build on travis does not match with current HEAD")
        if resp["branch"]["state"] != "passed":
            raise UserError("ci-check: latest build status is '{}'".format(resp["branch"]["state"]))

    def create_workspace(self):
        if self.args.debug and self.work_dir.is_dir():
            pass

        self.run_in_workspace(["git", "clone", "--branch", self.args.branch, self.args.remote, self.work_dir])

    def make(self, target: str):
        self.run_in_workspace(["make", target])

    def initialize_workspace(self):
        self.make("pre-release")

    def bump_version(self):
        self.run_in_workspace([".venv/bin/bumpversion", self.args.release_type])

    def check_doc(self):
        bv = BumpVersion(self.work_dir)
        current_version = bv.get_current_version()

        if not self.work_dir.joinpath("doc/_build/html").is_dir():
            raise UserError("check-doc: No documentation build found")

        if not self.work_dir.joinpath("doc/_build/html/index.html").is_file():
            raise UserError("check-doc: No documentation index.html found")

        if not self.work_dir.joinpath("doc/_build/html/changes.html").is_file():
            raise UserError("check-doc: No documentation changes.html found")

        changes_html = self.work_dir.joinpath("doc/_build/html/changes.html").read_text()
        version_string = f" {current_version} documentation"
        if version_string not in changes_html:
            raise UserError(f"check-doc: wrong title, title missing: '{version_string}'")

    def check_changelog(self):
        current_version = BumpVersion(self.work_dir).get_current_version()

        for line in self.work_dir.joinpath("CHANGES.rst").open():
            if line == current_version + "\n":
                return

        raise UserError(f"check-changelog: version missing from CHANGES.rst: {current_version}")

    def main(self):
        self.args = args = self.parse_args()
        self.work_dir = self.args.work_dir

        print(f"Working directory: {self.args.work_dir}")
        print(args.branch)
        self.create_workspace()
        # self.check_ci_build()
        self.initialize_workspace()
        self.bump_version()
        self.run_in_workspace(["git", "--no-pager", "show", "HEAD"])
        self.make("doc-clean")
        self.make("doc")
        self.make("changes")
        self.check_doc()
        self.check_changelog()


if __name__ == "__main__":
    app = Application()
    try:
        sys.exit(app.main())
    except UserError as err:
        print(str(err), file=sys.stderr)
        sys.exit(1)
