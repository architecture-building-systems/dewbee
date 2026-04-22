"""
Install or update Dewbee. Please update your Ladybug Tools version using the
"LB Versioner" grasshopper component BEFORE installing dewbee.

When _run is "True", it installs or updates the Dewbee Python package into the Ladybug Tools Python environment,
installs Dewbee .ghuser components into the Grasshopper UserObjects folder, and Dewbee material
library into the custom constructions folder.

Only works with Rhino 8.0 and LBT version 1.10 or higher.
-

    Args:
       _run: Set to True to install or update Dewbee.
       _dewbee_ver: Optional version string for dewbee package (format: "0.1.0").
                    If empty, the latest version will be installed.
       _github_ref: Optional GitHub ref to download GH components from.
                    Can be a branch name like "main" or a tag like "v0.1.0".
                    If empty, the latest released version will be used.
"""

ghenv.Component.Name = "DB Installer and Updater"
ghenv.Component.NickName = "DBInstallUpdate"
ghenv.Component.Message = '0.1.1'
ghenv.Component.Category = "Dewbee"
ghenv.Component.SubCategory = "0 :: Miscellaneous"

try:
    ghenv.Component.ToggleObsolete(False)
except Exception:
    pass


import os
import shutil
import zipfile
import subprocess
import System.Net
import System.Windows.Forms
import Rhino
from Grasshopper.Folders import UserObjectFolders
 
from Grasshopper.Kernel import GH_RuntimeMessageLevel as Message

# Import ladybug dependencies
try:
    from ladybug.futil import preparedir, nukedir, copy_file_tree, download_file_by_name, unzip_file
except Exception as e:
    raise ImportError("Failed to import ladybug.futil utilities:\n\t{}".format(e))

# Get Ladybug Tools python executable and site-packages path, as well as standards dir.
try:
    from honeybee.config import folders as hb_folders
except Exception as e:
    raise ImportError(
        "Failed to import honeybee.config.folders.\n"
        "Ladybug Tools / Honeybee must already be installed.\n{}".format(e)
    )



# -----------------------------------------------------------------------------
# CONFIG
# -----------------------------------------------------------------------------

PY_EXE = hb_folders.python_exe_path
PY_SITE = hb_folders.python_package_path
CONSTRUCTIONS_DIR = os.path.join(hb_folders.default_standards_folder, "constructions")

if not PY_EXE or not os.path.isfile(PY_EXE):
    raise IOError("Could not find Ladybug Tools python executable:\n{}".format(PY_EXE))
if not PY_SITE or not os.path.isdir(PY_SITE):
    raise IOError("Could not find Ladybug Tools site-packages:\n{}".format(PY_SITE))
if not CONSTRUCTIONS_DIR or not os.path.isdir(CONSTRUCTIONS_DIR):
    raise IOError("Could not find Ladybug Tools custom constructions:\n{}".format(CONSTRUCTIONS_DIR))

PYPI_PACKAGE = "dewbee"
PYPI_IMPORT_NAME = "dewbee"

GITHUB_OWNER = "architecture-building-systems"
GITHUB_REPO = "dewbee"
_github_ref = None

# relative path inside the downloaded repo zip
REPO_GHUSER_SUBFOLDER = os.path.join("grasshopper", "user_objects")

# target folder name inside Grasshopper UserObjects
GHUSER_TARGET_FOLDER_NAME = "dewbee"

CUSTOM_ENV = os.environ.copy()
CUSTOM_ENV["PYTHONHOME"] = ""

# -----------------------------------------------------------------------------
# UI HELPERS
# -----------------------------------------------------------------------------

def give_warning(message):
    ghenv.Component.AddRuntimeMessage(Message.Warning, str(message))


def give_error(message):
    ghenv.Component.AddRuntimeMessage(Message.Error, str(message))


def give_popup_message(message, window_title=""):
    icon = System.Windows.Forms.MessageBoxIcon.Information
    buttons = System.Windows.Forms.MessageBoxButtons.OK
    Rhino.UI.Dialogs.ShowMessageBox(str(message), window_title, buttons, icon)


# -----------------------------------------------------------------------------
# FILE HELPERS
# -----------------------------------------------------------------------------
def remove_dist_info_files(directory, startswith_name=None):
    """Remove .dist-info folders, optionally filtering by prefix."""
    if not os.path.isdir(directory):
        return

    for name in os.listdir(directory):
        if not name.endswith(".dist-info"):
            continue
        if startswith_name is not None:
            if not name.lower().startswith(startswith_name.lower().replace("-", "_")):
                continue
        full_path = os.path.join(directory, name)
        print("Removing dist-info folder: {}".format(full_path))
        nukedir(full_path, rmdir=True)


def remove_existing_package(site_dir, package_name):
    """Remove any existing package folder and its dist-info from site_dir.

    This is needed because ``pip install --target --upgrade`` does not
    uninstall the previous version at the target first; it installs over it.
    If the previous install left files or a stale dist-info, or if another
    copy of the package exists earlier on sys.path, ``import`` can resolve to
    the wrong version. Wiping the target package dir + dist-info prior to
    install avoids that whole class of problem.
    """
    if not site_dir or not os.path.isdir(site_dir):
        return

    pkg_dir = os.path.join(site_dir, package_name)
    if os.path.isdir(pkg_dir):
        print("Removing existing package folder: {}".format(pkg_dir))
        nukedir(pkg_dir, rmdir=True)

    remove_dist_info_files(site_dir, startswith_name=package_name)


# -----------------------------------------------------------------------------
# DOWNLOAD HELPERS
# -----------------------------------------------------------------------------

def build_github_zip_url(owner, repo, ref):
    """
    Build GitHub archive URL.
    GitHub supports archive/refs/heads/<branch>.zip and archive/refs/tags/<tag>.zip.
    We try tag-style if ref starts with 'v', otherwise branch-style.
    """
    if ref and ref.startswith("v"):
        return "https://github.com/{}/{}/archive/refs/tags/{}.zip".format(owner, repo, ref)
    return "https://github.com/{}/{}/archive/refs/heads/{}.zip".format(owner, repo, ref or "main")


def expected_unzipped_repo_folder(base_dir, repo, ref):
    """Best-guess the name of the folder GitHub extracts from the archive zip.

    - For branch archives the folder is ``repo-<branch>``.
    - For tag archives, GitHub strips a leading ``v`` from the tag,
      so ``v0.1.1`` becomes the folder ``repo-0.1.1``.
    """
    if not ref:
        return os.path.join(base_dir, "{}-main".format(repo))
    folder_ref = ref
    if folder_ref[:1] in ("v", "V") and len(folder_ref) > 1 and folder_ref[1].isdigit():
        folder_ref = folder_ref[1:]
    return os.path.join(base_dir, "{}-{}".format(repo, folder_ref))

def download_and_extract_repo(owner, repo, ref, temp_root):
    """Download repo zip and return extracted repo directory."""
    url = build_github_zip_url(owner, repo, ref)
    zip_name = "{}_{}.zip".format(repo, ref or "main")
    zip_path = os.path.join(temp_root, zip_name)

    print("- " * 30)
    print("Downloading repo from GitHub:")
    print(url)

    preparedir(temp_root, remove_content=True)

    # This function downloads the file but does not return the path
    download_file_by_name(url, temp_root, zip_name, mkdir=True)

    if not os.path.isfile(zip_path):
        raise IOError("Zip file was not downloaded successfully:\n{}".format(zip_path))

    print("Downloaded zip to:")
    print(zip_path)

    unzip_file(zip_path, temp_root)

    extracted_repo_dir = expected_unzipped_repo_folder(temp_root, repo, ref or "main")

    if not os.path.isdir(extracted_repo_dir):
        candidates = []
        for name in os.listdir(temp_root):
            full = os.path.join(temp_root, name)
            if os.path.isdir(full) and name.startswith(repo + "-"):
                candidates.append(full)
        if len(candidates) == 1:
            extracted_repo_dir = candidates[0]

    if not os.path.isdir(extracted_repo_dir):
        raise IOError("Could not locate extracted repo folder inside:\n{}".format(temp_root))

    return zip_path, extracted_repo_dir

# -----------------------------------------------------------------------------
# LBT / PYTHON HELPERS
# -----------------------------------------------------------------------------

def run_pip_install(python_exe, package_name, version=None, target=None, env=None):
    """Install or update a package with pip."""
    if env is None:
        env = os.environ

    requirement = package_name if not version else "{}=={}".format(package_name, version)

    cmds = [python_exe, "-m", "pip", "install", requirement, "--no-deps", "--no-user", "--upgrade"]
    if target:
        cmds.extend(["--target", target])

    print("- " * 30)
    print("Running pip command:")
    print(" ".join(cmds))

    use_shell = True if os.name == "nt" else False
    process = subprocess.Popen(
        cmds,
        shell=use_shell,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env
    )
    stdout, stderr = process.communicate()

    try:
        stdout = stdout.decode("utf-8")
    except Exception:
        stdout = str(stdout)

    try:
        stderr = stderr.decode("utf-8")
    except Exception:
        stderr = str(stderr)

    return process.returncode, stdout, stderr

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
        msg = (
            "Dewbee installer needs administrator privileges to write into:\n"
            "C:\\Program Files\\ladybug_tools\\python\\Lib\\site-packages\n\n"
            "Please close Rhino, right-click Rhino, choose 'Run as administrator', "
            "then run the installer again."
        )
        give_error(msg)
        give_popup_message(msg, "Administrator privileges required")
        raise Exception(msg)

# -----------------------------------------------------------------------------
# GH USER OBJECT INSTALL
# -----------------------------------------------------------------------------

def get_ghuser_target_folder():
    if not UserObjectFolders or len(UserObjectFolders) == 0:
        raise IOError("Could not find Grasshopper UserObjects directory.")
    base = UserObjectFolders[0]
    target = os.path.join(base, GHUSER_TARGET_FOLDER_NAME)
    return target

def install_ghuser_objects_from_repo(extracted_repo_dir, gh_target_folder):
    """Copy grasshopper/user_objects/* to GH UserObjects/dewbee."""
    source_ghuser_folder = os.path.join(extracted_repo_dir, REPO_GHUSER_SUBFOLDER)

    if not os.path.isdir(source_ghuser_folder):
        raise IOError(
            "Could not find expected GH user objects folder in repo:\n{}".format(source_ghuser_folder)
        )

    print("Copying .ghuser files from:\n{}\nTo:\n{}".format(source_ghuser_folder, gh_target_folder))
    preparedir(gh_target_folder, remove_content=True)
    copy_file_tree(source_ghuser_folder, gh_target_folder, overwrite=True)

def install_dewbee_materials_from_repo(extracted_repo_dir):
    """Copy dewbee_materials.json into Honeybee standards/constructions."""

    source_file = os.path.join(
        extracted_repo_dir,
        "resources",
        "standards",
        "dewbee_materials.json"
    )

    if not os.path.isfile(source_file):
        raise IOError(
            "Could not find dewbee_materials.json in repo:\n{}".format(source_file)
        )

    target_file = os.path.join(CONSTRUCTIONS_DIR, "dewbee_materials.json")

    print("Installing Dewbee materials from:")
    print(source_file)
    print("To:")
    print(target_file)
    shutil.copyfile(source_file, target_file)

def resolve_github_ref(user_github_ref, user_dewbee_ver, installed_version):
    """Resolve which GitHub ref to use for GH assets/materials."""
    if user_github_ref:
        return user_github_ref

    if user_dewbee_ver:
        return "v{}".format(user_dewbee_ver)

    if installed_version:
        return "v{}".format(installed_version)

    return "main"

# -----------------------------------------------------------------------------
# MAIN INSTALL
# -----------------------------------------------------------------------------

def verify_python_package(python_exe):
    """Read __version__ directly from the installed package file.

    We deliberately avoid ``import dewbee`` here: if another copy of dewbee
    is earlier on sys.path (e.g. a stale install in the user site-packages),
    ``import`` would return its version and mask the install we just did.
    Reading the file at PY_SITE directly guarantees we verify the install
    we actually performed.
    """
    init_path = os.path.join(PY_SITE, PYPI_IMPORT_NAME, "__init__.py")
    if not os.path.isfile(init_path):
        return 1, "", "Could not find {} after install.".format(init_path)

    try:
        with open(init_path, "r") as f:
            src = f.read()
    except Exception as e:
        return 1, "", "Could not read {}: {}".format(init_path, e)

    import re
    match = re.search(r"__version__\s*=\s*[\"']([^\"']+)[\"']", src)
    if not match:
        return 1, "", "Could not find __version__ in {}".format(init_path)

    return 0, match.group(1).strip(), ""

def install_dewbee(dewbee_version=None, github_ref=None):
    print("Ladybug Tools Python executable:")
    print(PY_EXE)
    print("Ladybug Tools site-packages:")
    print(PY_SITE)
    print("Ladybug Tools custom constructions folder")
    print(CONSTRUCTIONS_DIR)

    print("- " * 30)
    print("Installing Dewbee Python package into Ladybug Tools site-packages...")

    # Wipe any previous install at the target so --target --upgrade can't
    # leave stale files, and so a stale copy cannot shadow the new one.
    remove_existing_package(PY_SITE, PYPI_IMPORT_NAME)

    returncode, stdout, stderr = run_pip_install(
        python_exe=PY_EXE,
        package_name=PYPI_PACKAGE,
        version=dewbee_version,
        target=PY_SITE,
        env=CUSTOM_ENV
    )

    print(stdout)
    if stderr:
        print(stderr)

    if returncode != 0:
        raise Exception("pip install failed for '{}'.\n{}".format(PYPI_PACKAGE, stderr))

    check_code, check_out, check_err = verify_python_package(PY_EXE)
    if check_code != 0:
        raise Exception(
            "Dewbee installation could not be verified from Ladybug Tools Python.\n{}".format(check_err)
        )

    installed_version = check_out.strip()
    print("Verified Dewbee version in LBT Python: {}".format(installed_version))

    effective_github_ref = resolve_github_ref(
        user_github_ref=github_ref,
        user_dewbee_ver=dewbee_version,
        installed_version=installed_version
    )

    print("Using GitHub ref for GH assets/materials: {}".format(effective_github_ref))

    home_folder = os.getenv("HOME") or os.path.expanduser("~")
    temp_root = os.path.join(home_folder, "dewbee_installer_temp")
    gh_target = get_ghuser_target_folder()

    zip_path = None
    extracted_repo_dir = None

    try:
        zip_path, extracted_repo_dir = download_and_extract_repo(
            owner=GITHUB_OWNER,
            repo=GITHUB_REPO,
            ref=effective_github_ref,
            temp_root=temp_root
        )

        install_ghuser_objects_from_repo(
            extracted_repo_dir=extracted_repo_dir,
            gh_target_folder=gh_target
        )

        install_dewbee_materials_from_repo(
            extracted_repo_dir=extracted_repo_dir
        )

    finally:
        try:
            if zip_path and os.path.isfile(zip_path):
                os.remove(zip_path)
        except Exception:
            pass

        try:
            if extracted_repo_dir and os.path.isdir(extracted_repo_dir):
                nukedir(extracted_repo_dir, rmdir=True)
        except Exception:
            pass

        try:
            if os.path.isdir(temp_root):
                nukedir(temp_root, rmdir=True)
        except Exception:
            pass
    
    success_lines = [
        "Dewbee has been successfully installed.",
        "Verified Dewbee in Ladybug Tools Python: {}".format(check_out),
        "Grasshopper user objects installed to:",
        gh_target,
        "",
        "RESTART RHINO to load the new components and library."
    ]

    success_msg = "\n".join(success_lines)
    print(success_msg)
    give_popup_message(success_msg, "Dewbee Installation Successful")

# -----------------------------------------------------------------------------
# EXECUTION
# -----------------------------------------------------------------------------

if _run:
    ensure_admin()

    try:
        install_dewbee(
            dewbee_version=_dewbee_ver if _dewbee_ver else None,
            github_ref=_github_ref if _github_ref else None
        )
    except Exception as e:
        msg = "Dewbee installation failed:\n{}".format(e)
        print(msg)
        give_error(msg)
else:
    print("Set _run to True to install Dewbee.")
    print("Optional:")
    print("  _dewbee_ver  -> specific PyPI version, eg. 0.1.0")