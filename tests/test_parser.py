"""
test_parser.py - Testes de parsing Synesis

Propósito:
    Validar parsing de blocos e tokens principais.

Gerado conforme: Especificação Synesis v1.1
"""

from __future__ import annotations

from pathlib import Path

import pytest

from synesis.ast.nodes import ChainNode, ItemNode, OntologyNode, SourceNode
from synesis.parser.lexer import SynesisSyntaxError, parse_file, parse_string
from synesis.parser.transformer import SynesisTransformer


def _parse_nodes(text: str, filename: str = "test.syn"):
    tree = parse_string(text, filename)
    return SynesisTransformer(filename).transform(tree)


def test_parse_valid_source():
    nodes = _parse_nodes(
        "SOURCE @ref2020\n"
        "    description: Example\n"
        "END SOURCE\n"
    )
    source = next(n for n in nodes if isinstance(n, SourceNode))
    assert source.bibref == "@ref2020"
    assert source.fields["description"] == "Example"


def test_parse_valid_item_with_codes():
    nodes = _parse_nodes(
        "ITEM @ref2020\n"
        "    quote: \"Text\"\n"
        "    code: A, B\n"
        "END ITEM\n"
    )
    item = next(n for n in nodes if isinstance(n, ItemNode))
    assert item.codes == ["A", "B"]


def test_parse_valid_item_with_chains():
    nodes = _parse_nodes(
        "ITEM @ref2020\n"
        "    quote: \"Text\"\n"
        "    chain: A -> INFLUENCES -> B\n"
        "END ITEM\n"
    )
    item = next(n for n in nodes if isinstance(n, ItemNode))
    assert isinstance(item.chains[0], ChainNode)
    assert item.chains[0].nodes == ["A", "INFLUENCES", "B"]


def test_parse_valid_item_mixed():
    nodes = _parse_nodes(
        "ITEM @ref2020\n"
        "    quote: \"Text\"\n"
        "    note: First note\n"
        "    chain: A -> B\n"
        "    aspect: Social\n"
        "END ITEM\n"
    )
    item = next(n for n in nodes if isinstance(n, ItemNode))
    assert item.notes == ["First note"]
    assert item.chains[0].nodes == ["A", "B"]
    assert item.extra_fields["aspect"] == "Social"


def test_parse_valid_ontology():
    nodes = _parse_nodes(
        "ONTOLOGY Concept A\n"
        "    description: Desc\n"
        "END ONTOLOGY\n"
    )
    ontology = next(n for n in nodes if isinstance(n, OntologyNode))
    assert ontology.concept == "Concept A"
    assert ontology.description == "Desc"


def test_parse_chain_simple():
    nodes = _parse_nodes(
        "ITEM @ref2020\n"
        "    quote: \"Text\"\n"
        "    chain: A -> B -> C\n"
        "END ITEM\n"
    )
    item = next(n for n in nodes if isinstance(n, ItemNode))
    assert item.chains[0].nodes == ["A", "B", "C"]


def test_parse_chain_qualified():
    nodes = _parse_nodes(
        "ITEM @ref2020\n"
        "    quote: \"Text\"\n"
        "    chain: A -> INFLUENCES -> B\n"
        "END ITEM\n"
    )
    item = next(n for n in nodes if isinstance(n, ItemNode))
    assert item.chains[0].nodes == ["A", "INFLUENCES", "B"]


def test_parse_chain_long():
    nodes = _parse_nodes(
        "ITEM @ref2020\n"
        "    quote: \"Text\"\n"
        "    chain: A -> REL -> B -> REL -> C\n"
        "END ITEM\n"
    )
    item = next(n for n in nodes if isinstance(n, ItemNode))
    assert len(item.chains[0].nodes) == 5


def test_parse_multiline_string():
    nodes = _parse_nodes(
        "ITEM @ref2020\n"
        "    quote:\n"
        "        Line 1\n"
        "        Line 2\n"
        "END ITEM\n"
    )
    item = next(n for n in nodes if isinstance(n, ItemNode))
    assert "Line 1" in item.quote
    assert "Line 2" in item.quote


def test_parse_ordered_values():
    text = (
        "TEMPLATE demo\n"
        "FIELD level TYPE ORDERED SCOPE ITEM\n"
        "    VALUES\n"
        "        [1] low: Low\n"
        "        [2] high: High\n"
        "    END VALUES\n"
        "END FIELD\n"
    )
    nodes = _parse_nodes(text, "template.synt")
    field_spec = next(n for n in nodes if hasattr(n, "name") and n.name == "level")
    assert field_spec.values[0].index == 1
    assert field_spec.values[1].label == "high"


def test_parse_topic_field():
    text = (
        "TEMPLATE demo\n"
        "FIELD topic TYPE TOPIC SCOPE ONTOLOGY\n"
        "END FIELD\n"
    )
    nodes = _parse_nodes(text, "template.synt")
    field_spec = next(n for n in nodes if hasattr(n, "name") and n.name == "topic")
    assert field_spec.type.value == "TOPIC"


def test_keywords_case_insensitive():
    nodes = _parse_nodes(
        "source @ref2020\n"
        "    description: Text\n"
        "end source\n"
    )
    source = next(n for n in nodes if isinstance(n, SourceNode))
    assert source.bibref == "@ref2020"


def test_empty_lines_allowed():
    nodes = _parse_nodes(
        "\n\nSOURCE @ref2020\n"
        "    description: Text\n"
        "END SOURCE\n\n"
    )
    assert any(isinstance(n, SourceNode) for n in nodes)


def test_scientific_symbols_in_text():
    nodes = _parse_nodes(
        "ITEM @ref2020\n"
        "    quote: p<0.05 and n=2383\n"
        "END ITEM\n"
    )
    item = next(n for n in nodes if isinstance(n, ItemNode))
    assert "p<0.05" in item.quote


def test_syntax_error_unclosed_block(fixtures_dir: Path):
    with pytest.raises(SynesisSyntaxError):
        parse_file(fixtures_dir / "invalid_syntax" / "unclosed_block.syn")


def test_syntax_error_invalid_token(fixtures_dir: Path):
    with pytest.raises(SynesisSyntaxError):
        parse_file(fixtures_dir / "invalid_syntax" / "invalid_token.syn")
