"""test_integration.py - Integration tests for case-studies/Tests projects."""
import pytest
from pathlib import Path
from synesis.compiler import SynesisCompiler

TESTS_ROOT = Path(__file__).parent / "fixtures"


def _compile(project_name, synp_filename=None):
    project_dir = TESTS_ROOT / project_name
    if synp_filename is None:
        synp_path = sorted(project_dir.glob("*.synp"))[0]
    else:
        synp_path = project_dir / synp_filename
    return SynesisCompiler(synp_path).compile().validation_result


def ecodes(r): return [e.CODE for e in r.errors]
def wcodes(r): return [e.CODE for e in r.warnings]


class TestT01:
    def test_unregistered_source(self): assert "SYNESIS_E001" in ecodes(_compile("T01-Bibliographic-Ontology-Links"))
    def test_orphan_item(self): assert "SYNESIS_E002" in ecodes(_compile("T01-Bibliographic-Ontology-Links"))
    def test_duplicate_ontology_concept(self): assert "SYNESIS_E068" in ecodes(_compile("T01-Bibliographic-Ontology-Links"))
    def test_duplicate_source_bibref(self): assert "SYNESIS_E070" in ecodes(_compile("T01-Bibliographic-Ontology-Links"))
    def test_undefined_code_warning(self): assert "SYNESIS_E004" in wcodes(_compile("T01-Bibliographic-Ontology-Links"))


class TestT02:
    def test_invalid_chain_relation(self): assert "SYNESIS_E010" in ecodes(_compile("T02-Chain-Relations"))
    def test_simple_chain_with_relations_required(self): assert "SYNESIS_E009" in ecodes(_compile("T02-Chain-Relations"))
    def test_malformed_qualified_chain(self): assert "SYNESIS_E011" in ecodes(_compile("T02-Chain-Relations"))
    def test_concept_name_matches_relation(self): assert "SYNESIS_E014" in ecodes(_compile("T02-Chain-Relations"))
    def test_concept_with_spaces(self): assert "SYNESIS_E015" in ecodes(_compile("T02-Chain-Relations"))


class TestT03:
    def test_missing_bundle_field(self): assert "SYNESIS_E016" in ecodes(_compile("T03-Bundle"))
    def test_bundle_count_mismatch(self): assert "SYNESIS_E017" in ecodes(_compile("T03-Bundle"))
    def test_single_field_bundle(self): assert "SYNESIS_E018" in ecodes(_compile("T03-Bundle"))


class TestT04:
    def test_missing_required_field(self): assert "SYNESIS_E020" in ecodes(_compile("T04-Fields-Types-Scope"))
    def test_empty_item_block(self): assert "SYNESIS_E023" in ecodes(_compile("T04-Fields-Types-Scope"))
    def test_scale_out_of_range(self): assert "SYNESIS_E030" in ecodes(_compile("T04-Fields-Types-Scope"))
    def test_decimal_in_integer_scale(self): assert "SYNESIS_E026" in ecodes(_compile("T04-Fields-Types-Scope"))
    def test_invalid_enumerated_value(self): assert "SYNESIS_E027" in ecodes(_compile("T04-Fields-Types-Scope"))
    def test_invalid_ordered_value(self): assert "SYNESIS_E029" in ecodes(_compile("T04-Fields-Types-Scope"))
    def test_topic_with_spaces(self): assert "SYNESIS_E032" in ecodes(_compile("T04-Fields-Types-Scope"))
    def test_duplicate_code_warning(self): assert "SYNESIS_W031" in wcodes(_compile("T04-Fields-Types-Scope"))


class TestT05:
    def test_undefined_field_in_scope_fields(self): assert "SYNESIS_E039" in ecodes(_compile("T05-Template-Declaration"))
    def test_orphan_field_definition_warning(self): assert "SYNESIS_E042" in wcodes(_compile("T05-Template-Declaration"))
    def test_duplicate_field_name(self): assert "SYNESIS_E069" in ecodes(_compile("T05-Template-Declaration"))
    def test_chain_without_arity(self): assert "SYNESIS_E047" in ecodes(_compile("T05-Template-Declaration"))
    def test_arity_relations_mismatch(self): assert "SYNESIS_E048" in ecodes(_compile("T05-Template-Declaration"))
    def test_ordered_without_values(self): assert "SYNESIS_E049" in ecodes(_compile("T05-Template-Declaration"))
    def test_enumerated_without_values(self): assert "SYNESIS_E050" in ecodes(_compile("T05-Template-Declaration"))
    def test_scale_without_format(self): assert "SYNESIS_E051" in ecodes(_compile("T05-Template-Declaration"))
    def test_format_on_non_scale(self): assert "SYNESIS_E054" in ecodes(_compile("T05-Template-Declaration"))
    def test_arity_on_non_chain(self): assert "SYNESIS_E055" in ecodes(_compile("T05-Template-Declaration"))
    def test_relations_on_non_chain(self): assert "SYNESIS_E056" in ecodes(_compile("T05-Template-Declaration"))
    def test_duplicate_value(self): assert "SYNESIS_E059" in ecodes(_compile("T05-Template-Declaration"))


class TestT06:
    def test_missing_annotations_include(self): assert "SYNESIS_E061" in ecodes(_compile("T06-Project-Structure", "t06_no_include_annotations.synp"))
    def test_missing_ontology_include(self): assert "SYNESIS_E062" in ecodes(_compile("T06-Project-Structure", "t06_no_include_ontology.synp"))
    def test_missing_bibliography_file(self): assert "SYNESIS_E063" in ecodes(_compile("T06-Project-Structure", "t06_missing_bib.synp"))
    def test_missing_template_file(self): assert "SYNESIS_E064" in ecodes(_compile("T06-Project-Structure", "t06_missing_template.synp"))
    def test_missing_template_declaration(self): assert "SYNESIS_E064" in ecodes(_compile("T06-Project-Structure", "t06_no_template.synp"))
    def test_duplicate_project_block(self): assert "SYNESIS_E066" in ecodes(_compile("T06-Project-Structure", "t06_duplicate_project.synp"))
    def test_modified_before_created(self): assert "SYNESIS_W067" in wcodes(_compile("T06-Project-Structure", "t06_metadata_dates.synp"))
    def test_ontology_without_template_fields(self): assert "SYNESIS_E005" in ecodes(_compile("T06-Project-Structure", "t06_no_ontology_fields.synp"))


class TestT07NoBibliography:
    """WI-1: projetos sem INCLUDE BIBLIOGRAPHY tratam bibrefs como chaves internas."""

    def test_no_bibliography_no_e001(self):
        r = _compile("T07-No-Bibliography")
        assert "SYNESIS_E001" not in ecodes(r)

    def test_no_bibliography_compiles_clean(self):
        r = _compile("T07-No-Bibliography")
        assert not r.errors, f"erros inesperados: {ecodes(r)}"


class TestT10CustomChainName:
    """WI-2: campo TYPE CHAIN com nome customizado exporta relacoes nomeadas no JSON."""

    def _triples(self):
        from synesis.exporters.json_export import build_json_payload
        project_dir = TESTS_ROOT / "T10-Custom-Chain-Name"
        synp = sorted(project_dir.glob("*.synp"))[0]
        result = SynesisCompiler(synp).compile()
        data = build_json_payload(result.linked_project, result.template, result.bibliography)
        triples = []

        def walk(o):
            if isinstance(o, dict):
                if "from" in o and "relation" in o:
                    triples.append(o)
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)

        walk(data)
        return triples

    def test_named_relation_preserved(self):
        triples = self._triples()
        assert any(t["relation"] == "INFLUENCES" for t in triples), \
            f"relacao nomeada perdida (esperado INFLUENCES): {[t['relation'] for t in triples]}"

    def test_no_implicit_relation(self):
        triples = self._triples()
        assert all(t["relation"] != "IMPLICIT" for t in triples), \
            "cadeia qualificada exportada como simples (IMPLICIT)"


class TestT09OptionalBundle:
    """WI-4: OPTIONAL BUNDLE — ausência total válida; parcial e mismatch geram erros."""

    def test_template_loads_optional_bundle(self):
        from synesis.parser.template_loader import load_template
        from synesis.ast.nodes import Scope
        project_dir = TESTS_ROOT / "T09-OptionalBundle"
        template = load_template(project_dir / "t09.synt")
        assert Scope.ITEM in template.optional_bundles
        assert ("period", "region") in template.optional_bundles[Scope.ITEM]

    def test_partial_presence_generates_e016(self):
        r = _compile("T09-OptionalBundle")
        assert "SYNESIS_E016" in ecodes(r), \
            f"esperado E016 (MissingBundleField) — erros presentes: {ecodes(r)}"

    def test_count_mismatch_generates_e017(self):
        r = _compile("T09-OptionalBundle")
        assert "SYNESIS_E017" in ecodes(r), \
            f"esperado E017 (BundleCountMismatch) — erros presentes: {ecodes(r)}"

    def test_total_absence_and_complete_bundle_produce_no_extra_errors(self):
        r = _compile("T09-OptionalBundle")
        bundle_errors = [e for e in r.errors if e.CODE in ("SYNESIS_E016", "SYNESIS_E017")]
        # Exatamente 2 erros de bundle: cenário B (E016) e cenário C (E017).
        assert len(bundle_errors) == 2, \
            f"esperado exatamente 2 erros de bundle, encontrado {len(bundle_errors)}: {[e.CODE for e in bundle_errors]}"

    def test_required_bundle_unaffected(self):
        """T03 (REQUIRED BUNDLE) continua gerando E016/E017/E018 — sem regressão."""
        r = _compile("T03-Bundle")
        assert "SYNESIS_E016" in ecodes(r)
        assert "SYNESIS_E017" in ecodes(r)
        assert "SYNESIS_E018" in ecodes(r)


class TestRealProjectRegression:
    def test_basic_project_no_fase4_false_positives(self):
        basic = Path(__file__).parent / "fixtures" / "Basic" / "project.synp"
        if not basic.exists():
            pytest.skip("Projeto Basic nao encontrado")
        result = SynesisCompiler(basic).compile().validation_result
        fase4 = {"SYNESIS_E061", "SYNESIS_E062", "SYNESIS_E063", "SYNESIS_E065", "SYNESIS_E066", "SYNESIS_W067"}
        found = {e.CODE for e in result.errors + result.warnings} & fase4
        assert not found, f"Falsos positivos Fase 4: {found}"
