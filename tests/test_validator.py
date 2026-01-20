"""
test_validator.py - Testes de validacao semantica Synesis

Propósito:
    Cobrir validacoes basicas, chain e bundle.

Gerado conforme: Especificacao Synesis v1.1
"""

from __future__ import annotations

from pathlib import Path

from synesis.ast.nodes import ChainNode, ItemNode, OntologyNode, SourceLocation, SourceNode
from synesis.parser.template_loader import load_template
from synesis.semantic.validator import SemanticValidator


def _location() -> SourceLocation:
    return SourceLocation(file=Path("test.syn"), line=1, column=1)


def test_missing_required_field(minimal_template):
    item = ItemNode(bibref="@ref2020", quote="", location=_location())
    validator = SemanticValidator(minimal_template, bibliography={}, ontology_index={})
    result = validator.validate_item(item)
    assert result.has_errors()


def test_forbidden_field_present(tmp_path: Path):
    template_text = (
        "TEMPLATE demo\n"
        "ITEM FIELDS\n"
        "    FORBIDDEN secret\n"
        "END ITEM FIELDS\n"
        "FIELD secret TYPE TEXT SCOPE ITEM\n"
        "END FIELD\n"
    )
    path = tmp_path / "forbidden.synt"
    path.write_text(template_text, encoding="utf-8")
    template = load_template(path)
    item = ItemNode(bibref="@ref2020", quote="Text", extra_fields={"secret": "x"}, location=_location())
    validator = SemanticValidator(template, bibliography={}, ontology_index={})
    result = validator.validate_item(item)
    assert result.has_errors()


def test_invalid_enumerated_value(tmp_path: Path):
    template_text = (
        "TEMPLATE demo\n"
        "ITEM FIELDS\n"
        "    REQUIRED level\n"
        "END ITEM FIELDS\n"
        "FIELD level TYPE ENUMERATED SCOPE ITEM\n"
        "    VALUES\n"
        "        low: Low\n"
        "        high: High\n"
        "    END VALUES\n"
        "END FIELD\n"
    )
    path = tmp_path / "enum.synt"
    path.write_text(template_text, encoding="utf-8")
    template = load_template(path)
    item = ItemNode(bibref="@ref2020", quote="Text", extra_fields={"level": "mid"}, location=_location())
    validator = SemanticValidator(template, bibliography={}, ontology_index={})
    result = validator.validate_item(item)
    assert result.has_errors()


def test_unknown_field_name(tmp_path: Path):
    template_text = (
        "TEMPLATE demo\n"
        "ITEM FIELDS\n"
        "    REQUIRED quote\n"
        "END ITEM FIELDS\n"
        "FIELD quote TYPE QUOTATION SCOPE ITEM\n"
        "END FIELD\n"
    )
    path = tmp_path / "unknown_field.synt"
    path.write_text(template_text, encoding="utf-8")
    template = load_template(path)
    item = ItemNode(
        bibref="@ref2020",
        quote="Text",
        extra_fields={"secret": "x"},
        field_names=["secret"],
        location=_location(),
    )
    validator = SemanticValidator(template, bibliography={}, ontology_index={})
    result = validator.validate_item(item)
    assert result.has_errors()


def test_invalid_ordered_value(tmp_path: Path):
    template_text = (
        "TEMPLATE demo\n"
        "ITEM FIELDS\n"
        "    REQUIRED rank\n"
        "END ITEM FIELDS\n"
        "FIELD rank TYPE ORDERED SCOPE ITEM\n"
        "    VALUES\n"
        "        [1] low: Low\n"
        "        [2] high: High\n"
        "    END VALUES\n"
        "END FIELD\n"
    )
    path = tmp_path / "ordered.synt"
    path.write_text(template_text, encoding="utf-8")
    template = load_template(path)
    item = ItemNode(bibref="@ref2020", quote="Text", extra_fields={"rank": 3}, location=_location())
    validator = SemanticValidator(template, bibliography={}, ontology_index={})
    result = validator.validate_item(item)
    assert result.has_errors()


def test_invalid_bibref_with_suggestions(minimal_template):
    source = SourceNode(bibref="@missing", fields={"description": "x"}, location=_location())
    bibliography = {"ref2020": {"ID": "ref2020"}}
    validator = SemanticValidator(minimal_template, bibliography=bibliography, ontology_index={})
    result = validator.validate_source(source)
    assert result.has_errors()


def test_unknown_relation(energy_template):
    chain = ChainNode(nodes=["A", "UNKNOWN", "B"], relations=[], location=_location())
    item = ItemNode(bibref="@ref2020", quote="Text", chains=[chain], location=_location())
    validator = SemanticValidator(energy_template, bibliography={}, ontology_index={"A": None, "B": None})
    result = validator.validate_item(item)
    assert result.has_errors()


def test_arity_violation(tmp_path: Path):
    template_text = (
        "TEMPLATE demo\n"
        "ITEM FIELDS\n"
        "    REQUIRED chain\n"
        "END ITEM FIELDS\n"
        "FIELD chain TYPE CHAIN SCOPE ITEM\n"
        "    ARITY = 3\n"
        "END FIELD\n"
    )
    path = tmp_path / "arity.synt"
    path.write_text(template_text, encoding="utf-8")
    template = load_template(path)
    chain = ChainNode(nodes=["A", "B"], relations=[], location=_location())
    item = ItemNode(bibref="@ref2020", quote="Text", chains=[chain], location=_location())
    validator = SemanticValidator(template, bibliography={}, ontology_index={})
    result = validator.validate_item(item)
    assert result.has_errors()


def test_bundle_valid_equal_counts(energy_template):
    chain1 = ChainNode(nodes=["A", "INFLUENCES", "B"], relations=[], location=_location())
    chain2 = ChainNode(nodes=["B", "ENABLES", "C"], relations=[], location=_location())
    item = ItemNode(
        bibref="@ref2020",
        quote="Text",
        notes=["n1", "n2"],
        chains=[chain1, chain2],
        location=_location(),
    )
    validator = SemanticValidator(energy_template, bibliography={}, ontology_index={})
    result = validator.validate_item(item)
    assert not result.has_errors()


def test_bundle_violation_unequal_counts(energy_template):
    chain1 = ChainNode(nodes=["A", "INFLUENCES", "B"], relations=[], location=_location())
    item = ItemNode(
        bibref="@ref2020",
        quote="Text",
        notes=["n1", "n2"],
        chains=[chain1],
        location=_location(),
    )
    validator = SemanticValidator(energy_template, bibliography={}, ontology_index={})
    result = validator.validate_item(item)
    assert result.has_errors()


def test_bundle_violation_missing_field(energy_template):
    item = ItemNode(
        bibref="@ref2020",
        quote="Text",
        notes=["n1"],
        chains=[],
        location=_location(),
    )
    validator = SemanticValidator(energy_template, bibliography={}, ontology_index={})
    result = validator.validate_item(item)
    assert result.has_errors()


def test_code_without_ontology_warning(energy_template):
    item = ItemNode(
        bibref="@ref2020",
        quote="Text",
        codes=["Unknown"],
        location=_location(),
    )
    validator = SemanticValidator(energy_template, bibliography={}, ontology_index={})
    result = validator.validate_item(item)
    assert result.has_warnings()


def test_custom_code_field_warning(tmp_path: Path):
    template_text = (
        "TEMPLATE demo\n"
        "ITEM FIELDS\n"
        "    REQUIRED ordem_2a\n"
        "END ITEM FIELDS\n"
        "FIELD ordem_2a TYPE CODE SCOPE ITEM\n"
        "END FIELD\n"
    )
    path = tmp_path / "custom_code.synt"
    path.write_text(template_text, encoding="utf-8")
    template = load_template(path)
    item = ItemNode(
        bibref="@ref2020",
        quote="",
        extra_fields={"ordem_2a": "Conversao"},
        field_names=["ordem_2a"],
        location=_location(),
    )
    validator = SemanticValidator(template, bibliography={}, ontology_index={})
    result = validator.validate_item(item)
    assert result.has_warnings()


def test_topic_accepts_any_string(tmp_path: Path):
    template_text = (
        "TEMPLATE demo\n"
        "ONTOLOGY FIELDS\n"
        "    OPTIONAL topic\n"
        "END ONTOLOGY FIELDS\n"
        "FIELD topic TYPE TOPIC SCOPE ONTOLOGY\n"
        "END FIELD\n"
    )
    path = tmp_path / "topic.synt"
    path.write_text(template_text, encoding="utf-8")
    template = load_template(path)
    ontology = OntologyNode(concept="A", description="Desc", fields={"topic": "Any"}, location=_location())
    validator = SemanticValidator(template, bibliography={}, ontology_index={})
    result = validator.validate_ontology(ontology)
    assert not result.has_errors()


def test_chain_simple_vs_qualified(energy_template):
    chain = ChainNode(nodes=["A", "B"], relations=[], location=_location())
    item = ItemNode(bibref="@ref2020", quote="Text", chains=[chain], location=_location())
    validator = SemanticValidator(energy_template, bibliography={}, ontology_index={"A": None, "B": None})
    result = validator.validate_item(item)
    assert result.has_errors()
