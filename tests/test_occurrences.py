"""Valor de campo por ocorrência (FieldEntry) — fase 0a.

Antes, o compilador guardava os valores fundidos por nome e o linker os
reinterpretava estendendo a lista do transformer:

- D1: CODE de nome livre escrito mais de uma vez no ITEM saía duplicado
  (`X, Y` + `Z` -> `['X, Y', 'Z', 'X', 'Y', 'Z']`) e inflava code_frequency;
- D1': como o parse_cache devolve os mesmos nós e o linker os modificava no
  lugar, a duplicação crescia a cada recompilação no mesmo processo (LSP);
- D2: `note` e `memo` caíam no mesmo atributo e cada um devolvia os dois;
- D6: `quote` escrito duas vezes guardava só a última ocorrência;
- D7/D8: a fronteira das ocorrências se perdia, e o BUNDLE não emparelhava.
"""

from pathlib import Path

import synesis
from synesis.ast.nodes import ItemNode
from synesis.compiler import SynesisCompiler
from synesis.exporters._helpers import _get_item_field_value, _get_ontology_field_value
from synesis.exporters.json_export import build_json_payload
from synesis.parser.parse_cache import invalidate_cache
from synesis.semantic.occurrences import field_occurrences, item_field_value
from tests.conftest import BIBLIOGRAPHY_BASIC, PROJECT_CONTENT

TEMPLATE = """\
TEMPLATE t

SOURCE FIELDS
    OPTIONAL temas
END SOURCE FIELDS

FIELD temas TYPE CODE
    SCOPE SOURCE
END FIELD

ITEM FIELDS
    REQUIRED quote
    OPTIONAL note, memo, cadeia
    OPTIONAL BUNDLE justificativa, rotulos
END ITEM FIELDS

FIELD quote TYPE QUOTATION
    SCOPE ITEM
END FIELD

FIELD note TYPE MEMO
    SCOPE ITEM
END FIELD

FIELD memo TYPE MEMO
    SCOPE ITEM
END FIELD

FIELD justificativa TYPE MEMO
    SCOPE ITEM
END FIELD

FIELD rotulos TYPE CODE
    SCOPE ITEM
END FIELD

FIELD cadeia TYPE CHAIN
    SCOPE ITEM
    ARITY >= 2
END FIELD
"""

ANNOTATIONS = """\
SOURCE @smith2024
    temas: Autonomia, Recursos
END SOURCE

ITEM @smith2024
    quote: PRIMEIRO trecho
    quote: SEGUNDO trecho
    note: NOTA-DO-NOTE
    memo: NOTA-DO-MEMO
    justificativa: m1
    rotulos: X, Y
    justificativa: m2
    rotulos: Z
    cadeia: Alfa -> Beta
END ITEM
"""


def _load():
    r = synesis.load(
        project_content=PROJECT_CONTENT,
        template_content=TEMPLATE,
        annotation_contents={"annotations.syn": ANNOTATIONS},
        bibliography_content=BIBLIOGRAPHY_BASIC,
    )
    assert not r.has_errors(), r.get_diagnostics(verbose=False)
    return r


def _item(r) -> ItemNode:
    return next(iter(r.linked_project.sources.values())).items[0]


def test_entries_preserve_every_occurrence_in_order():
    item = _item(_load())
    names = [e.name for e in item.entries]
    assert names == [
        "quote",
        "quote",
        "note",
        "memo",
        "justificativa",
        "rotulos",
        "justificativa",
        "rotulos",
        "cadeia",
    ]
    assert [e.location.line for e in item.entries] == list(range(6, 15))


def test_free_named_code_is_not_duplicated():
    """D1: o linker substitui, não estende."""
    r = _load()
    item = _item(r)
    assert item.extra_fields["rotulos"] == ["X", "Y", "Z"]
    payload = build_json_payload(r.linked_project, r.template, r.bibliography)
    freq = payload["indices"]["code_frequency"]
    assert freq["x"] == 1 and freq["y"] == 1 and freq["z"] == 1


def test_code_occurrences_keep_their_boundary():
    """D7/D8: cada ocorrência de CODE é a sua lista; o BUNDLE emparelha por ocorrência."""
    r = _load()
    item = _item(r)
    rotulos = field_occurrences(item, "rotulos", r.template)
    justificativas = field_occurrences(item, "justificativa", r.template)
    assert rotulos == [["X", "Y"], ["Z"]]
    assert list(zip(justificativas, rotulos)) == [("m1", ["X", "Y"]), ("m2", ["Z"])]


def test_note_and_memo_keep_their_own_values():
    """D2: cada nome roteado devolve só as próprias ocorrências."""
    item = _item(_load())
    assert item_field_value(item, "note") == ["NOTA-DO-NOTE"]
    assert item_field_value(item, "memo") == ["NOTA-DO-MEMO"]
    assert _get_item_field_value(item, "memo") == ["NOTA-DO-MEMO"]


def test_repeated_quote_keeps_both_occurrences():
    """D6: as duas ocorrências chegam ao acessor (como num nome livre)."""
    r = _load()
    item = _item(r)
    assert item_field_value(item, "quote") == ["PRIMEIRO trecho", "SEGUNDO trecho"]
    assert field_occurrences(item, "quote", r.template) == ["PRIMEIRO trecho", "SEGUNDO trecho"]


def test_code_outside_item_is_a_list_per_occurrence():
    """D3: CODE em SOURCE também é lista de códigos na ocorrência."""
    r = _load()
    source = next(iter(r.linked_project.sources.values()))
    assert field_occurrences(source, "temas", r.template) == [["Autonomia", "Recursos"]]


def test_chain_occurrence_resolved_by_type():
    r = _load()
    (chain,) = field_occurrences(_item(r), "cadeia", r.template)
    assert chain.nodes == ["Alfa", "Beta"]


def test_hand_built_item_keeps_legacy_access():
    """Nó sem `entries` (construído à mão) responde pelos atributos de sempre."""
    item = ItemNode(bibref="@a", quote="Q", notes=["n1", "n2"], codes=["c"])
    assert item_field_value(item, "quote") == "Q"
    assert item_field_value(item, "memo") == ["n1", "n2"]
    assert item_field_value(item, "code") == ["c"]
    assert item_field_value(item, "livre") is None


def _write_project(tmp_path: Path) -> Path:
    (tmp_path / "template.synt").write_text(TEMPLATE, encoding="utf-8")
    (tmp_path / "references.bib").write_text(BIBLIOGRAPHY_BASIC, encoding="utf-8")
    (tmp_path / "annotations.syn").write_text(ANNOTATIONS, encoding="utf-8")
    synp = tmp_path / "project.synp"
    synp.write_text(
        PROJECT_CONTENT.replace('    INCLUDE ONTOLOGY "ontology.syno"\n', ""), encoding="utf-8"
    )
    return synp


def _snapshot(result):
    payload = build_json_payload(result.linked_project, result.template, result.bibliography)
    payload["export_metadata"].pop("timestamp", None)
    diagnostics = [
        e.to_cli_line() for e in result.validation_result.errors + result.validation_result.warnings
    ]
    return payload, diagnostics


def test_recompiling_in_the_same_process_is_idempotent(tmp_path):
    """D1': o parse_cache devolve os mesmos nós; compilar de novo não pode mudá-los."""
    invalidate_cache()
    synp = _write_project(tmp_path)
    first = SynesisCompiler(synp).compile()
    assert not first.has_errors(), first.get_diagnostics(verbose=False)
    expected = _snapshot(first)
    for _ in range(3):
        again = SynesisCompiler(synp).compile()
        assert _snapshot(again) == expected
    item = next(iter(again.linked_project.sources.values())).items[0]
    assert item.extra_fields["rotulos"] == ["X", "Y", "Z"]


# --- Fase 0c: CHAIN de ONTOLOGY acessível pelo nome, sem atribuir sentido ---

ONTOLOGY_TEMPLATE = """\
TEMPLATE t

ITEM FIELDS
    REQUIRED quote, code
END ITEM FIELDS

FIELD quote TYPE QUOTATION
    SCOPE ITEM
END FIELD

FIELD code TYPE CODE
    SCOPE ITEM
END FIELD

ONTOLOGY FIELDS
    REQUIRED definicao
    OPTIONAL is_a, pai
END ONTOLOGY FIELDS

FIELD definicao TYPE TEXT
    SCOPE ONTOLOGY
END FIELD

FIELD is_a TYPE CHAIN
    SCOPE ONTOLOGY
    ARITY >= 2
END FIELD

FIELD pai TYPE CHAIN
    SCOPE ONTOLOGY
    ARITY >= 2
END FIELD
"""

ONTOLOGY = """\
ONTOLOGY Recursos
    definicao: Meios da escola.
    pai: Gestao -> Recursos
END ONTOLOGY

ONTOLOGY Autonomia
    definicao: Decidir localmente.
    is_a: Gestao -> Autonomia
END ONTOLOGY

ONTOLOGY Gestao
    definicao: Conceito-pai.
END ONTOLOGY
"""


def _load_ontology():
    r = synesis.load(
        project_content=PROJECT_CONTENT,
        template_content=ONTOLOGY_TEMPLATE,
        annotation_contents={
            "annotations.syn": "SOURCE @smith2024\nEND SOURCE\n\n"
            "ITEM @smith2024\n    quote: Um trecho.\n    code: Recursos, Autonomia\nEND ITEM\n"
        },
        ontology_contents={"ontology.syno": ONTOLOGY},
        bibliography_content=BIBLIOGRAPHY_BASIC,
    )
    assert not r.has_errors(), r.get_diagnostics(verbose=False)
    return r


def test_ontology_chain_is_reachable_by_its_declared_name():
    """`is_a` ia para parent_chains e o acessor devolvia vazio; `pai` já funcionava."""
    r = _load_ontology()
    index = r.linked_project.ontology_index
    assert _get_ontology_field_value(index["autonomia"], "is_a").nodes == ["Gestao", "Autonomia"]
    assert _get_ontology_field_value(index["recursos"], "pai").nodes == ["Gestao", "Recursos"]
    assert _get_ontology_field_value(index["gestao"], "is_a") == ""


def test_ontology_chain_access_does_not_change_hierarchy():
    """Acesso genérico não é semântica: só o nome roteado continua formando hierarquia."""
    r = _load_ontology()
    assert r.linked_project.hierarchy == {"gestao": "autonomia"}


def test_ontology_chain_reaches_tabular_exports():
    r = _load_ontology()
    headers, rows = r.to_csv_tables()["ontologies"]
    # Com template, o conceito sai na coluna do campo CODE do ITEM (`code`).
    by_concept = {row["code"]: row for row in rows}
    assert by_concept["Autonomia"]["is_a"] == "Gestao -> Autonomia"
    assert by_concept["Recursos"]["pai"] == "Gestao -> Recursos"
