"""
lexer.py - Carregamento e execucao do parser Lark

Proposito:
    Ler a gramatica Synesis e expor funcoes de parsing para arquivos e strings.
    Centraliza a criacao do parser LALR com suporte a regex Unicode.

Componentes principais:
    - load_grammar: leitura do arquivo synesis.lark do pacote
    - create_parser: construcao do parser Lark
    - parse_file/parse_string: parsing com tratamento de erros

Dependencias criticas:
    - lark: parser LALR e excecoes de sintaxe
    - importlib.resources: acesso a dados do pacote

Exemplo de uso:
    from synesis.parser.lexer import parse_file
    tree = parse_file("projeto.synp")

Notas de implementacao:
    - Usa regex=True para suportar tokens com \\p{L}/\\p{N}.
    - Erros de sintaxe geram SynesisSyntaxError com SourceLocation.

Gerado conforme: Especificacao Synesis v1.1
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Optional

from lark import Lark, Tree
from lark.indenter import Indenter
from lark.exceptions import UnexpectedCharacters, UnexpectedToken

from synesis.ast.nodes import SourceLocation
from synesis.error_handler import create_pedagogical_error


@dataclass
class SynesisSyntaxError(Exception):
    """
    Erro de sintaxe com localizacao precisa.

    Attributes:
        message: descricao curta do erro
        location: localizacao no arquivo fonte
        expected: lista de tokens esperados (quando disponivel)
    """

    message: str
    location: SourceLocation
    expected: Optional[list[str]] = None

    def __str__(self) -> str:
        # A mensagem pedagógica já contém tudo necessário
        return f"{self.location}: {self.message}"


@lru_cache(maxsize=1)
def load_grammar() -> str:
    """Carrega o arquivo synesis.lark a partir do pacote synesis.grammar."""
    grammar_path = resources.files("synesis.grammar").joinpath("synesis.lark")
    return grammar_path.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def create_parser() -> Lark:
    """Cria o parser LALR com suporte a regex Unicode."""
    grammar_text = load_grammar()
    return Lark(
        grammar_text,
        parser="lalr",
        lexer="contextual",
        regex=True,
        maybe_placeholders=False,
        postlex=SynesisIndenter(),
        propagate_positions=True,
    )


class SynesisIndenter(Indenter):
    NL_type = "NEWLINE"
    INDENT_type = "_INDENT"
    DEDENT_type = "_DEDENT"
    OPEN_PAREN_types = []
    CLOSE_PAREN_types = []
    tab_len = 4


def parse_string(content: str, filename: str) -> Tree:
    """Parseia conteudo Synesis a partir de uma string."""
    parser = create_parser()
    try:
        return parser.parse(content)
    except UnexpectedToken as exc:
        # Gera mensagem pedagogica antes de lancar excecao
        pedagogical_msg = create_pedagogical_error(exc, content, filename)
        location = SourceLocation(file=Path(filename), line=exc.line, column=exc.column)
        expected = sorted(exc.expected) if exc.expected else None
        raise SynesisSyntaxError(
            message=pedagogical_msg,
            location=location,
            expected=expected,
        ) from exc
    except UnexpectedCharacters as exc:
        # Gera mensagem pedagogica antes de lancar excecao
        pedagogical_msg = create_pedagogical_error(exc, content, filename)
        location = SourceLocation(file=Path(filename), line=exc.line, column=exc.column)
        raise SynesisSyntaxError(
            message=pedagogical_msg,
            location=location,
        ) from exc


def parse_file(path: Path | str) -> Tree:
    """Parseia conteudo Synesis a partir de um arquivo."""
    file_path = Path(path)
    content = file_path.read_text(encoding="utf-8")
    return parse_string(content, str(file_path))
