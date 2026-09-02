"""
Export all installed Dewbee user objects to a local Dewbee repository.

The component:
  1. requires DB Development Mode to be active for the selected repository;
  2. loads every ``DB*.ghuser`` from Grasshopper's Dewbee UserObjects folder;
  3. replaces the first hardcoded component-message assignment with a runtime
     call to ``dewbee.component_message()``;
  4. writes the component code to ``grasshopper/src``;
  5. writes the modified user object to ``grasshopper/user_objects``; and
  6. copies the updated user object back to Grasshopper's local folder.

The saved .ghuser metadata uses the numeric ``dewbee.__version__``. Therefore,
``DEV`` is never baked into a release artifact; the dynamic component code
changes the message to ``DEV`` only while development mode is active.
-
    Args:
        _run: Set to True to export the Dewbee components.
        _repo: Optional Dewbee repository root. If empty, DEFAULT_REPO is used.

    Returns:
        report: Summary of exported components and paths.
"""

import io
import json
import os
import re
import shutil

import Grasshopper.Kernel as ghK
from Grasshopper.Folders import UserObjectFolders
from Grasshopper.Kernel import GH_RuntimeMessageLevel as Message


ghenv.Component.Name = "DB Save Compos"
ghenv.Component.NickName = "SaveCompos"
ghenv.Component.Category = "Dewbee"
ghenv.Component.SubCategory = "0 :: Miscellaneous"

try:
    ghenv.Component.ToggleObsolete(False)
except Exception:
    pass


# -----------------------------------------------------------------------------
# CONFIG
# -----------------------------------------------------------------------------

DEFAULT_REPO = r"C:\Users\gzorzeto\Documents\GitHub_repos\dewbee_main"

REPO_GHUSER_SUBFOLDER = os.path.join("grasshopper", "user_objects")
REPO_SOURCE_SUBFOLDER = os.path.join("grasshopper", "src")
GHUSER_TARGET_FOLDER_NAME = "dewbee"
COMPONENT_PREFIX = "DB"

APPDATA_DIR = os.getenv("APPDATA")
if not APPDATA_DIR:
    raise IOError("Could not resolve %APPDATA%.")

DEV_INFO_FILE = os.path.join(
    APPDATA_DIR,
    "ladybug_tools",
    "dewbee",
    "dev_mode",
    "active.json",
)

DYNAMIC_MESSAGE_LINE = "ghenv.Component.Message = dewbee.component_message()"


# -----------------------------------------------------------------------------
# DEWBEE STATE
# -----------------------------------------------------------------------------

try:
    import dewbee
except Exception as error:
    raise ImportError("Failed to import dewbee:\n\t{}".format(error))

DEWBEE_VERSION = dewbee.__version__

if hasattr(dewbee, "component_message"):
    ghenv.Component.Message = dewbee.component_message()
else:
    # Allows the utility to perform the one-time migration after __init__.py
    # has been edited but before Rhino has reloaded the module.
    ghenv.Component.Message = DEWBEE_VERSION


# -----------------------------------------------------------------------------
# HELPERS
# -----------------------------------------------------------------------------

def give_warning(message):
    ghenv.Component.AddRuntimeMessage(Message.Warning, str(message))


def give_error(message):
    ghenv.Component.AddRuntimeMessage(Message.Error, str(message))


def ensure_dir(path):
    if not os.path.isdir(path):
        os.makedirs(path)


def normalize_path(path):
    path = os.path.abspath(os.path.expanduser(str(path)))
    return os.path.normcase(path) if os.name == "nt" else path


def read_dev_state():
    if not os.path.isfile(DEV_INFO_FILE):
        return None
    try:
        with io.open(DEV_INFO_FILE, "r", encoding="utf-8") as stream:
            return json.load(stream)
    except Exception:
        return None


def get_local_ghuser_folder():
    if not UserObjectFolders or len(UserObjectFolders) == 0:
        raise IOError("Could not find the Grasshopper UserObjects directory.")
    return os.path.join(UserObjectFolders[0], GHUSER_TARGET_FOLDER_NAME)


def validate_repo(repo_dir):
    required = (
        os.path.join(repo_dir, "pyproject.toml"),
        os.path.join(repo_dir, "dewbee", "__init__.py"),
        os.path.join(repo_dir, "grasshopper"),
    )
    missing = [path for path in required if not os.path.exists(path)]
    if missing:
        raise IOError(
            "The selected folder is not a Dewbee repository.\nMissing:\n{}"
            .format("\n".join(missing))
        )


def read_repo_version(repo_dir):
    """Read the numeric version directly from the selected checkout."""
    init_file = os.path.join(repo_dir, "dewbee", "__init__.py")
    with io.open(init_file, "r", encoding="utf-8") as stream:
        source = stream.read()

    match = re.search(
        r"^__version__\s*=\s*[\"']([^\"']+)[\"']",
        source,
        re.MULTILINE,
    )
    if not match:
        raise ValueError("Could not find __version__ in:\n{}".format(init_file))

    version = match.group(1).strip()
    if not re.match(r"^\d+\.\d+\.\d+(?:[A-Za-z0-9._+-]*)?$", version):
        raise ValueError(
            "Dewbee's repository version must remain numeric, not {!r}."
            .format(version)
        )
    return version


def validate_development_mode(repo_dir):
    state = read_dev_state()
    if not state or not state.get("active"):
        raise RuntimeError(
            "DB Development Mode is not active. Run DB Development Mode for "
            "this repository before exporting components."
        )

    state_repo = state.get("repo")
    if not state_repo or normalize_path(state_repo) != normalize_path(repo_dir):
        raise RuntimeError(
            "Development mode is active for a different repository.\n"
            "Active: {}\nSelected: {}".format(state_repo or "unknown", repo_dir)
        )


def fallback_message(component_name):
    if component_name == "DB Installer and Updater":
        return "INSTALL"
    if component_name == "DB Development Mode":
        return "DEV"
    return "?"


def dynamic_message_block(component_name):
    """Return a bootstrap-safe runtime message block."""
    return [
        "try:",
        "    import dewbee",
        "    {}".format(DYNAMIC_MESSAGE_LINE),
        "except ImportError:",
        "    ghenv.Component.Message = {!r}".format(
            fallback_message(component_name)
        ),
    ]


def update_component_message(gh_component):
    """Replace the hardcoded metadata message while leaving status messages.

    Only an unindented ``ghenv.Component.Message = ...`` assignment is treated
    as the component metadata line. Indented runtime/status assignments remain
    untouched. The operation is idempotent.
    """
    if not hasattr(gh_component, "Code"):
        return False

    source = gh_component.Code
    if DYNAMIC_MESSAGE_LINE in source:
        gh_component.Message = dewbee.component_message()
        return False

    lines = source.splitlines()
    message_index = None
    for index, line in enumerate(lines):
        if re.match(r"^ghenv\.Component\.Message\s*=", line):
            message_index = index
            break

    block = dynamic_message_block(gh_component.Name)

    if message_index is None:
        # Components should normally have a message line. If one is absent,
        # place the runtime block immediately after NickName (or Name).
        insert_index = 0
        for index, line in enumerate(lines):
            if re.match(r"^ghenv\.Component\.(NickName|Name)\s*=", line):
                insert_index = index + 1
        lines[insert_index:insert_index] = block
    else:
        lines[message_index:message_index + 1] = block

    trailing_newline = source.endswith("\n") or source.endswith("\r")
    gh_component.Code = "\n".join(lines) + ("\n" if trailing_newline else "")
    gh_component.Message = dewbee.component_message()
    return True


class NamespaceComponentsOntoCanvas(object):
    """Temporarily instantiate matching user objects on the active canvas."""

    def __init__(self, namespace, source_dir, ghdoc):
        self.namespace = namespace
        self.source_dir = source_dir
        self.ghdoc = ghdoc
        self.compos = []

    def __enter__(self):
        print("Adding {} components to the canvas...".format(self.namespace))

        for filename in sorted(os.listdir(self.source_dir)):
            if filename.startswith(".") or filename.startswith("__"):
                continue
            if not filename.endswith(".ghuser"):
                continue
            if not filename.startswith(self.namespace):
                continue

            source_path = os.path.join(self.source_dir, filename)
            user_object = ghK.GH_UserObject(source_path)
            component = user_object.InstantiateObject()

            if component is None:
                give_warning("Failed to instantiate: {}".format(filename))
                continue

            self.ghdoc.AddObject(component, False)
            self.compos.append((component, user_object, source_path))
            print("Added: {}".format(filename))

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        print("Cleaning the temporary components from the canvas...")
        for component, _, _ in self.compos:
            self.ghdoc.RemoveObject(component, False)


def write_py_code(gh_component, target_dir):
    if not hasattr(gh_component, "Code"):
        return None

    target_path = os.path.join(target_dir, gh_component.Name + ".py")
    with io.open(target_path, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(gh_component.Code)

    print("Wrote code: {}".format(target_path))
    return target_path


def write_ghuser(original_uo, gh_component, target_dir, release_version):
    """Save dynamic code but numeric release metadata into the user object."""
    target_path = os.path.join(target_dir, gh_component.Name + ".ghuser")
    runtime_message = gh_component.Message

    try:
        # Do not serialize DEV into the distributable .ghuser metadata.
        gh_component.Message = release_version
        original_uo.SetDataFromObject(gh_component)
        original_uo.Path = target_path

        if not original_uo.SaveToFile():
            raise IOError("Failed to save ghuser: {}".format(target_path))
    finally:
        gh_component.Message = runtime_message

    print("Wrote ghuser: {}".format(target_path))
    return target_path


def refresh_local_ghusers(repo_files, local_dir):
    ensure_dir(local_dir)
    copied = []
    for repo_file in repo_files:
        target = os.path.join(local_dir, os.path.basename(repo_file))
        shutil.copy2(repo_file, target)
        copied.append(target)
        print("Refreshed local user object: {}".format(target))
    return copied


# -----------------------------------------------------------------------------
# EXECUTION
# -----------------------------------------------------------------------------

report = "Set _run to True to export Dewbee components."

if _run:
    try:
        repo_dir = normalize_path(_repo if _repo else DEFAULT_REPO)
        validate_repo(repo_dir)
        validate_development_mode(repo_dir)
        repo_version = read_repo_version(repo_dir)

        if repo_version != DEWBEE_VERSION:
            give_warning(
                "The selected checkout reports version {}, while the currently "
                "cached dewbee module reports {}. The repository version will "
                "be written to .ghuser metadata.".format(
                    repo_version, DEWBEE_VERSION
                )
            )

        if not hasattr(dewbee, "component_message"):
            raise AttributeError(
                "The imported dewbee package has no component_message(). "
                "Update dewbee/__init__.py and restart Rhino first."
            )

        local_ghuser = get_local_ghuser_folder()
        if not os.path.isdir(local_ghuser):
            raise IOError(
                "Dewbee's local UserObjects folder does not exist:\n{}"
                .format(local_ghuser)
            )

        repo_ghuser = os.path.join(repo_dir, REPO_GHUSER_SUBFOLDER)
        repo_py = os.path.join(repo_dir, REPO_SOURCE_SUBFOLDER)
        ensure_dir(repo_ghuser)
        ensure_dir(repo_py)

        ghdoc = ghenv.Component.OnPingDocument()
        py_files = []
        ghuser_files = []
        changed_messages = 0

        with NamespaceComponentsOntoCanvas(
            COMPONENT_PREFIX, local_ghuser, ghdoc
        ) as components:
            if not components.compos:
                raise RuntimeError(
                    "No DB*.ghuser components were found in:\n{}"
                    .format(local_ghuser)
                )

            for component, user_object, _ in components.compos:
                if update_component_message(component):
                    changed_messages += 1
                py_path = write_py_code(component, repo_py)
                if py_path:
                    py_files.append(py_path)
                ghuser_files.append(
                    write_ghuser(
                        user_object,
                        component,
                        repo_ghuser,
                        repo_version,
                    )
                )

        refresh_local_ghusers(ghuser_files, local_ghuser)

        report = "\n".join([
            "Dewbee components exported successfully.",
            "Repository: {}".format(repo_dir),
            "Components exported: {}".format(len(ghuser_files)),
            "Python files written: {}".format(len(py_files)),
            "Hardcoded messages migrated: {}".format(changed_messages),
            "Runtime canvas message: {}".format(dewbee.component_message()),
            "Serialized .ghuser message: {}".format(repo_version),
            "Repository user objects: {}".format(repo_ghuser),
            "Repository source files: {}".format(repo_py),
            "Local user objects refreshed: {}".format(local_ghuser),
        ])
        print(report)

    except Exception as error:
        report = "Dewbee component export failed:\n{}".format(error)
        print(report)
        give_error(report)
else:
    print(report)
