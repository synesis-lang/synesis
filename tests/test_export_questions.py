"""
test_export_questions.py - Blocos QUESTIONS e EXPORT do .synp e `synesis export`

Etapas Q e A1 do plano ROLE/EXPORT (Spec_ROLE_EXPORT_SKOS v7, §1, §2, §6, §8, §9):
    - gramatica e AST de QUESTIONS, EXPORT e MAP;
    - diagnosticos E091-E093 (questoes, erros do nucleo) e E094-E100 (EXPORT,
      avisos locais ao bloco);
    - `project.questions` no JSON so com o bloco; GENERATED_AT fixa o timestamp;
    - `synesis export`: todos os blocos, por nome, por formato; erro local para
      so o bloco; erro do nucleo para todos.
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

import synesis
from synesis.cli import main

from .conftest import (
    ANNOTATIONS_VALID,
    BIBLIOGRAPHY_BASIC,
    ONTOLOGY_VALID,
    PROJECT_CONTENT,
    TEMPLATE_BASIC,
)


def _project(extra: str) -> str:
    """PROJECT_CONTENT com blocos extras recuados como os vizinhos."""
    body = "".join(("    " + line) if line.strip() else line for line in extra.splitlines(True))
    return PROJECT_CONTENT.replace("END PROJECT", body + "END PROJECT")


def _load(project: str, annotations: str = ANNOTATIONS_VALID):
    return synesis.load(
        project_content=project,
        template_content=TEMPLATE_BASIC,
        annotation_contents={"annotations.syn": annotations},
        ontology_contents={"ontology.syno": ONTOLOGY_VALID},
        bibliography_content=BIBLIOGRAPHY_BASIC,
    )


def _codes(result, kind: str = "all") -> list[str]:
    errors = [e.CODE for e in result.validation_result.errors]
    warnings = [w.CODE for w in result.validation_result.warnings]
    return {"errors": errors, "warnings": warnings}.get(kind, errors + warnings)


QUESTIONS_OK = """
QUESTIONS
    Q1: Quais fatores aparecem juntos?
    Q2: Que evidencias sustentam a coesao social -> e a resiliencia?
END QUESTIONS
"""


# ------------------------------------------------------------------ QUESTIONS

class TestQuestions:
    def test_questions_parse_and_reach_json(self):
        result = _load(_project(QUESTIONS_OK))
        assert not result.validation_result.has_errors()
        project = result.to_json_dict()["project"]
        assert project["questions"] == [
            {"id": "Q1", "text": "Quais fatores aparecem juntos?"},
            {"id": "Q2", "text": "Que evidencias sustentam a coesao social -> e a resiliencia?"},
        ]

    def test_project_without_questions_has_no_key(self):
        result = _load(PROJECT_CONTENT)
        assert "questions" not in result.to_json_dict()["project"]

    def test_e091_line_without_id(self):
        result = _load(_project("QUESTIONS\n    Quais fatores aparecem?\nEND QUESTIONS\n"))
        assert "SYNESIS_E091" in _codes(result, "errors")

    def test_e092_id_without_text(self):
        result = _load(_project("QUESTIONS\n    Q1:\nEND QUESTIONS\n"))
        assert "SYNESIS_E092" in _codes(result, "errors")

    def test_e093_duplicate_id_ignores_case(self):
        result = _load(_project("QUESTIONS\n    Q1: Uma?\n    q1: Outra?\nEND QUESTIONS\n"))
        assert "SYNESIS_E093" in _codes(result, "errors")

    def test_indented_comment_is_not_a_question(self):
        result = _load(_project("QUESTIONS\n    # rascunho\n    Q1: Uma?\nEND QUESTIONS\n"))
        assert not result.validation_result.has_errors()
        assert [q["id"] for q in result.to_json_dict()["project"]["questions"]] == ["Q1"]

    def test_word_questions_is_still_a_plain_word_elsewhere(self):
        """`questions` so e palavra-chave dentro do PROJECT (lexer contextual)."""
        ontology = ONTOLOGY_VALID + "\nONTOLOGY questions\n    description: Perguntas.\nEND ONTOLOGY\n"
        result = synesis.load(
            project_content=PROJECT_CONTENT,
            template_content=TEMPLATE_BASIC,
            annotation_contents={"annotations.syn": ANNOTATIONS_VALID},
            ontology_contents={"ontology.syno": ontology},
            bibliography_content=BIBLIOGRAPHY_BASIC,
        )
        assert "questions" in result.linked_project.ontology_index


# --------------------------------------------------------------------- EXPORT

class TestExportDiagnostics:
    def test_blocks_parse_without_diagnostics(self):
        result = _load(_project(
            'EXPORT JSON\n    OUTPUT "saida/p.json"\n    GENERATED_AT 2026-11-16T00:00:00Z\nEND EXPORT\n'
            'EXPORT CSV tabelas\n    OUTPUT "saida/csv"\nEND EXPORT\n'
        ))
        assert not any(c.startswith("SYNESIS_E09") or c == "SYNESIS_E100" for c in _codes(result))

    def test_export_blocks_not_in_json(self):
        result = _load(_project('EXPORT JSON\n    OUTPUT "x.json"\nEND EXPORT\n'))
        assert "exports" not in result.to_json_dict()["project"]

    def test_e094_unknown_format_is_warning(self):
        result = _load(_project('EXPORT PDF\n    OUTPUT "x.pdf"\nEND EXPORT\n'))
        assert "SYNESIS_E094" in _codes(result, "warnings")
        assert not result.validation_result.has_errors()

    def test_e094_planned_format_says_so(self):
        result = _load(_project('EXPORT CNA\n    OUTPUT "x.csv"\nEND EXPORT\n'))
        warning = next(w for w in result.validation_result.warnings if w.CODE == "SYNESIS_E094")
        assert "planned" in warning.to_diagnostic()

    def test_e095_unknown_property(self):
        result = _load(_project('EXPORT XLS\n    OUTPUT "x.xlsx"\n    COLOR azul\nEND EXPORT\n'))
        assert "SYNESIS_E095" in _codes(result, "warnings")

    def test_e096_missing_output(self):
        result = _load(_project("EXPORT JSON\n    DESCRIPTION painel\nEND EXPORT\n"))
        assert "SYNESIS_E096" in _codes(result, "warnings")

    def test_e097_duplicate_property(self):
        result = _load(_project('EXPORT JSON\n    OUTPUT "a.json"\n    OUTPUT "b.json"\nEND EXPORT\n'))
        assert "SYNESIS_E097" in _codes(result, "warnings")

    def test_e098_two_unnamed_blocks_of_same_format(self):
        result = _load(_project(
            'EXPORT JSON\n    OUTPUT "a.json"\nEND EXPORT\n'
            'EXPORT JSON\n    OUTPUT "b.json"\nEND EXPORT\n'
        ))
        assert "SYNESIS_E098" in _codes(result, "warnings")

    def test_e098_name_equal_to_a_format(self):
        result = _load(_project('EXPORT JSON csv\n    OUTPUT "a.json"\nEND EXPORT\n'))
        assert "SYNESIS_E098" in _codes(result, "warnings")

    def test_e099_map_not_supported(self):
        result = _load(_project('EXPORT JSON\n    OUTPUT "a.json"\n    MAP C, B TO CONDITION\nEND EXPORT\n'))
        assert "SYNESIS_E099" in _codes(result, "warnings")

    def test_e100_generated_at_without_timezone(self):
        result = _load(_project('EXPORT JSON\n    OUTPUT "a.json"\n    GENERATED_AT 2026-11-16T00:00:00\nEND EXPORT\n'))
        assert "SYNESIS_E100" in _codes(result, "warnings")

    def test_map_relations_keeps_relation_case(self):
        result = _load(_project(
            'EXPORT SKOS\n    OUTPUT "x.ttl"\n    MAP RELATIONS TIPO_DE FROM chain TO HIERARCHY KIND\nEND EXPORT\n'
        ))
        export = result.linked_project.project.exports[0]
        node = export.maps[0]
        assert (node.kind, node.names, node.from_field, node.target) == (
            "relations", ["TIPO_DE"], "chain", "HIERARCHY KIND")


# ------------------------------------------------------------- synesis export

def _write_project(root: Path, extra: str) -> Path:
    (root / "template.synt").write_text(TEMPLATE_BASIC, encoding="utf-8")
    (root / "references.bib").write_text(BIBLIOGRAPHY_BASIC, encoding="utf-8")
    (root / "annotations.syn").write_text(ANNOTATIONS_VALID, encoding="utf-8")
    (root / "ontology.syno").write_text(ONTOLOGY_VALID, encoding="utf-8")
    synp = root / "project.synp"
    synp.write_text(_project(extra), encoding="utf-8")
    return synp


BLOCKS = (
    'EXPORT JSON\n    OUTPUT "saida/p.json"\n    GENERATED_AT 2026-11-16T00:00:00Z\nEND EXPORT\n'
    'EXPORT CSV tabelas\n    OUTPUT "saida/csv"\nEND EXPORT\n'
    'EXPORT OKF\n    OUTPUT "saida/okf"\n    GENERATED_AT 2026-11-16T00:00:00Z\nEND EXPORT\n'
)


class TestExportCommand:
    def test_runs_every_block(self, tmp_path):
        synp = _write_project(tmp_path, BLOCKS)
        result = CliRunner().invoke(main, ["export", str(synp)])
        assert result.exit_code == 0, result.output
        assert (tmp_path / "saida" / "p.json").is_file()
        assert (tmp_path / "saida" / "csv").is_dir()
        assert (tmp_path / "saida" / "okf" / "index.md").is_file()

    def test_json_equals_compile_flag_except_timestamp(self, tmp_path):
        synp = _write_project(tmp_path, BLOCKS)
        CliRunner().invoke(main, ["export", str(synp), "json"])
        flag = tmp_path / "flag.json"
        CliRunner().invoke(main, ["compile", str(synp), "--json", str(flag)])
        a = json.loads((tmp_path / "saida" / "p.json").read_text(encoding="utf-8"))
        b = json.loads(flag.read_text(encoding="utf-8"))
        assert a["export_metadata"].pop("timestamp") == "2026-11-16T00:00:00Z"
        b["export_metadata"].pop("timestamp")
        assert a == b

    def test_generated_at_makes_json_reproducible(self, tmp_path):
        synp = _write_project(tmp_path, BLOCKS)
        runner = CliRunner()
        runner.invoke(main, ["export", str(synp), "json"])
        first = (tmp_path / "saida" / "p.json").read_bytes()
        runner.invoke(main, ["export", str(synp), "json"])
        assert (tmp_path / "saida" / "p.json").read_bytes() == first

    def test_selector_by_name(self, tmp_path):
        synp = _write_project(tmp_path, BLOCKS)
        result = CliRunner().invoke(main, ["export", str(synp), "tabelas"])
        assert result.exit_code == 0, result.output
        assert (tmp_path / "saida" / "csv").is_dir()
        assert not (tmp_path / "saida" / "p.json").exists()

    def test_unknown_selector_fails(self, tmp_path):
        synp = _write_project(tmp_path, BLOCKS)
        result = CliRunner().invoke(main, ["export", str(synp), "nada"])
        assert result.exit_code == 1

    def test_local_error_stops_only_that_block(self, tmp_path):
        synp = _write_project(
            tmp_path, BLOCKS + 'EXPORT XLS\n    OUTPUT "saida/p.xlsx"\n    COLOR azul\nEND EXPORT\n')
        result = CliRunner().invoke(main, ["export", str(synp)])
        assert result.exit_code == 1
        assert (tmp_path / "saida" / "p.json").is_file()
        assert not (tmp_path / "saida" / "p.xlsx").exists()

    def test_core_error_stops_every_block(self, tmp_path):
        synp = _write_project(tmp_path, BLOCKS + "QUESTIONS\n    sem id\nEND QUESTIONS\n")
        result = CliRunner().invoke(main, ["export", str(synp)])
        assert result.exit_code == 1
        assert not (tmp_path / "saida").exists()

    def test_project_without_export_is_informative(self, tmp_path):
        synp = _write_project(tmp_path, "")
        result = CliRunner().invoke(main, ["export", str(synp)])
        assert result.exit_code == 0
        assert "no EXPORT block" in result.output


def test_generated_at_accepts_z_suffix_on_every_python():
    """Python 3.10: `fromisoformat` nao aceita "Z"; a validacao normaliza.

    So o CI do 3.10 pegava: `GENERATED_AT 2026-11-16T00:00:00Z` virava erro
    de bloco ali e passava no 3.11+ (release 0.15.0, 2026-11-17).
    """
    from synesis.exporters.okf_export import _check_generated_at
    from synesis.semantic.project_blocks import _is_iso_with_tz

    assert _is_iso_with_tz("2026-11-16T00:00:00Z")
    assert _is_iso_with_tz("2026-11-16T00:00:00z")
    assert _is_iso_with_tz("2026-11-16T00:00:00+00:00")
    assert not _is_iso_with_tz("2026-11-16T00:00:00")
    _check_generated_at("2026-11-16T00:00:00Z")  # nao levanta
