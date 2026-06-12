"""CLI contract tests for synesis (compiler).

Locks --help / --version output as a regression contract. Uses CliRunner so
ANSI colour is off (_tty() returns False) and output is plain and stable.
"""

from __future__ import annotations

from importlib.metadata import version

from click.testing import CliRunner

from synesis.cli import main


def _run(*args: str):
    runner = CliRunner()
    return runner.invoke(main, list(args))


def test_version_reports_package_version():
    result = _run("--version")
    assert result.exit_code == 0
    assert version("synesis") in result.output


def test_help_shows_title_and_usage():
    result = _run("--help")
    assert result.exit_code == 0
    out = result.output
    assert "SYNESIS COMPILER" in out
    assert "Usage:" in out
    assert "Commands:" in out


def test_help_lists_all_commands():
    result = _run("--help")
    assert result.exit_code == 0
    out = result.output
    for cmd in ("init", "compile", "check", "validate-template"):
        assert cmd in out


def test_compile_subcommand_help():
    result = _run("compile", "--help")
    assert result.exit_code == 0
    out = result.output
    assert "--json" in out
    assert "--csv" in out
    assert "--strict" in out


def test_check_subcommand_help():
    result = _run("check", "--help")
    assert result.exit_code == 0
    assert "--help" in result.output or "FILE" in result.output
