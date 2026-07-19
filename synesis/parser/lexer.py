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

import threading
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Optional

from lark import Lark, Tree
from lark.exceptions import UnexpectedCharacters, UnexpectedToken
from lark.indenter import DedentError, Indenter

from synesis.ast.nodes import SourceLocation
from synesis.error_handler import create_pedagogical_error

# Teto de tamanho para arquivos-fonte. O LSP e um processo de longa duracao;
# sem limite, um .syn/.bib de varios GB (por engano ou gerado por LLM) e lido
# inteiro na memoria e trava o editor. 32 MB cobre qualquer projeto real com
# folga (o maior case study cabe em kilobytes).
MAX_SOURCE_BYTES = 32 * 1024 * 1024


class SourceFileTooLarge(OSError):
    """Arquivo-fonte excede MAX_SOURCE_BYTES."""


def read_source_file(path: Path | str) -> str:
    """Le um arquivo-fonte UTF-8 recusando arquivos acima do teto de tamanho.

    Ponto unico de leitura para .syn/.syno/.synp/.synt/.bib. Levanta
    SourceFileTooLarge (subclasse de OSError) para que os chamadores ja o tratem
    junto de FileNotFoundError/UnicodeDecodeError como UnreadableIncludedFile.
    """
    file_path = Path(path)
    size = file_path.stat().st_size  # levanta FileNotFoundError se ausente
    if size > MAX_SOURCE_BYTES:
        raise SourceFileTooLarge(
            f"arquivo tem {size / 1024 / 1024:.1f} MB, acima do limite de "
            f"{MAX_SOURCE_BYTES // 1024 // 1024} MB"
        )
    return file_path.read_text(encoding="utf-8")


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


class SynesisIndenter(Indenter):
    NL_type = "NEWLINE"
    INDENT_type = "_INDENT"
    DEDENT_type = "_DEDENT"
    OPEN_PAREN_types = []
    CLOSE_PAREN_types = []
    tab_len = 4


# threading.local: cada thread tem seu proprio parser, evitando race condition
# no estado mutavel do SynesisIndenter (indent_level, paren_level).
_thread_local = threading.local()


def create_parser() -> Lark:
    """
    Retorna parser LALR thread-local, criando-o na primeira chamada por thread.

    Cada thread recebe sua propria instancia do parser (incluindo SynesisIndenter),
    eliminando a race condition no estado mutavel do Indenter (indent_level,
    paren_level) quando o compilador processa arquivos em paralelo via
    ThreadPoolExecutor.

    Custo: ~4ms na primeira chamada por thread; zero nas subsequentes.
    """
    if not hasattr(_thread_local, "parser"):
        _thread_local.parser = _make_parser_instance()
    return _thread_local.parser


def _make_parser_instance() -> Lark:
    """Cria uma instancia do parser com SynesisIndenter proprio."""
    try:
        from lark import Token as _LarkToken

        # O modulo standalone define classes proprias (Tree, Token, excecoes) que
        # sao incompativeis com o Transformer e error handlers do Lark.
        # Substituimos pelas classes oficiais antes de instanciar o parser:
        #   - Tree/Token: para que isinstance() no Transformer funcione corretamente
        #   - UnexpectedToken/UnexpectedCharacters: para que os except em parse_string
        #     capturem os erros lancados pelo parser standalone
        from lark import Tree as _LarkTree
        from lark.exceptions import UnexpectedCharacters as _UC
        from lark.exceptions import UnexpectedToken as _UT

        import synesis.grammar.synesis_standalone as _sa
        _sa.Tree = _LarkTree
        _sa.Token = _LarkToken
        _sa.UnexpectedToken = _UT
        _sa.UnexpectedCharacters = _UC
        return _sa.Lark_StandAlone(postlex=SynesisIndenter())
    except ImportError:
        # Fallback: compilar da gramatica (modo desenvolvimento ou standalone ausente)
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


def parse_string(content: str, filename: str) -> Tree:
    """Parseia conteudo Synesis a partir de uma string."""
    parser = create_parser()
    # Normaliza TABs para 4 espacos para evitar comportamento inconsistente
    # do Indenter quando arquivos misturam TAB e espacos na indentacao.
    if "\t" in content:
        content = content.replace("\t", "    ")
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
    except DedentError as exc:
        # Indentacao inconsistente (fechar um bloco numa coluna que nao alinha
        # com nenhum nivel aberto). E erro comum de usuario, mas o DedentError
        # do Lark nao carrega linha/coluna nem passa pelo error_handler: sem
        # este except, vazava cru pela API publica.
        line, column = _locate_dedent_failure(content)
        raise SynesisSyntaxError(
            message=_dedent_error_message(exc, content, line),
            location=SourceLocation(file=Path(filename), line=line, column=column),
        ) from exc


def _locate_dedent_failure(content: str) -> tuple[int, int]:
    """
    Descobre onde a indentacao quebrou.

    O DedentError do Lark nao carrega posicao. Re-tokenizar com lex_tokens()
    (que trunca no ponto da falha em vez de levantar) revela ate onde o lexer
    chegou; a linha seguinte e a que nao alinha.
    """
    try:
        from synesis.parser.lex_tokens import lex_tokens

        tokens = lex_tokens(content)
        if tokens:
            ultimo = tokens[-1]
            return ultimo.end_line, max(1, ultimo.end_column)
    except Exception:  # noqa: BLE001 - localizacao e best-effort
        pass
    return 1, 1


def _dedent_error_message(exc: Exception, content: str, line: int) -> str:
    """Mensagem pedagogica para indentacao inconsistente."""
    linhas = content.splitlines()
    trecho = linhas[line - 1] if 0 < line <= len(linhas) else ""
    coluna_atual = len(trecho) - len(trecho.lstrip()) + 1 if trecho.strip() else 1

    return (
        f"Indentacao inconsistente na linha {line}.\n"
        f"\n"
        f"  {line} | {trecho}\n"
        f"\n"
        f"Esta linha esta indentada na coluna {coluna_atual}, que nao alinha com\n"
        f"nenhum bloco aberto. Cada nivel deve fechar na mesma coluna em que abriu.\n"
        f"\n"
        f"Verifique se:\n"
        f"  - a linha nao mistura TABs e espacos com outras do mesmo bloco;\n"
        f"  - o recuo corresponde a um nivel realmente aberto acima.\n"
        f"\n"
        f"(detalhe do parser: {exc})"
    )


def parse_file(path: Path | str) -> Tree:
    """Parseia conteudo Synesis a partir de um arquivo."""
    file_path = Path(path)
    content = read_source_file(file_path)
    return parse_string(content, str(file_path))
