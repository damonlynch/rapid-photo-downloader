# SPDX-FileCopyrightText: Copyright 2011-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

import importlib.metadata


def installed_using_pip(package: str, suppress_errors: bool = True) -> bool:
    """
    Determine if python package was installed in local directory using pip.

    Determination is not 100% robust in all circumstances.

    :param package: package name to search for
    :param suppress_errors: if True, silently catch all exceptions and return False
    :return: True if installed via pip, else False
    """

    try:
        d = importlib.metadata.distribution(package)
        return d.read_text("INSTALLER").strip().lower() == "pip"
    except Exception:
        if not suppress_errors:
            raise
        return False


def python_package_source(package: str) -> str:
    """
    Return package installation source for Python package
    :param package: package name
    :return:
    """

    pip_install = "(installed using pip)"
    system_package = "(system package)"
    return pip_install if installed_using_pip(package) else system_package
