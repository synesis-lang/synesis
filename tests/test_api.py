"""
test_api.py - Testes para a API em memoria do Synesis

Proposito:
    Validar funcionalidade de synesis.load() e MemoryCompilationResult.
    Testa compilacao em memoria, exportacao e tratamento de erros.

Componentes testados:
    - load(): compilacao completa a partir de strings
    - compile_string(): parsing de arquivo unico
    - MemoryCompilationResult: exportacao em memoria (JSON, CSV, DataFrames)
    - load_template_from_string(): parsing de template
    - load_bibliography_from_string(): parsing de bibliografia

Gerado conforme: Especificacao Synesis v1.1
"""

from __future__ import annotations

import pytest

import synesis
from synesis.api import (
    compile_string,
    load,
    MemoryCompilationResult,
)
from synesis.parser.template_loader import load_template_from_string
from synesis.parser.bib_loader import load_bibliography_from_string


# =============================================================================
# Fixtures
# =============================================================================

MINIMAL_PROJECT = """
PROJECT TestProject
    TEMPLATE "template.synt"
END PROJECT
"""

MINIMAL_TEMPLATE = """
TEMPLATE TestTemplate
ITEM FIELDS
    REQUIRED quote
END ITEM FIELDS
FIELD quote TYPE QUOTATION SCOPE ITEM
END FIELD
"""

FULL_TEMPLATE = """
TEMPLATE FullTemplate

SOURCE FIELDS
    REQUIRED date
    OPTIONAL country
END SOURCE FIELDS

ITEM FIELDS
    REQUIRED quote
    OPTIONAL code
END ITEM FIELDS

ONTOLOGY FIELDS
    REQUIRED description
END ONTOLOGY FIELDS

FIELD date TYPE DATE SCOPE SOURCE
END FIELD

FIELD country TYPE TEXT SCOPE SOURCE
END FIELD

FIELD quote TYPE QUOTATION SCOPE ITEM
END FIELD

FIELD code TYPE CODE SCOPE ITEM
END FIELD

FIELD description TYPE TEXT SCOPE ONTOLOGY
END FIELD
"""

SAMPLE_ANNOTATIONS = """
SOURCE @silva2023
    date: 2023-05-15
    country: Brazil
END SOURCE

ITEM @silva2023
    quote: This is a sample quote from the source.
    code: Climate_Change
END ITEM

ITEM @silva2023
    quote: Another important excerpt from the research.
    code: Energy_Policy
END ITEM
"""

SAMPLE_ONTOLOGY = """
ONTOLOGY Climate_Change
    description: Fenomenos relacionados a mudancas climaticas globais
END ONTOLOGY

ONTOLOGY Energy_Policy
    description: Politicas publicas sobre energia
END ONTOLOGY
"""

SAMPLE_BIBLIOGRAPHY = """
@article{silva2023,
    author = {Silva, Maria},
    title = {Estudo sobre Energia Renovavel},
    journal = {Environmental Research},
    year = {2023}
}

@book{santos2022,
    author = {Santos, Joao},
    title = {Politicas Energeticas},
    publisher = {Editora ABC},
    year = {2022}
}
"""


# =============================================================================
# Tests: load_template_from_string
# =============================================================================

class TestLoadTemplateFromString:
    """Testes para load_template_from_string()."""

    def test_minimal_template(self):
        """Template minimo com apenas quote."""
        template = load_template_from_string(MINIMAL_TEMPLATE)

        assert template.name == "TestTemplate"
        assert "quote" in template.field_specs
        assert template.field_specs["quote"].type.value == "QUOTATION"

    def test_full_template(self):
        """Template completo com SOURCE, ITEM e ONTOLOGY fields."""
        template = load_template_from_string(FULL_TEMPLATE)

        assert template.name == "FullTemplate"
        assert "date" in template.field_specs
        assert "quote" in template.field_specs
        assert "description" in template.field_specs

        # Verifica REQUIRED fields
        from synesis.ast.nodes import Scope
        assert "date" in template.required_fields[Scope.SOURCE]
        assert "quote" in template.required_fields[Scope.ITEM]
        assert "description" in template.required_fields[Scope.ONTOLOGY]

    def test_invalid_syntax_raises_error(self):
        """Erro de sintaxe deve levantar excecao."""
        from synesis.parser.lexer import SynesisSyntaxError

        with pytest.raises(SynesisSyntaxError):
            load_template_from_string("INVALID CONTENT HERE")


# =============================================================================
# Tests: load_bibliography_from_string
# =============================================================================

class TestLoadBibliographyFromString:
    """Testes para load_bibliography_from_string()."""

    def test_load_valid_bibliography(self):
        """Carrega bibliografia valida."""
        bib = load_bibliography_from_string(SAMPLE_BIBLIOGRAPHY)

        assert "silva2023" in bib
        assert "santos2022" in bib
        assert bib["silva2023"]["author"] == "Silva, Maria"
        assert bib["santos2022"]["year"] == "2022"

    def test_empty_bibliography(self):
        """Bibliografia vazia retorna dict vazio."""
        bib = load_bibliography_from_string("")
        assert bib == {}

    def test_normalized_keys(self):
        """Chaves sao normalizadas para lowercase."""
        bib_content = """
        @article{SILVA2023,
            author = {Silva},
            year = {2023}
        }
        """
        bib = load_bibliography_from_string(bib_content)
        assert "silva2023" in bib  # lowercase


# =============================================================================
# Tests: compile_string
# =============================================================================

class TestCompileString:
    """Testes para compile_string()."""

    def test_parse_source(self):
        """Parseia SOURCE corretamente."""
        content = """SOURCE @test2023
    date: 2023-01-15
END SOURCE
"""
        nodes = compile_string(content, "test.syn")

        assert len(nodes) == 1
        assert nodes[0].bibref in ("test2023", "@test2023")
        assert nodes[0].fields.get("date") == "2023-01-15"

    def test_parse_item(self):
        """Parseia ITEM corretamente."""
        content = """ITEM @test2023
    quote: Sample text
END ITEM
"""
        nodes = compile_string(content, "test.syn")

        assert len(nodes) == 1
        assert nodes[0].bibref in ("test2023", "@test2023")
        assert nodes[0].quote == "Sample text"

    def test_parse_ontology(self):
        """Parseia ONTOLOGY corretamente."""
        content = """ONTOLOGY TestConcept
    description: Test description
END ONTOLOGY
"""
        nodes = compile_string(content, "test.syno")

        assert len(nodes) == 1
        assert nodes[0].concept == "TestConcept"
        assert nodes[0].description == "Test description"

    def test_parse_multiple_nodes(self):
        """Parseia multiplos nos."""
        nodes = compile_string(SAMPLE_ANNOTATIONS, "test.syn")

        sources = [n for n in nodes if hasattr(n, "bibref") and hasattr(n, "items")]
        items = [n for n in nodes if hasattr(n, "quote")]

        assert len(sources) == 1
        assert len(items) == 2


# =============================================================================
# Tests: load (compilacao completa)
# =============================================================================

class TestLoad:
    """Testes para load() - compilacao completa em memoria."""

    def test_minimal_load(self):
        """Compilacao minima apenas com projeto e template."""
        result = load(
            project_content=MINIMAL_PROJECT,
            template_content=MINIMAL_TEMPLATE,
        )

        assert isinstance(result, MemoryCompilationResult)
        assert result.template is not None
        assert result.template.name == "TestTemplate"

    def test_full_load_success(self):
        """Compilacao completa com sucesso."""
        result = load(
            project_content=MINIMAL_PROJECT,
            template_content=FULL_TEMPLATE,
            annotation_contents={"sample.syn": SAMPLE_ANNOTATIONS},
            ontology_contents={"concepts.syno": SAMPLE_ONTOLOGY},
            bibliography_content=SAMPLE_BIBLIOGRAPHY,
        )

        assert result.success is True
        assert result.has_errors() is False
        assert result.linked_project is not None
        assert result.stats.source_count == 1
        assert result.stats.item_count == 2
        assert result.stats.ontology_count == 2

    def test_load_with_validation_errors(self):
        """Compilacao com erros de validacao."""
        # Anotacao referencia fonte inexistente na bibliografia
        annotations_missing_source = """SOURCE @nonexistent2023
    date: 2023-01-01
END SOURCE

ITEM @nonexistent2023
    quote: Some text
END ITEM
"""

        result = load(
            project_content=MINIMAL_PROJECT,
            template_content=FULL_TEMPLATE,
            annotation_contents={"test.syn": annotations_missing_source},
            bibliography_content=SAMPLE_BIBLIOGRAPHY,
        )

        # Deve ter warnings (SOURCE sem bib entry)
        # mas ainda deve compilar
        assert result.linked_project is not None

    def test_load_statistics(self):
        """Verifica estatisticas de compilacao."""
        result = load(
            project_content=MINIMAL_PROJECT,
            template_content=FULL_TEMPLATE,
            annotation_contents={"sample.syn": SAMPLE_ANNOTATIONS},
            ontology_contents={"concepts.syno": SAMPLE_ONTOLOGY},
        )

        stats = result.stats
        assert stats.source_count == 1
        assert stats.item_count == 2
        assert stats.ontology_count == 2


# =============================================================================
# Tests: MemoryCompilationResult exportacao
# =============================================================================

class TestMemoryCompilationResultExport:
    """Testes para metodos de exportacao do MemoryCompilationResult."""

    @pytest.fixture()
    def compiled_result(self) -> MemoryCompilationResult:
        """Resultado de compilacao para testes de exportacao."""
        return load(
            project_content=MINIMAL_PROJECT,
            template_content=FULL_TEMPLATE,
            annotation_contents={"sample.syn": SAMPLE_ANNOTATIONS},
            ontology_contents={"concepts.syno": SAMPLE_ONTOLOGY},
            bibliography_content=SAMPLE_BIBLIOGRAPHY,
        )

    def test_to_json_dict(self, compiled_result: MemoryCompilationResult):
        """Exporta para dict JSON."""
        data = compiled_result.to_json_dict()

        assert isinstance(data, dict)
        assert data["version"] == "2.0"
        assert "export_metadata" in data
        assert "project" in data
        assert "corpus" in data
        assert "ontology" in data

        # Verifica corpus
        assert len(data["corpus"]) == 2  # 2 items

    def test_to_csv_tables(self, compiled_result: MemoryCompilationResult):
        """Exporta para tabelas CSV."""
        tables = compiled_result.to_csv_tables()

        assert isinstance(tables, dict)
        assert "sources" in tables
        assert "items" in tables
        assert "ontologies" in tables

        # Verifica estrutura
        headers, rows = tables["items"]
        assert isinstance(headers, list)
        assert isinstance(rows, list)
        assert len(rows) == 2  # 2 items
        assert "bibref" in headers
        assert "quote" in headers

    def test_to_json_dict_empty_on_error(self):
        """JSON dict vazio quando ha erros que impedem compilacao."""
        # Cria resultado vazio simulando falha
        from synesis.ast.results import ValidationResult

        result = MemoryCompilationResult(
            success=False,
            linked_project=None,
            validation_result=ValidationResult(),
            template=None,
            bibliography=None,
        )

        data = result.to_json_dict()
        assert data == {}

    def test_to_csv_tables_empty_on_error(self):
        """CSV tables vazio quando ha erros que impedem compilacao."""
        from synesis.ast.results import ValidationResult

        result = MemoryCompilationResult(
            success=False,
            linked_project=None,
            validation_result=ValidationResult(),
            template=None,
            bibliography=None,
        )

        tables = result.to_csv_tables()
        assert tables == {}


# =============================================================================
# Tests: synesis module imports
# =============================================================================

class TestModuleImports:
    """Testes para imports do modulo synesis."""

    def test_load_available(self):
        """synesis.load() esta disponivel."""
        assert hasattr(synesis, "load")
        assert callable(synesis.load)

    def test_compile_string_available(self):
        """synesis.compile_string() esta disponivel."""
        assert hasattr(synesis, "compile_string")
        assert callable(synesis.compile_string)

    def test_memory_compilation_result_available(self):
        """MemoryCompilationResult esta disponivel."""
        assert hasattr(synesis, "MemoryCompilationResult")

    def test_linked_project_available(self):
        """LinkedProject esta disponivel."""
        assert hasattr(synesis, "LinkedProject")

    def test_ast_nodes_available(self):
        """Nos AST estao disponiveis."""
        assert hasattr(synesis, "SourceNode")
        assert hasattr(synesis, "ItemNode")
        assert hasattr(synesis, "OntologyNode")
        assert hasattr(synesis, "TemplateNode")
        assert hasattr(synesis, "ProjectNode")

    def test_version_available(self):
        """Versao esta disponivel."""
        assert hasattr(synesis, "__version__")
        assert synesis.__version__ == "0.2.1"


# =============================================================================
# Tests: Pandas integration (optional)
# =============================================================================

class TestPandasIntegration:
    """Testes para integracao com Pandas (requer pandas instalado)."""

    @pytest.fixture()
    def compiled_result(self) -> MemoryCompilationResult:
        """Resultado de compilacao para testes."""
        return load(
            project_content=MINIMAL_PROJECT,
            template_content=FULL_TEMPLATE,
            annotation_contents={"sample.syn": SAMPLE_ANNOTATIONS},
            ontology_contents={"concepts.syno": SAMPLE_ONTOLOGY},
        )

    def test_to_dataframe(self, compiled_result: MemoryCompilationResult):
        """Exporta tabela para DataFrame."""
        pytest.importorskip("pandas")

        df = compiled_result.to_dataframe("items")

        assert len(df) == 2
        assert "bibref" in df.columns
        assert "quote" in df.columns

    def test_to_dataframes(self, compiled_result: MemoryCompilationResult):
        """Exporta todas as tabelas para DataFrames."""
        pytest.importorskip("pandas")

        dfs = compiled_result.to_dataframes()

        assert "items" in dfs
        assert "sources" in dfs
        assert "ontologies" in dfs

    def test_to_dataframe_invalid_table(self, compiled_result: MemoryCompilationResult):
        """Erro ao acessar tabela inexistente."""
        pytest.importorskip("pandas")

        with pytest.raises(KeyError):
            compiled_result.to_dataframe("nonexistent_table")
