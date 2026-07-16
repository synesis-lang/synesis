"""test_refers_to.py - Etapa 2a: REFERS TO, ON BIBLIOGRAPHY, value_origin.

Cobre:
  - parsing/transform de REFERS TO e ON BIBLIOGRAPHY (value_origin);
  - E078: IDENTIFIES/REFERS TO fora de SCOPE SOURCE;
  - E079: campo REQUIRED ... ON BIBLIOGRAPHY sem valor no .bib;
  - I080 (INFO): referencia externa declarada (REFERS TO isolado);
  - ausencia de E020 espurio para campo ON BIBLIOGRAPHY.
"""
from pathlib import Path

from synesis.ast.nodes import FieldType, Scope
from synesis.compiler import SynesisCompiler
from synesis.parser.template_loader import load_template_from_string, validate_template

FIXTURES = Path(__file__).parent / "fixtures"


def _compile(project_name, synp="t21.synp"):
    return SynesisCompiler(FIXTURES / project_name / synp).compile().validation_result


def _ecodes(r): return [e.CODE for e in r.errors]
def _wcodes(r): return [w.CODE for w in r.warnings]
def _icodes(r): return [i.CODE for i in r.info]


# --------------------------------------------------------------------------
# Parsing / transform
# --------------------------------------------------------------------------

def test_refers_to_parses_into_fieldspec():
    tmpl = load_template_from_string(
        "TEMPLATE d\n\n"
        "FIELD lattes_id TYPE TEXT\n"
        "    SCOPE SOURCE\n"
        "    REFERS TO researcher\n"
        "END FIELD\n",
        "d.synt",
    )
    assert tmpl.field_specs["lattes_id"].refers_to == "researcher"
    # default de origem preservado
    assert tmpl.field_specs["lattes_id"].value_origin == "document"


def test_on_bibliography_sets_value_origin():
    tmpl = load_template_from_string(
        "TEMPLATE d\n\n"
        "SOURCE FIELDS\n"
        "    REQUIRED descricao\n"
        "    REQUIRED lattes_id ON BIBLIOGRAPHY\n"
        "END SOURCE FIELDS\n\n"
        "FIELD descricao TYPE TEXT\n"
        "    SCOPE SOURCE\n"
        "END FIELD\n\n"
        "FIELD lattes_id TYPE TEXT\n"
        "    SCOPE SOURCE\n"
        "END FIELD\n",
        "d.synt",
    )
    assert tmpl.field_specs["lattes_id"].value_origin == "bibliography"
    assert tmpl.field_specs["descricao"].value_origin == "document"
    # o campo ON BIBLIOGRAPHY continua REQUIRED normal
    assert "lattes_id" in tmpl.required_fields[Scope.SOURCE]


def test_list_with_on_bibliography_is_syntax_error():
    """REQUIRED a, b ON BIBLIOGRAPHY e ambiguo -> rejeitado na gramatica."""
    from synesis.parser.lexer import parse_string, SynesisSyntaxError
    with __import__("pytest").raises(SynesisSyntaxError):
        parse_string(
            "TEMPLATE d\n\nSOURCE FIELDS\n    REQUIRED a, b ON BIBLIOGRAPHY\n"
            "END SOURCE FIELDS\n",
            "d.synt",
        )


def test_refers_to_and_value_origin_in_json_dict():
    tmpl = load_template_from_string(
        "TEMPLATE d\n\n"
        "FIELD f TYPE TEXT\n    SCOPE SOURCE\n    REFERS TO researcher\nEND FIELD\n",
        "d.synt",
    )
    d = tmpl.field_specs["f"].to_dict()
    assert d["refers_to"] == "researcher"
    assert d["value_origin"] == "document"


# --------------------------------------------------------------------------
# E078 — modificador fora de SCOPE SOURCE
# --------------------------------------------------------------------------

def test_identifies_outside_source_is_error():
    tmpl = load_template_from_string(
        "TEMPLATE d\n\nFIELD x TYPE TEXT\n    SCOPE ITEM\n    IDENTIFIES researcher\nEND FIELD\n",
        "d.synt",
    )
    r = validate_template(tmpl)
    assert "SYNESIS_E078" in [e.CODE for e in r.errors]


def test_refers_to_outside_source_is_error():
    tmpl = load_template_from_string(
        "TEMPLATE d\n\nFIELD x TYPE TEXT\n    SCOPE ITEM\n    REFERS TO researcher\nEND FIELD\n",
        "d.synt",
    )
    r = validate_template(tmpl)
    codes = [e.CODE for e in r.errors]
    assert "SYNESIS_E078" in codes


def test_modifier_in_source_is_ok():
    tmpl = load_template_from_string(
        "TEMPLATE d\n\nFIELD x TYPE TEXT\n    SCOPE SOURCE\n    IDENTIFIES researcher\nEND FIELD\n",
        "d.synt",
    )
    r = validate_template(tmpl)
    assert "SYNESIS_E078" not in [e.CODE for e in r.errors]


# --------------------------------------------------------------------------
# E079 / I080 / no spurious E020 — via compilacao real
# --------------------------------------------------------------------------

def test_refers_to_isolated_emits_info_not_warning():
    r = _compile("T21-RefersTo-Ok")
    assert "SYNESIS_I080" in _icodes(r)
    # nunca warning nem erro para a referencia externa isolada
    assert "SYNESIS_I080" not in _wcodes(r)
    assert r.errors == []


def test_on_bibliography_value_resolved_no_spurious_missing_field():
    """lattes_id vem do .bib; NAO deve disparar E020 (MissingRequiredField)."""
    r = _compile("T21-RefersTo-Ok")
    assert "SYNESIS_E020" not in _ecodes(r)
    assert "SYNESIS_E079" not in _ecodes(r)


def test_missing_bibliography_value_is_error():
    r = _compile("T21-RefersTo-MissingBib")
    assert "SYNESIS_E079" in _ecodes(r)


def test_missing_bib_message_mentions_field_and_bibref():
    r = _compile("T21-RefersTo-MissingBib")
    err = next(e for e in r.errors if e.CODE == "SYNESIS_E079")
    cli = err.to_cli_line()
    assert "lattes_id" in cli
    assert "artigo2024" in cli


def test_cli_prints_i080_info_on_isolated_compile():
    """Compilacao isolada com REFERS TO exibe o INFO de referencia externa (§5)."""
    from click.testing import CliRunner

    from synesis.cli import main

    runner = CliRunner()
    result = runner.invoke(main, ["compile", str(FIXTURES / "T21-RefersTo-Ok" / "t21.synp")])
    assert result.exit_code == 0, result.output
    combined = result.output + (result.stderr if result.stderr_bytes else "")
    assert "[INFO]" in combined
    assert "researcher" in combined
