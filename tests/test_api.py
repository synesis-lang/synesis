"""
test_api.py - Testes da API em memoria synesis.load()

Cobre: compilacao completa, erros semanticos, warnings, stats e exportacao.
       to_diagnostics(verbose=False): formato compacto para o usuario pesquisador.

Gerado conforme: Especificacao Synesis v1.1
"""

import pytest

import synesis
from synesis.api import MemoryCompilationResult
from tests.conftest import (
    BIBLIOGRAPHY_BASIC,
    PROJECT_CONTENT,
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
        from synesis.ast.nodes import ItemNode, SourceNode
        assert any(isinstance(n, SourceNode) for n in nodes)
        assert any(isinstance(n, ItemNode) for n in nodes)


# ===========================================================================
# to_diagnostics(verbose=False) — formato compacto para o usuario pesquisador
# ===========================================================================

class TestDiagnosticsCompact:
    """Verifica que verbose=False agrega UndefinedCode e usa uma linha por erro."""

    # Template sem ontology para forcar UndefinedCode warnings
    _TEMPLATE_NO_ONTOLOGY = """\
TEMPLATE test_compact

SOURCE FIELDS
    OPTIONAL summary
END SOURCE FIELDS

ITEM FIELDS
    REQUIRED citation
    OPTIONAL tag
END ITEM FIELDS

FIELD summary TYPE TEXT
    SCOPE SOURCE
END FIELD

FIELD citation TYPE QUOTATION
    SCOPE ITEM
END FIELD

FIELD tag TYPE CODE
    SCOPE ITEM
END FIELD
"""

    def _load(self, annotations: str, ontology: str = "") -> "MemoryCompilationResult":
        import synesis
        kw = dict(
            project_content=PROJECT_CONTENT,
            template_content=self._TEMPLATE_NO_ONTOLOGY,
            annotation_contents={"annotations.syn": annotations},
            bibliography_content=BIBLIOGRAPHY_BASIC,
        )
        if ontology:
            kw["ontology_contents"] = {"ontology.syno": ontology}
        return synesis.load(**kw)

    def test_verbose_true_default_preserves_full_text(self):
        """verbose=True (default) deve conter o bloco pedagogico completo."""
        ann = """\
SOURCE @smith2024
    summary: A source.
END SOURCE
ITEM @smith2024
    citation: A quote.
    tag: Alpha
END ITEM
"""
        result = self._load(ann)
        diag = result.get_diagnostics()  # verbose=True por padrao
        assert "ONTOLOGY Alpha" in diag
        assert "END ONTOLOGY" in diag

    def test_compact_groups_undefined_codes(self):
        """verbose=False deve agrupar UndefinedCode por codigo, sem repeticao."""
        ann = """\
SOURCE @smith2024
    summary: A source.
END SOURCE
ITEM @smith2024
    citation: First quote.
    tag: Alpha
END ITEM
ITEM @smith2024
    citation: Second quote.
    tag: Alpha
END ITEM
ITEM @smith2024
    citation: Third quote.
    tag: Beta
END ITEM
"""
        result = self._load(ann)
        diag = result.get_diagnostics(verbose=False)

        # Deve ter exatamente uma linha para Alpha (nao duas)
        alpha_lines = [l for l in diag.splitlines() if "Alpha" in l]
        assert len(alpha_lines) == 1, f"Alpha deve aparecer 1 vez, achou: {alpha_lines}"

        # Deve indicar 2 ocorrencias de Alpha e 1 de Beta
        assert "2 ocorrencia" in diag or "2 ocorrencias" in diag
        assert "Beta" in diag

    def test_compact_has_dica_when_undefined_codes(self):
        """verbose=False deve incluir dica de synesis-coder ontology."""
        ann = """\
SOURCE @smith2024
    summary: A source.
END SOURCE
ITEM @smith2024
    citation: A quote.
    tag: UndefinedCode
END ITEM
"""
        result = self._load(ann)
        diag = result.get_diagnostics(verbose=False)
        assert "synesis-coder ontology" in diag

    def test_compact_no_redundant_ontology_block(self):
        """verbose=False NAO deve conter o bloco ONTOLOGY ... END ONTOLOGY como exemplo."""
        ann = """\
SOURCE @smith2024
    summary: A source.
END SOURCE
ITEM @smith2024
    citation: A quote.
    tag: SomeCode
END ITEM
"""
        result = self._load(ann)
        diag = result.get_diagnostics(verbose=False)
        assert "END ONTOLOGY" not in diag

    def test_compact_no_undefined_codes_no_dica(self):
        """verbose=False sem UndefinedCode nao deve conter a dica."""
        ann = """\
SOURCE @smith2024
    summary: A source.
END SOURCE
ITEM @smith2024
    citation: A quote.
    tag: Social_Cohesion
END ITEM
"""
        ontology = """\
ONTOLOGY Social_Cohesion
    definition: Degree of trust among community members.
END ONTOLOGY
"""
        result = self._load(ann, ontology=ontology)
        diag = result.get_diagnostics(verbose=False)
        assert "synesis-coder ontology" not in diag

    def test_verbose_default_true_unchanged(self):
        """Chamada sem kwarg deve ter comportamento identico a verbose=True."""
        ann = """\
SOURCE @smith2024
    summary: A source.
END SOURCE
ITEM @smith2024
    citation: A quote.
    tag: CodeA
END ITEM
"""
        result = self._load(ann)
        assert result.get_diagnostics() == result.get_diagnostics(verbose=True)
