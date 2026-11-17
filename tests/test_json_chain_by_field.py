"""JSON: CHAIN lido pelo TIPO e no modo do PRÓPRIO campo — fase 0b.

O linker já coletava as cadeias de todo campo CHAIN, cada uma com o modo do seu
campo. O exportador JSON não: em `_build_item_data`, `_build_triples_index` e
`_build_chain_usage` ele usava um flag de relação GLOBAL e só `item.chains`
(os campos chamados `chain`/`chains`). Com um CHAIN qualificado e outro simples
no mesmo template, a cadeia simples `Gama -> Delta -> Eps` virava a tripla
`{from: Gama, relation: Delta, to: Eps}`; e as cadeias de nome livre ficavam
fora de `indices.triples` e de `code_frequency`.
"""

import synesis
from synesis.exporters.json_export import build_json_payload
from tests.conftest import BIBLIOGRAPHY_BASIC, PROJECT_CONTENT

TEMPLATE = """\
TEMPLATE t

ITEM FIELDS
    REQUIRED citation
    OPTIONAL chain, cadeia, nexo
END ITEM FIELDS

FIELD citation TYPE QUOTATION
    SCOPE ITEM
END FIELD

FIELD chain TYPE CHAIN
    SCOPE ITEM
    ARITY >= 2
    RELATIONS
        GERA: A produz B
    END RELATIONS
END FIELD

FIELD cadeia TYPE CHAIN
    SCOPE ITEM
    ARITY >= 2
END FIELD

FIELD nexo TYPE CHAIN
    SCOPE ITEM
    ARITY >= 2
    RELATIONS
        LEVA_A: A conduz a B
    END RELATIONS
END FIELD
"""

ANNOTATIONS = """\
SOURCE @smith2024
END SOURCE

ITEM @smith2024
    citation: Um trecho.
    chain: Alfa -> GERA -> Beta
    cadeia: Gama -> Delta -> Eps
    nexo: Zeta -> LEVA_A -> Eta
END ITEM
"""


def _payload():
    r = synesis.load(
        project_content=PROJECT_CONTENT,
        template_content=TEMPLATE,
        annotation_contents={"annotations.syn": ANNOTATIONS},
        bibliography_content=BIBLIOGRAPHY_BASIC,
    )
    assert not r.has_errors(), r.get_diagnostics(verbose=False)
    return r, build_json_payload(r.linked_project, r.template, r.bibliography)


def _triples(items):
    return [(t["from"], t["relation"], t["to"]) for t in items or []]


def test_simple_chain_is_not_read_as_qualified():
    _, payload = _payload()
    data = payload["corpus"][0]["data"]
    assert _triples(data["chain"]) == [("Alfa", "GERA", "Beta")]
    assert _triples(data["cadeia"]) == [("Gama", "IMPLICIT", "Delta"), ("Delta", "IMPLICIT", "Eps")]
    assert _triples(data["nexo"]) == [("Zeta", "LEVA_A", "Eta")]


def test_triples_index_covers_every_chain_field():
    r, payload = _payload()
    got = _triples(payload["indices"]["triples"])
    assert sorted(got) == sorted(r.linked_project.all_triples)
    assert len(got) == 4


def test_code_frequency_counts_concepts_of_every_chain_field():
    _, payload = _payload()
    freq = payload["indices"]["code_frequency"]
    # Regra (decisão do projeto, 2026-10-22): a frequência de um conceito usado
    # em CHAIN conta UMA VEZ POR OCORRÊNCIA NA TRIPLA, não por ITEM. O nó do
    # meio (`Delta`) está em duas triplas e conta 2. Vale para todo campo CHAIN.
    expected = {"alfa": 1, "beta": 1, "gama": 1, "delta": 2, "eps": 1, "zeta": 1, "eta": 1}
    assert {k: freq.get(k) for k in expected} == expected
    # A relação de uma cadeia qualificada não é conceito; a da simples não existe.
    assert "gera" not in freq and "leva_a" not in freq


# --- CSV e XLS: a mesma regra (antes: heuristica pela contagem de elementos) ---


def _rows_csv(r):
    headers, rows = r.to_csv_tables()["chains"]
    return sorted((row["from_code"], row["relation"], row["to_code"]) for row in rows)


def _rows_xls(r):
    from synesis.exporters.xls_export import build_xls_workbook

    wb = build_xls_workbook(r.linked_project, r.template, r.bibliography)
    ws = wb["chains"]
    rows = list(ws.iter_rows(min_row=2, values_only=True))
    return sorted((row[1], row[2], row[3]) for row in rows)


def test_tabular_chains_follow_each_field():
    r, _ = _payload()
    expected = sorted(r.linked_project.all_triples)
    assert _rows_csv(r) == expected
    assert _rows_xls(r) == expected


SIMPLE_ONLY = """\
TEMPLATE t

ITEM FIELDS
    REQUIRED citation, cadeia
END ITEM FIELDS

FIELD citation TYPE QUOTATION
    SCOPE ITEM
END FIELD

FIELD cadeia TYPE CHAIN
    SCOPE ITEM
    ARITY >= 2
END FIELD
"""


def test_simple_three_element_chain_is_not_read_as_qualified():
    """A heuristica antiga lia `A -> B -> C` (3 elementos, impar) como qualificada."""
    r = synesis.load(
        project_content=PROJECT_CONTENT,
        template_content=SIMPLE_ONLY,
        annotation_contents={
            "annotations.syn": "SOURCE @smith2024\nEND SOURCE\n\n"
            "ITEM @smith2024\n    citation: Um trecho.\n    cadeia: Gama -> Delta -> Eps\nEND ITEM\n"
        },
        bibliography_content=BIBLIOGRAPHY_BASIC,
    )
    assert not r.has_errors(), r.get_diagnostics(verbose=False)
    expected = [("Delta", "IMPLICIT", "Eps"), ("Gama", "IMPLICIT", "Delta")]
    assert _rows_csv(r) == expected
    assert _rows_xls(r) == expected
