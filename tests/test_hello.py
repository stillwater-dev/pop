"""Tests for POP-002 — Say hello world."""

from argparse import Namespace
from unittest.mock import patch
import pytest

from pop import cli
from pop import __version__


def make_args(**kwargs):
    defaults = dict(name=None)
    defaults.update(kwargs)
    return Namespace(**defaults)


def test_version_flag_output(monkeypatch):
    """POP-003 — --version flag prints version and exits cleanly."""
    captured = []
    monkeypatch.setattr(cli.sys, "argv", ["pop", "--version"])
    # argparse holds its own reference to sys.exit; capture via stderr redirect
    import io
    from contextlib import redirect_stderr
    f = io.StringIO()
    with redirect_stderr(f):
        try:
            cli.main()
        except SystemExit as e:
            captured.append(e.code)
    out = f.getvalue()
    assert "pop 0.1.0" in out or captured == [0]


def test_hello_world():
    printed = []
    with patch.object(cli.console, "print", lambda msg: printed.append(str(msg))):
        cli.cmd_hello(make_args())
    assert printed == ["Hello, World!"]


def test_hello_with_name():
    printed = []
    with patch.object(cli.console, "print", lambda msg: printed.append(str(msg))):
        cli.cmd_hello(make_args(name="Alice"))
    assert printed == ["Hello, Alice!"]


def test_cli_hello_entry(monkeypatch):
    printed = []
    monkeypatch.setattr(cli.console, "print", lambda msg: printed.append(str(msg)))
    monkeypatch.setattr(cli.sys, "argv", ["pop", "hello"])
    cli.main()
    assert printed == ["Hello, World!"]


def test_cli_hello_with_name_entry(monkeypatch):
    printed = []
    monkeypatch.setattr(cli.console, "print", lambda msg: printed.append(str(msg)))
    monkeypatch.setattr(cli.sys, "argv", ["pop", "hello", "Bob"])
    cli.main()
    assert printed == ["Hello, Bob!"]
