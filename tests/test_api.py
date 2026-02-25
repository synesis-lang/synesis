"""
test_api.py - Testes da API em memoria synesis.load()

Cobre: compilacao completa, erros semanticos, warnings, stats e exportacao.

Gerado conforme: Especificacao Synesis v1.1
"""

import pytest
import synesis
from synesis.api import MemoryCompilationResult, CompilationStats
from synesis.parser.lexer import SynesisSyntaxError
from tests.conftest import (
    PROJECT_CONTENT,
    TEMPLATE_BASIC,
    BIBLIOGRAPHY_BASIC,
    ONTOLOGY_VALID,
)


# ===========================================================================
# Compilacao bem-sucedida
# ===========================================================================

class TestSuccessfulCompilation:

    def test_returns_memory_compilation_result(self, compiled_result):
        assert isinstance(compiled_result, MemoryCompilationResult)

    def test_success_flag_true(self, compiled_result):
        assert compiled_result.success is True

    def test_no_errors(self, compiled_result):
        assert not compiled_result.has_errors()

    def test_stats_source_count(self, compiled_result):
        assert compiled_result.stats.source_count == 1

    def test_stats_item_count(self, compiled_result):
        assert compiled_result.stats.item_count == 1

    def test_stats_ontology_count(self, compiled_result):
        assert compiled_result.stats.ontology_count == 2

    def test_stats_code_count(self, compiled_result):
        assert compiled_result.stats.code_count == 2

    def test_linked_project_not_none(self, compiled_result):
        assert compiled_result.linked_project is not None

    def test_template_loaded(self, compiled_result):
        assert compiled_result.template is not None

    def test_bibliography_loaded(self, compiled_result):
        assert compiled_result.bibliography is not None
        assert "smith2024" in compiled_result.bibliography

    def test_to_json_dict_returns_dict(self, compiled_result):
        data = compiled_result.to_json_dict()
        assert isinstance(data, dict)
        assert len(data) > 0

    def test_to_csv_tables_returns_dict(self, compiled_result):
        tables = compiled_result.to_csv_tables()
        assert isinstance(tables, dict)
        assert len(tables) > 0

    def test_csv_tables_contain_items(self, compiled_result):
        tables = compiled_result.to_csv_tables()
        assert "items" in tables

    def test_csv_items_has_rows(self, compiled_result):
        tables = compiled_result.to_csv_tables()
        headers, rows = tables["items"]
        assert len(rows) == 1

    def test_csv_sources_has_rows(self, compiled_result):
        tables = compiled_result.to_csv_tables()
        headers, rows = tables["sources"]
        assert len(rows) == 1

    def test_csv_ontologies_has_rows(self, compiled_result):
        tables = compiled_result.to_csv_tables()
        headers, rows = tables["ontologies"]
        assert len(rows) == 2


# ===========================================================================
# Compilacao sem conteudo opcional
# ===========================================================================

class TestMinimalCompilation:

    def test_no_annotations_succeeds(self, template_basic):
        result = synesis.load(
            project_content=PROJECT_CONTENT,
            template_content=template_basic,
        )
        assert isinstance(result, MemoryCompilationResult)
        assert result.stats.item_count == 0
        assert result.stats.source_count == 0

    def test_no_ontology_succeeds(self, template_basic, bibliography_basic):
        result = synesis.load(
            project_content=PROJECT_CONTENT,
            template_content=template_basic,
            bibliography_content=bibliography_basic,
        )
        assert result.stats.ontology_count == 0

    def test_json_dict_is_dict_without_data(self, template_basic):
        result = synesis.load(
            project_content=PROJECT_CONTENT,
            template_content=template_basic,
        )
        data = result.to_json_dict()
        assert isinstance(data, dict)


# ===========================================================================
# Erros semanticos
# ===========================================================================

class TestSemanticErrors:

    def test_undefined_bibref_generates_error(self, template_basic, bibliography_basic, ontology_valid):
        annotations = """\
SOURCE @nonexistent2099
    summary: This source does not exist in the bib file.
END SOURCE

ITEM @nonexistent2099
    citation: Some quote here.
    memo: Some memo here.
    tag: Social_Cohesion
END ITEM
"""
        result = synesis.load(
            project_content=PROJECT_CONTENT,
            template_content=template_basic,
            annotation_contents={"a.syn": annotations},
            ontology_contents={"o.syno": ontology_valid},
            bibliography_content=bibliography_basic,
        )
        assert result.has_errors()

    def test_missing_required_field_generates_error(self, template_basic, bibliography_basic, ontology_valid):
        # ITEM sem 'citation' (REQUIRED)
        annotations = """\
SOURCE @smith2024
    summary: Some source.
END SOURCE

ITEM @smith2024
    memo: Only a memo, no citation.
    tag: Social_Cohesion
END ITEM
"""
        result = synesis.load(
            project_content=PROJECT_CONTENT,
            template_content=template_basic,
            annotation_contents={"a.syn": annotations},
            ontology_contents={"o.syno": ontology_valid},
            bibliography_content=bibliography_basic,
        )
        assert result.has_errors()

    def test_undefined_code_generates_warning(self, template_basic, bibliography_basic, ontology_valid):
        annotations = """\
SOURCE @smith2024
    summary: A source.
END SOURCE

ITEM @smith2024
    citation: A quote.
    memo: A memo.
    tag: UndefinedCode_XYZ
END ITEM
"""
        result = synesis.load(
            project_content=PROJECT_CONTENT,
            template_content=template_basic,
            annotation_contents={"a.syn": annotations},
            ontology_contents={"o.syno": ontology_valid},
            bibliography_content=bibliography_basic,
        )
        assert result.has_warnings()

    def test_source_without_items_generates_warning(self, template_basic, bibliography_basic, ontology_valid):
        annotations = """\
SOURCE @smith2024
    summary: A source with no items.
END SOURCE
"""
        result = synesis.load(
            project_content=PROJECT_CONTENT,
            template_content=template_basic,
            annotation_contents={"a.syn": annotations},
            ontology_contents={"o.syno": ontology_valid},
            bibliography_content=bibliography_basic,
        )
        assert result.has_warnings()

    def test_orphan_item_generates_error(self, template_basic, bibliography_basic, ontology_valid):
        # ITEM com bibref diferente do SOURCE declarado
        annotations = """\
SOURCE @smith2024
    summary: A source.
END SOURCE

ITEM @jones2023
    citation: Quote from jones.
    memo: A memo.
    tag: Social_Cohesion
END ITEM
"""
        result = synesis.load(
            project_content=PROJECT_CONTENT,
            template_content=template_basic,
            annotation_contents={"a.syn": annotations},
            ontology_contents={"o.syno": ontology_valid},
            bibliography_content=bibliography_basic,
        )
        assert result.has_errors()


# ===========================================================================
# Erros sintaticos
# ===========================================================================

class TestSyntaxErrors:

    def test_invalid_annotation_syntax_raises_exception(self, template_basic):
        bad_content = "THIS IS NOT VALID SYNESIS SYNTAX !!!"
        with pytest.raises(Exception):
            synesis.load(
                project_content=PROJECT_CONTENT,
                template_content=template_basic,
                annotation_contents={"bad.syn": bad_content},
            )


# ===========================================================================
# compile_string
# ===========================================================================

class TestCompileString:

    def test_parse_source_block(self):
        content = """\
SOURCE @ref2024
    summary: A simple source.
END SOURCE
"""
        nodes = synesis.compile_string(content)
        from synesis.ast.nodes import SourceNode
        sources = [n for n in nodes if isinstance(n, SourceNode)]
        assert len(sources) == 1
        assert sources[0].bibref == "@ref2024"

    def test_parse_item_block(self):
        content = """\
ITEM @ref2024
    citation: A quote from the source.
    memo: An analytical memo.
    tag: SomeCode
END ITEM
"""
        nodes = synesis.compile_string(content)
        from synesis.ast.nodes import ItemNode
        items = [n for n in nodes if isinstance(n, ItemNode)]
        assert len(items) == 1

    def test_parse_ontology_block(self):
        content = """\
ONTOLOGY MyCode
    definition: Definition of the code.
    theme: MyGroup
END ONTOLOGY
"""
        nodes = synesis.compile_string(content)
        from synesis.ast.nodes import OntologyNode
        ontologies = [n for n in nodes if isinstance(n, OntologyNode)]
        assert len(ontologies) == 1
        assert ontologies[0].concept == "MyCode"

    def test_parse_multiple_blocks(self):
        content = """\
SOURCE @ref2024
    summary: A source.
END SOURCE

ITEM @ref2024
    citation: A quote.
    memo: A memo.
    tag: SomeCode
END ITEM
"""
        nodes = synesis.compile_string(content)
        from synesis.ast.nodes import SourceNode, ItemNode
        assert any(isinstance(n, SourceNode) for n in nodes)
        assert any(isinstance(n, ItemNode) for n in nodes)
