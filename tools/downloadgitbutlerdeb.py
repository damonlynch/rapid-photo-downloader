# Copyright (c) 2024 Damon Lynch
# SPDX - License - Identifier: MIT

import shlex
import subprocess
from argparse import ArgumentParser, HelpFormatter
from pathlib import Path

import requests
from rich.console import Console
from rich.progress import Progress
from rich.prompt import Confirm
from rich.theme import Theme

console = Console(
    theme=Theme(
        {
            "info": "cyan",
            "warning": "magenta",
            "danger": "bold red",
            "fail": "red",
            "installed": "yellow",
        }
    )
)


def get_parser(formatter_class=HelpFormatter) -> ArgumentParser:
    parser = ArgumentParser(
        description=(
            "Query the latest version of GitButler, download it, and optionally "
            "install it."
        ),
        formatter_class=formatter_class,
    )
    parser.add_argument(
        dest="path",
        default="",
        nargs="?",
        help=(
            "Optional directory in which to the save the downloaded package. "
            "If not specified, it will be the current working directory."
        ),
    )
    return parser


def get_latest_version() -> str:
    console.print(
        "Checking for latest GitButler version...", style="info", highlight=False
    )
    r = requests.get("https://app.gitbutler.com/latest_version")
    if r.status_code != 200:
        raise SystemExit(f"Error checking for latest version {r.status_code}")
    return r.content.decode().strip()


def installed_package_version() -> str:
    cmd = shlex.split("dpkg-query -f '${Version}' -W git-butler")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"Error checking if GitButler installed {r.returncode}")
    return r.stdout.strip()


def download_gitbutler(package_name: str, path: Path) -> None:
    HEADERS = {"User-Agent": __file__}
    url = "https://app.gitbutler.com/downloads/release/linux/x86_64/deb"
    with requests.get(url, headers=HEADERS, stream=True) as resp:
        TOTAL_SIZE = int(resp.headers.get("Content-Length", 0))
        CHUNK_SIZE = 10**6
        with open(path / package_name, mode="wb") as file, Progress() as progress:
            task = progress.add_task(f"Downloading {package_name}...", total=TOTAL_SIZE)
            for data in resp.iter_content(chunk_size=CHUNK_SIZE):
                size = file.write(data)
                progress.update(task, advance=size)


def install_gitbutler(package_path: Path) -> None:
    cmd = shlex.split(f"sudo dpkg -i {package_path}")
    subprocess.check_call(cmd)


def main():
    parser = get_parser()
    args = parser.parse_args()
    path = Path(args.path) if args.path and Path(args.path).is_dir() else Path.cwd()

    latest_version = get_latest_version()
    package_name = f"git-butler_{latest_version}_amd64.deb"

    if latest_version == installed_package_version():
        console.print(
            f"{package_name} is already installed", style="installed", highlight=False
        )
    else:
        try:
            download_gitbutler(package_name, path)
        except Exception as e:
            console.print(f"GitButler could not be downloaded: {e}", style="fail")
        else:
            if Confirm.ask(f"Install {package_name}?", default=True):
                package_path = path / package_name
                try:
                    install_gitbutler(package_path)
                except Exception as e:
                    console.print(
                        f"GitButler could not be installed: {e}", style="fail"
                    )
                else:
                    if Confirm.ask(f"Delete {package_path}?", default=True):
                        try:
                            package_path.unlink()
                        except Exception as e:
                            console.print(
                                f"Could not delete {package_path}: {e}", style="fail"
                            )


if __name__ == "__main__":
    main()
