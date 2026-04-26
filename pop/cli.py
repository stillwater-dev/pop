"""pop — CLI entry point."""

import argparse
import sys
import os
from pathlib import Path

from .server import Server
from .config import load_config, list_configs
from . import dreamwave
from .commands import run_command, run_playbook, upload_file
from rich.console import Console
from rich.table import Table

console = Console()


def cmd_connect(args):
    srv = Server.from_config(args.config, args.name)
    srv.connect()


def cmd_run(args):
    srv = Server.from_config(args.config, args.name)
    result = srv.run(args.command, background=args.bg)
    if not args.bg:
        console.print(result)


def cmd_exec(args):
    srv = Server.from_config(args.config, args.name)
    result = srv.exec_script(Path(args.script))
    console.print(result)


def cmd_upload(args):
    srv = Server.from_config(args.config, args.name)
    srv.upload(args.local, args.remote)


def cmd_deploy(args):
    srv = Server.from_config(args.config, args.name)
    playbook = Path(args.playbook)
    if not playbook.exists():
        playbook = Path(__file__).parent.parent / "playbooks" / f"{args.playbook}.yaml"
    if not playbook.exists():
        console.print(f"[red]Playbook not found: {args.playbook}[/red]")
        return
    result = srv.run_playbook(playbook)
    console.print(result)


def cmd_list(args):
    configs = list_configs(args.config)
    if not configs:
        console.print("No servers configured. Create ~/.pop.yaml to get started.")
        return
    table = Table(title="[violet]Servers[/violet]", border_style="dim")
    table.add_column("Name", style="cyan")
    table.add_column("Host")
    table.add_column("User")
    table.add_column("Port")
    for cfg in configs:
        table.add_row(
            cfg.get("name", "?"),
            cfg.get("host", "?"),
            cfg.get("user", "?"),
            str(cfg.get("port", 22)),
        )
    console.print(table)


def main():
    parser = argparse.ArgumentParser(
        description="pop — pop your code onto a VPS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-c", "--config", default="~/.pop.yaml", help="Config file path")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="List configured servers")

    p_connect = sub.add_parser("connect", help="Interactive SSH connect")
    p_connect.add_argument("name", help="Server name from config")
    p_connect.set_defaults(fn=cmd_connect)

    p_run = sub.add_parser("run", help="Run a shell command")
    p_run.add_argument("name", help="Server name from config")
    p_run.add_argument("command", help="Shell command to run")
    p_run.add_argument("-b", "--bg", action="store_true", help="Run in background")
    p_run.set_defaults(fn=cmd_run)

    p_exec = sub.add_parser("exec", help="Execute a local script on server")
    p_exec.add_argument("name", help="Server name from config")
    p_exec.add_argument("script", help="Local script path")
    p_exec.set_defaults(fn=cmd_exec)

    p_up = sub.add_parser("upload", help="Upload a file")
    p_up.add_argument("name", help="Server name from config")
    p_up.add_argument("local", help="Local file path")
    p_up.add_argument("remote", help="Remote destination path")
    p_up.set_defaults(fn=cmd_upload)

    p_deploy = sub.add_parser("deploy", help="Run a deployment playbook")
    p_deploy.add_argument("name", help="Server name from config")
    p_deploy.add_argument("playbook", help="Playbook name or path")
    p_deploy.set_defaults(fn=cmd_deploy)

    # dreamwave
    dreamwave.register(sub)

    args = parser.parse_args()

    if args.cmd == "list":
        cmd_list(args)
        return

    if args.cmd == "dreamwave":
        result = args.fn(args)
        if result:
            console.print(result)
        return

    fn = args.fn
    fn(args)


if __name__ == "__main__":
    main()
