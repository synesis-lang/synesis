"""test_identifies.py - Etapa 1: modificador IDENTIFIES + unicidade (erro 77).

Cobre:
  - parsing/transform do modificador IDENTIFIES em FieldSpec;
  - anotacao no JSON (v3.1 aditivo) e compatibilidade v3.0 (chave nova ignoravel);
  - validacao de unicidade cross-source (DuplicateIdentityValue / SYNESIS_E077).
"""
import json
from pathlib import Path

from synesis.ast.nodes import FieldSpec, FieldType, Scope
from synesis.compiler import SynesisCompiler
from synesis.parser.lexer import parse_string
from synesis.parser.transformer import SynesisTransformer

FIXTURES = Path(__file__).parent / "fixtures"


def _compile(project_name, synp="t20.synp"):
    return SynesisCompiler(FIXTURES / project_name / synp).compile()


def _ecodes(result):
    return [e.CODE for e in result.errors]


# --------------------------------------------------------------------------
# Grammar + transformer
# --------------------------------------------------------------------------

def test_identifies_parses_into_fieldspec():
    """FIELD com IDENTIFIES <entidade> preenche FieldSpec.identifies."""
    tmpl = (
        "TEMPLATE demo\n\n"
        "FIELD lattes_id TYPE TEXT\n"
        "    SCOPE SOURCE\n"
        "    IDENTIFIES researcher\n"
        "END FIELD\n"
    )
    tree = parse_string(tmpl, "demo.synt")
    result = SynesisTransformer("demo.synt").transform(tree)

    specs = _collect_fieldspecs(result)
    assert len(specs) == 1
    assert specs[0].identifies == "researcher"


def test_field_without_identifies_defaults_none():
    """Campo sem IDENTIFIES mantem identifies=None (aditivo, nao-regressivo)."""
    spec = FieldSpec(name="x", type=FieldType.TEXT, scope=Scope.SOURCE)
    assert spec.identifies is None
    assert spec.to_dict()["identifies"] is None


def _collect_fieldspecs(obj):
    found = []
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, FieldSpec):
            found.append(cur)
        elif isinstance(cur, (list, tuple)):
            stack.extend(cur)
    return found


# --------------------------------------------------------------------------
# Validacao de unicidade (erro 77)
# --------------------------------------------------------------------------

def test_duplicate_identity_value_is_error():
    """Dois SOURCEs com o mesmo valor de IDENTIFIES -> SYNESIS_E077."""
    result = _compile("T20-Identifies-Dup").validation_result
    assert "SYNESIS_E077" in _ecodes(result)


def test_distinct_identity_values_ok():
    """Valores distintos de IDENTIFIES nao disparam erro de unicidade."""
    result = _compile("T20-Identifies-Ok").validation_result
    assert "SYNESIS_E077" not in _ecodes(result)
    assert result.errors == []


def test_duplicate_identity_message_mentions_both_sources():
    """Mensagem dual cita a entidade, o valor e os dois bibrefs (sem @@)."""
    result = _compile("T20-Identifies-Dup").validation_result
    err = next(e for e in result.errors if e.CODE == "SYNESIS_E077")
    cli = err.to_cli_line()
    assert "researcher" in cli
    assert "3474555741700167" in cli
    assert "@silva2023" in cli and "@souza2024" in cli
    assert "@@" not in cli
    assert "@@" not in err.to_diagnostic()


# --------------------------------------------------------------------------
# JSON v3.1 aditivo
# --------------------------------------------------------------------------

def test_json_annotates_identifies(tmp_path):
    """O JSON exportado anota identifies no field_spec correspondente."""
    compiled = _compile("T20-Identifies-Ok")
    assert not compiled.has_errors()
    out = tmp_path / "export.json"
    compiled.to_json(out)

    data = json.loads(out.read_text(encoding="utf-8"))
    specs = data["template"]["field_specs"]
    assert specs["lattes_id"]["identifies"] == "researcher"


def test_json_v30_consumer_ignores_new_key(tmp_path):
    """Um consumidor v3.0 (que le por chaves conhecidas) nao quebra: as chaves
    antigas seguem presentes e intactas; identifies e apenas uma chave a mais."""
    compiled = _compile("T20-Identifies-Ok")
    out = tmp_path / "export.json"
    compiled.to_json(out)

    spec = json.loads(out.read_text(encoding="utf-8"))["template"]["field_specs"]["lattes_id"]
    # Chaves v3.0 conhecidas continuam la e legiveis:
    for key in ("name", "type", "scope", "description"):
        assert key in spec
    assert spec["type"].upper() == "TEXT"
    # identifies e aditiva; ignora-la nao afeta a leitura v3.0.
