#!/usr/bin/env python3

# Copyright (C) 2020-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Simple utility to extract language names for Rapid Photo Downloader using
languages in the po directory

Not included in program tarball distributed to end users.
"""

__author__ = "Damon Lynch"
__copyright__ = "Copyright 2020-2024, Damon Lynch"

import glob
import os
import re
import sys

import polib

PO_DIR = "po"
CODE_DIR = "raphodo"
SCRIPT = "utilities.py"

po_dir = os.path.abspath(
    os.path.join(os.path.realpath(__file__), os.path.join("../../", PO_DIR))
)
lang_english_re = re.compile("(.+)<.+>")
raphodo_dir = os.path.abspath(
    os.path.join(os.path.realpath(__file__), os.path.join("../../", CODE_DIR))
)
script = os.path.join(raphodo_dir, SCRIPT)

lang_names = []

for pofile in glob.iglob(os.path.join(po_dir, "*.po")):
    po = polib.pofile(pofile)
    lang_metadata = po.metadata["Language-Team"]
    lang_code = po.metadata["Language"]
    if not lang_code:
        lang_code = os.path.splitext(os.path.basename(pofile))[0]
    match = lang_english_re.search(lang_metadata)
    lang_english = match.group(1).strip() if match else lang_metadata

    lang_names.append((lang_code, lang_english))


with open(script) as script_py:
    code = script_py.read()

    dict_start = (
        "# Auto-generated from extract_language_names.py do not delete\n"
        "substitute_languages = {"
    )
    dict_end = "}  # Auto-generated from extract_language_names.py do not delete"

    start = code.find(dict_start) + len(dict_start)
    end = code.find(dict_end, start)
    if start < 0 or end < 0:
        print("Abort: cannot locate code block to replace")
        sys.exit(1)

    elements = [
        f"    '{lang_code}': '{lang_english}',"
        for lang_code, lang_english in lang_names
    ]
    new_code = "{}\n{}\n{}".format(code[:start], "\n".join(elements), code[end:])

    # write out the updated script
    with open(script, "w") as script_py:
        script_py.write(new_code)
