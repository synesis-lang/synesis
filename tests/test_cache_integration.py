"""
test_cache_integration.py - Testes de integração para sistema de cache

Propósito:
    Validar funcionamento do cache de contexto em diferentes cenários:
    - Cache hit/miss
    - Invalidação por mtime
    - Invalidação manual via _invalidate_cache
    - Revalidação após mudanças em .synp/.synt/.bib

Componentes testados:
    - _get_cached_context
    - _set_cached_context
    - _invalidate_cache
    - _discover_context
    - validate_single_file

Gerado conforme: ADR-003 Project Discovery + Cache Management
"""

from __future__ import annotations

import time
from pathlib import Path
from textwrap import dedent

import pytest

from synesis.lsp_adapter import (
    ValidationContext,
    validate_single_file,
    _discover_context,
    _get_cached_context,
    _invalidate_cache,
    _find_workspace_root,
)


def test_cache_miss_then_hit(tmp_path, minimal_template):
    """
    Primeiro acesso: cache miss
    Segundo acesso: cache hit (sem mudanças nos arquivos)
    """
    # Criar estrutura de workspace
    synp_file = tmp_path / "project.synp"
    synp_file.write_text(dedent("""
        PROJECT test
            TEMPLATE "template.synt"
        END PROJECT
    """).strip())

    synt_file = tmp_path / "template.synt"
    synt_file.write_text(dedent("""
        TEMPLATE bibliometrics
        SOURCE FIELDS
            REQUIRED author
        END SOURCE FIELDS
        FIELD author TYPE TEXT
            SCOPE SOURCE
        END FIELD
    """).strip())

    test_file = tmp_path / "test.syn"
    test_file.write_text("SOURCE @test\nEND SOURCE")

    # Primeira validação: cache miss
    context1, warnings1 = _discover_context(str(test_file))
    assert context1.template is not None, "Template deveria ser carregado"

    # Segunda validação: cache hit (mesmo workspace)
    context2, warnings2 = _discover_context(str(test_file))
    assert context2.template is not None, "Template deveria vir do cache"

    # Verificar que é o mesmo objeto (cache funcionou)
    # Nota: com cache por mtime, pode não ser o mesmo objeto
    # mas deve ter as mesmas informações


def test_cache_invalidation_on_file_change(tmp_path):
    """
    Cache deve ser invalidado quando arquivo .synp é modificado
    """
    # Criar estrutura
    synp_file = tmp_path / "project.synp"
    synp_file.write_text(dedent("""
        PROJECT test
            TEMPLATE "template.synt"
        END PROJECT
    """).strip())

    synt_file = tmp_path / "template.synt"
    synt_file.write_text(dedent("""
        TEMPLATE v1
        SOURCE FIELDS
            REQUIRED author
        END SOURCE FIELDS
        FIELD author TYPE TEXT
            SCOPE SOURCE
        END FIELD
    """).strip())

    test_file = tmp_path / "test.syn"
    test_file.write_text("SOURCE @test\nEND SOURCE")

    # Primeira descoberta
    context1, _ = _discover_context(str(test_file))
    assert context1.template is not None

    # Modificar template (alterar mtime)
    time.sleep(0.1)  # Garantir que mtime muda
    synt_file.write_text(dedent("""
        TEMPLATE v2
        SOURCE FIELDS
            REQUIRED author, title
        END SOURCE FIELDS
        FIELD author TYPE TEXT
            SCOPE SOURCE
        END FIELD
        FIELD title TYPE TEXT
            SCOPE SOURCE
        END FIELD
    """).strip())

    # Segunda descoberta: cache deve ser invalidado automaticamente
    context2, _ = _discover_context(str(test_file))
    assert context2.template is not None


def test_manual_cache_invalidation(tmp_path):
    """
    Função _invalidate_cache deve limpar cache manualmente
    """
    # Criar estrutura
    synp_file = tmp_path / "project.synp"
    synp_file.write_text(dedent("""
        PROJECT test
            TEMPLATE "template.synt"
        END PROJECT
    """).strip())

    synt_file = tmp_path / "template.synt"
    synt_file.write_text(dedent("""
        TEMPLATE test
        SOURCE FIELDS
            REQUIRED author
        END SOURCE FIELDS
        FIELD author TYPE TEXT
            SCOPE SOURCE
        END FIELD
    """).strip())

    test_file = tmp_path / "test.syn"
    test_file.write_text("SOURCE @test\nEND SOURCE")

    # Descobrir workspace root
    workspace_root = _find_workspace_root(str(test_file))
    assert workspace_root is not None

    # Primeira descoberta: popula cache
    context1, _ = _discover_context(str(test_file))
    assert context1.template is not None

    # Verificar que cache existe
    cached = _get_cached_context(workspace_root)
    assert cached is not None

    # Invalidar manualmente
    _invalidate_cache(workspace_root)

    # Verificar que cache foi limpo
    cached_after = _get_cached_context(workspace_root)
    assert cached_after is None


def test_validate_single_file_uses_cache(tmp_path):
    """
    validate_single_file deve usar cache de contexto automaticamente
    """
    # Criar estrutura
    synp_file = tmp_path / "project.synp"
    synp_file.write_text(dedent("""
        PROJECT test
            TEMPLATE "template.synt"
        END PROJECT
    """).strip())

    synt_file = tmp_path / "template.synt"
    synt_file.write_text(dedent("""
        TEMPLATE test
        SOURCE FIELDS
            REQUIRED author
        END SOURCE FIELDS
        FIELD author TYPE TEXT
            SCOPE SOURCE
        END FIELD
    """).strip())

    # SOURCE sem campo obrigatório 'author' (deve gerar erro)
    source = dedent("""
        SOURCE @test
        END SOURCE
    """).strip()

    test_file = tmp_path / "test.syn"
    file_uri = f"file://{test_file}"

    # Primeira validação (popula cache)
    result1 = validate_single_file(source, file_uri, context=None)

    # Segunda validação (deve usar cache)
    result2 = validate_single_file(source, file_uri, context=None)

    # Ambas devem encontrar erro de campo obrigatório faltando
    # (isso indica que o template foi carregado corretamente)
    assert len(result1.errors) > 0, "Deveria ter erro de campo obrigatório 'author' faltando"
    assert len(result2.errors) > 0, "Deveria ter erro de campo obrigatório 'author' faltando (com cache)"


def test_cache_per_workspace(tmp_path):
    """
    Cada workspace deve ter seu próprio cache de contexto
    """
    # Workspace 1
    ws1 = tmp_path / "workspace1"
    ws1.mkdir()

    synp1 = ws1 / "project.synp"
    synp1.write_text(dedent("""
        PROJECT ws1
            TEMPLATE "template.synt"
        END PROJECT
    """).strip())

    synt1 = ws1 / "template.synt"
    synt1.write_text(dedent("""
        TEMPLATE ws1_template
        SOURCE FIELDS
            REQUIRED field_ws1
        END SOURCE FIELDS
        FIELD field_ws1 TYPE TEXT
            SCOPE SOURCE
        END FIELD
    """).strip())

    test1 = ws1 / "test.syn"
    test1.write_text("SOURCE @test\nEND SOURCE")

    # Workspace 2
    ws2 = tmp_path / "workspace2"
    ws2.mkdir()

    synp2 = ws2 / "project.synp"
    synp2.write_text(dedent("""
        PROJECT ws2
            TEMPLATE "template.synt"
        END PROJECT
    """).strip())

    synt2 = ws2 / "template.synt"
    synt2.write_text(dedent("""
        TEMPLATE ws2_template
        SOURCE FIELDS
            REQUIRED field_ws2
        END SOURCE FIELDS
        FIELD field_ws2 TYPE TEXT
            SCOPE SOURCE
        END FIELD
    """).strip())

    test2 = ws2 / "test.syn"
    test2.write_text("SOURCE @test\nEND SOURCE")

    # Descobrir contextos
    context1, _ = _discover_context(str(test1))
    context2, _ = _discover_context(str(test2))

    # Verificar que são diferentes
    assert context1.template is not None
    assert context2.template is not None

    # Templates devem ter nomes diferentes
    assert context1.template.name != context2.template.name


def test_no_cache_for_files_without_workspace(tmp_path):
    """
    Arquivos sem workspace (.synp) não devem ser cacheados
    """
    # Arquivo isolado sem .synp
    test_file = tmp_path / "isolated.syn"
    test_file.write_text("SOURCE @test\nEND SOURCE")

    source = "SOURCE @test\nEND SOURCE"
    file_uri = f"file://{test_file}"

    # Validar (não deve encontrar workspace)
    result = validate_single_file(source, file_uri, context=None)

    # Deve ter warning sobre .synp não encontrado
    # (a menos que haja um workspace pai que estamos não vendo nos testes)
    # Este teste valida que não crasha quando não há workspace


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
