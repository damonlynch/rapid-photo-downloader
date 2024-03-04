from argparse import ArgumentParser, HelpFormatter

from buildconfig import package_abbreviations


def get_parser(formatter_class=HelpFormatter) -> ArgumentParser:
    parser = ArgumentParser(
        prog="Prepare source tarball and Debian folder",
        description="Prepare source tarball and Debian folder for Ubuntu PPA",
        formatter_class=formatter_class,
    )
    abbreviations = package_abbreviations()
    parser.add_argument(
        dest="package",
        choices=abbreviations,
        default=abbreviations[0],
        nargs="?"
    )
    return parser
