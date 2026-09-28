"""
bib_loader.py - Carregamento de bibliografia BibTeX/BibLaTeX

Proposito:
    Ler arquivos .bib, normalizar chaves e oferecer busca robusta.
    Inclui sugestoes por similaridade quando referencias faltam.

Componentes principais:
    - parse_bibtex: parse compatível com bibtexparser 1.x e 2.x
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
from typing import Dict, Iterable, List, Optional, Tuple, TypedDict, cast

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


# bibtexparser 2.x trocou a API (parse_string/Library no lugar de
# loads/BibDatabase). parse_bibtex() isola a diferença: o resto do módulo — e o
# synesis-coder — recebe o mesmo formato com as duas versões.
_BIBTEXPARSER_V2 = hasattr(bibtexparser, "parse_string")


@dataclass(frozen=True)
class ParsedBibtex:
    """Resultado de parse_bibtex, idêntico nas versões 1.x e 2.x do bibtexparser.

    Attributes:
        entries: Entradas no formato 1.x — dict com `ID`, `ENTRYTYPE` (minúsculo)
            e os campos com nome em minúsculas —, na ordem do arquivo. Uma chave
            repetida no mesmo arquivo aparece duas vezes (quem monta o dict fica
            com a última, como sempre foi).
        comments: Texto dos blocos que o parser não reconheceu como entrada
            (comentários implícitos e explícitos); é onde uma entrada malformada
            vai parar.
    """

    entries: List[Dict[str, str]]
    comments: List[str]


def parse_bibtex(content: str) -> ParsedBibtex:
    """Parseia um .bib com o bibtexparser instalado, 1.x ou 2.x.

    Normaliza as duas diferenças que mudariam o resultado:
      - nomes de campo em minúsculas (a 2.x preserva a caixa: `Author`);
      - tipos de entrada não padrão (`@online`, `@dataset`, `@software`): a 1.x,
        com o parser padrão, os DESCARTAVA em silêncio ("not considered") — e o
        bibref virava E001. Aqui os dois lados os aceitam.

    Chave repetida no mesmo arquivo: a 2.x separa a repetição num bloco de erro;
    ela é devolvida como entrada, na posição em que aparece, para que a última
    ocorrência vença nas duas versões.
    """
    if _BIBTEXPARSER_V2:
        return _parse_bibtex_v2(content)

    from bibtexparser.bparser import BibTexParser

    database = bibtexparser.loads(content, parser=BibTexParser(ignore_nonstandard_types=False))
    return ParsedBibtex(entries=list(database.entries), comments=list(database.comments))


# Macros de mês que a 1.x pré-define (bibdatabase.COMMON_STRINGS).
_MONTH_STRINGS = {
    "jan": "January", "feb": "February", "mar": "March", "apr": "April",
    "may": "May", "jun": "June", "jul": "July", "aug": "August",
    "sep": "September", "oct": "October", "nov": "November", "dec": "December",
}
_CONTINUATION_INDENT = re.compile(r"\n[ \t]+")


def _parse_bibtex_v2(content: str) -> ParsedBibtex:
    """Caminho 2.x, reproduzindo o valor que a 1.x entrega.

    A 2.x com a pilha padrão difere da 1.x em quatro pontos, todos medidos:
    mantém a indentação das linhas de continuação (abstracts, títulos), não
    converte `\\r\\n`, não pré-define as macros de mês (`month = jan`) e não
    resolve concatenação (`pub # " Ltda"` chega cru). Por isso o parse é feito
    SEM middlewares, e o valor bruto é resolvido aqui com as regras da 1.x.
    """
    library = bibtexparser.parse_string(content.replace("\r\n", "\n"), parse_stack=[])

    strings: Dict[str, str] = dict(_MONTH_STRINGS)
    for string in library.strings:  # em ordem: uma @string pode usar as anteriores
        strings[string.key.lower()] = _resolve_value(string.value, strings)

    positioned: List[Tuple[int, Dict[str, str]]] = [
        (entry.start_line, _entry_from_v2(entry, strings)) for entry in library.entries
    ]
    comments = [block.comment for block in library.comments]
    for block in library.failed_blocks:
        duplicate = getattr(block, "ignore_error_block", None)
        if type(block).__name__ == "DuplicateBlockKeyBlock":
            # Chave repetida no mesmo arquivo: a 1.x devolvia as duas entradas.
            if duplicate is not None and hasattr(duplicate, "fields"):
                positioned.append((block.start_line, _entry_from_v2(duplicate, strings)))
        else:
            comments.append(block.raw)
    positioned.sort(key=lambda item: item[0])
    return ParsedBibtex(entries=[entry for _, entry in positioned], comments=comments)


def _entry_from_v2(entry, strings: Dict[str, str]) -> Dict[str, str]:
    """Entry do bibtexparser 2.x no formato de dict da 1.x.

    Inclusive a ORDEM das chaves: a 1.x devolve os campos na ordem inversa à do
    arquivo, seguidos de ENTRYTYPE e ID. O JSON exportado percorre a entrada
    nessa ordem — sem isto, o mesmo projeto geraria JSON diferente conforme a
    versão do bibtexparser instalada.
    """
    data: Dict[str, str] = {
        field.key.lower(): _resolve_value(field.value, strings)
        for field in reversed(entry.fields)
    }
    data["ENTRYTYPE"] = entry.entry_type.lower()
    data["ID"] = entry.key
    return data


def _resolve_value(raw: str, strings: Dict[str, str]) -> str:
    """Valor bruto da 2.x (`{..}`, `"..."`, macro, número, `a # b`) -> texto da 1.x."""
    parts = []
    for part in _split_concatenation(raw.strip()):
        if len(part) >= 2 and part[0] == "{" and part[-1] == "}":
            parts.append(part[1:-1])
        elif len(part) >= 2 and part[0] == '"' and part[-1] == '"':
            parts.append(part[1:-1])
        else:
            parts.append(strings.get(part.lower(), part))
    return _CONTINUATION_INDENT.sub("\n", "".join(parts))


def _split_concatenation(value: str) -> List[str]:
    """Divide `a # {b # c} # "d"` nos `#` de nível zero (fora de chaves e aspas)."""
    parts: List[str] = []
    depth = 0
    in_quotes = False
    start = 0
    for i, ch in enumerate(value):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif ch == '"' and depth == 0:
            in_quotes = not in_quotes
        elif ch == "#" and depth == 0 and not in_quotes:
            parts.append(value[start:i].strip())
            start = i + 1
    parts.append(value[start:].strip())
    return [part for part in parts if part]


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
    normalized: Dict[str, BibEntry] = {}
    for entry in parse_bibtex(content).entries:
        original_key = entry.get("ID", "")
        key = original_key.lower().strip()
        if not key:
            continue
        entry["_original_key"] = original_key
        normalized[key] = cast(BibEntry, entry)
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
    parsed = parse_bibtex(content)
    lines = content.splitlines()
    malformed: list[tuple[str, int]] = []

    # Caso 1: entradas sem tipo/chave que caíram nos comentários implícitos do parser
    for comment in parsed.comments:
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
    for entry in parsed.entries:
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
