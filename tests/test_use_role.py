"""
test_use_role.py - Etapa U: ROLE USE (Spec_USE_Etapa_U.md)

Preterido -> alvo: validação (E145–E149), projeção resolvida no JSON,
hierarquia e fundamentação resolvidas, SKOS (rótulo do alvo, obsoleto com
isReplacedBy quando o IRI foi publicado, registro), OKF sem página do
preterido.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import synesis
from synesis.exporters.json_export import build_json_payload
from synesis.exporters.skos_export import build_skos, export_skos, read_registry

rdflib = pytest.importorskip("rdflib")
from rdflib.namespace import OWL, SKOS  # noqa: E402

BIB = "@article{a1, title={T}, author={A}, year={2024}}\n@article{a2, title={U}, author={B}, year={2024}}\n"

TEMPLATE = """\
ITEM FIELDS
    REQUIRED trecho
    OPTIONAL codigo, cadeia
END ITEM FIELDS

FIELD trecho TYPE QUOTATION
    SCOPE ITEM
END FIELD

FIELD codigo TYPE CODE
    SCOPE ITEM
END FIELD

FIELD cadeia TYPE CHAIN
    SCOPE ITEM
    RELATIONS
        USA: usa
        TIPO_DE: tipo de
    END RELATIONS
END FIELD

ONTOLOGY FIELDS
    REQUIRED definicao
    OPTIONAL tipo_de, usado_por, usar
END ONTOLOGY FIELDS

FIELD definicao TYPE TEXT
    SCOPE ONTOLOGY
    ROLE NOTE DEFINITION
END FIELD

FIELD tipo_de TYPE CODE
    SCOPE ONTOLOGY
    ROLE HIERARCHY KIND
END FIELD

FIELD usado_por TYPE TEXT
    SCOPE ONTOLOGY
    ROLE LABEL ALTERNATIVE
END FIELD

FIELD usar TYPE CODE
    SCOPE ONTOLOGY
    ROLE USE
END FIELD
"""

# Spec §2: um ITEM cita o preterido em CODE e o alvo na CHAIN; outro ITEM da
# mesma fonte cita só o preterido.
ANNOTATIONS = """\
SOURCE @a1
END SOURCE

ITEM @a1
    trecho: x
    codigo: pig-butchering
    cadeia: pig_butchering -> USA -> cripto
END ITEM

ITEM @a1
    trecho: y
    codigo: pig-butchering
END ITEM

SOURCE @a2
END SOURCE

ITEM @a2
    trecho: z
    cadeia: pig-butchering -> TIPO_DE -> golpe
END ITEM

ITEM @a2
    trecho: w
    cadeia: pig_butchering -> TIPO_DE -> golpe
END ITEM
"""

ONTOLOGY = """\
ONTOLOGY pig_butchering
    definicao: Golpe de investimento de longo prazo.
    tipo_de: golpe
END ONTOLOGY

ONTOLOGY pig-butchering
    usar: pig_butchering
END ONTOLOGY

ONTOLOGY cripto
    definicao: Criptoativo.
END ONTOLOGY

ONTOLOGY golpe
    definicao: Fraude.
END ONTOLOGY
"""

SKOS_BLOCK = """\
EXPORT SKOS
    OUTPUT "saida/t.ttl"
    NAMESPACE "https://example.org/id/t/"
    LANGUAGE pt-BR
{extra}    MAP RELATIONS TIPO_DE TO HIERARCHY KIND
END EXPORT
"""

N = "https://example.org/id/t/"


def C(name: str):
    return rdflib.URIRef(N + "concept/" + name)


def load(ontology: str = ONTOLOGY, extra: str = "", annotations: str = ANNOTATIONS):
    project = (
        'PROJECT t\nTEMPLATE "t.synt"\nINCLUDE BIBLIOGRAPHY "r.bib"\n'
        'INCLUDE ANNOTATIONS "a.syn"\nINCLUDE ONTOLOGY "o.syno"\n\n'
        + SKOS_BLOCK.format(extra=extra) + "END PROJECT\n"
    )
    return synesis.load(
        project_content=project, template_content=TEMPLATE,
        annotation_contents={"a.syn": annotations}, ontology_contents={"o.syno": ontology},
        bibliography_content=BIB,
    )


def codes(result) -> list:
    vr = result.validation_result
    return [e.CODE for e in vr.errors + vr.warnings]


def skos(result, published=None):
    export = result.linked_project.project.exports[0]
    return build_skos(result.linked_project, result.template, export, published)


def graph(text: str):
    g = rdflib.Graph()
    g.parse(data=text, format="turtle")
    return g


# --------------------------------------------------------------- validação

def test_alias_compiles_without_required_fields_and_maps_identity():
    result = load()
    assert not result.validation_result.has_errors(), result.get_diagnostics()
    assert result.linked_project.aliases == {"pig-butchering": "pig_butchering"}


def test_e145_use_self():
    ontology = ONTOLOGY.replace("    usar: pig_butchering\n", "    usar: pig-butchering\n")
    assert "SYNESIS_E145" in codes(load(ontology))


def test_e146_use_chain():
    ontology = ONTOLOGY + "\nONTOLOGY pig_butcher\n    usar: pig-butchering\nEND ONTOLOGY\n"
    annotations = ANNOTATIONS
    assert "SYNESIS_E146" in codes(load(ontology, annotations=annotations))


def test_e147_use_with_two_targets():
    ontology = ONTOLOGY.replace("    usar: pig_butchering\n", "    usar: pig_butchering, golpe\n")
    assert "SYNESIS_E147" in codes(load(ontology))


def test_e148_alias_with_content():
    ontology = ONTOLOGY.replace("    usar: pig_butchering\n", "    usar: pig_butchering\n    definicao: Outra.\n")
    assert "SYNESIS_E148" in codes(load(ontology))


def test_e149_hierarchy_collapses_after_resolution():
    # golpe tipo_de pig-butchering; pig-butchering usa pig_butchering; pig_butchering tipo_de golpe
    ontology = ONTOLOGY.replace("    definicao: Fraude.\n", "    definicao: Fraude.\n    tipo_de: pig-butchering\n")
    result = load(ontology)
    assert "SYNESIS_E118" in codes(result) or "SYNESIS_E119" in codes(result)  # ciclo resolvido
    ontology = ONTOLOGY.replace("    tipo_de: golpe\n", "    tipo_de: pig-butchering\n")
    assert "SYNESIS_E149" in codes(load(ontology))


def test_target_without_block_is_undeclared():
    ontology = ONTOLOGY.replace("    usar: pig_butchering\n", "    usar: inexistente\n")
    assert "SYNESIS_E101" in codes(load(ontology))


# ----------------------------------------------------- projeção resolvida

def test_json_resolved_projection_keeps_written_form():
    result = load()
    payload = build_json_payload(result.linked_project, result.template, result.bibliography, None)
    onto = payload["ontology"]
    assert onto["pig-butchering"]["usar"] == ["pig_butchering"]
    assert "frequency" not in onto["pig-butchering"]
    # união: 4 ITEMs citam o preterido ou o alvo; o primeiro cita os dois e conta uma vez
    assert onto["pig_butchering"]["frequency"] == 4
    assert onto["pig_butchering"]["source_count"] == 2
    assert payload["indices"]["aliases"] == {"pig-butchering": "pig_butchering"}
    assert "pig-butchering" not in payload["indices"]["code_frequency"]
    # forma escrita: o corpus e as triplas continuam com o nome preterido
    assert any(t["from"] == "pig-butchering" for t in payload["indices"]["triples"])
    assert "pig-butchering" not in payload["indices"]["subtree"]
    assert payload["indices"]["subtree"]["golpe"]["items_subtree"] >= 3


def test_no_alias_no_new_json_keys():
    ontology = ONTOLOGY.replace("ONTOLOGY pig-butchering\n    usar: pig_butchering\nEND ONTOLOGY\n",
                                "ONTOLOGY pig-butchering\n    definicao: Grafia antiga.\nEND ONTOLOGY\n")
    result = load(ontology)
    payload = build_json_payload(result.linked_project, result.template, result.bibliography, None)
    assert "aliases" not in payload["indices"]


def test_alias_mentions_ground_the_target():
    ontology = ONTOLOGY + "\nONTOLOGY so_alias\n    definicao: x\nEND ONTOLOGY\n"
    result = load(ontology)
    ungrounded = [w for w in result.validation_result.warnings if w.CODE == "SYNESIS_E120"]
    assert [w.concept for w in ungrounded] == ["so_alias"]  # o preterido nunca é avaliado


# ------------------------------------------------------------------ SKOS

def test_skos_alias_becomes_hidden_label_of_target():
    out = skos(load())
    assert not out.errors, out.errors
    g = graph(out.text)
    assert (C("pig-butchering"), None, None) not in g
    assert (C("pig_butchering"), SKOS.hiddenLabel, rdflib.Literal("pig-butchering", lang="pt-BR")) in g
    # par mapeado resolvido: pig-butchering -> TIPO_DE -> golpe soma ao par do alvo
    assert (C("pig_butchering"), SKOS.broader, C("golpe")) in g
    assert out.report["aliases"] == 1 and out.report["deprecated"] == 0


def test_skos_alias_label_alternative():
    out = skos(load(extra="    ALIAS_LABEL ALTERNATIVE\n"))
    g = graph(out.text)
    assert (C("pig_butchering"), SKOS.altLabel, rdflib.Literal("pig-butchering", lang="pt-BR")) in g


def test_e150_unknown_alias_label():
    assert "SYNESIS_E150" in codes(load(extra="    ALIAS_LABEL OCULTO\n"))


def test_e151_alias_label_collision():
    ontology = ONTOLOGY.replace("    tipo_de: golpe\n", "    tipo_de: golpe\n    usado_por: pig-butchering\n")
    out = skos(load(ontology))
    assert "SYNESIS_E151" in [w.CODE for w in out.warnings]


def test_published_alias_is_deprecated_with_replacement():
    out = skos(load(), published={str(C("pig-butchering"))})
    g = graph(out.text)
    assert (C("pig-butchering"), OWL.deprecated, rdflib.Literal(True)) in g
    assert (C("pig-butchering"), rdflib.URIRef("http://purl.org/dc/terms/isReplacedBy"), C("pig_butchering")) in g
    assert (C("pig-butchering"), SKOS.broader, None) not in g
    assert out.report["deprecated"] == 1


def test_e153_published_iri_without_block():
    out = skos(load(), published={str(C("sumiu"))})
    assert "SYNESIS_E153" in [w.CODE for w in out.warnings]


def test_collapsed_pair_is_reported():
    annotations = ANNOTATIONS + "\nITEM @a2\n    trecho: v\n    cadeia: pig-butchering -> TIPO_DE -> pig_butchering\nEND ITEM\n"
    out = skos(load(annotations=annotations))
    tipo = next(m for m in out.report["maps"] if m["relation"] == "TIPO_DE")
    assert any("collapses after USE" in k for k in tipo["dropped"])


def test_registry_publish_and_e152(tmp_path: Path):
    result = load()
    export = result.linked_project.project.exports[0]
    registry = tmp_path / "iris.txt"
    out = export_skos(result.linked_project, result.template, export, tmp_path / "t.ttl",
                      registry=registry, publish=True)
    published, ok = read_registry(registry)
    assert ok and str(C("pig_butchering")) in published and str(C("pig-butchering")) not in published
    assert out.report["registered"] == len(published)
    bad = export_skos(result.linked_project, result.template, export, tmp_path / "t2.ttl",
                      registry=tmp_path)  # pasta: inutilizável
    assert "SYNESIS_E152" in [w.CODE for w in bad.warnings]


def test_publish_refuses_when_a_registered_iri_would_vanish(tmp_path: Path):
    """R5 (avaliação de 2026-11-17): publicar, apagar o bloco, publicar de novo."""
    result = load()
    export = result.linked_project.project.exports[0]
    registry = tmp_path / "iris.txt"
    gone = str(C("sumiu"))
    registry.write_text(gone + "\n", encoding="utf-8")
    before = registry.read_text(encoding="utf-8")

    published = export_skos(result.linked_project, result.template, export, tmp_path / "pub.ttl",
                            registry=registry, publish=True)
    assert "SYNESIS_E153" in [e.CODE for e in published.errors]
    assert published.text is None
    assert not (tmp_path / "pub.ttl").exists(), "the artifact must not be replaced"
    assert registry.read_text(encoding="utf-8") == before, "the registry must not change"

    # Export local (sem --publish): continua tolerante — aviso, arquivo gravado.
    local = export_skos(result.linked_project, result.template, export, tmp_path / "local.ttl",
                        registry=registry)
    assert "SYNESIS_E153" in [w.CODE for w in local.warnings] and not local.errors
    assert (tmp_path / "local.ttl").exists()


# ------------------------------------------------------------------- OKF

def test_okf_has_no_page_for_the_alias(tmp_path: Path):
    from synesis.exporters.okf_export import export_okf

    result = load()
    out = tmp_path / "okf"
    export_okf(result.linked_project, out, result.template, result.bibliography, None)
    pages = sorted(p.stem for p in (out / "concepts").glob("*.md") if p.stem != "index")
    # três conceitos que valem; o slug do alvo pig_butchering é "pig-butchering"
    assert pages == ["cripto", "golpe", "pig-butchering"]
    target = (out / "concepts" / "pig-butchering.md").read_text(encoding="utf-8")
    assert "concept: pig_butchering" in target or "pig_butchering" in target
    assert "aliases" in target


# ------------------------------------- publicação (revisão de 2026-11-17)

def test_publish_with_unusable_registry_writes_nothing(tmp_path: Path):
    """1.1: registro ilegível tornaria a conferência vazia e silenciosa."""
    result = load()
    export = result.linked_project.project.exports[0]
    out = export_skos(result.linked_project, result.template, export, tmp_path / "p.ttl",
                      registry=tmp_path, publish=True)  # pasta: inutilizável
    assert [e.CODE for e in out.errors] == ["SYNESIS_E152"]
    assert not (tmp_path / "p.ttl").exists()
    local = export_skos(result.linked_project, result.template, export, tmp_path / "l.ttl",
                        registry=tmp_path)  # export local continua tolerante
    assert "SYNESIS_E152" in [w.CODE for w in local.warnings] and (tmp_path / "l.ttl").exists()


@pytest.mark.parametrize("publish", [False, True])
def test_output_equal_to_registry_is_refused_and_keeps_the_file(tmp_path: Path, publish: bool):
    """1.3: mesmo arquivo, inclusive por grafia equivalente; o conteúdo anterior fica."""
    result = load()
    export = result.linked_project.project.exports[0]
    target = tmp_path / "same.ttl"
    target.write_text("conteudo anterior\n", encoding="utf-8")
    alias = tmp_path / "sub" / ".." / "same.ttl"
    (tmp_path / "sub").mkdir()
    out = export_skos(result.linked_project, result.template, export, target,
                      registry=alias, publish=publish)
    assert [e.CODE for e in out.errors] == ["SYNESIS_E157"] and out.text is None
    assert target.read_text(encoding="utf-8") == "conteudo anterior\n"


def test_other_namespace_in_registry_is_only_a_warning(tmp_path: Path):
    """1.2: o NAMESPACE é do pesquisador — mudar não bloqueia; o aviso diz o que ficou de fora."""
    result = load()
    export = result.linked_project.project.exports[0]
    registry = tmp_path / "iris.txt"
    registry.write_text("https://antigo.example.org/concept/phishing\n", encoding="utf-8")
    out = export_skos(result.linked_project, result.template, export, tmp_path / "n.ttl",
                      registry=registry, publish=True)
    assert not out.errors and (tmp_path / "n.ttl").exists()
    warning = next(w for w in out.warnings if w.CODE == "SYNESIS_E156")
    assert warning.count == 1 and "antigo.example.org" in warning.examples[0]
    assert "antigo.example.org" in registry.read_text(encoding="utf-8"), "the registry only grows"
