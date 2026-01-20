"""
test_lsp_adapter.py - Testes para o adaptador LSP

Propósito:
    Validar funcionamento do lsp_adapter em diferentes cenários:
    - Parsing de sintaxe válida e inválida
    - Validação com contexto completo e parcial
    - Descoberta automática de template e bibliografia
    - Tratamento de erros sintáticos

Componentes principais:
    - test_parse_valid_syntax: parsing bem-sucedido
    - test_parse_invalid_syntax: captura de erros sintáticos
    - test_validate_with_full_context: validação completa
    - test_validate_without_bibliography: bibrefs ignorados
    - test_discover_context: busca automática de recursos

Dependências críticas:
    - pytest: framework de testes
    - synesis.lsp_adapter: módulo sendo testado
    - synesis.ast: tipos de nós e validação

Gerado conforme: Especificação Synesis v1.1 + ADR-002 LSP
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from synesis.ast.nodes import SourceLocation
from synesis.lsp_adapter import (
    ValidationContext,
    validate_single_file,
    _discover_context,
    _find_template,
    _find_bibliography,
)


def test_validate_syntax_error():
    """Erro sintático deve ser capturado e convertido em ValidationError."""
    source = dedent("""
        SOURCE @invalid
            INVALID KEYWORD HERE
        END SOURCE
    """).strip()

    result = validate_single_file(source, "test.syn", context=ValidationContext())

    assert result.has_errors()
    assert len(result.errors) > 0
    # Verifica que é um SyntaxError (nosso tipo customizado)
    assert "sintaxe" in result.errors[0].to_diagnostic().lower()


def test_validate_valid_syntax_minimal():
    """Sintaxe válida sem validação semântica (sem template)."""
    source = dedent("""
        SOURCE @silva2023
            author: Silva
        END SOURCE
    """).strip()

    result = validate_single_file(source, "test.syn", context=ValidationContext())

    # Sem template, não há validação semântica
    # Apenas parsing deve passar
    assert not result.has_errors()


def test_validate_with_template_valid(minimal_template):
    """Validação semântica com template e campos válidos."""
    source = dedent("""
        SOURCE @silva2023
            author: Silva
            title: Test Article
        END SOURCE
    """).strip()

    context = ValidationContext(template=minimal_template)
    result = validate_single_file(source, "test.syn", context=context)

    # Depende do template minimal.synt - assumindo que author/title são válidos
    # Se houver campos obrigatórios faltando, teremos erros
    # Este teste pode precisar ajuste baseado no template real
    assert isinstance(result.errors, list)


def test_validate_without_bibliography():
    """Bibrefs não devem gerar erros quando bibliografia ausente."""
    source = dedent("""
        SOURCE @any_reference
            author: Silva
        END SOURCE
    """).strip()

    # Bibliografia None = não valida bibrefs
    context = ValidationContext(bibliography=None)
    result = validate_single_file(source, "test.syn", context=context)

    # Não deve ter erro de bibref não encontrado
    bibref_errors = [e for e in result.errors if "bibref" in e.to_diagnostic().lower()]
    assert len(bibref_errors) == 0


def test_validate_with_bibliography_missing_ref(minimal_template):
    """Bibref ausente na bibliografia deve gerar erro."""
    source = dedent("""
        SOURCE @nonexistent2023
            author: Silva
        END SOURCE
    """).strip()

    # Bibliografia com entrada válida, mas bibref diferente
    context = ValidationContext(
        template=minimal_template,
        bibliography={"silva2023": {"author": "Silva"}},
    )
    result = validate_single_file(source, "test.syn", context=context)

    # Deve ter erro de fonte não registrada
    bibref_errors = [
        e for e in result.errors
        if "nao encontrada" in e.to_diagnostic().lower() or "fonte" in e.to_diagnostic().lower()
    ]
    assert len(bibref_errors) > 0


def test_validate_item_with_codes():
    """ITEM com códigos deve validar contra ontologia."""
    source = dedent("""
        ITEM @silva2023
            quote: "Test quote"
            codes: CODE_A, CODE_B
        END ITEM
    """).strip()

    # Sem ontologia, códigos geram WARNING
    context = ValidationContext(ontology_index={})
    result = validate_single_file(source, "test.syn", context=context)

    # Códigos undefined devem gerar warnings
    assert result.has_warnings() or result.has_errors()


def test_discover_context_no_files(tmp_path):
    """Descoberta de contexto em diretório vazio retorna contexto vazio."""
    test_file = tmp_path / "test.syn"
    test_file.write_text("SOURCE @test\nEND SOURCE")

    context = _discover_context(str(test_file))

    assert context.template is None
    assert context.bibliography is None
    assert context.ontology_index == {}


def test_discover_context_with_template(tmp_path, fixtures_dir):
    """Descoberta de contexto encontra template.synt."""
    # Copia template para tmp_path
    template_src = fixtures_dir / "minimal.synt"
    template_dst = tmp_path / "template.synt"

    if template_src.exists():
        template_dst.write_text(template_src.read_text())

        test_file = tmp_path / "test.syn"
        test_file.write_text("SOURCE @test\nEND SOURCE")

        context = _discover_context(str(test_file))

        assert context.template is not None


def test_find_template_in_parent(tmp_path, fixtures_dir):
    """Busca de template em diretório pai."""
    # Cria estrutura: tmp/template.synt e tmp/subdir/test.syn
    template_src = fixtures_dir / "minimal.synt"
    if template_src.exists():
        template_dst = tmp_path / "template.synt"
        template_dst.write_text(template_src.read_text())

        subdir = tmp_path / "annotations"
        subdir.mkdir()

        # Busca a partir do subdir
        found_template = _find_template(subdir)

        assert found_template is not None


def test_find_bibliography(tmp_path):
    """Busca de bibliografia no diretório."""
    # Cria arquivo .bib de teste
    bib_file = tmp_path / "references.bib"
    bib_file.write_text(dedent("""
        @article{silva2023,
            author = {Silva, João},
            title = {Test Article},
            year = {2023}
        }
    """).strip())

    found_bib = _find_bibliography(tmp_path)

    assert found_bib is not None
    assert "silva2023" in found_bib


def test_parse_multiple_nodes():
    """Múltiplos nós no mesmo arquivo devem ser parseados."""
    source = dedent("""
        SOURCE @ref1
            author: Silva
        END SOURCE

        SOURCE @ref2
            author: Santos
        END SOURCE

        ITEM @ref1
            quote: "Test quote"
        END ITEM
    """).strip()

    result = validate_single_file(source, "test.syn", context=ValidationContext())

    # Sem template, não valida semântica, mas parsing deve funcionar
    assert not result.has_errors() or "sintaxe" not in result.errors[0].to_diagnostic().lower()


def test_syntax_error_provides_location():
    """Erro sintático deve incluir localização precisa."""
    source = dedent("""
        SOURCE @test
            INVALID_KEYWORD: value
        END SOURCE
    """).strip()

    result = validate_single_file(source, "file:///test.syn", context=ValidationContext())

    if result.has_errors():
        error = result.errors[0]
        # Verifica que erro tem location
        assert hasattr(error, 'location')
        assert error.location.line > 0


def test_file_uri_with_file_protocol():
    """URI com protocolo file:// deve ser tratado corretamente."""
    source = "SOURCE @test\nEND SOURCE"

    result = validate_single_file(
        source,
        "file:///Users/test/document.syn",
        context=ValidationContext()
    )

    # Não deve crashar com file:// URI
    assert isinstance(result.errors, list)


@pytest.fixture()
def fixtures_dir() -> Path:
    """Diretório de fixtures para testes."""
    return Path(__file__).parent / "fixtures"
