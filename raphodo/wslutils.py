import configparser
import functools
import logging
import re
import shlex
import subprocess
from pathlib import Path
from typing import Set

from showinfm.system.linux import translate_wsl_path


@functools.lru_cache(maxsize=None)
def wsl_env_variable(variable: str) -> str:
    """
    Return Windows environment variable within WSL
    """

    assert variable
    return subprocess.run(
        shlex.split(f"wslvar {variable}"),
        universal_newlines=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()


@functools.lru_cache(maxsize=None)
def wsl_home() -> Path:
    """
    Return user's Windows home directory within WSL
    """

    return Path(
        translate_wsl_path(wsl_env_variable("USERPROFILE"), from_windows_to_wsl=True)
    )


@functools.lru_cache(maxsize=None)
def _wsl_reg_query_standard_folder(folder: str) -> str:
    """
    Use reg query on Windows to query the user's Pictures and Videos folder.

    No error checking.

    :param folder: one of "My Pictures" or "My Video"
    :return: registry value for the folder
    """

    assert folder in ("My Pictures", "My Video")
    query = fr"reg.exe query 'HKEY_CURRENT_USER\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders\' /v '{folder}'"
    output = subprocess.run(
        shlex.split(query),
        stdout=subprocess.PIPE,
        universal_newlines=True,
    ).stdout
    regex = rf"{folder}\s+REG_EXPAND_SZ\s+(.+)\n\n$"
    p = re.search(regex, output).group(1)
    if "%USERPROFILE%" in p:
        # e.g. %USERPROFILE%\Videos
        # substitute the user profile
        p = str(wsl_home() / p.replace("%USERPROFILE%\\", ""))

    return p


@functools.lru_cache(maxsize=None)
def wsl_pictures_folder() -> str:
    """
    Query the Windows registry for the location of the user's Pictures folder
    :return: location as a Linux path
    """

    return translate_wsl_path(
        _wsl_reg_query_standard_folder("My Pictures"), from_windows_to_wsl=True
    )


@functools.lru_cache(maxsize=None)
def wsl_videos_folder() -> str:
    """
    Query the Windows registry for the location of the user's Videos folder
    :return: location as a Linux path
    """

    return translate_wsl_path(
        _wsl_reg_query_standard_folder("My Video"), from_windows_to_wsl=True
    )


@functools.lru_cache(maxsize=None)
def wsl_conf_mnt_location() -> str:
    """
    Determine location of WSL mount points using /etc/wsl.conf
    :return: mount point if specified, else "/mnt"
    """

    config = configparser.ConfigParser()
    try:
        config.read_file(open("/etc/wsl.conf"))
    except Exception:
        logging.debug("Could not load wsl.conf")
    else:
        if config.has_option("automount", "root"):
            mount_dir = config.get("automount", "root")
            if Path(mount_dir).is_dir():
                return mount_dir
            else:
                logging.warning("WSL root mount point %s does not exist", mount_dir)
    return "/mnt"


def wsl_filter_directories() -> Set[str]:
    """
    :return: Set of full paths of WSL system directories to not show in file browser
    """

    mnt_location = Path(wsl_conf_mnt_location())
    return {str(mnt_location / d) for d in ('wsl', 'wslg')}
