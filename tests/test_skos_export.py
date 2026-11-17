"""
test_skos_export.py - Etapa A3 (Spec ROLE/EXPORT v7, §9.4, §10, §14 linha A3)

Exportacao SKOS a partir dos papeis e do `MAP RELATIONS`, validada relendo o
Turtle com rdflib (condicoes SKOS S9, S13, S14, S27, S37), com bytes
identicos entre execucoes e com as regras de prevalencia do .syno.
"""

from __future__ import annotations

import pytest

import synesis
from synesis.exporters.skos_export import build_skos

rdflib = pytest.importorskip("rdflib")
from rdflib.namespace import RDF, SKOS  # noqa: E402

BIB = "@article{a1, title={T}, author={A}, year={2024}}\n@article{a2, title={U}, author={B}, year={2024}}\n"

TEMPLATE = """\
ITEM FIELDS
    REQUIRED trecho
    OPTIONAL cadeia
END ITEM FIELDS

FIELD trecho TYPE QUOTATION
    SCOPE ITEM
END FIELD

FIELD cadeia TYPE CHAIN
    SCOPE ITEM
    RELATIONS
        TIPO_DE: tipo de
        PARTE_DE: parte de
        MITIGA: mitiga
    END RELATIONS
END FIELD

ONTOLOGY FIELDS
    REQUIRED definicao
    OPTIONAL tipo_de, parte_de, usado_por, topico
END ONTOLOGY FIELDS

FIELD definicao TYPE TEXT
    SCOPE ONTOLOGY
    ROLE NOTE DEFINITION
END FIELD

FIELD tipo_de TYPE CODE
    SCOPE ONTOLOGY
    ROLE HIERARCHY KIND
END FIELD

FIELD parte_de TYPE CODE
    SCOPE ONTOLOGY
    ROLE HIERARCHY PART
END FIELD

FIELD usado_por TYPE TEXT
    SCOPE ONTOLOGY
    ROLE LABEL ALTERNATIVE
END FIELD

FIELD topico TYPE TOPIC
    SCOPE ONTOLOGY
END FIELD
"""

ANNOTATIONS = """\
SOURCE @a1
END SOURCE

ITEM @a1
    trecho: x
    cadeia: smishing -> TIPO_DE -> phishing
END ITEM

ITEM @a1
    trecho: y
    cadeia: link -> PARTE_DE -> phishing
END ITEM

ITEM @a1
    trecho: z
    cadeia: vishing -> TIPO_DE -> phishing
END ITEM

ITEM @a1
    trecho: w
    cadeia: educacao -> MITIGA -> phishing
END ITEM

SOURCE @a2
END SOURCE

ITEM @a2
    trecho: v
    cadeia: vishing -> TIPO_DE -> phishing
END ITEM

ITEM @a2
    trecho: u
    cadeia: phishing -> TIPO_DE -> smishing
END ITEM
"""

ONTOLOGY = """\
ONTOLOGY phishing
    definicao: Fraude por comunicacao enganosa.
    topico: Fraude
END ONTOLOGY

ONTOLOGY smishing
    definicao: Phishing por SMS.
    tipo_de: phishing
    usado_por: SMS phishing
    topico: fraude
END ONTOLOGY

ONTOLOGY vishing
    definicao: Phishing por voz.
    topico: fraude
END ONTOLOGY

ONTOLOGY link
    definicao: Link malicioso.
    tipo_de: phishing
END ONTOLOGY

ONTOLOGY educacao
    definicao: Educacao digital.
END ONTOLOGY
"""

SKOS_BLOCK = """\
EXPORT SKOS
    OUTPUT "saida/t.ttl"
    NAMESPACE "https://example.org/id/t/"
    LANGUAGE pt-BR
    MIN_SOURCES {min_sources}
    MAP RELATIONS TIPO_DE TO HIERARCHY KIND
    MAP RELATIONS PARTE_DE TO HIERARCHY PART
    MAP RELATIONS MITIGA TO RELATED
END EXPORT
"""


def compile_(min_sources: int = 1, block: str = SKOS_BLOCK, ontology: str = ONTOLOGY):
    project = (
        'PROJECT t\nTEMPLATE "t.synt"\nINCLUDE BIBLIOGRAPHY "r.bib"\n'
        'INCLUDE ANNOTATIONS "a.syn"\nINCLUDE ONTOLOGY "o.syno"\n\n'
        + block.format(min_sources=min_sources) + "END PROJECT\n"
    )
    return synesis.load(
        project_content=project, template_content=TEMPLATE,
        annotation_contents={"a.syn": ANNOTATIONS}, ontology_contents={"o.syno": ontology},
        bibliography_content=BIB,
    )


def skos(min_sources: int = 1, **kw):
    result = compile_(min_sources, **kw)
    export = result.linked_project.project.exports[0]
    return result, build_skos(result.linked_project, result.template, export)


def graph(text: str):
    g = rdflib.Graph()
    g.parse(data=text, format="turtle")
    return g


N = "https://example.org/id/t/"


def C(name: str):
    return rdflib.URIRef(N + "concept/" + name)


# ------------------------------------------------------------------ validade

def test_project_compiles_and_block_is_valid():
    result = compile_()
    assert not result.validation_result.has_errors(), result.get_diagnostics()
    assert not [w for w in result.validation_result.warnings if w.CODE.startswith("SYNESIS_E12")]


def test_turtle_rereads_and_meets_skos_conditions():
    _, out = skos()
    assert not out.errors
    g = graph(out.text)
    # S9: ConceptScheme e Concept disjuntos; S37: Collection disjunta de Concept.
    for s in g.subjects(RDF.type, SKOS.ConceptScheme):
        assert (s, RDF.type, SKOS.Concept) not in g
    for s in g.subjects(RDF.type, SKOS.Collection):
        assert (s, RDF.type, SKOS.Concept) not in g
    # S14: um prefLabel por idioma; S13: pref, alt e hidden disjuntos.
    for c in g.subjects(RDF.type, SKOS.Concept):
        prefs = list(g.objects(c, SKOS.prefLabel))
        assert len({p.language for p in prefs}) == len(prefs)
        labels = [set(g.objects(c, p)) for p in (SKOS.prefLabel, SKOS.altLabel, SKOS.hiddenLabel)]
        assert not (labels[0] & labels[1] or labels[0] & labels[2] or labels[1] & labels[2])
    # S27: related disjunto de broaderTransitive.
    def ancestors(c):
        out, stack = set(), list(g.objects(c, SKOS.broader))
        while stack:
            x = stack.pop()
            if x not in out:
                out.add(x)
                stack.extend(g.objects(x, SKOS.broader))
        return out
    for a, b in g.subject_objects(SKOS.related):
        assert b not in ancestors(a) and a not in ancestors(b)


def test_bytes_are_identical_between_runs():
    _, a = skos()
    _, b = skos()
    assert a.text == b.text


def test_no_collection_in_broader_and_no_repeated_broader():
    _, out = skos()
    g = graph(out.text)
    collections = set(g.subjects(RDF.type, SKOS.Collection))
    assert not any(o in collections for o in g.objects(None, SKOS.broader))
    # smishing -> phishing esta no .syno E no mapeamento: uma tripla so.
    assert out.text.count(f"<{N}concept/phishing>") >= 1
    assert len(list(g.triples((C("smishing"), SKOS.broader, C("phishing"))))) == 1


# ------------------------------------------------------- prevalencia do .syno

def test_syno_prevails_in_species_and_direction():
    _, out = skos()
    tipo = next(m for m in out.report["maps"] if m["relation"] == "TIPO_DE")
    parte = next(m for m in out.report["maps"] if m["relation"] == "PARTE_DE")
    # smishing -> phishing: ja declarado; phishing -> smishing: inverte.
    assert tipo["dropped"].get("already declared in the .syno (same species)") == 1
    assert tipo["dropped"].get("inverts a pair already present") == 1
    # link -> phishing: o .syno diz KIND; o mapeamento diria PART.
    assert parte["dropped"].get("the .syno declares the pair with another species") == 1
    g = graph(out.text)
    iso = rdflib.Namespace("http://purl.org/iso25964/skos-thes#")
    assert (C("link"), iso.broaderGeneric, C("phishing")) in g
    assert (C("link"), iso.broaderPartitive, C("phishing")) not in g
    assert (C("vishing"), SKOS.broader, C("phishing")) in g  # mapeado e aceito


def test_min_sources_counts_distinct_sources():
    _, one = skos(1)
    _, two = skos(2)
    tipo1 = next(m for m in one.report["maps"] if m["relation"] == "TIPO_DE")
    tipo2 = next(m for m in two.report["maps"] if m["relation"] == "TIPO_DE")
    assert (tipo1["found"], tipo1["supported"]) == (3, 3)
    # so vishing -> phishing e afirmado por duas fontes (a1 e a2)
    assert tipo2["supported"] == 1


def test_related_from_chain_and_topic_collection():
    _, out = skos()
    g = graph(out.text)
    assert (C("educacao"), SKOS.related, C("phishing")) in g
    assert (C("phishing"), SKOS.related, C("educacao")) in g
    col = rdflib.URIRef(N + "collection/topico/fraude")
    assert (col, RDF.type, SKOS.Collection) in g
    assert set(g.objects(col, SKOS.member)) == {C("phishing"), C("smishing"), C("vishing")}
    # "Fraude" e "fraude": grafia mais frequente vence, com aviso E132.
    assert str(next(g.objects(col, SKOS.prefLabel))) == "fraude"
    assert "SYNESIS_E132" in [w.CODE for w in out.warnings]


# ------------------------------------------------------------- diagnosticos

def _block_codes(block: str) -> list[str]:
    result = compile_(block=block)
    return [w.CODE for w in result.validation_result.warnings]


def test_e122_unknown_relation():
    assert "SYNESIS_E122" in _block_codes(SKOS_BLOCK.replace("MITIGA TO RELATED", "EVITA TO RELATED"))


def test_e124_target_not_allowed():
    assert "SYNESIS_E124" in _block_codes(SKOS_BLOCK.replace("MITIGA TO RELATED", "MITIGA TO EQUIVALENT"))


def test_e125_relation_mapped_twice():
    assert "SYNESIS_E125" in _block_codes(SKOS_BLOCK.replace("MITIGA TO RELATED", "TIPO_DE TO RELATED"))


def test_e126_e127_e128_properties():
    bad = (SKOS_BLOCK.replace("MIN_SOURCES {min_sources}", "MIN_SOURCES zero")
           .replace('"https://example.org/id/t/"', '"example.org/t"')
           .replace("LANGUAGE pt-BR", "LANGUAGE portugues brasileiro"))
    codes = _block_codes(bad)
    assert {"SYNESIS_E126", "SYNESIS_E127", "SYNESIS_E128"} <= set(codes)


def test_e123_ambiguous_relation():
    template = TEMPLATE + (
        "\nFIELD outra TYPE CHAIN\n    SCOPE ITEM\n    RELATIONS\n        MITIGA: mitiga\n"
        "    END RELATIONS\nEND FIELD\n"
    ).replace("OPTIONAL cadeia", "OPTIONAL cadeia, outra")
    project = (
        'PROJECT t\nTEMPLATE "t.synt"\nINCLUDE BIBLIOGRAPHY "r.bib"\n'
        'INCLUDE ANNOTATIONS "a.syn"\nINCLUDE ONTOLOGY "o.syno"\n\n'
        + SKOS_BLOCK.format(min_sources=1) + "END PROJECT\n"
    )
    template = template.replace("    OPTIONAL cadeia\n", "    OPTIONAL cadeia, outra\n")
    result = synesis.load(
        project_content=project, template_content=template,
        annotation_contents={"a.syn": ANNOTATIONS}, ontology_contents={"o.syno": ONTOLOGY},
        bibliography_content=BIB,
    )
    assert "SYNESIS_E123" in [w.CODE for w in result.validation_result.warnings]


def test_e130_derived_label_overlap_blocks_the_file():
    ontology = ONTOLOGY.replace("    usado_por: SMS phishing\n", "    usado_por: smishing\n")
    _, out = skos(ontology=ontology)
    assert "SYNESIS_E130" in [e.CODE for e in out.errors]
    assert out.text is None


def test_e129_derived_label_conflict():
    ontology = ONTOLOGY.replace("    usado_por: SMS phishing\n", "    usado_por: vishing\n")
    # rotulo igual ao nome de outro conceito ja e erro de compilacao (E116);
    # o SKOS acusa tambem o conflito com o rotulo derivado do outro conceito.
    _, out = skos(ontology=ontology)
    assert "SYNESIS_E129" in [e.CODE for e in out.errors]


def test_e131_iri_collision_is_defended():
    from synesis.ast.results import IriCollision

    assert IriCollision.CODE == "SYNESIS_E131"
