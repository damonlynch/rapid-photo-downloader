#!/usr/bin/env python3

# Copyright (C) 2020-2024 Damon Lynch <damonlynch@gmail.com>

# This file is part of Rapid Photo Downloader.
#
# Rapid Photo Downloader is free software: you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Rapid Photo Downloader is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Rapid Photo Downloader. If not,
# see <http://www.gnu.org/licenses/>.


"""
Utility to manage images for use in Rapid Photo Downloader.
Only for application development. Not included in program tarball distributed
to end users.

Exports plain SVG from source SVG files.

Checks resources.qrc against resources used in Python scripts.
Checks SVG sizes to ensure they are square.

Generates scaled PNG files from SVG, with option to scale at
1x and 2x, or  1x, 1.25x, 1.5x, 1.75x, and 2x.
"""

__author__ = "Damon Lynch"
__copyright__ = "Copyright 2020-2024, Damon Lynch"
__title__ = __file__
__description__ = "Manage PyQt5 application SVG and PNG image assets."

import argparse
import datetime
import filecmp
import glob
import os
import re
import shlex
import shutil
import subprocess
import sys
import traceback

try:
    from lxml import etree
except ImportError:
    print("Run:\nsudo apt -y install python3-lxml")
    sys.exit(1)

import pyprind

rename = {
    "folder-symbolic": "folder",
    "drive-removable-media-symbolic": "drive-removable-media",
}

fractional_scaling_support = False

fractional_output_sizes = [1, 1.25, 1.5, 1.75, 2]
round_output_sizes = [1, 2]

fractional_output_sizes_qt = [""] + [f"@{s}x" for s in fractional_output_sizes if s > 1]
round_output_sizes_qt = [""] + [f"@{s}x" for s in round_output_sizes if s > 1]

output_sizes = []
output_sizes_qt = []

base_directory = os.path.split(os.path.dirname(os.path.abspath(__file__)))[0]
code_directory = os.path.join(base_directory, "raphodo")
images_directory = os.path.join(base_directory, "images")
source_images_directory = os.path.join(base_directory, "sourceimages")
resources_qrc = "resources.qrc"
resources_input = os.path.join(code_directory, resources_qrc)
resources_output = os.path.join(code_directory, "qrc_resources.py")
backup_resources_qrc = os.path.join(os.path.expanduser("~"), "backup.resources_qrc")

inkscape_bin = shutil.which("inkscape")

inkscape_generate_png_cmd = (
    "{inkscape} --without-gui --file={svg} --export-png={png} --export-width={width} "
    "--export-height={height} --export-area-page"
)

inkscape_export_svg_cmd = (
    "{inkscape} --without-gui --file={svg} --export-plain-svg={output_svg}"
)

inkscape_query_cmd_line = "{inkscape} {query} {file}"

pyrcc_cmd_line = "{pyrcc} {input} -o {output}"

file_header = "File"
width_header = "| Width    "
height_header = "| Height   "
valid_header = "| Valid  "

table_row = (
    "{file:{file_len}}{width:>{width_len}}{height:>{height_len}}{valid:>{valid_len}}"
)

resource_re = re.compile(r"""[\"'(]:/(.+?\.[a-z]{3})[\"')]""")


def parser_options(formatter_class=argparse.HelpFormatter) -> argparse.ArgumentParser:
    """
    Construct the command line arguments for the script

    :return: the parser
    """
    parser = argparse.ArgumentParser(
        prog=__title__, formatter_class=formatter_class, description=__description__
    )

    parser.add_argument(
        "--fractional-scaling",
        action="store_true",
        default=False,
        help="Output fractionally scaled PNGs",
    )

    subparsers = parser.add_subparsers()
    parser_generate = subparsers.add_parser("generate")

    parser_check = subparsers.add_parser("check")
    check_all = parser_check.add_mutually_exclusive_group()
    check_single = parser_check.add_mutually_exclusive_group()

    parser_export = subparsers.add_parser("export")
    export_all = parser_export.add_mutually_exclusive_group()
    export_single = parser_export.add_mutually_exclusive_group()

    parser_generate.add_argument("SVG", action="store", help="SVG input file")
    parser_generate.add_argument(
        "--size", type=int, default=16, action="store", help="output base size"
    )
    parser_generate.add_argument(
        "-sp",
        "--skip-png",
        action="store_true",
        default=False,
        help="Skip PNG file generation",
    )
    parser_generate.add_argument(
        "--keep-svg",
        action="store_true",
        default=False,
        help="Keep SVG entry in resources.qrc file",
    )
    parser_generate.add_argument(
        "--skip-backup",
        action="store_true",
        default=False,
        help="Do not backup resources.qrc file",
    )

    parser_check.add_argument(
        "--resources",
        action="store_true",
        default=False,
        help="check resources.qrc matches resource use in python scripts",
    )

    check_single.add_argument(
        "--file", dest="check_file", action="store", help="file to check"
    )
    check_all.add_argument(
        "--all", dest="check_all", action="store_true", help="check all images"
    )

    export_single.add_argument(
        "--file", dest="export_file", action="store", help="file to export"
    )
    export_all.add_argument(
        "--all", dest="export_all", action="store_true", help="export all images"
    )

    return parser


def extract_code_graphic_resoucres() -> set[str]:
    resources = set()
    for script in glob.glob(os.path.join(code_directory, "*.py")):
        with open(script) as s:
            code = s.read()
            r = set(resource_re.findall(code))
            if r:
                resources = resources.union(r)

    return resources


def is_qt_scaled_resource(resource: str) -> bool:
    return any(resource.find(f"{scalar}.") > 0 for scalar in output_sizes_qt[1:])


def extract_qrc_resources() -> set[str]:
    parser = etree.XMLParser(remove_blank_text=True)
    tree = etree.parse(resources_input, parser)
    root = tree.getroot()
    qresource = root[0]
    resources = set()
    for child in qresource:
        alias = child.attrib["alias"]
        if not is_qt_scaled_resource(alias):
            resources.add(alias)
    return resources


def set_scaling(fractional_scaling: bool) -> None:
    global output_sizes
    global output_sizes_qt

    if fractional_scaling:
        output_sizes = fractional_output_sizes
        output_sizes_qt = fractional_output_sizes_qt
    else:
        output_sizes = round_output_sizes
        output_sizes_qt = round_output_sizes_qt


def full_file_name_from_partial(
    partial: str, add_ext: str | None = "svg", directory: str | None = None
) -> tuple[str, str]:
    basename, ext = os.path.splitext(partial)
    if not ext:
        partial = f"{partial}.{add_ext}"

    d = images_directory if directory is None else directory

    return basename, os.path.join(d, partial)


def get_sort_key(element) -> str:
    return element.get("alias")


def generate_png_file_names(basename: str, sizes: list[int]) -> tuple[list[str], ...]:
    fs = "{basename}{size}.png"
    aliases = [
        fs.format(basename=rename.get(basename, basename), size=size_qt)
        for size_qt in output_sizes_qt
    ]
    pngs = [fs.format(basename=basename, size=size) for size in sizes]

    return aliases, pngs


def generate_xml(
    basename: str, svg: str, remove_svg: bool, skip_backup: bool, sizes: list[int]
):
    # Remove existing formatting from the XML when opening it
    parser = etree.XMLParser(remove_blank_text=True)
    tree = etree.parse(resources_input, parser)
    root = tree.getroot()
    qresource = root[0]

    aliases, pngs = generate_png_file_names(basename=basename, sizes=sizes)

    alias_prefix = None
    filesys_prefix = None
    # Identify alias prefix and file system path prefix
    for name in (svg, pngs[0]):
        search = f".//file[contains(text(), '{os.path.sep}{name}')]"
        elements = qresource.xpath(search)
        if elements:
            assert len(elements) == 1
            element = elements[0]
            alias_prefix = os.path.split(element.get("alias"))[0]
            filesys_prefix = os.path.split(element.text)[0]
            break

    assert alias_prefix is not None
    assert filesys_prefix is not None

    print(
        f"SVG:               {svg}\n"
        f"Alias prefix:      {alias_prefix}\n"
        f"Filesystem prefix: {filesys_prefix}\n"
    )

    # Remove SVG entry from XML
    if remove_svg:
        search = f".//file[contains(text(), '{os.path.sep}{svg}')]"
        elements = qresource.xpath(search)
        if not elements:
            print(f"Did not remove {svg} from XML as it did not exist")
        else:
            print(f"Removing {svg} from XML")
            assert len(elements) == 1
            element = elements[0]
            qresource.remove(element)

    # Remove all existing PNG entries for this size
    for alias, png in zip(aliases, pngs):
        search = f".//file[contains(text(), '{os.path.sep}{png}')]"
        elements = qresource.xpath(search)
        if elements:
            print(f"Removing {png} from XML")
            assert len(elements) == 1
            element = elements[0]
            qresource.remove(element)

    # Add new ones
    for alias, png in zip(aliases, pngs):
        alias = os.path.join(alias_prefix, alias)
        png = os.path.join(filesys_prefix, png)
        print(f"Adding {png} to XML")
        element = etree.Element("file")
        element.set("alias", alias)
        element.text = png
        qresource.append(element)

    # Sort by alias attribute
    for parent in tree.xpath("//*[./*]"):  # Search for parent elements
        parent[:] = sorted(parent, key=get_sort_key)

    if not skip_backup:
        dt_backup_file = "{}-{}".format(
            datetime.datetime.now().strftime("%Y%m%d-%H%M"), resources_qrc
        )
        dt_backup = os.path.join(backup_resources_qrc, dt_backup_file)
        backup = os.path.join(backup_resources_qrc, resources_qrc)
        if not filecmp.cmp(resources_input, backup):
            print(f"\nBacking up resources.qrc to {dt_backup_file}")
            shutil.copy2(resources_input, dt_backup)
            shutil.copy2(resources_input, backup)

    # print(etree.tounicode(tree, pretty_print=True))
    tree.write(resources_input, pretty_print=True)


def generate_png(svg: str, png: str, width: int, height: int):
    cmd = inkscape_generate_png_cmd.format(
        inkscape=inkscape_bin, svg=svg, png=png, width=width, height=height
    )
    args = shlex.split(cmd)
    subprocess.run(args)


def inkscape_export_svg(image: str, export_image: str) -> None:
    cmd = inkscape_export_svg_cmd.format(
        inkscape=inkscape_bin, svg=image, output_svg=export_image
    )
    args = shlex.split(cmd)
    subprocess.run(args)


def inkscape_query(image: str, query: str) -> float:
    cmd = inkscape_query_cmd_line.format(inkscape=inkscape_bin, query=query, file=image)
    args = shlex.split(cmd)
    s = subprocess.run(args, capture_output=True)
    assert s.returncode == 0
    return float(s.stdout.decode())


def svg_width_inkscape(image: str) -> float:
    return inkscape_query(image, "-W")


def svg_height_inkscape(image: str) -> float:
    return inkscape_query(image, "-H")


def svg_size_data(full_file_name: str) -> tuple[str, float, float, bool]:
    name = os.path.split(full_file_name)[1]

    parser = etree.XMLParser()
    tree = etree.parse(full_file_name, parser)
    root = tree.getroot()
    try:
        x, y, w, h = root.attrib["viewBox"].split()
    except KeyError:
        try:
            w = root.attrib["width"]
            if w.endswith("px"):
                w = w[:-2]
            h = root.attrib["height"]
            if h.endswith("px"):
                h = h[:-2]
        except KeyError:
            print("\n\nUnable to determine width and height for", name)
            sys.exit(1)

    try:
        w = float(w)
        h = float(h)
    except ValueError:
        print("\n\nUnable to determine width and height for", name, "\n")
        traceback.print_exc()
        sys.exit(1)

    return name, w, h, w == h


def get_extension(full_file_name: str) -> str:
    ext = os.path.splitext(full_file_name)[1]
    if ext:
        ext = ext[1:].lower()
    return ext


def is_svg(full_file_name: str) -> bool:
    return get_extension(full_file_name) == "svg"


def export_files(full_file_name: str | None = None) -> None:
    if full_file_name is not None:
        bar = None
        svg_files = [full_file_name]
    else:
        svg_files = []
        for dirpath, dirname, names in os.walk(source_images_directory):
            names.sort()
            for name in names:
                full_file_name = os.path.join(dirpath, name)
                if is_svg(full_file_name):
                    svg_files.append(full_file_name)

        bar = pyprind.ProgBar(
            iterations=len(svg_files), stream=1, track_time=True, width=80
        )

    for full_file_name in svg_files:
        source_path, name = os.path.split(full_file_name)
        if len(source_path) > len(source_images_directory):
            dest_path = os.path.join(
                images_directory, source_path[len(source_images_directory) + 1 :]
            )
        else:
            dest_path = images_directory
        export_image = os.path.join(dest_path, name)
        inkscape_export_svg(image=full_file_name, export_image=export_image)
        if bar:
            bar.update()

    run_pyrcc()


def check_svg_validity(full_file_name: str | None = None) -> None:
    if full_file_name is not None:
        bar = None
        svg_files = [full_file_name]
    else:
        svg_files = []
        for dirpath, dirname, names in os.walk(images_directory):
            names.sort()
            for name in names:
                full_file_name = os.path.join(dirpath, name)
                if is_svg(full_file_name):
                    svg_files.append(full_file_name)

        bar = pyprind.ProgBar(
            iterations=len(svg_files), stream=1, track_time=True, width=80
        )
    rows = []

    for full_file_name in svg_files:
        rows.append(svg_size_data(full_file_name))
        if bar:
            bar.update()

    file_len = max(len(row[0]) for row in rows) + 2
    row_len = file_len + len(width_header) + len(height_header) + len(valid_header)
    print(
        table_row.format(
            file=file_header,
            file_len=file_len,
            width=width_header,
            width_len=len(width_header),
            height=height_header,
            height_len=len(height_header),
            valid=valid_header,
            valid_len=len(valid_header),
        )
    )
    print("-" * row_len)

    for row in rows:
        width = f"{row[1]:.1f}"
        height = f"{row[2]:.1f}"
        valid = "" if row[3] else "false"
        print(
            table_row.format(
                file=row[0],
                file_len=file_len,
                width=width,
                width_len=len(width_header),
                height=height,
                height_len=len(height_header),
                valid=valid,
                valid_len=len(valid_header),
            )
        )


def check_resources_match_code():
    code_resources = extract_code_graphic_resoucres()
    print(len(code_resources), "resources found in code")
    qrc_resources = extract_qrc_resources()
    print(len(qrc_resources), "resources found in qrc file")

    only_in_code = code_resources - qrc_resources
    if only_in_code:
        r = list(only_in_code)
        r.sort()
        print("\nResources in code not in resources.qrc:")
        for e in r:
            print(e)

    only_in_qrc = qrc_resources - code_resources
    if only_in_qrc:
        r = list(only_in_qrc)
        r.sort()
        print("\nResources not in code:")
        for e in r:
            print(e)


def check_resources_validity(
    check_resources: bool, check_svg: bool, full_file_name: str | None = None
) -> None:
    if check_svg:
        check_svg_validity(full_file_name)

    if check_resources:
        check_resources_match_code()


def run_pyrcc():
    print("\nGenerating resource file")

    pyrcc = shutil.which("pyrcc5")
    cmd = pyrcc_cmd_line.format(
        pyrcc=pyrcc, input=resources_input, output=resources_output
    )
    args = shlex.split(cmd)
    subprocess.run(args)


if __name__ == "__main__":
    parser = parser_options()

    args = parser.parse_args()

    set_scaling(args.fractional_scaling)

    if "SVG" in args:
        svg = args.SVG

        basename, svg_full_name = full_file_name_from_partial(partial=svg)

        if not os.path.isfile(svg_full_name):
            print(f"Input file {svg_full_name} does not exist")
            sys.exit(1)

        if not svg_size_data(svg_full_name)[2]:
            print("SVG is not square")
            sys.exit(1)

        sizes = [int(args.size * s) for s in output_sizes]

        if not args.skip_png:
            for size in sizes:
                png = os.path.join(images_directory, f"{basename}{size}.png")
                generate_png(svg=svg_full_name, png=png, width=size, height=size)

        generate_xml(
            basename=basename,
            svg=svg,
            remove_svg=not args.keep_svg,
            skip_backup=args.skip_backup,
            sizes=sizes,
        )
        run_pyrcc()

    elif "export_file" in args:
        if args.export_file is not None:
            export_file = args.export_file
            basename, full_file_name = full_file_name_from_partial(
                partial=export_file, directory=source_images_directory
            )

            if not os.path.isfile(full_file_name):
                print(f"Input file {full_file_name} does not exist")
                sys.exit(1)

        elif args.export_all:
            full_file_name = None
        else:
            parser.print_help()
            sys.exit(1)

        export_files(full_file_name)

        if full_file_name is not None:
            print()
            check_svg_validity(full_file_name)

    elif "check_file" in args:
        check_resources = args.resources
        check_svg = args.check_file is not None or args.check_all

        full_file_name = None

        if args.check_file is not None:
            check_file = args.check_file
            basename, full_file_name = full_file_name_from_partial(partial=check_file)

            if not os.path.isfile(full_file_name):
                print(f"Input file {full_file_name} does not exist")
                sys.exit(1)

        elif not check_resources and not args.check_all:
            parser.print_help()
            sys.exit(1)

        check_resources_validity(
            check_resources=check_resources,
            check_svg=check_svg,
            full_file_name=full_file_name,
        )
