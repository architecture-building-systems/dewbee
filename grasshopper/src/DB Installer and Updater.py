"""
Install or update a coherent released version of Dewbee.

The installed Python package determines the GitHub release tag used for the
Grasshopper components and dewbee_materials.json:

    PyPI dewbee X  ->  GitHub tag vX

The component clears a DB Development Mode path override only after the full
release installation succeeds.
-
    Args:
        _run: Set to True to install or update Dewbee.
        _dewbee_ver: Optional released version, for example "0.1.2". If empty,
                     the latest PyPI version is installed.
"""

DEWBEE_COMPONENT_VERSION = "0.1.2"
ghenv.Component.Name = "DB Installer and Updater"
ghenv.Component.NickName = "DBInstallUpdate"
try:
    import dewbee
    ghenv.Component.Message = dewbee.component_message(
        DEWBEE_COMPONENT_VERSION
    )
except ImportError:
    ghenv.Component.Message = "?"
ghenv.Component.Category = "Dewbee"
ghenv.Component.SubCategory = "0 :: Miscellaneous"

try:
    ghenv.Component.ToggleObsolete(False)
except Exception:
    pass


import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ElementTree
from xml.sax.saxutils import escape as xml_escape

import Rhino
import System.Windows.Forms
from Grasshopper.Folders import UserObjectFolders
from Grasshopper.Kernel import GH_RuntimeMessageLevel as Message


try:
    from ladybug.futil import (
        preparedir,
        nukedir,
        copy_file_tree,
        download_file_by_name,
        unzip_file,
    )
except Exception as error:
    raise ImportError(
        "Failed to import ladybug.futil utilities:\n\t{}".format(error)
    )

try:
    from honeybee.config import folders as hb_folders
except Exception as error:
    raise ImportError(
        "Failed to import honeybee.config.folders. Ladybug Tools / Honeybee "
        "must already be installed.\n{}".format(error)
    )


# -----------------------------------------------------------------------------
# CONFIG
# -----------------------------------------------------------------------------

PY_EXE = hb_folders.python_exe_path
PY_SITE = hb_folders.python_package_path

APPDATA_DIR = os.getenv("APPDATA")
if not APPDATA_DIR:
    raise IOError("Could not resolve %APPDATA%.")

STANDARDS_DIR = os.path.join(APPDATA_DIR, "ladybug_tools", "standards")
CONSTRUCTIONS_DIR = os.path.join(STANDARDS_DIR, "constructions")
MATERIAL_TARGET = os.path.join(CONSTRUCTIONS_DIR, "dewbee_materials.json")

PYPI_PACKAGE = "dewbee"
PYPI_IMPORT_NAME = "dewbee"
GITHUB_OWNER = "architecture-building-systems"
GITHUB_REPO = "dewbee"
REPO_GHUSER_SUBFOLDER = os.path.join("grasshopper", "user_objects")
REPO_MATERIAL_FILE = os.path.join(
    "resources", "standards", "dewbee_materials.json"
)
GHUSER_TARGET_FOLDER_NAME = "dewbee"

RHINO_SCRIPTS_DIR = os.path.join(
    APPDATA_DIR, "McNeel", "Rhinoceros", "8.0", "scripts"
)
DEV_PTH_FILES = (
    os.path.join(RHINO_SCRIPTS_DIR, "python-2_dewbee-dev.pth"),
    os.path.join(RHINO_SCRIPTS_DIR, "python-3_dewbee-dev.pth"),
)
DEV_INFO_DIR = os.path.join(APPDATA_DIR, "ladybug_tools", "dewbee", "dev_mode")
DEV_INFO_FILE = os.path.join(DEV_INFO_DIR, "active.json")

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

CUSTOM_ENV = os.environ.copy()
CUSTOM_ENV["PYTHONHOME"] = ""


if not PY_EXE or not os.path.isfile(PY_EXE):
    raise IOError("Could not find Ladybug Tools Python executable:\n{}".format(PY_EXE))
if not PY_SITE or not os.path.isdir(PY_SITE):
    raise IOError("Could not find Ladybug Tools site-packages:\n{}".format(PY_SITE))

for subfolder in (
    "constructions",
    "constructionsets",
    "schedules",
    "programtypes",
):
    folder = os.path.join(STANDARDS_DIR, subfolder)
    if not os.path.isdir(folder):
        preparedir(folder, remove_content=False)


# -----------------------------------------------------------------------------
# UI HELPERS
# -----------------------------------------------------------------------------

def give_warning(message):
    ghenv.Component.AddRuntimeMessage(Message.Warning, str(message))


def give_error(message):
    ghenv.Component.AddRuntimeMessage(Message.Error, str(message))


def give_popup_message(message, window_title=""):
    Rhino.UI.Dialogs.ShowMessageBox(
        str(message),
        window_title,
        System.Windows.Forms.MessageBoxButtons.OK,
        System.Windows.Forms.MessageBoxIcon.Information,
    )


# -----------------------------------------------------------------------------
# FILE / ADMIN HELPERS
# -----------------------------------------------------------------------------

def remove_dist_info_files(directory, startswith_name=None):
    if not os.path.isdir(directory):
        return
    normalized = None
    if startswith_name is not None:
        normalized = startswith_name.lower().replace("-", "_")

    for name in os.listdir(directory):
        if not name.endswith(".dist-info"):
            continue
        if normalized is not None and not name.lower().startswith(normalized):
            continue
        nukedir(os.path.join(directory, name), rmdir=True)


def remove_existing_package(site_dir, package_name):
    package_dir = os.path.join(site_dir, package_name)
    if os.path.isdir(package_dir):
        nukedir(package_dir, rmdir=True)
    remove_dist_info_files(site_dir, startswith_name=package_name)


def is_windows_user_admin():
    if os.name != "nt":
        return True
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def ensure_admin():
    if os.name == "nt" and not is_windows_user_admin():
        message = (
            "Dewbee installer needs administrator privileges to write into "
            "the Ladybug Tools Python site-packages folder.\n\nClose Rhino, "
            "right-click Rhino, choose 'Run as administrator', and run the "
            "installer again."
        )
        give_error(message)
        give_popup_message(message, "Administrator privileges required")
        raise Exception(message)


def normalize_path(path):
    path = os.path.abspath(os.path.expanduser(str(path)))
    return os.path.normcase(path) if os.name == "nt" else path


def read_development_state():
    if not os.path.isfile(DEV_INFO_FILE):
        return None
    try:
        import json
        with open(DEV_INFO_FILE, "r") as stream:
            return json.load(stream)
    except Exception:
        return None


def read_development_repo():
    state = read_development_state()
    return state.get("repo") if state else None


def remove_managed_development_junction(state):
    """Remove only the junction recorded as created by DB Development Mode."""
    if not state:
        return None
    junction = state.get("junction")
    if not junction or not os.path.exists(junction):
        return None

    # Never use rmtree here. os.rmdir removes the junction itself without
    # traversing into or deleting the source repository.
    try:
        os.rmdir(junction)
    except Exception as error:
        raise IOError(
            "Could not remove the managed Dewbee development junction:\n{}\n{}"
            .format(junction, error)
        )
    return junction


def ironpython_settings_files():
    if not os.path.isdir(IRONPYTHON_SETTINGS_DIR):
        return []
    settings_files = []
    if os.path.isfile(IRONPYTHON_DEFAULT_SETTINGS):
        settings_files.append(IRONPYTHON_DEFAULT_SETTINGS)
    for name in os.listdir(IRONPYTHON_SETTINGS_DIR):
        if not name.startswith("settings-Scheme") or not name.endswith(".xml"):
            continue
        path = os.path.join(IRONPYTHON_SETTINGS_DIR, name)
        if normalize_path(path) != normalize_path(IRONPYTHON_DEFAULT_SETTINGS):
            settings_files.append(path)
    return settings_files


def set_release_ironpython_search_paths(settings_file, dev_repo=None):
    """Remove the dev repo and put LBT site-packages first."""
    with io.open(settings_file, "r", encoding="utf-8") as stream:
        contents = stream.read()
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

    dev_norm = normalize_path(dev_repo) if dev_repo else None
    lbt_norm = normalize_path(PY_SITE)
    filtered = []
    for path in existing_paths.split(";"):
        path = path.strip()
        if not path:
            continue
        path_norm = normalize_path(path)
        if path_norm == lbt_norm or (dev_norm and path_norm == dev_norm):
            continue
        filtered.append(path)
    new_paths = [PY_SITE] + filtered

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

    with io.open(settings_file, "w", encoding="utf-8") as stream:
        stream.write(updated)
    return settings_file


def use_release_in_current_session(dev_repo=None):
    dev_norm = normalize_path(dev_repo) if dev_repo else None
    lbt_norm = normalize_path(PY_SITE)
    cleaned = []
    for path in sys.path:
        path_norm = normalize_path(path)
        if path_norm == lbt_norm or (dev_norm and path_norm == dev_norm):
            continue
        cleaned.append(path)
    sys.path[:] = [PY_SITE] + cleaned

    for module_name in list(sys.modules.keys()):
        if module_name == "dewbee" or module_name.startswith("dewbee."):
            try:
                del sys.modules[module_name]
            except Exception:
                pass


def clear_development_override():
    state = read_development_state()
    dev_repo = state.get("repo") if state else None
    settings_files = []
    for settings_file in ironpython_settings_files():
        settings_files.append(
            set_release_ironpython_search_paths(settings_file, dev_repo)
        )

    removed_junction = remove_managed_development_junction(state)

    for pth_file in DEV_PTH_FILES:
        try:
            if os.path.isfile(pth_file):
                os.remove(pth_file)
        except Exception as error:
            give_warning(
                "Could not remove development path file {}: {}".format(
                    pth_file, error
                )
            )

    try:
        if os.path.isdir(DEV_INFO_DIR):
            shutil.rmtree(DEV_INFO_DIR)
    except Exception as error:
        give_warning("Could not remove development-mode state: {}".format(error))

    use_release_in_current_session(dev_repo)
    return settings_files, removed_junction


# -----------------------------------------------------------------------------
# PIP / VERSION
# -----------------------------------------------------------------------------

def decode_output(value):
    try:
        return value.decode("utf-8")
    except Exception:
        return str(value)


def run_pip_install(python_exe, package_name, version=None, target=None, env=None):
    requirement = (
        package_name if not version
        else "{}=={}".format(package_name, version)
    )
    commands = [
        python_exe,
        "-m",
        "pip",
        "install",
        requirement,
        "--no-deps",
        "--no-user",
        "--upgrade",
    ]
    if target:
        commands.extend(["--target", target])

    process = subprocess.Popen(
        commands,
        shell=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env if env is not None else os.environ,
    )
    stdout, stderr = process.communicate()
    return process.returncode, decode_output(stdout), decode_output(stderr)


def verify_python_package():
    init_path = os.path.join(PY_SITE, PYPI_IMPORT_NAME, "__init__.py")
    if not os.path.isfile(init_path):
        raise IOError("Could not find installed package file:\n{}".format(init_path))

    with open(init_path, "r") as stream:
        source = stream.read()

    match = re.search(r"__version__\s*=\s*[\"']([^\"']+)[\"']", source)
    if not match:
        raise ValueError("Could not find __version__ in:\n{}".format(init_path))
    return match.group(1).strip()


# -----------------------------------------------------------------------------
# GITHUB RELEASE ASSETS
# -----------------------------------------------------------------------------

def github_tag_zip_url(tag):
    return "https://github.com/{}/{}/archive/refs/tags/{}.zip".format(
        GITHUB_OWNER, GITHUB_REPO, tag
    )


def expected_unzipped_repo_folder(base_dir, tag):
    folder_ref = tag
    if (
        folder_ref[:1] in ("v", "V")
        and len(folder_ref) > 1
        and folder_ref[1].isdigit()
    ):
        folder_ref = folder_ref[1:]
    return os.path.join(base_dir, "{}-{}".format(GITHUB_REPO, folder_ref))


def download_and_extract_release(tag, temp_root):
    zip_name = "{}_{}.zip".format(GITHUB_REPO, tag)
    zip_path = os.path.join(temp_root, zip_name)
    preparedir(temp_root, remove_content=True)

    url = github_tag_zip_url(tag)
    print("Downloading released assets from {}".format(url))
    download_file_by_name(url, temp_root, zip_name, mkdir=True)
    if not os.path.isfile(zip_path):
        raise IOError("Release archive was not downloaded:\n{}".format(zip_path))

    unzip_file(zip_path, temp_root)
    extracted = expected_unzipped_repo_folder(temp_root, tag)
    if not os.path.isdir(extracted):
        candidates = []
        for name in os.listdir(temp_root):
            full_path = os.path.join(temp_root, name)
            if os.path.isdir(full_path) and name.startswith(GITHUB_REPO + "-"):
                candidates.append(full_path)
        if len(candidates) == 1:
            extracted = candidates[0]

    if not os.path.isdir(extracted):
        raise IOError(
            "Could not locate the extracted Dewbee release in:\n{}".format(temp_root)
        )
    return extracted


def get_ghuser_target_folder():
    if not UserObjectFolders or len(UserObjectFolders) == 0:
        raise IOError("Could not find the Grasshopper UserObjects directory.")
    return os.path.join(UserObjectFolders[0], GHUSER_TARGET_FOLDER_NAME)


def install_release_assets(extracted_repo_dir):
    gh_source = os.path.join(extracted_repo_dir, REPO_GHUSER_SUBFOLDER)
    material_source = os.path.join(extracted_repo_dir, REPO_MATERIAL_FILE)
    gh_target = get_ghuser_target_folder()

    if not os.path.isdir(gh_source):
        raise IOError("Released .ghuser folder is missing:\n{}".format(gh_source))
    if not os.path.isfile(material_source):
        raise IOError("Released material file is missing:\n{}".format(material_source))

    preparedir(gh_target, remove_content=True)
    copy_file_tree(gh_source, gh_target, overwrite=True)

    # The release material data always comes from the same tag as the backend.
    shutil.copy2(material_source, MATERIAL_TARGET)
    return gh_target, material_source


# -----------------------------------------------------------------------------
# MAIN INSTALL
# -----------------------------------------------------------------------------

def install_dewbee(dewbee_version=None):
    print("Ladybug Tools Python executable:\n{}".format(PY_EXE))
    print("Ladybug Tools site-packages:\n{}".format(PY_SITE))
    print("Custom constructions folder:\n{}".format(CONSTRUCTIONS_DIR))

    remove_existing_package(PY_SITE, PYPI_IMPORT_NAME)
    returncode, stdout, stderr = run_pip_install(
        python_exe=PY_EXE,
        package_name=PYPI_PACKAGE,
        version=dewbee_version,
        target=PY_SITE,
        env=CUSTOM_ENV,
    )
    print(stdout)
    if stderr:
        print(stderr)
    if returncode != 0:
        raise Exception("pip install failed for Dewbee.\n{}".format(stderr))

    installed_version = verify_python_package()
    github_tag = "v{}".format(installed_version)
    temp_root = os.path.join(tempfile.gettempdir(), "dewbee_release_installer")

    try:
        extracted_repo_dir = download_and_extract_release(github_tag, temp_root)
        gh_target, material_source = install_release_assets(extracted_repo_dir)

        # Clear the local-repo import only after backend + both assets succeeded.
        ironpython_files, removed_junction = clear_development_override()
    finally:
        try:
            if os.path.isdir(temp_root):
                nukedir(temp_root, rmdir=True)
        except Exception:
            pass

    success_message = "\n".join([
        "Dewbee has been installed in RELEASE mode.",
        "Python package: dewbee {}".format(installed_version),
        "Grasshopper components: GitHub tag {} -> {}".format(
            github_tag, gh_target
        ),
        "Materials: GitHub tag {} -> {}".format(
            github_tag, MATERIAL_TARGET
        ),
        "",
        "Any DB Development Mode override has been cleared.",
        "Development package junction removed:",
        removed_junction if removed_junction else "No managed junction found.",
        "Legacy IronPython release paths restored in:",
        "\n".join(ironpython_files) if ironpython_files else "No settings files found.",
        "Restart Rhino to load the released package and components.",
    ])
    print(success_message)
    give_popup_message(success_message, "Dewbee Installation Successful")


# -----------------------------------------------------------------------------
# EXECUTION
# -----------------------------------------------------------------------------

if _run:
    ensure_admin()
    try:
        install_dewbee(_dewbee_ver if _dewbee_ver else None)
    except Exception as error:
        message = "Dewbee installation failed:\n{}".format(error)
        print(message)
        give_error(message)
else:
    print("Set _run to True to install/update Dewbee RELEASE mode.")
    print("Optional: _dewbee_ver -> released PyPI version, for example 0.1.2")
    print("Grasshopper components and materials come from the matching Git tag.")
