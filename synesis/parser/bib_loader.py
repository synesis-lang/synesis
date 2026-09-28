"""
bib_loader.py - Carregamento de bibliografia BibTeX/BibLaTeX

Proposito:
    Ler arquivos .bib, normalizar chaves e oferecer busca robusta.
    Inclui sugestoes por similaridade quando referencias faltam.

Componentes principais:
    - load_bibliography: carrega e normaliza entradas BibTeX
    - merge_bibliographies: une varios .bib, com proveniencia e deteccao de
      chave duplicada entre arquivos (E089)
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
    - Campos iniciados por `_` sao internos (proveniencia): nao fazem parte da
      entrada BibTeX e nao sao exportados.

Gerado conforme: Especificacao Synesis v1.1
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import get_close_matches
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple, TypedDict

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
    _source_file: str  # arquivo .bib de origem (quando varios sao unidos)
    _source_line: int  # linha da entrada no arquivo; 0 quando nao localizada


@dataclass(frozen=True)
class DuplicateBibKey:
    """Mesma chave em dois arquivos .bib do projeto (base do E089)."""

    key: str
    first_file: str
    first_line: int
    duplicate_file: str
    duplicate_line: int


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


_ENTRY_START = re.compile(r"^[ \t]*@\w+\s*[{(]\s*([^,\s]+)\s*,")


def entry_lines(content: str) -> Dict[str, int]:
    """Mapa chave-normalizada -> linha (1-indexed) em que a entrada comeca.

    Uma unica passada pelo arquivo: linear no tamanho do .bib.
    """
    lines: Dict[str, int] = {}
    for i, line in enumerate(content.splitlines(), start=1):
        match = _ENTRY_START.match(line)
        if match:
            lines.setdefault(match.group(1).lower().strip(), i)
    return lines


def merge_bibliographies(
    parts: Iterable[Tuple[str, str]],
) -> Tuple[Dict[str, BibEntry], List[DuplicateBibKey]]:
    """Une varios .bib, na ordem recebida, registrando a origem de cada entrada.

    Args:
        parts: Pares (rotulo_do_arquivo, conteudo). O rotulo vai para
            `_source_file` e para as mensagens de erro.

    Returns:
        (bibliografia, duplicatas). Numa chave repetida entre arquivos vale a
        PRIMEIRA ocorrencia — a ordem e deterministica, e a duplicata e
        reportada (E089) em vez de sombreada em silencio.
    """
    merged: Dict[str, BibEntry] = {}
    duplicates: List[DuplicateBibKey] = []
    for label, content in parts:
        lines = entry_lines(content)
        for key, entry in load_bibliography_from_string(content).items():
            line = lines.get(key, 0)
            if key in merged:
                first = merged[key]
                if first.get("_source_file") != label:
                    duplicates.append(DuplicateBibKey(
                        key=entry.get("_original_key", key),
                        first_file=first.get("_source_file", ""),
                        first_line=first.get("_source_line", 0),
                        duplicate_file=label,
                        duplicate_line=line,
                    ))
                continue
            entry["_source_file"] = label
            entry["_source_line"] = line
            merged[key] = entry
    return merged, duplicates


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
