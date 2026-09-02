"""
Activate or refresh Dewbee development mode from a local repository.

This component uses the local checkout as the source of truth for:
  1. the Dewbee Python package;
  2. Grasshopper .ghuser components; and
  3. dewbee_materials.json.

Run DB Installer and Updater to return to a coherent released installation.
-
    Args:
        _run: Set to True to activate or refresh development mode.
        _repo: Optional path to the Dewbee repository root. If empty, the
               default development path below is used.
        _sync_main: If True, require a clean Git working tree and fast-forward
                    the current checkout from origin/main before copying the
                    development assets. If empty, defaults to False.

    Returns:
        report: Status and actions performed.
"""

ghenv.Component.Name = "DB Development Mode"
ghenv.Component.NickName = "DBDevMode"
try:
    import dewbee
    ghenv.Component.Message = dewbee.component_message()
except ImportError:
    ghenv.Component.Message = 'DEV'

try:
    import dewbee
    component_message = getattr(dewbee, "component_message", None)

    if component_message is None:
        ghenv.Component.Message = getattr(dewbee, "__version__", "DEV")
    else:
        ghenv.Component.Message = component_message()

except Exception:
    ghenv.Component.Message = "DEV"

ghenv.Component.Category = "Dewbee"
ghenv.Component.SubCategory = "0 :: Miscellaneous"

try:
    ghenv.Component.ToggleObsolete(False)
except Exception:
    pass


import json
import io
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ElementTree
from xml.sax.saxutils import escape as xml_escape

from Grasshopper.Folders import UserObjectFolders
from Grasshopper.Kernel import GH_RuntimeMessageLevel as Message


# -----------------------------------------------------------------------------
# CONFIG
# -----------------------------------------------------------------------------

DEFAULT_REPO = r"C:\Users\gzorzeto\Documents\GitHub_repos\dewbee_main"

REPO_GHUSER_SUBFOLDER = os.path.join("grasshopper", "user_objects")
REPO_MATERIAL_FILE = os.path.join(
    "resources", "standards", "dewbee_materials.json"
)
GHUSER_TARGET_FOLDER_NAME = "dewbee"

APPDATA_DIR = os.getenv("APPDATA")
if not APPDATA_DIR:
    raise IOError("Could not resolve %APPDATA%.")

STANDARDS_DIR = os.path.join(APPDATA_DIR, "ladybug_tools", "standards")
CONSTRUCTIONS_DIR = os.path.join(STANDARDS_DIR, "constructions")
MATERIAL_TARGET = os.path.join(CONSTRUCTIONS_DIR, "dewbee_materials.json")

RHINO_SCRIPTS_DIR = os.path.join(
    APPDATA_DIR, "McNeel", "Rhinoceros", "8.0", "scripts"
)
DEV_PTH_FILES = (
    os.path.join(RHINO_SCRIPTS_DIR, "python-2_dewbee-dev.pth"),
    os.path.join(RHINO_SCRIPTS_DIR, "python-3_dewbee-dev.pth"),
)

DEV_INFO_DIR = os.path.join(APPDATA_DIR, "ladybug_tools", "dewbee", "dev_mode")
DEV_INFO_FILE = os.path.join(DEV_INFO_DIR, "active.json")
DEV_PACKAGE_JUNCTION = os.path.join(RHINO_SCRIPTS_DIR, "dewbee")

# Legacy GhPython / Grasshopper IronPython stores its paths here. This is
# separate from Rhino 8 Script Editor's python-2*.pth path system.
IRONPYTHON_ID = "814d908a-e25c-493d-97e9-ee3861957f49"
IRONPYTHON_SETTINGS_DIR = os.path.join(
    APPDATA_DIR,
    "McNeel",
    "Rhinoceros",
    "8.0",
    "Plug-ins",
    "IronPython ({})".format(IRONPYTHON_ID),
    "settings",
)
IRONPYTHON_DEFAULT_SETTINGS = os.path.join(
    IRONPYTHON_SETTINGS_DIR, "settings-Scheme__Default.xml"
)


# -----------------------------------------------------------------------------
# HELPERS
# -----------------------------------------------------------------------------

def give_error(message):
    ghenv.Component.AddRuntimeMessage(Message.Error, str(message))


def ensure_dir(path):
    if not os.path.isdir(path):
        os.makedirs(path)


def normalize_path(path):
    path = os.path.abspath(os.path.expanduser(str(path)))
    return os.path.normcase(path) if os.name == "nt" else path


def decode_output(value):
    try:
        return value.decode("utf-8")
    except Exception:
        return str(value)


def run_process(commands, cwd=None):
    process = subprocess.Popen(
        commands,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
    )
    stdout, stderr = process.communicate()
    return process.returncode, decode_output(stdout), decode_output(stderr)


def validate_repo(repo_dir):
    required = (
        os.path.join(repo_dir, "pyproject.toml"),
        os.path.join(repo_dir, "dewbee", "__init__.py"),
        os.path.join(repo_dir, REPO_GHUSER_SUBFOLDER),
        os.path.join(repo_dir, REPO_MATERIAL_FILE),
    )
    missing = [path for path in required if not os.path.exists(path)]
    if missing:
        raise IOError(
            "The selected folder is not a complete Dewbee repository.\n"
            "Missing:\n{}".format("\n".join(missing))
        )


def sync_repo_with_main(repo_dir):
    if not os.path.isdir(os.path.join(repo_dir, ".git")):
        raise IOError(
            "_sync_main is True, but the selected folder is not a Git "
            "checkout:\n{}".format(repo_dir)
        )

    code, out, err = run_process(["git", "status", "--porcelain"], cwd=repo_dir)
    if code != 0:
        raise Exception("Could not read Git status.\n{}".format(err or out))
    if out.strip():
        raise Exception(
            "The Dewbee repository has uncommitted changes and was not "
            "updated. Commit/stash them, or set _sync_main to False.\n\n{}"
            .format(out.strip())
        )

    code, out, err = run_process(
        ["git", "fetch", "origin", "main"], cwd=repo_dir
    )
    if code != 0:
        raise Exception("git fetch origin main failed.\n{}".format(err or out))

    code, out, err = run_process(
        ["git", "merge", "--ff-only", "origin/main"], cwd=repo_dir
    )
    if code != 0:
        raise Exception(
            "The checkout could not be fast-forwarded to origin/main. "
            "Merge or rebase it manually, or set _sync_main to False.\n\n{}"
            .format(err or out)
        )
    return (out or "Repository is already up to date.").strip()


def get_ghuser_target_folder():
    if not UserObjectFolders or len(UserObjectFolders) == 0:
        raise IOError("Could not find the Grasshopper UserObjects directory.")
    return os.path.join(UserObjectFolders[0], GHUSER_TARGET_FOLDER_NAME)


def replace_directory(source, target):
    if not os.path.isdir(source):
        raise IOError("Source folder does not exist:\n{}".format(source))
    if os.path.isdir(target):
        shutil.rmtree(target)
    ensure_dir(os.path.dirname(target))
    shutil.copytree(source, target)


def ensure_honeybee_standard_folders():
    for subfolder in (
        "constructions",
        "constructionsets",
        "schedules",
        "programtypes",
    ):
        ensure_dir(os.path.join(STANDARDS_DIR, subfolder))


def install_local_assets(repo_dir):
    gh_source = os.path.join(repo_dir, REPO_GHUSER_SUBFOLDER)
    gh_target = get_ghuser_target_folder()
    material_source = os.path.join(repo_dir, REPO_MATERIAL_FILE)

    replace_directory(gh_source, gh_target)
    ensure_honeybee_standard_folders()

    # Copy, do not move: the repository file remains the development source.
    shutil.copy2(material_source, MATERIAL_TARGET)
    return gh_source, gh_target, material_source


def write_dev_paths(repo_dir):
    """Also configure Rhino 8 Script Editor Python 2/3 environments."""
    ensure_dir(RHINO_SCRIPTS_DIR)
    for pth_file in DEV_PTH_FILES:
        with open(pth_file, "w") as stream:
            stream.write(repo_dir + "\n")


def read_dev_info():
    if not os.path.isfile(DEV_INFO_FILE):
        return None
    try:
        with open(DEV_INFO_FILE, "r") as stream:
            return json.load(stream)
    except Exception:
        return None


def create_dev_package_junction(repo_dir):
    """Expose local dewbee through Rhino's existing pre-LBT scripts path."""
    if os.name != "nt":
        raise EnvironmentError(
            "The Dewbee development package junction is currently Windows-only."
        )

    source = os.path.join(repo_dir, "dewbee")
    target = DEV_PACKAGE_JUNCTION
    state = read_dev_info()

    if not os.path.isfile(os.path.join(source, "__init__.py")):
        raise IOError("Local Dewbee package is missing:\n{}".format(source))

    if os.path.exists(target):
        managed = (
            state
            and state.get("junction")
            and normalize_path(state.get("junction")) == normalize_path(target)
        )
        same_source = (
            managed
            and state.get("package_source")
            and normalize_path(state.get("package_source")) == normalize_path(source)
        )
        if same_source and os.path.isfile(os.path.join(target, "__init__.py")):
            return source, target
        if not managed:
            raise IOError(
                "Development junction target already exists and was not created "
                "by DB Development Mode. It was left untouched:\n{}".format(target)
            )

        # os.rmdir removes a Windows directory junction itself; it does not
        # recurse into or delete the local repository that it points to.
        os.rmdir(target)

    ensure_dir(os.path.dirname(target))
    code, out, err = run_process(
        ["cmd.exe", "/d", "/c", "mklink", "/J", target, source]
    )
    if code != 0:
        raise Exception(
            "Could not create the Dewbee development junction.\n{}".format(
                err or out
            )
        )
    if not os.path.isfile(os.path.join(target, "__init__.py")):
        raise IOError(
            "The development junction was created but could not be verified:\n{}"
            .format(target)
        )
    return source, target


def ironpython_settings_files():
    """Return legacy IronPython settings files for Rhino and Rhino.Inside."""
    ensure_dir(IRONPYTHON_SETTINGS_DIR)
    settings_files = [IRONPYTHON_DEFAULT_SETTINGS]
    for name in os.listdir(IRONPYTHON_SETTINGS_DIR):
        if not name.startswith("settings-Scheme") or not name.endswith(".xml"):
            continue
        path = os.path.join(IRONPYTHON_SETTINGS_DIR, name)
        if normalize_path(path) != normalize_path(IRONPYTHON_DEFAULT_SETTINGS):
            settings_files.append(path)
    return settings_files


def _new_ironpython_settings_file(settings_file):
    ensure_dir(os.path.dirname(settings_file))
    contents = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<settings id="2.0">\n'
        '  <settings>\n'
        '  </settings>\n'
        '</settings>\n'
    )
    with io.open(settings_file, "w", encoding="utf-8") as stream:
        stream.write(contents)


def prepend_ironpython_search_path(settings_file, repo_dir):
    """Put repo_dir first in a legacy IronPython SearchPaths entry."""
    if not os.path.isfile(settings_file):
        _new_ironpython_settings_file(settings_file)

    with io.open(settings_file, "r", encoding="utf-8") as stream:
        contents = stream.read()

    # Validate before changing a Rhino settings file and keep a recovery copy.
    try:
        root = ElementTree.fromstring(contents)
    except Exception as error:
        raise ValueError(
            "Could not parse IronPython settings file:\n{}\n{}".format(
                settings_file, error
            )
        )

    existing_paths = ""
    for entry in root.iter("entry"):
        if entry.get("key") == "SearchPaths":
            existing_paths = entry.text or ""
            break

    filtered = []
    repo_norm = normalize_path(repo_dir)
    for path in existing_paths.split(";"):
        path = path.strip()
        if path and normalize_path(path) != repo_norm:
            filtered.append(path)
    new_paths = [repo_dir] + filtered

    entry_text = '<entry key="SearchPaths">{}</entry>'.format(
        xml_escape(";".join(new_paths))
    )
    pattern = re.compile(
        r'<entry\s+key=["\']SearchPaths["\']\s*>.*?</entry>',
        re.DOTALL,
    )
    if pattern.search(contents):
        updated = pattern.sub(lambda match: entry_text, contents, count=1)
    else:
        close_index = contents.find("</settings>")
        if close_index == -1:
            raise ValueError(
                "IronPython settings file has no closing settings element:\n{}"
                .format(settings_file)
            )
        updated = (
            contents[:close_index]
            + "    " + entry_text + "\n  "
            + contents[close_index:]
        )

    backup_file = settings_file + ".dewbee-backup"
    if not os.path.isfile(backup_file):
        shutil.copy2(settings_file, backup_file)

    with io.open(settings_file, "w", encoding="utf-8") as stream:
        stream.write(updated)
    return settings_file


def configure_legacy_ironpython(repo_dir):
    configured = []
    for settings_file in ironpython_settings_files():
        configured.append(
            prepend_ironpython_search_path(settings_file, repo_dir)
        )
    return configured


def use_repo_in_current_session(repo_dir):
    normalized_repo = normalize_path(repo_dir)
    sys.path[:] = [
        path for path in sys.path
        if normalize_path(path) != normalized_repo
    ]
    sys.path.insert(0, repo_dir)

    for module_name in list(sys.modules.keys()):
        if module_name == "dewbee" or module_name.startswith("dewbee."):
            try:
                del sys.modules[module_name]
            except Exception:
                pass


def write_dev_info(repo_dir, package_source, junction):
    ensure_dir(DEV_INFO_DIR)
    with open(DEV_INFO_FILE, "w") as stream:
        json.dump(
            {
                "active": True,
                "repo": repo_dir,
                "package_source": package_source,
                "junction": junction,
            },
            stream,
            indent=2,
        )


def current_status():
    if os.path.isfile(DEV_INFO_FILE):
        return (
            "Dewbee development mode is configured. Run this component again "
            "to refresh local Grasshopper components and materials."
        )

    return "Set _run to True to activate or refresh Dewbee development mode."


# -----------------------------------------------------------------------------
# EXECUTION
# -----------------------------------------------------------------------------

report = current_status()

if _run:
    try:
        repo_dir = normalize_path(_repo if _repo else DEFAULT_REPO)
        validate_repo(repo_dir)

        sync_report = None
        sync_main = False if _sync_main is None else bool(_sync_main)
        if sync_main:
            sync_report = sync_repo_with_main(repo_dir)
            validate_repo(repo_dir)

        gh_source, gh_target, material_source = install_local_assets(repo_dir)
        package_source, package_junction = create_dev_package_junction(repo_dir)
        write_dev_paths(repo_dir)
        use_repo_in_current_session(repo_dir)
        write_dev_info(repo_dir, package_source, package_junction)

        lines = [
            "Dewbee DEVELOPMENT mode activated/refreshed.",
            "Python source: {}".format(repo_dir),
            "Grasshopper components: {} -> {}".format(gh_source, gh_target),
            "Materials: {} -> {}".format(material_source, MATERIAL_TARGET),
            "Legacy IronPython package junction:",
            "{} -> {}".format(package_junction, package_source),
        ]
        if sync_report:
            lines.append("Git: {}".format(sync_report))
        lines.extend([
            "",
            "The repository material file was copied, not removed.",
            "The current IronPython session was updated immediately.",
            "After restart, Rhino's existing scripts path resolves the junction",
            "before Ladybug Tools site-packages.",
            "Run DB Installer and Updater to return to release mode.",
        ])
        report = "\n".join(lines)
        print(report)

    except Exception as error:
        report = "Dewbee development-mode activation failed:\n{}".format(error)
        print(report)
        give_error(report)

else:
    print(report)
