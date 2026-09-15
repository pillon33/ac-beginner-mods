"""
deploy_app.py — copy an in-game app folder from this repo into your
Assetto Corsa installation, so you can playtest it without manually
dragging folders around every time you make a change.

Why a script instead of just editing the file in place inside the AC
folder: this repo is your git-tracked source of truth. Editing copies
inside a Steam install directory is a good way to lose work if Steam
ever verifies/reinstalls game files. Keep editing here, redeploy
often.

Usage:
    python scripts/deploy_app.py hello_hud
    python scripts/deploy_app.py hello_hud --ac-dir "D:\\SteamLibrary\\steamapps\\common\\assettocorsa"
    python scripts/deploy_app.py hello_hud --link   # symlink instead of copy (see note below)

You can also set the AC install path once via an environment
variable instead of passing --ac-dir every time:
    setx AC_INSTALL_DIR "C:\\Program Files (x86)\\Steam\\steamapps\\common\\assettocorsa"
(open a new terminal after running setx for it to take effect)

--link creates a symlink instead of copying, so edits here show up
in-game immediately with no redeploy step. On Windows this needs
either Developer Mode turned on (Settings > Update & Security > For
developers) or an elevated (admin) terminal — otherwise you'll get a
permissions error, in which case just omit --link and re-run the
script after each change instead.
"""

import argparse
import os
import shutil
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APPS_SOURCE_DIR = os.path.join(REPO_ROOT, "apps", "python")

DEFAULT_STEAM_PATHS = [
    r"C:\Program Files (x86)\Steam\steamapps\common\assettocorsa",
    r"C:\Program Files\Steam\steamapps\common\assettocorsa",
]


def find_ac_dir(explicit_path):
    if explicit_path:
        return explicit_path

    env_path = os.environ.get("AC_INSTALL_DIR")
    if env_path:
        return env_path

    for candidate in DEFAULT_STEAM_PATHS:
        if os.path.isdir(candidate):
            return candidate

    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app_name", help="Folder name under apps/python/ to deploy, e.g. hello_hud")
    parser.add_argument("--ac-dir", dest="ac_dir", default=None,
                         help="Path to your Assetto Corsa install directory")
    parser.add_argument("--link", action="store_true",
                         help="Symlink instead of copy (see docstring for caveats)")
    args = parser.parse_args()

    source = os.path.join(APPS_SOURCE_DIR, args.app_name)
    if not os.path.isdir(source):
        sys.exit("No such app folder: {}".format(source))

    ac_dir = find_ac_dir(args.ac_dir)
    if not ac_dir or not os.path.isdir(ac_dir):
        sys.exit(
            "Couldn't find your Assetto Corsa install directory.\n"
            "Pass it explicitly: --ac-dir \"...\\steamapps\\common\\assettocorsa\"\n"
            "or set it once with: setx AC_INSTALL_DIR \"...\""
        )

    destination = os.path.join(ac_dir, "apps", "python", args.app_name)

    if args.link:
        if os.path.exists(destination):
            sys.exit("Destination already exists, remove it first: {}".format(destination))
        os.symlink(source, destination, target_is_directory=True)
        print("Linked {} -> {}".format(destination, source))
    else:
        shutil.copytree(source, destination, dirs_exist_ok=True)
        print("Copied {} -> {}".format(source, destination))

    print("Now in AC: Options > General > tick '{}' in the apps list.".format(args.app_name))


if __name__ == "__main__":
    main()
