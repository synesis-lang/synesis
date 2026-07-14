"""
bib_loader.py - Carregamento de bibliografia BibTeX/BibLaTeX

Proposito:
    Ler arquivos .bib, normalizar chaves e oferecer busca robusta.
    Inclui sugestoes por similaridade quando referencias faltam.

Componentes principais:
    - load_bibliography: carrega e normaliza entradas BibTeX
    - detect_malformed_entries: localiza entradas BibTeX em formato invalido
    - find_bibref: busca por chave com normalizacao
    - suggest_bibref: sugestoes por fuzzy matching

Dependencias criticas:
    - bibtexparser: parser de arquivos .bib
    - difflib: fuzzy matching de chaves

Exemplo de uso:
    from synesis.parser.bib_loader import load_bibliography, find_bibref
    bib = load_bibliography("refs.bib")
    entry = find_bibref(bib, "silva2023")

Notas de implementacao:
    - Chaves sempre normalizadas com lowercase + trim.
    - entry['_original_key'] preserva a chave original.

Gerado conforme: Especificacao Synesis v1.1
"""

from __future__ import annotations

import re
from difflib import get_close_matches
from pathlib import Path
from typing import Dict, Optional, TypedDict

import bibtexparser


class BibEntry(TypedDict, total=False):
    ID: str
    ENTRYTYPE: str
    title: str
    author: str
    year: str
    journal: str
    booktitle: str
    _original_key: str


def load_bibliography(path: Path | str) -> Dict[str, BibEntry]:
    """
    Carrega arquivo .bib do disco e retorna dicionario com chaves normalizadas.

    Args:
        path: Caminho para o arquivo .bib

    Returns:
        Dict mapeando chave normalizada (lowercase) para BibEntry
    """
    from synesis.parser.lexer import read_source_file

    content = read_source_file(path)
    return load_bibliography_from_string(content)


def load_bibliography_from_string(content: str) -> Dict[str, BibEntry]:
    """
    Carrega bibliografia a partir de string em memoria.

    Reutiliza a logica de load_bibliography() sem dependencia de I/O em disco.
    Ideal para uso em Jupyter Notebooks, LSP e testes.

    Args:
        content: Conteudo do arquivo .bib como string

    Returns:
        Dict mapeando chave normalizada (lowercase) para BibEntry

    Example:
        >>> bib = load_bibliography_from_string('''
        ...     @article{silva2023,
        ...         author = {Silva, Maria},
        ...         title = {Estudo sobre energia},
        ...         year = {2023}
        ...     }
        ... ''')
        >>> bib["silva2023"]["author"]
        'Silva, Maria'
    """
    bib_database = bibtexparser.loads(content)

    normalized: Dict[str, BibEntry] = {}
    for entry in bib_database.entries:
        original_key = entry.get("ID", "")
        key = original_key.lower().strip()
        if not key:
            continue
        entry["_original_key"] = original_key
        normalized[key] = entry
    return normalized


def detect_malformed_entries(content: str) -> list[tuple[str, int]]:
    """
    Localiza entradas BibTeX em formato invalido no conteudo de um .bib.

    O bibtexparser nao lanca excecao com entradas malformadas: blocos que nao
    casam com a sintaxe BibTeX caem no catch-all de "comentario implicito" e
    sao guardados em BibDatabase.comments em vez de BibDatabase.entries. Um
    bloco que comeca com `@` e foi parar em comments e, portanto, uma entrada
    que o parser nao reconheceu (ex: falta o tipo, a chave nao esta entre
    chaves, ou os campos usam `:` no lugar de `=`).

    Args:
        content: Conteudo do arquivo .bib como string

    Returns:
        Lista de tuplas (chave_suspeita, numero_da_linha), uma por entrada
        malformada. A linha e 1-indexed; 0 quando a chave nao e localizada.
    """
    bib_database = bibtexparser.loads(content)
    lines = content.splitlines()
    malformed: list[tuple[str, int]] = []

    # Caso 1: entradas sem tipo/chave que caíram nos comentários implícitos do parser
    for comment in bib_database.comments:
        for match in re.finditer(r"(?m)^[ \t]*@([A-Za-z][\w-]*)", comment):
            key = match.group(1)
            line_number = next(
                (
                    i
                    for i, line in enumerate(lines, start=1)
                    if re.match(rf"[ \t]*@{re.escape(key)}\b", line)
                ),
                0,
            )
            malformed.append((key, line_number))

    # Caso 2: entradas parseadas cuja chave começa com @ (ex: @book{@BibliaNVT,...})
    for entry in bib_database.entries:
        entry_id = entry.get("ID", "")
        if entry_id.startswith("@"):
            clean_key = entry_id.lstrip("@")
            line_number = next(
                (
                    i
                    for i, line in enumerate(lines, start=1)
                    if re.search(rf"@\w+\s*\{{\s*@{re.escape(clean_key)}\b", line, re.IGNORECASE)
                ),
                0,
            )
            malformed.append((clean_key, line_number))

    return malformed


def find_bibref(bibliography: Dict[str, BibEntry], bibref: str) -> Optional[BibEntry]:
    """Busca referencia com normalizacao automatica."""
    normalized = bibref.lower().strip()
    return bibliography.get(normalized)


def suggest_bibref(
    bibref: str,
    available_keys: list[str],
    max_suggestions: int = 3,
) -> list[str]:
    """
    Retorna chaves BibTeX similares usando fuzzy matching.
    """
    matches = get_close_matches(bibref, available_keys, n=max_suggestions, cutoff=0.6)
    return matches
