"""
test_parser.py - Testes do parser e transformer Synesis

Cobre: parsing de blocos SOURCE/ITEM/ONTOLOGY, AST resultante,
       erros de sintaxe e normalizacao de valores.

Gerado conforme: Especificacao Synesis v1.1
"""

import pytest

import synesis
from synesis.ast.nodes import (
    ChainNode,
    FieldType,
    ItemNode,
    OntologyNode,
    Scope,
    SourceNode,
    TemplateNode,
)
from synesis.parser.lexer import SynesisSyntaxError
from synesis.parser.template_loader import load_template_from_string

# ===========================================================================
# Helpers
# ===========================================================================

def parse(content: str) -> list:
    return synesis.compile_string(content, "<test>")


def parse_nodes(content: str, node_type):
    return [n for n in parse(content) if isinstance(n, node_type)]


# ===========================================================================
# SOURCE
# ===========================================================================

class TestSourceParsing:

    def test_source_bibref_parsed(self):
        content = """\
SOURCE @smith2024
    summary: A simple description.
END SOURCE
"""
        sources = parse_nodes(content, SourceNode)
        assert len(sources) == 1
        assert sources[0].bibref == "@smith2024"

    def test_source_field_parsed(self):
        content = """\
SOURCE @smith2024
    summary: Study on resilience.
END SOURCE
"""
        sources = parse_nodes(content, SourceNode)
        assert "summary" in sources[0].fields
        assert sources[0].fields["summary"] == "Study on resilience."

    def test_source_location_set(self):
        content = """\
SOURCE @smith2024
    summary: A description.
END SOURCE
"""
        sources = parse_nodes(content, SourceNode)
        assert sources[0].location is not None
        assert sources[0].location.line >= 1

    def test_multiple_sources(self):
        content = """\
SOURCE @ref2024
    summary: First source.
END SOURCE

SOURCE @ref2023
    summary: Second source.
END SOURCE
"""
        sources = parse_nodes(content, SourceNode)
        assert len(sources) == 2
        bibrefs = {s.bibref for s in sources}
        assert "@ref2024" in bibrefs
        assert "@ref2023" in bibrefs


# ===========================================================================
# ITEM
# ===========================================================================

class TestItemParsing:

    def test_item_bibref_parsed(self):
        content = """\
ITEM @smith2024
    note: An analytical memo.
    code: SomeCode
END ITEM
"""
        items = parse_nodes(content, ItemNode)
        assert len(items) == 1
        assert items[0].bibref == "@smith2024"

    def test_item_quote_captured_via_quotation_field(self):
        # O campo 'quotation' é mapeado para item.quote pelo transformer
        content = """\
ITEM @ref2024
    quotation: The exact text from the source.
    note: My interpretation.
    code: MyCode
END ITEM
"""
        items = parse_nodes(content, ItemNode)
        assert items[0].quote == "The exact text from the source."

    def test_item_code_field_name(self):
        content = """\
ITEM @ref2024
    note: A memo.
    code: Social_Cohesion
END ITEM
"""
        items = parse_nodes(content, ItemNode)
        assert "Social_Cohesion" in items[0].codes

    def test_item_multiple_codes_comma_separated(self):
        content = """\
ITEM @ref2024
    note: A memo.
    code: Social_Cohesion, Collective_Action
END ITEM
"""
        items = parse_nodes(content, ItemNode)
        assert "Social_Cohesion" in items[0].codes
        assert "Collective_Action" in items[0].codes

    def test_item_note_captured(self):
        content = """\
ITEM @ref2024
    note: My analytical note here.
    code: SomeCode
END ITEM
"""
        items = parse_nodes(content, ItemNode)
        assert "My analytical note here." in items[0].notes

    def test_item_chain_parsed(self):
        content = """\
ITEM @ref2024
    chain: A -> INFLUENCES -> B
END ITEM
"""
        items = parse_nodes(content, ItemNode)
        assert len(items[0].chains) == 1
        chain = items[0].chains[0]
        assert isinstance(chain, ChainNode)
        assert "A" in chain.nodes
        assert "B" in chain.nodes
        assert "INFLUENCES" in chain.nodes

    def test_multiple_items(self):
        content = """\
ITEM @ref2024
    note: First memo.
    code: Code_A
END ITEM

ITEM @ref2024
    note: Second memo.
    code: Code_B
END ITEM
"""
        items = parse_nodes(content, ItemNode)
        assert len(items) == 2


# ===========================================================================
# ONTOLOGY
# ===========================================================================

class TestOntologyParsing:

    def test_ontology_concept_parsed(self):
        content = """\
ONTOLOGY Social_Cohesion
    definition: Degree of community trust.
    theme: Community_Resilience
END ONTOLOGY
"""
        ontologies = parse_nodes(content, OntologyNode)
        assert len(ontologies) == 1
        assert ontologies[0].concept == "Social_Cohesion"

    def test_ontology_field_stored(self):
        content = """\
ONTOLOGY MyCode
    definition: A clear definition of the code.
    theme: MyGroup
END ONTOLOGY
"""
        ontologies = parse_nodes(content, OntologyNode)
        assert "definition" in ontologies[0].fields

    def test_ontology_topic_field(self):
        content = """\
ONTOLOGY MyCode
    definition: A definition.
    theme: Thematic_Category
END ONTOLOGY
"""
        ontologies = parse_nodes(content, OntologyNode)
        assert "theme" in ontologies[0].fields
        assert ontologies[0].fields["theme"] == "Thematic_Category"

    def test_multiple_ontologies(self):
        content = """\
ONTOLOGY Code_A
    definition: First code definition.
    theme: Category_One
END ONTOLOGY

ONTOLOGY Code_B
    definition: Second code definition.
    theme: Category_Two
END ONTOLOGY
"""
        ontologies = parse_nodes(content, OntologyNode)
        assert len(ontologies) == 2
        concepts = {o.concept for o in ontologies}
        assert "Code_A" in concepts
        assert "Code_B" in concepts


# ===========================================================================
# TEMPLATE
# ===========================================================================

class TestTemplateParsing:

    def test_template_loads_field_specs(self):
        template_content = """\
TEMPLATE test

ITEM FIELDS
    REQUIRED citation
END ITEM FIELDS

FIELD citation TYPE QUOTATION
    SCOPE ITEM
END FIELD
"""
        template = load_template_from_string(template_content, "<test>")
        assert isinstance(template, TemplateNode)
        assert "citation" in template.field_specs

    def test_template_field_type(self):
        template_content = """\
TEMPLATE test

ITEM FIELDS
    REQUIRED citation
END ITEM FIELDS

FIELD citation TYPE QUOTATION
    SCOPE ITEM
END FIELD
"""
        template = load_template_from_string(template_content, "<test>")
        assert template.field_specs["citation"].type == FieldType.QUOTATION

    def test_template_field_scope(self):
        template_content = """\
TEMPLATE test

ITEM FIELDS
    REQUIRED citation
END ITEM FIELDS

FIELD citation TYPE QUOTATION
    SCOPE ITEM
END FIELD
"""
        template = load_template_from_string(template_content, "<test>")
        assert template.field_specs["citation"].scope == Scope.ITEM

    def test_template_required_fields(self):
        template_content = """\
TEMPLATE test

ITEM FIELDS
    REQUIRED citation
    OPTIONAL summary
END ITEM FIELDS

FIELD citation TYPE QUOTATION
    SCOPE ITEM
END FIELD

FIELD summary TYPE MEMO
    SCOPE ITEM
END FIELD
"""
        template = load_template_from_string(template_content, "<test>")
        assert "citation" in template.required_fields.get(Scope.ITEM, [])
        assert "summary" not in template.required_fields.get(Scope.ITEM, [])

    def test_template_chain_with_relations(self):
        template_content = """\
TEMPLATE test

ITEM FIELDS
    OPTIONAL chain
END ITEM FIELDS

FIELD chain TYPE CHAIN
    SCOPE ITEM
    ARITY >= 2
    RELATIONS
        INFLUENCES: Causal influence
        ENABLES: Enabling condition
    END RELATIONS
END FIELD
"""
        template = load_template_from_string(template_content, "<test>")
        chain_spec = template.field_specs["chain"]
        assert chain_spec.type == FieldType.CHAIN
        assert "INFLUENCES" in chain_spec.relations
        assert "ENABLES" in chain_spec.relations
        assert chain_spec.arity == ">= 2"


# ===========================================================================
# Normalizacao de nomes de campos
# ===========================================================================

class TestFieldNameNormalization:

    def test_uppercase_code_field_name_normalized(self):
        # CODE (all-caps) é normalizado para 'code' → vai para item.codes
        content = """\
ITEM @ref2024
    CODE: SomeCode
END ITEM
"""
        items = parse_nodes(content, ItemNode)
        assert len(items) == 1
        assert "SomeCode" in items[0].codes

    def test_mixed_case_field_name_preserved(self):
        content = """\
SOURCE @ref2024
    myField: Some value.
END SOURCE
"""
        sources = parse_nodes(content, SourceNode)
        fields = sources[0].fields
        assert "myField" in fields or "myfield" in fields


# ===========================================================================
# Erros de sintaxe
# ===========================================================================

class TestSyntaxErrors:

    def test_missing_end_raises_error(self):
        content = """\
SOURCE @ref2024
    summary: A description.
"""
        with pytest.raises(SynesisSyntaxError):
            parse(content)

    def test_empty_content_raises_error(self):
        with pytest.raises(Exception):
            parse("")

    def test_invalid_keyword_raises_error(self):
        content = "INVALID_BLOCK @ref\nEND INVALID_BLOCK\n"
        with pytest.raises(Exception):
            parse(content)
