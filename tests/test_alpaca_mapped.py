"""EXPORT ALPACA com composicao declarada (MAP <campos> TO INSTRUCTION/INPUT/OUTPUT).

Testes de aceitacao do estudo Estudo_Alpaca_Composicao_Declarada_MAP_TO.md (§9).
O formato Alpaca nao muda: as tres chaves sao strings.
"""

import json
from pathlib import Path

import pytest

from synesis.ast.results import ExportBlockError, ExportBlockNotice
from synesis.compiler import SynesisCompiler
from synesis.exporters.alpaca_export import build_alpaca_pairs
from synesis.exporters.alpaca_mapped import export_alpaca_mapped
from synesis.semantic.project_blocks import (
    alpaca_plan,
    export_block_errors,
    export_block_notices,
)

TEMPLATE = """\
TEMPLATE t

SOURCE FIELDS
    OPTIONAL descricao
    OPTIONAL autor ON BIBLIOGRAPHY
END SOURCE FIELDS

ITEM FIELDS
    REQUIRED trecho, zona
    OPTIONAL BUNDLE chain, estatuto, justificativa
    OPTIONAL BUNDLE outro, nota
    OPTIONAL observacao, rotulos, quando, grupo, grau
END ITEM FIELDS

ONTOLOGY FIELDS
    OPTIONAL definicao
END ONTOLOGY FIELDS

FIELD descricao TYPE TEXT
    SCOPE SOURCE
END FIELD

FIELD autor TYPE TEXT
    SCOPE SOURCE
END FIELD

FIELD trecho TYPE QUOTATION
    SCOPE ITEM
END FIELD

FIELD zona TYPE ENUMERATED
    SCOPE ITEM
    VALUES
        Resultados: achados
        Metodo: procedimento
    END VALUES
END FIELD

FIELD chain TYPE CHAIN
    SCOPE ITEM
    ARITY >= 2
    RELATIONS
        EXPLORA: A explora B
        VISA: A visa B
    END RELATIONS
END FIELD

FIELD estatuto TYPE ENUMERATED
    SCOPE ITEM
    VALUES
        Afirmada: afirma
        Hipotetica: propoe
    END VALUES
END FIELD

FIELD justificativa TYPE MEMO
    SCOPE ITEM
END FIELD

FIELD outro TYPE TEXT
    SCOPE ITEM
END FIELD

FIELD nota TYPE MEMO
    SCOPE ITEM
END FIELD

FIELD observacao TYPE MEMO
    SCOPE ITEM
END FIELD

FIELD rotulos TYPE CODE
    SCOPE ITEM
END FIELD

FIELD quando TYPE DATE
    SCOPE ITEM
END FIELD

FIELD grupo TYPE TOPIC
    SCOPE ITEM
END FIELD

FIELD grau TYPE SCALE
    SCOPE ITEM
    FORMAT [1..5]
END FIELD

FIELD definicao TYPE TEXT
    SCOPE ONTOLOGY
END FIELD
"""

ANNOTATIONS = """\
SOURCE @a1
    descricao: Estudo sobre iscas
END SOURCE

ITEM @a1
    trecho: A isca explora a confianca e visa idosos.
    zona: Resultados
    chain: isca -> EXPLORA -> confianca
    estatuto: Afirmada
    justificativa: O texto afirma.
    chain: isca -> VISA -> idosos
    estatuto: Hipotetica
    justificativa: O texto sugere.
    observacao: primeira nota
    observacao: segunda nota
    rotulos: isca, confianca
    quando: 2024-03-01
    grupo: golpes
    grau: 4
END ITEM

ITEM @a1
    trecho: Outro trecho, sem cadeia.
    zona: Resultados
END ITEM

ITEM @a1
    trecho: Terceiro trecho, diferente.
    zona: Resultados
END ITEM
"""

ONTOLOGY = "".join(f"ONTOLOGY {c}\nEND ONTOLOGY\n\n" for c in ("isca", "confianca", "idosos"))


def _project(root: Path, export: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "t.synt").write_text(TEMPLATE, encoding="utf-8")
    (root / "r.bib").write_text("@misc{a1,\n  title = {T},\n  author = {Silva, Ana}\n}\n", encoding="utf-8")
    (root / "a.syn").write_text(ANNOTATIONS, encoding="utf-8")
    (root / "o.syno").write_text(ONTOLOGY, encoding="utf-8")
    synp = root / "p.synp"
    synp.write_text(
        'PROJECT p\n    TEMPLATE "t.synt"\n    INCLUDE BIBLIOGRAPHY "r.bib"\n'
        '    INCLUDE ANNOTATIONS "a.syn"\n    INCLUDE ONTOLOGY "o.syno"\n'
        + export + "END PROJECT\n",
        encoding="utf-8",
    )
    return synp


def _compile(root: Path, export: str):
    result = SynesisCompiler(_project(root, export).resolve()).compile()
    assert result.linked_project is not None, result.get_diagnostics()
    assert not result.has_errors(), result.get_diagnostics()
    block = result.linked_project.project.exports[0]
    return result, block


def _block(*lines: str, name: str = "tarefa") -> str:
    body = "".join(f"        {line}\n" for line in lines)
    return f"    EXPORT ALPACA {name}\n        OUTPUT \"saida/{name}.jsonl\"\n{body}    END EXPORT\n"


def _errors(result, block):
    return [type(e).__name__ for e in export_block_errors(block, result.template)]


def _run(result, block, tmp_path):
    out = tmp_path / "out" / "d.jsonl"
    card = export_alpaca_mapped(result.linked_project, out, result.template, block)
    lines = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    return lines, card


MECANISMO = _block(
    "INSTRUCTION Identifique a relacao causal no trecho.",
    "MAP trecho TO INPUT",
    "MAP chain, estatuto, justificativa TO OUTPUT",
)


# --- 1. iterador + contexto ---------------------------------------------------

def test_bundle_iterates_and_context_repeats(tmp_path):
    result, block = _compile(tmp_path, MECANISMO)
    assert _errors(result, block) == []
    lines, card = _run(result, block, tmp_path)
    assert len(lines) == 2
    assert {line["input"] for line in lines} == {"A isca explora a confianca e visa idosos."}
    assert lines[0]["output"] == (
        "chain:\nisca → EXPLORA → confianca\nestatuto: Afirmada\njustificativa:\nO texto afirma."
    )
    assert "estatuto: Hipotetica" in lines[1]["output"]
    assert card["counts"]["items_without_bundle"] == 2
    assert card["qualifier_counts"] == {"estatuto": {"Afirmada": 1, "Hipotetica": 1}}
    assert card["composition"]["unit"] == "bundle occurrence"
    assert all(isinstance(v, str) for line in lines for v in line.values())


# --- 2. contexto com varias ocorrencias -----------------------------------------

def test_repeated_context_enters_whole_without_multiplying(tmp_path):
    result, block = _compile(tmp_path, _block(
        "INSTRUCTION Explique.",
        "MAP trecho, observacao TO INPUT",
        "MAP chain TO OUTPUT",
    ))
    lines, _ = _run(result, block, tmp_path)
    assert len(lines) == 2
    assert lines[0]["input"].endswith("observacao:\nprimeira nota\nsegunda nota")


# --- 3. dois bundles -------------------------------------------------------------

def test_two_bundles_block_the_artifact(tmp_path):
    result, block = _compile(tmp_path, _block(
        "INSTRUCTION X.", "MAP outro TO INPUT", "MAP chain TO OUTPUT",
    ))
    assert "AlpacaMultipleBundles" in _errors(result, block)


# --- 4. entradas distintas, mesma resposta ----------------------------------------

def test_distinct_inputs_with_same_answer_are_kept(tmp_path):
    result, block = _compile(tmp_path, _block(
        "INSTRUCTION Classifique a zona.", "MAP trecho TO INPUT", "MAP zona TO OUTPUT", name="zona",
    ))
    lines, card = _run(result, block, tmp_path)
    assert len(lines) == 3
    assert {line["output"] for line in lines} == {"Resultados"}
    assert card["counts"]["duplicates_removed"] == 0
    assert card["composition"]["unit"] == "item"


# --- 5. trio identico ------------------------------------------------------------

def test_identical_trio_is_removed_and_counted(tmp_path):
    result, block = _compile(tmp_path, _block(
        "INSTRUCTION Classifique.", "MAP zona TO OUTPUT", name="zona",
    ))
    lines, card = _run(result, block, tmp_path)
    assert len(lines) == 1
    assert lines[0] == {"instruction": "Classifique.", "input": "", "output": "Resultados"}
    assert card["counts"]["duplicates_removed"] == 2


# --- 6 e 7. vazamento ------------------------------------------------------------

def test_leak_through_instruction_blocks(tmp_path):
    result, block = _compile(tmp_path, _block("MAP zona TO INSTRUCTION", "MAP zona TO OUTPUT"))
    assert "AlpacaFieldLeak" in _errors(result, block)


def test_leak_through_input_blocks(tmp_path):
    result, block = _compile(tmp_path, _block(
        "INSTRUCTION X.", "MAP trecho, zona TO INPUT", "MAP zona TO OUTPUT",
    ))
    assert "AlpacaFieldLeak" in _errors(result, block)


# --- 8. formato rotulado unico ------------------------------------------------------

def test_single_field_has_no_label_and_format_property_is_refused(tmp_path):
    result, block = _compile(tmp_path, _block(
        "INSTRUCTION X.", "MAP trecho TO INPUT", "MAP chain TO OUTPUT",
    ))
    lines, _ = _run(result, block, tmp_path)
    assert lines[0]["output"] == "isca → EXPLORA → confianca"
    result2, block2 = _compile(tmp_path / "b", _block(
        "INSTRUCTION X.", "FORMAT JSON", "MAP chain TO OUTPUT",
    ))
    assert "UnknownExportProperty" in _errors(result2, block2)


# --- 9. vazio sobre os valores; resposta curta valida -----------------------------------

def test_empty_output_skipped_and_short_answer_kept(tmp_path):
    result, block = _compile(tmp_path, _block(
        "INSTRUCTION X.", "MAP trecho TO INPUT", "MAP observacao TO OUTPUT",
    ))
    lines, card = _run(result, block, tmp_path)
    assert len(lines) == 1
    assert card["counts"]["skipped_empty_output"] == 2
    result2, block2 = _compile(tmp_path / "b", _block(
        "INSTRUCTION X.", "MAP chain TO INPUT", "MAP estatuto TO OUTPUT",
    ))
    lines2, _ = _run(result2, block2, tmp_path)
    assert [line["output"] for line in lines2] == ["Afirmada", "Hipotetica"]


# --- 10. aviso de integridade nao bloqueia --------------------------------------------

def test_omitted_partner_is_a_notice_and_the_artifact_is_written(tmp_path):
    result, block = _compile(tmp_path, _block(
        "INSTRUCTION X.", "MAP trecho TO INPUT", "MAP chain, justificativa TO OUTPUT",
    ))
    assert _errors(result, block) == []
    notices = export_block_notices(block, result.template)
    assert [type(n).__name__ for n in notices] == ["AlpacaBundlePartnerOmitted"]
    assert all(isinstance(n, ExportBlockNotice) and not isinstance(n, ExportBlockError) for n in notices)
    lines, _ = _run(result, block, tmp_path)
    assert len(lines) == 2


def test_export_command_writes_the_artifact_with_the_notice(tmp_path):
    from click.testing import CliRunner

    from synesis.cli import main as cli

    synp = _project(tmp_path, _block(
        "INSTRUCTION X.", "MAP trecho TO INPUT", "MAP chain, justificativa TO OUTPUT",
    ))
    run = CliRunner().invoke(cli, ["export", str(synp)])
    assert run.exit_code == 0, run.output
    assert (tmp_path / "saida" / "tarefa.jsonl").exists()
    assert (tmp_path / "saida" / "tarefa.card.json").exists()
    assert "estatuto" in run.output


# --- 11 e 12. instrucao e OUTPUT obrigatorios --------------------------------------------

@pytest.mark.parametrize("lines,expected", [
    (("MAP chain TO OUTPUT",), "AlpacaInstructionSource"),
    (("INSTRUCTION X.", "MAP observacao TO INSTRUCTION", "MAP chain TO OUTPUT"), "AlpacaInstructionSource"),
    (("INSTRUCTION X.", "MAP trecho TO INPUT"), "AlpacaOutputMapMissing"),
    (("INSTRUCTION X.",), "AlpacaOutputMapMissing"),
])
def test_instruction_and_output_contract(tmp_path, lines, expected):
    result, block = _compile(tmp_path, _block(*lines))
    assert expected in _errors(result, block)


# --- 13. campos nao suportados --------------------------------------------------------

@pytest.mark.parametrize("field", ["autor", "definicao"])
def test_unsupported_fields_block(tmp_path, field):
    result, block = _compile(tmp_path, _block("INSTRUCTION X.", f"MAP {field} TO INPUT", "MAP chain TO OUTPUT"))
    assert "AlpacaFieldNotSupported" in _errors(result, block)


def test_unknown_field_suggests(tmp_path):
    result, block = _compile(tmp_path, _block("INSTRUCTION X.", "MAP trech TO INPUT", "MAP chain TO OUTPUT"))
    errors = export_block_errors(block, result.template)
    unknown = [e for e in errors if type(e).__name__ == "AlpacaUnknownField"]
    assert unknown and unknown[0].suggestion == "trecho"


@pytest.mark.parametrize("line,expected", [
    ("MAP chain TO RESPONSE", "AlpacaMapTarget"),
    ("MAP Afirmada FROM estatuto TO OUTPUT", "AlpacaMapTarget"),
    ("MAP chain, chain TO OUTPUT", "AlpacaDuplicateField"),
])
def test_targets_from_and_duplicates(tmp_path, line, expected):
    result, block = _compile(tmp_path, _block("INSTRUCTION X.", "MAP trecho TO INPUT", line))
    assert expected in _errors(result, block)


# --- 14. modo embutido inalterado ----------------------------------------------------------

def test_block_without_map_keeps_builtin_mode(tmp_path):
    result, block = _compile(tmp_path, _block())
    assert alpaca_plan(block, result.template) is None
    assert _errors(result, block) == []
    notices = export_block_notices(block, result.template)
    assert [type(n).__name__ for n in notices] == ["AlpacaLegacyDropsQualifier"]
    assert build_alpaca_pairs(result.linked_project, result.template, result.bibliography)


def test_to_alpaca_without_block_is_the_builtin_mode(tmp_path):
    result, block = _compile(tmp_path, _block())
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    result.to_alpaca(a)
    result.to_alpaca(b, block)
    assert a.read_text(encoding="utf-8") == b.read_text(encoding="utf-8")


def test_to_alpaca_with_declared_block(tmp_path):
    result, block = _compile(tmp_path, MECANISMO)
    out = tmp_path / "m.jsonl"
    result.to_alpaca(out, block)
    assert len(out.read_text(encoding="utf-8").splitlines()) == 2


# --- 15. CODE, DATE, TOPIC, SCALE -----------------------------------------------------------

def test_code_date_topic_scale_rendering(tmp_path):
    result, block = _compile(tmp_path, _block(
        "INSTRUCTION X.", "MAP trecho TO INPUT", "MAP rotulos, quando, grupo, grau TO OUTPUT",
    ))
    lines, _ = _run(result, block, tmp_path)
    assert lines[0]["output"] == "rotulos: isca; confianca\nquando: 2024-03-01\ngrupo: golpes\ngrau: 4"


def test_card_paths_are_project_relative_and_deterministic(tmp_path):
    result, block = _compile(tmp_path, MECANISMO)
    _, card1 = _run(result, block, tmp_path)
    _, card2 = _run(result, block, tmp_path)
    assert card1 == card2
    assert card1["project"]["file"] == "p.synp"
    assert card1["template"]["file"] == "t.synt"
    assert "observacao" in card1["excluded_fields"]


# --- catalogo de diagnosticos ------------------------------------------------------------

@pytest.mark.parametrize("name,code,severity", [
    ("AlpacaOutputMapMissing", "SYNESIS_E158", "warning"),
    ("AlpacaInstructionSource", "SYNESIS_E159", "warning"),
    ("AlpacaUnknownField", "SYNESIS_E160", "warning"),
    ("AlpacaDuplicateField", "SYNESIS_E161", "warning"),
    ("AlpacaFieldLeak", "SYNESIS_E162", "warning"),
    ("AlpacaMultipleBundles", "SYNESIS_E163", "warning"),
    ("AlpacaFieldNotSupported", "SYNESIS_E164", "warning"),
    ("AlpacaMapTarget", "SYNESIS_E165", "warning"),
    ("AlpacaBundlePartnerOmitted", "SYNESIS_I166", "info"),
    ("AlpacaLegacyDropsQualifier", "SYNESIS_I167", "info"),
])
def test_diagnostic_codes_and_severity(name, code, severity):
    """Impeditivos saem como warning na compilacao (local ao bloco); informativos como info."""
    import synesis.ast.results as results

    cls = getattr(results, name)
    assert cls.CODE == code
    assert cls.DEFAULT_SEVERITY.value == severity


def test_compile_reports_notices_as_info(tmp_path):
    result, _ = _compile(tmp_path, _block(
        "INSTRUCTION X.", "MAP trecho TO INPUT", "MAP chain TO OUTPUT",
    ))
    codes = [getattr(i, "CODE", "") for i in result.validation_result.info]
    assert "SYNESIS_I166" in codes
    assert not [w for w in result.validation_result.warnings if getattr(w, "CODE", "").startswith("SYNESIS_E16")]
