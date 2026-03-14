"""
parse_cache.py - Cache por arquivo para compilacao incremental

Proposito:
    Cachear resultado de parse por arquivo (path, mtime) -> list[nodes],
    evitando re-parsing de arquivos nao modificados entre compilacoes no
    mesmo processo (ex: testes, LSP via lsp_adapter, API).

Funcoes:
    - get_cached_nodes: retorna nos cacheados se arquivo nao mudou, ou None
    - put_cached_nodes: armazena nos no cache
    - invalidate_cache: limpa todo o cache (ex: apos mudanca em .synt/.synp)

Uso:
    from synesis.parser.parse_cache import get_cached_nodes, put_cached_nodes

    cached = get_cached_nodes(path)
    if cached is None:
        nodes = parse_and_transform(path)
        put_cached_nodes(path, nodes)

Notas de implementacao:
    - Cache e global por processo (similar ao GlobalModelRepository do textX).
    - Chave: (str(path.resolve()), mtime_float).
    - Entradas antigas do mesmo arquivo sao removidas ao inserir nova versao.
    - Para CLI (cada invocacao e um novo processo), o cache nao persiste entre
      invocacoes. O beneficio e em cenarios multi-compilacao no mesmo processo.
    - Coordenacao LSP: chamar invalidate_cache() ao salvar .synt/.synp para
      garantir que nos cacheados nao sejam reutilizados com template desatualizado.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

# Cache global por processo: (path_str, mtime) -> list[nodes]
_parse_cache: dict[tuple[str, float], list] = {}


def get_cached_nodes(path: Path) -> Optional[List]:
    """Retorna nos cacheados se arquivo nao mudou desde o cache, ou None.

    Args:
        path: Caminho do arquivo a consultar.

    Returns:
        Lista de nos AST cacheados, ou None se cache miss ou erro de I/O.
    """
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None

    key = (str(path.resolve()), mtime)
    return _parse_cache.get(key)


def put_cached_nodes(path: Path, nodes: List) -> None:
    """Armazena nos no cache, removendo entradas antigas do mesmo arquivo.

    Args:
        path: Caminho do arquivo.
        nodes: Lista de nos AST a cachear.
    """
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return

    path_str = str(path.resolve())
    key = (path_str, mtime)

    # Remover entradas antigas do mesmo arquivo (mtime diferente)
    stale = [k for k in _parse_cache if k[0] == path_str and k[1] != mtime]
    for k in stale:
        del _parse_cache[k]

    _parse_cache[key] = nodes


def invalidate_cache() -> None:
    """Limpa todo o cache do processo.

    Deve ser chamado quando arquivos de contexto (.synt, .synp, .bib) mudam,
    para evitar que nos cacheados sejam reutilizados com template desatualizado.
    """
    _parse_cache.clear()
