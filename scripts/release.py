
import subprocess
import argparse
from pathlib import Path
import re
from typing import List


class UsageError(Exception):
    pass


def parse_version():
    with Path("setup.py").open() as infile:
        for line in infile:
            if m := re.match(r"VERSION\s*=\s*\"(.*)\"$", line):
                return m.groups()[0]


def bump_version(path: Path, prefixes: List[str], current_version: str, new_version: str):
    prefixes = tuple(prefixes)
    lines = []
    for line in path.open():
        if line.startswith(prefixes):
            line = line.replace(current_version, new_version)
        lines.append(line)

    path.write_text("".join(lines))


def git(*args):
    return subprocess.check_call(["git"] + list(args))


def make(*args):
    return subprocess.check_call(["make"] + list(args))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("new_version", help="Version to release")

    args = parser.parse_args()
    new_version: str = args.new_version

    current_version = parse_version()
    if current_version is None:
        raise UsageError("Unable to parse version")

    print(current_version)
    bump_version(Path("setup.py"), ["VERSION"], current_version, new_version)
    bump_version(Path("doc/conf.py"), ["version"], current_version, new_version)

    git("add", "setup.py", "doc/conf.py")
    git("commit", "-m", "Version bump to {}".format(new_version))
    git("tag", new_version)
    make("changes")
    git("add", "CHANGES.rst")
    git("commit", "-m", "CHANGES.rst: add release notes for {}".format(new_version))
    git("tag", "-f", new_version)


if __name__ == "__main__":
    main()
