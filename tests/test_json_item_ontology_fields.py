"""JSON: campos ONTOLOGY repassados ao `data` do ITEM so quando ha valor.

O exportador repete, em cada trecho, o valor de cada campo SCOPE ONTOLOGY dos
conceitos que o trecho menciona. Campo que nenhum desses conceitos preenche
saia como `null` (um codigo) ou lista de `null` (varios) em todos os trechos —
no Fraudes Digitais, `tipo_de`, `parte_de`, `usado_por` e `nome_antigo` em
1.182 trechos (teste real de 2026-11-17). Agora o campo so entra quando ha
algum valor; havendo, a lista fica inteira, alinhada aos codigos do trecho.
"""

import synesis
from synesis.exporters.json_export import _has_any_value, build_json_payload
from tests.conftest import BIBLIOGRAPHY_BASIC, PROJECT_CONTENT

TEMPLATE = """\
TEMPLATE t

ITEM FIELDS
    REQUIRED citation, code
END ITEM FIELDS

ONTOLOGY FIELDS
    REQUIRED definition
    OPTIONAL aspect, old_name
END ONTOLOGY FIELDS

FIELD citation TYPE QUOTATION
    SCOPE ITEM
END FIELD

FIELD code TYPE CODE
    SCOPE ITEM
END FIELD

FIELD definition TYPE TEXT
    SCOPE ONTOLOGY
END FIELD

FIELD aspect TYPE TEXT
    SCOPE ONTOLOGY
END FIELD

FIELD old_name TYPE TEXT
    SCOPE ONTOLOGY
END FIELD
"""

ONTOLOGY = """\
ONTOLOGY Alfa
    definition: Primeiro conceito.
    aspect: Social
END ONTOLOGY

ONTOLOGY Beta
    definition: Segundo conceito.
END ONTOLOGY
"""

ANNOTATIONS = """\
SOURCE @smith2024
END SOURCE

ITEM @smith2024
    citation: Trecho com dois codigos.
    code: Alfa, Beta
END ITEM

ITEM @smith2024
    citation: Trecho so com Beta.
    code: Beta
END ITEM
"""


def _corpus():
    r = synesis.load(
        project_content=PROJECT_CONTENT,
        template_content=TEMPLATE,
        annotation_contents={"annotations.syn": ANNOTATIONS},
        ontology_contents={"ontology.syno": ONTOLOGY},
        bibliography_content=BIBLIOGRAPHY_BASIC,
    )
    assert not r.has_errors(), r.get_diagnostics(verbose=False)
    payload = build_json_payload(r.linked_project, r.template, r.bibliography)
    return {it["data"]["citation"]: it["data"] for it in payload["corpus"]}


def test_field_no_concept_fills_is_left_out():
    for data in _corpus().values():
        assert "old_name" not in data


def test_partial_values_keep_the_list_aligned_with_codes():
    data = _corpus()["Trecho com dois codigos."]
    assert data["aspect"] == ["Social", None]
    assert data["definition"] == ["Primeiro conceito.", "Segundo conceito."]


def test_single_code_without_value_is_left_out():
    data = _corpus()["Trecho so com Beta."]
    assert "aspect" not in data
    assert data["definition"] == "Segundo conceito."


def test_consistent_with_ontology_section():
    r = synesis.load(
        project_content=PROJECT_CONTENT,
        template_content=TEMPLATE,
        annotation_contents={"annotations.syn": ANNOTATIONS},
        ontology_contents={"ontology.syno": ONTOLOGY},
        bibliography_content=BIBLIOGRAPHY_BASIC,
    )
    onto = build_json_payload(r.linked_project, r.template, r.bibliography)["ontology"]
    # A secao ontology ja omitia o campo sem valor; o ITEM agora faz o mesmo.
    assert "old_name" not in onto["Beta"] and "aspect" not in onto["Beta"]
    assert onto["Alfa"]["aspect"] == "Social"


def test_has_any_value():
    assert not _has_any_value(None)
    assert not _has_any_value([None, None])
    assert not _has_any_value(["", None])
    assert _has_any_value([None, "x"])
    assert _has_any_value(0)
    assert _has_any_value(False)
