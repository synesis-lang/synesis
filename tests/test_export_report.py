"""Relatório do `synesis export`: um bloco por EXPORT, tabela de mapeamento, avisos agrupados."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import pytest
from click.testing import CliRunner

from synesis.cli import _print_grouped_warnings, main

PROJECT = Path(__file__).resolve().parents[2] / "case-studies" / "Exemplo_Tipos_Relacionais"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    if not (PROJECT / "fraudes.synp").exists():
        pytest.skip("projeto de teste fora deste checkout")
    for name in ("fraudes.synp", "fraudes.synt", "ontologia.syno", "anotacoes.syn", "referencias.bib"):
        shutil.copy2(PROJECT / name, tmp_path / name)
    return tmp_path / "fraudes.synp"


def test_skos_block_has_header_wrote_line_table_and_validation(project: Path):
    out = CliRunner().invoke(main, ["export", str(project), "skos"]).output
    assert "Exporting SKOS: (unnamed) (fraudes.synp:" in out
    assert "✔ Wrote" in out and "triples)" in out
    assert "Model metrics:" in out and "Relation mapping (MAP RELATIONS):" in out
    header = next(line for line in out.splitlines() if "SOURCE" in line and "DROPPED" in line)
    assert header.split() == ["SOURCE", "TARGET", "PAIRS", "SUPPORTED", "ACCEPTED", "DROPPED"]
    assert "Integrity:  OK" in out and "Profile:" in out
    # Avisos do PROJETO (compilação) continuam com arquivo:linha — apontam
    # lugares diferentes. Os do bloco EXPORT saem agrupados na seção do bloco.
    assert not [line for line in out.splitlines() if "[WARNING]" in line and "EXPORT " in line]


@dataclass
class _Warning:
    title: str
    item: str

    def cli_group(self):
        return self.title, self.item


def test_warnings_repeated_from_an_earlier_block_become_a_reference(capsys):
    seen: dict = {}
    first = [_Warning("TOPIC spellings merged", "(A, a) -> \"a\""), _Warning("TOPIC spellings merged", "(B, b) -> \"b\"")]
    _print_grouped_warnings(first, seen, "corroborado")
    _print_grouped_warnings(list(first), seen, "candidatos")
    out = capsys.readouterr().out
    assert out.count("(A, a)") == 1
    assert "TOPIC spellings merged: same 2 as in `corroborado`" in out


def test_new_warning_in_a_later_block_is_shown_in_full(capsys):
    seen: dict = {}
    _print_grouped_warnings([_Warning("TOPIC spellings merged", "(A, a) -> \"a\"")], seen, "x")
    _print_grouped_warnings([_Warning("TOPIC spellings merged", "(A, a) -> \"a\""),
                             _Warning("TOPIC spellings merged", "(C, c) -> \"c\"")], seen, "y")
    out = capsys.readouterr().out
    assert "(C, c)" in out and "same" not in out


def test_report_marks_titles_totals_and_status_by_role(project: Path):
    """A CLI colore por papel; sem estilo o texto é o mesmo (saída redirecionada)."""
    from synesis.compiler import SynesisCompiler
    from synesis.exporters.skos_export import build_skos, report_lines

    result = SynesisCompiler(project).compile()
    export = next(e for e in result.linked_project.project.exports if e.format == "SKOS")
    skos = build_skos(result.linked_project, result.template, export)
    plain = report_lines(skos, project)
    tagged = report_lines(skos, project, style=lambda text, role: f"<{role}>{text}</{role}>")
    strip = re.compile(r"</?\w+>")
    assert [strip.sub("", line) for line in tagged] == plain
    joined = "\n".join(tagged)
    for role in ("title", "header", "total", "ok", "value", "dim"):
        assert f"<{role}>" in joined, role
    assert "<title>Relation mapping (MAP RELATIONS):</title>" in joined
