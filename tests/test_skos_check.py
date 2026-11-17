"""Verificação do SKOS gerado (skos_check), antes de gravar.

Origem: validação do `ufg-fraudes` no VocBench (2026-11-17). SHACL e
condições S limpos; o ICV acusou dois grupos editoriais vindos do exportador
(valores de vocabulário fechado sem topo; esquema principal sem prefLabel).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from synesis.exporters.skos_check import CYCLE_RULE, check_skos, summary_lines

S = "http://ex.org/"


def g(*triples):
    """Grafo no formato do exportador: {sujeito: {predicado: {objetos}}}."""
    out: dict = {}
    for s, p, o in triples:
        out.setdefault(S + s, {}).setdefault(p, set()).add(o)
    return out


def ok_concept(name, scheme="scheme"):
    return [
        (name, "a", "skos:Concept"),
        (name, "skos:prefLabel", f'"{name}"@en'),
        (name, "skos:inScheme", f"<{S}{scheme}>"),
        (name, "skos:topConceptOf", f"<{S}{scheme}>"),
        (scheme, "skos:hasTopConcept", f"<{S}{name}>"),
    ]


SCHEME = [("scheme", "a", "skos:ConceptScheme"), ("scheme", "skos:prefLabel", '"s"@en')]


def test_clean_graph_has_no_violation_and_no_notice():
    r = check_skos(g(*SCHEME, *ok_concept("a")), "en")
    assert r.ok and not r.quality
    assert summary_lines(r)[0].startswith("SKOS check: integrity OK")


@pytest.mark.parametrize("extra, condition", [
    ([("a", "a", "skos:ConceptScheme")], "S9"),
    ([("a", "skos:altLabel", '"a"@en')], "S13"),
    ([("a", "skos:prefLabel", '"outro"@en')], "S14"),
    ([("a", "a", "skos:Collection")], "S37"),
])
def test_integrity_conditions(extra, condition):
    r = check_skos(g(*SCHEME, *ok_concept("a"), *extra), "en")
    assert condition in r.integrity and not r.ok


def test_same_text_in_two_languages_is_not_s14():
    r = check_skos(g(*SCHEME, *ok_concept("a"), ("a", "skos:prefLabel", '"a"@pt')), "en")
    assert "S14" not in r.integrity


def test_related_between_ancestor_and_descendant_is_s27():
    triples = [*SCHEME, *ok_concept("p"), *ok_concept("c"), *ok_concept("n"),
               ("c", "skos:broader", f"<{S}p>"), ("n", "skos:broader", f"<{S}c>"),
               ("n", "skos:related", f"<{S}p>")]
    assert "S27" in check_skos(g(*triples), "en").integrity


def test_broader_cycle_is_integrity():
    triples = [*SCHEME, *ok_concept("a"), *ok_concept("b"),
               ("a", "skos:broader", f"<{S}b>"), ("b", "skos:broader", f"<{S}a>")]
    assert CYCLE_RULE in check_skos(g(*triples), "en").integrity


def test_quality_notices_are_the_vocbench_icv_groups():
    triples = [
        ("scheme", "a", "skos:ConceptScheme"),            # sem prefLabel, sem topo
        ("v", "a", "skos:Concept"), ("v", "skos:prefLabel", '"v"@en'),
        ("v", "skos:inScheme", f"<{S}scheme>"),           # sem posição
        ("solto", "a", "skos:Concept"), ("solto", "skos:prefLabel", '"solto"'),  # sem esquema, sem idioma
    ]
    q = check_skos(g(*triples), "en").quality
    assert set(q) == {"no prefLabel", "scheme without top concept", "concept without position",
                      "concept without scheme", "label without language"}
    assert check_skos(g(*triples), "en").ok, "editorial notices do not block writing"


def test_concept_with_parent_in_its_scheme_has_a_position():
    triples = [*SCHEME, *ok_concept("p"), ("c", "a", "skos:Concept"), ("c", "skos:prefLabel", '"c"@en'),
               ("c", "skos:inScheme", f"<{S}scheme>"), ("c", "skos:broader", f"<{S}p>")]
    assert "concept without position" not in check_skos(g(*triples), "en").quality


# ---------------------------------------------- o exportador, pela saída real

def _test_project_skos():
    from synesis.compiler import SynesisCompiler
    from synesis.exporters.skos_export import build_skos

    root = Path(__file__).resolve().parents[2] / "case-studies" / "Exemplo_Tipos_Relacionais"
    synp = root / "fraudes.synp"
    if not synp.exists():
        pytest.skip("projeto de teste fora deste checkout")
    result = SynesisCompiler(synp).compile()
    export = next(e for e in result.linked_project.project.exports if e.format == "SKOS")
    return build_skos(result.linked_project, result.template, export)


def test_exporter_fixes_from_the_vocbench_validation():
    rdflib = pytest.importorskip("rdflib")
    from rdflib.namespace import SKOS

    out = _test_project_skos()
    assert not out.errors and not [w for w in out.warnings if w.CODE == "SYNESIS_E155"]
    graph = rdflib.Graph().parse(data=out.text, format="turtle")
    for scheme in graph.subjects(rdflib.RDF.type, SKOS.ConceptScheme):
        labels = list(graph.objects(scheme, SKOS.prefLabel))
        assert labels and all(lab.language for lab in labels), f"{scheme} needs a prefLabel with language"
        assert list(graph.objects(scheme, SKOS.hasTopConcept)), f"{scheme} has no top concept"
        if "/vocab/" in str(scheme):
            values = set(graph.subjects(SKOS.inScheme, scheme))
            assert all((v, SKOS.topConceptOf, scheme) in graph for v in values)
            assert not any(True for v in values for _ in graph.objects(v, SKOS.broader)), \
                "the order of a closed vocabulary must not become broader"


def test_integrity_violation_blocks_the_file_as_e154(monkeypatch):
    """Uma violação de integridade vira SYNESIS_E154 e o Turtle não é gerado."""
    import synesis.exporters.skos_check as skos_check

    real = skos_check.check_skos

    def broken(subjects, language=""):
        result = real(subjects, language)
        result.add("integrity", "S14", "<http://ex.org/x>: 2 prefLabels in \"pt-BR\"")
        return result

    monkeypatch.setattr(skos_check, "check_skos", broken)
    out = _test_project_skos()
    assert [e.CODE for e in out.errors] == ["SYNESIS_E154"]
    assert out.text is None
    assert out.report["check"][0].startswith("SKOS check: INTEGRITY VIOLATIONS (S14 1)")


def test_cycle_is_reported_as_a_synesis_rule_not_a_skos_condition():
    """SKOS admite ciclos hierárquicos (§8.6.8); a proibição é do Synesis."""
    assert CYCLE_RULE.startswith("Synesis rule")
    line = summary_lines(check_skos(g(*SCHEME, *ok_concept("a")), "en"))[0]
    assert "S9, S13, S14, S27, S37; Synesis rule: acyclic broader" in line


def _chain(n):
    triples = [*SCHEME, *ok_concept("c0")]
    for i in range(1, n):
        triples += [(f"c{i}", "a", "skos:Concept"), (f"c{i}", "skos:prefLabel", f'"c{i}"@en'),
                    (f"c{i}", "skos:inScheme", f"<{S}scheme>"), (f"c{i}", "skos:broader", f"<{S}c{i - 1}>")]
    return triples


def test_deep_chain_is_linear_not_quadratic():
    """Revisão de 2026-11-17, 1.4: cadeia de 3.000 sem materializar ancestrais."""
    import time
    import tracemalloc

    graph = g(*_chain(3000))
    tracemalloc.start()
    start = time.perf_counter()
    result = check_skos(graph, "en")
    elapsed = time.perf_counter() - start
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert result.ok and not result.quality
    assert peak < 20 * 1024 * 1024, f"peak {peak / 1024 ** 2:.1f} MiB"
    assert elapsed < 5.0


def test_s27_is_found_at_the_end_of_a_deep_chain():
    triples = _chain(500) + [("c499", "skos:related", f"<{S}c0>")]
    assert "S27" in check_skos(g(*triples), "en").integrity
