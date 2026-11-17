"""Projeto de teste (C6): case-studies/Exemplo_Tipos_Relacionais.

As respostas esperadas as QUESTIONS e o perfil estrutural registrados no
LEIA-ME do exemplo. Pulado quando o repositorio case-studies nao esta ao lado
(CI). Aceite da etapa A2c (Spec ROLE/EXPORT v7, §14).
"""

from pathlib import Path

import pytest

from synesis.compiler import SynesisCompiler
from synesis.exporters.json_export import build_json_payload
from synesis.semantic.hierarchy import structural_profile

SYNP = Path(__file__).resolve().parents[2] / "case-studies" / "Exemplo_Tipos_Relacionais" / "fraudes.synp"
pytestmark = pytest.mark.skipif(not SYNP.exists(), reason="case-studies ausente")


@pytest.fixture(scope="module")
def compiled():
    result = SynesisCompiler(SYNP).compile()
    data = build_json_payload(result.linked_project, result.template, result.bibliography, result.dataset)
    return result, data


def test_compiles_without_errors(compiled):
    result, _ = compiled
    assert not result.has_errors(), result.get_diagnostics()


def test_q1_phishing_subtree(compiled):
    _, data = compiled
    assert data["indices"]["subtree"]["phishing"] == {
        "children": 6, "descendants": 8, "items": 2, "items_subtree": 4, "grounded": True,
    }


def test_q2_ungrounded_concepts(compiled):
    _, data = compiled
    ungrounded = sorted(k for k, v in data["indices"]["subtree"].items() if not v["grounded"])
    assert ungrounded == ["campanha_falsa_entrega_2025", "phishing_em_massa", "phishing_por_e-mail", "spear_phishing"]


def test_q3_kinds_of_phishing(compiled):
    _, data = compiled
    kinds = sorted(c for c, p in data["indices"]["relations"]["KIND"] if p == "phishing")
    assert kinds == ["phishing_em_massa", "phishing_por_e-mail", "smishing", "spear_phishing", "vishing"]
    assert data["ontology"]["smishing"]["usado_por"] == ["phishing por SMS", "SMS phishing"]


def test_q4_parts(compiled):
    _, data = compiled
    assert ["link_malicioso", "mensagem_de_phishing"] in data["indices"]["relations"]["PART"]


def test_profile_matches_the_readme(compiled):
    result, _ = compiled
    lines = structural_profile(result.linked_project, result.template, result.validation_result)
    for expected in ("Concepts: 19", "With KIND parent: 7", "With PART parent: 2", "With INSTANCE parent: 1",
                     "Top concepts: 9", "Ungrounded: 4",
                     "Organizing model: Terminological: With synonyms (1 code without concept)  |  "
                     "Conceptual: Multi-relation taxonomy"):
        assert expected in lines


def test_skos_of_the_test_project(compiled):
    from synesis.exporters.skos_export import build_skos

    result, _ = compiled
    export = next(e for e in result.linked_project.project.exports if e.format == "SKOS")
    first = build_skos(result.linked_project, result.template, export)
    second = build_skos(result.linked_project, result.template, export)
    assert not first.errors
    assert first.text == second.text
    # 243 da etapa 3 + o rótulo oculto `voice phishing` de vishing (etapa U)
    # + prefLabel do esquema principal + topo dos 6 valores de `natureza`
    # nas duas direções (validação VocBench de 2026-11-17): 244 + 1 + 12
    assert first.triple_count == 257
    assert first.report["check"][0].startswith("SKOS check: integrity OK")
    assert "no notice" in first.report["check"][1]
    assert first.report["aliases"] == 1 and first.report["alias_labels"] == 1
    assert first.report["related"] == 2
    assert first.report["profile"] == "Terminological: Thesaurus  |  Conceptual: Multi-relation taxonomy"


def test_profile_lists_each_skos_artifact(compiled):
    """O perfil do .syno e o do artefato diferem: MAP RELATIONS acrescenta RELATED."""
    from synesis.cli import _artifact_profiles

    result, _ = compiled
    assert _artifact_profiles(result.linked_project, result.template) == [
        "EXPORT SKOS: Terminological: Thesaurus  |  Conceptual: Multi-relation taxonomy"
    ]
