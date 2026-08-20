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


# ===========================================================================
# Agrupamento de diagnosticos repetidos
# ===========================================================================

class TestRepeatedDiagnosticCollapse:
    """Mensagens identicas repetidas sao colapsadas para nao poluir o terminal.

    Um defeito sistematico (todo um `.syno` na forma errada) produzia centenas de
    linhas identicas que escondiam os demais diagnosticos.
    """

    def _err(self, file: str, line: int, msg: str):
        from pathlib import Path

        from synesis.ast.nodes import SourceLocation

        class _Diag:
            def __init__(self, loc, text):
                self.location = loc
                self._text = text

            def to_cli_line(self):
                return self._text

        return _Diag(SourceLocation(file=Path(file), line=line, column=1), msg)

    def _capture(self, errors):
        import click
        from click.testing import CliRunner

        from synesis.cli import _print_diagnostics

        @click.command()
        def cmd():
            _print_diagnostics(errors, "ERROR")

        return CliRunner().invoke(cmd).output

    def test_few_repeats_are_listed_individually(self):
        errors = [self._err("a.syno", n, "mesma mensagem") for n in (1, 2)]
        out = self._capture(errors)
        assert out.count("mesma mensagem") == 2
        assert "2x" not in out

    def test_many_repeats_are_collapsed(self):
        errors = [self._err("a.syno", n, "mesma mensagem") for n in range(1, 21)]
        out = self._capture(errors)
        assert out.count("mesma mensagem") == 1
        assert "20x" in out

    def test_collapsed_block_shows_sample_and_remainder(self):
        errors = [self._err("a.syno", n, "msg") for n in range(1, 11)]
        out = self._capture(errors)
        assert "a.syno:1:1" in out
        assert "e mais 7" in out  # 10 - 3 exibidos

    def test_distinct_messages_are_not_merged(self):
        errors = [self._err("a.syno", n, f"msg {n % 2}") for n in range(1, 21)]
        out = self._capture(errors)
        assert "msg 0" in out and "msg 1" in out

    def test_mixed_collapsed_and_individual(self):
        errors = [self._err("a.syno", n, "repetida") for n in range(1, 9)]
        errors.append(self._err("b.syno", 99, "unica"))
        out = self._capture(errors)
        assert "8x" in out
        assert "b.syno:99:1" in out

    def test_empty_input_prints_nothing(self):
        assert self._capture([]) == ""
