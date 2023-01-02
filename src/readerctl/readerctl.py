from pathlib import Path

import click
from buvis.adapters import console

from readerctl.commands import CommandAdd, CommandLogin


@click.group(help="CLI tool to manage Reader from Readwise")
def cli():
    pass


@cli.command("login")
def login():
    cmd = CommandLogin()
    cmd.execute()


@cli.command("add")
@click.option("-u", "--url", default="NONE", help="URL to add to Reader")
@click.option("-f",
              "--file",
              default="NONE",
              help="File with URLs to add to Reader")
def add(url, file):
    if url or file:
        cmd = CommandLogin()
        cmd.execute()

    if url != "NONE":
        cmd = CommandAdd()
        cmd.execute(url)
    elif file != "NONE":
        if Path(file).is_file():
            cmd = CommandAdd()
            with open(Path(file), "r") as f:
                urls = f.readlines()

            for url in urls:
                cmd.execute(url)
        else:
            console.panic(f"File {file} not found")


if __name__ == "__main__":
    cli()
