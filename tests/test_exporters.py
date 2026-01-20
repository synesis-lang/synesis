"""
test_exporters.py - Testes de exportacao JSON/CSV

Propósito:
    Verificar estrutura e rastreabilidade dos artefatos exportados.

Gerado conforme: Especificacao Synesis v2.0
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from synesis.ast.nodes import ChainNode, ItemNode, OntologyNode, ProjectNode, SourceLocation, SourceNode
from synesis.exporters.csv_export import export_csv
from synesis.exporters.json_export import export_json
from synesis.semantic.linker import LinkedProject


def _location() -> SourceLocation:
    return SourceLocation(file=Path("test.syn"), line=1, column=1)


def _linked_project() -> LinkedProject:
    project = ProjectNode(
        name="demo",
        template_path=Path("template.synt"),
        includes=[],
        metadata={},
        description=None,
        location=_location(),
    )
    source = SourceNode(bibref="@ref2020", fields={"description": "Desc"}, location=_location())
    chain = ChainNode(nodes=["A", "B"], relations=[], location=_location())
    item = ItemNode(bibref="@ref2020", quote="Text", chains=[chain], codes=["A"], location=_location())
    source.items = [item]
    ontology = OntologyNode(concept="A", description="Desc", fields={"topic": "Social"}, location=_location())
    return LinkedProject(
        project=project,
        sources={"ref2020": source},
        ontology_index={"A": ontology},
        code_usage={"A": [item]},
        hierarchy={},
        all_triples=chain.to_triples(),
        topic_index={"Social": ["A"]},
    )


def test_json_roundtrip(tmp_path: Path):
    """Verifica que JSON v2.0 pode ser carregado e tem project name correto."""
    linked = _linked_project()
    path = tmp_path / "out.json"
    export_json(linked, path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == "2.0"
    assert data["project"]["name"] == "demo"


def test_json_structure(tmp_path: Path):
    """Verifica estrutura completa do JSON v2.0."""
    linked = _linked_project()
    path = tmp_path / "out.json"
    export_json(linked, path)
    data = json.loads(path.read_text(encoding="utf-8"))

    # Verificar todas seções presentes
    assert data["version"] == "2.0"
    assert "export_metadata" in data
    assert "project" in data
    assert "template" in data
    assert "bibliography" in data
    assert "indices" in data
    assert "ontology" in data
    assert "corpus" in data

    # Verificar sub-seções de indices
    assert "hierarchy" in data["indices"]
    assert "triples" in data["indices"]
    assert "topics" in data["indices"]
    assert "code_frequency" in data["indices"]


def test_json_includes_location(tmp_path: Path):
    linked = _linked_project()
    path = tmp_path / "out.json"
    export_json(linked, path)
    data = json.loads(path.read_text(encoding="utf-8"))
    item = data["corpus"][0]
    assert "traceability" in item
    assert "file" in item["traceability"]
    assert "line" in item["traceability"]


def test_csv_files_created(tmp_path: Path):
    linked = _linked_project()
    export_csv(linked, None, tmp_path)
    assert (tmp_path / "sources.csv").exists()
    assert (tmp_path / "items.csv").exists()
    assert (tmp_path / "ontologies.csv").exists()
    assert (tmp_path / "chains.csv").exists()
    assert (tmp_path / "codes.csv").exists()


def test_csv_chains_format(tmp_path: Path):
    linked = _linked_project()
    export_csv(linked, None, tmp_path)
    with (tmp_path / "chains.csv").open("r", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["from_code"] == "A"
    assert rows[0]["to_code"] == "B"


def test_csv_includes_source_location(tmp_path: Path):
    linked = _linked_project()
    export_csv(linked, None, tmp_path)
    with (tmp_path / "sources.csv").open("r", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["source_file"] == "test.syn"
    assert rows[0]["source_line"] == "1"


# Novos testes para v2.0

def test_export_metadata_section(tmp_path: Path):
    """Verifica seção export_metadata."""
    linked = _linked_project()
    path = tmp_path / "out.json"
    export_json(linked, path)
    data = json.loads(path.read_text(encoding="utf-8"))

    meta = data["export_metadata"]
    assert "timestamp" in meta
    assert meta["compiler_version"] == "1.1"
    assert meta["export_mode"] == "universal"
    assert meta["chain_count"] == 1
    assert meta["item_count"] == 1
    assert meta["source_count"] == 1
    assert meta["concept_count"] == 1


def test_triples_with_provenance(tmp_path: Path):
    """Verifica que triplas incluem source_item e location."""
    linked = _linked_project()
    path = tmp_path / "out.json"
    export_json(linked, path)
    data = json.loads(path.read_text(encoding="utf-8"))

    triples = data["indices"]["triples"]
    assert len(triples) == 1
    assert triples[0]["from"] == "A"
    assert triples[0]["to"] == "B"
    assert triples[0]["relation"] == "IMPLICIT"
    assert triples[0]["source_item"] == "ref2020_item0001"
    assert triples[0]["location"]["file"] == "test.syn"
    assert triples[0]["location"]["line"] == 1


def test_ontology_enrichment(tmp_path: Path):
    """Verifica enriquecimento de ontologia com frequency e source_count."""
    linked = _linked_project()
    path = tmp_path / "out.json"
    export_json(linked, path)
    data = json.loads(path.read_text(encoding="utf-8"))

    ontology_a = data["ontology"]["A"]
    assert ontology_a["frequency"] == 1
    assert ontology_a["source_count"] == 1
    assert ontology_a["concept"] == "A"
    assert ontology_a["description"] == "Desc"


def test_code_frequency_index(tmp_path: Path):
    """Verifica índice de frequências de códigos."""
    linked = _linked_project()
    path = tmp_path / "out.json"
    export_json(linked, path)
    data = json.loads(path.read_text(encoding="utf-8"))

    freq = data["indices"]["code_frequency"]
    assert freq["A"] == 1


def test_chain_serialization_as_object(tmp_path: Path):
    """Verifica que chains são serializadas como objetos to_dict()."""
    linked = _linked_project()
    path = tmp_path / "out.json"
    export_json(linked, path)
    data = json.loads(path.read_text(encoding="utf-8"))

    item = data["corpus"][0]
    chain = item["data"]["chains"][0]

    # Deve ser objeto com nodes, relations, location (não array simples)
    assert isinstance(chain, dict)
    assert "nodes" in chain
    assert "relations" in chain
    assert "location" in chain
    assert chain["nodes"] == ["A", "B"]
    assert chain["relations"] == []


def test_template_section_none_when_no_template(tmp_path: Path):
    """Verifica que template é null quando não fornecido."""
    linked = _linked_project()
    path = tmp_path / "out.json"
    export_json(linked, path, template=None)
    data = json.loads(path.read_text(encoding="utf-8"))

    assert data["template"] is None


def test_bibliography_section_empty_when_none(tmp_path: Path):
    """Verifica que bibliography é objeto vazio quando não fornecido."""
    linked = _linked_project()
    path = tmp_path / "out.json"
    export_json(linked, path, bibliography=None)
    data = json.loads(path.read_text(encoding="utf-8"))

    assert data["bibliography"] == {}
