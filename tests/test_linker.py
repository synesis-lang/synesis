"""
test_linker.py - Testes do vinculador Synesis

Propósito:
    Validar associacoes SOURCE/ITEM, indices e grafos.

Gerado conforme: Especificacao Synesis v1.1
"""

from __future__ import annotations

from pathlib import Path

from synesis.ast.nodes import ChainNode, ItemNode, OntologyNode, SourceLocation, SourceNode, TemplateNode, FieldSpec, FieldType, Scope
from synesis.semantic.linker import Linker


def _location() -> SourceLocation:
    return SourceLocation(file=Path("test.syn"), line=1, column=1)


def test_link_items_to_sources():
    source = SourceNode(bibref="@ref2020", fields={}, location=_location())
    item = ItemNode(bibref="@ref2020", quote="Text", location=_location())
    linker = Linker([source], [item], [])
    linked = linker.link()
    assert linked.sources["ref2020"].items[0].bibref == "@ref2020"


def test_item_without_source_error():
    item = ItemNode(bibref="@ref2020", quote="Text", location=_location())
    linker = Linker([], [item], [])
    linker.link()
    assert linker.validation_result.has_errors()


def test_code_usage_index():
    source = SourceNode(bibref="@ref2020", fields={}, location=_location())
    item = ItemNode(bibref="@ref2020", quote="Text", codes=["A", "B"], location=_location())
    linker = Linker([source], [item], [OntologyNode(concept="A", description="d", location=_location())])
    linked = linker.link()
    assert "A" in linked.code_usage
    assert len(linked.code_usage["A"]) == 1


def test_hierarchy_construction():
    chain = ChainNode(nodes=["Child", "Parent"], relations=[], location=_location())
    ontology = OntologyNode(concept="Child", description="d", parent_chains=[chain], location=_location())
    linker = Linker([], [], [ontology])
    linked = linker.link()
    assert linked.hierarchy["Child"] == "Parent"


def test_triple_collection():
    source = SourceNode(bibref="@ref2020", fields={}, location=_location())
    chain = ChainNode(nodes=["A", "B"], relations=[], location=_location())
    item = ItemNode(bibref="@ref2020", quote="Text", chains=[chain], location=_location())
    linker = Linker([source], [item], [])
    linked = linker.link()
    assert linked.all_triples[0] == ("A", "IMPLICIT", "B")


def test_topic_index_construction():
    topic_spec = FieldSpec(
        name="topic",
        type=FieldType.TOPIC,
        scope=Scope.ONTOLOGY,
        location=_location(),
    )
    template = TemplateNode(
        name="demo",
        metadata={},
        field_specs={"topic": topic_spec},
        required_fields={Scope.SOURCE: [], Scope.ITEM: [], Scope.ONTOLOGY: []},
        optional_fields={Scope.SOURCE: [], Scope.ITEM: [], Scope.ONTOLOGY: []},
        forbidden_fields={Scope.SOURCE: [], Scope.ITEM: [], Scope.ONTOLOGY: []},
        bundled_fields={Scope.SOURCE: [], Scope.ITEM: [], Scope.ONTOLOGY: []},
        location=_location(),
    )
    ontology = OntologyNode(
        concept="A",
        description="d",
        fields={"topic": "Social"},
        location=_location(),
    )
    linker = Linker([], [], [ontology], template=template)
    linked = linker.link()
    assert "Social" in linked.topic_index
