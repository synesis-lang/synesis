"""
bib_loader.py - Carregamento de bibliografia BibTeX/BibLaTeX

Proposito:
    Ler arquivos .bib, normalizar chaves e oferecer busca robusta.
    Inclui sugestoes por similaridade quando referencias faltam.

Componentes principais:
    - load_bibliography: carrega e normaliza entradas BibTeX
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
    file_path = Path(path)
    content = file_path.read_text(encoding="utf-8")
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
