"""
test_dataset_resolution.py - Fase 3: resolução + validador + export de ON DATASET

Cobre o "trio indivisível" (§11):
  - synesis.load resolve valores ON DATASET a partir do dataset_index;
  - campo REQUIRED ON DATASET sem valor emite MissingDatasetValue (E085),
    NÃO MissingRequiredField (E020) espúrio;
  - o JSON exportado tem uma seção `dataset` separada de `bibliography`.
"""

from __future__ import annotations

import synesis
from synesis.ast.results import MissingDatasetValue, MissingRequiredField
from synesis.exporters.json_export import build_json_payload

_TEMPLATE = """
TEMPLATE demo

SOURCE FIELDS
    REQUIRED researcher_id ON DATASET "meta.id"
    OPTIONAL grant ON DATASET "meta.grant"
END SOURCE FIELDS

ITEM FIELDS
    REQUIRED quote
END ITEM FIELDS

FIELD researcher_id TYPE TEXT
    SCOPE SOURCE
    IDENTIFIES researcher
END FIELD

FIELD grant TYPE TEXT
    SCOPE SOURCE
END FIELD

FIELD quote TYPE QUOTATION
    SCOPE ITEM
END FIELD
"""

_PROJECT = """
PROJECT demo
TEMPLATE "demo.synt"
INCLUDE DATASET "records/*.toml"
END PROJECT
"""

_ANNOTATION = """
SOURCE @rec-1
END SOURCE
ITEM @rec-1
    quote: um trecho literal
END ITEM
"""


def _load(dataset_index):
    return synesis.load(
        project_content=_PROJECT,
        template_content=_TEMPLATE,
        annotation_contents={"a.syn": _ANNOTATION},
        dataset_index=dataset_index,
        project_filename="demo.synp",
        template_filename="demo.synt",
    )


def test_on_dataset_value_resolves_no_spurious_error():
    """Valor presente no dataset: compila sem MissingRequiredField nem MissingDatasetValue."""
    ds = {"rec-1": {"meta": {"id": "rec-1", "grant": "CNPq-123"}, "_source_file": "r1.toml"}}
    result = _load(ds)
    errs = result.validation_result.errors
    assert not any(isinstance(e, MissingRequiredField) and e.field_name == "researcher_id"
                   for e in errs), "MissingRequiredField espúrio para campo ON DATASET"
    assert not any(isinstance(e, MissingDatasetValue) for e in errs)


def test_missing_dataset_value_emits_e085_not_e020():
    """Campo REQUIRED ON DATASET sem valor: E085, nunca E020 espúrio."""
    ds = {"rec-1": {"meta": {"grant": "x"}, "_source_file": "r1.toml"}}  # sem meta.id
    result = _load(ds)
    errs = result.validation_result.errors
    e085 = [e for e in errs if isinstance(e, MissingDatasetValue)]
    assert any(e.field_name == "researcher_id" for e in e085), (
        "esperado MissingDatasetValue para researcher_id ausente"
    )
    # cobertura explícita do código de erro (catálogo E085 = SYNESIS_E085)
    assert e085[0].CODE == "SYNESIS_E085"
    assert not any(
        isinstance(e, MissingRequiredField) and e.field_name == "researcher_id"
        for e in errs
    ), "MissingRequiredField (E020) espúrio não deve ocorrer para ON DATASET"


def test_json_export_has_separate_dataset_section():
    ds = {"rec-1": {"meta": {"id": "rec-1", "grant": "CNPq-123"}, "_source_file": "r1.toml"}}
    result = _load(ds)
    payload = build_json_payload(
        result.linked_project, result.template, result.bibliography, dataset_index=ds
    )
    assert "dataset" in payload
    assert "bibliography" in payload
    # o valor do dataset aparece na seção dataset, resolvido pelo caminho
    entry = payload["dataset"].get("rec-1") or payload["dataset"].get("@rec-1")
    assert entry is not None
    assert entry.get("researcher_id") == "rec-1"
    assert entry.get("grant") == "CNPq-123"


def test_optional_on_dataset_absent_is_not_error():
    """Campo OPTIONAL ON DATASET sem valor no TOML NÃO gera E085 (regressão Fase 6).

    Bug: validate_dataset_values sinalizava qualquer campo dataset ausente, mesmo
    OPTIONAL — o E085 espúrio empurrava o registro ao loop de correção, que
    alucinava o campo. Só REQUIRED deve disparar E085.
    """
    # template do módulo: researcher_id REQUIRED, grant OPTIONAL (ambos ON DATASET)
    ds = {"rec-1": {"meta": {"id": "rec-1"}, "_source_file": "r1.toml"}}  # grant ausente
    result = _load(ds)
    errs = result.validation_result.errors
    assert not any(
        isinstance(e, MissingDatasetValue) and e.field_name == "grant" for e in errs
    ), "campo OPTIONAL grant ausente não deve gerar MissingDatasetValue"
    # e researcher_id (REQUIRED) presente também não erra
    assert not any(isinstance(e, MissingDatasetValue) for e in errs)


def test_no_dataset_is_noop():
    """Projeto sem dataset_index: seção dataset vazia, sem erro."""
    result = synesis.load(
        project_content='PROJECT demo\nTEMPLATE "demo.synt"\nEND PROJECT\n',
        template_content=_TEMPLATE.replace('ON DATASET "meta.id"', "").replace(
            'ON DATASET "meta.grant"', ""
        ),
        annotation_contents={"a.syn": _ANNOTATION},
        project_filename="demo.synp",
        template_filename="demo.synt",
    )
    payload = build_json_payload(result.linked_project, result.template, result.bibliography)
    assert payload["dataset"] == {}
