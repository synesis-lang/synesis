"""
lex_tokens.py - Tokenizacao posicional tolerante a erro

Proposito:
    Expor o fluxo de tokens do lexer com posicoes de linha/coluna, para
    consumidores que precisam saber ONDE cada construto aparece no texto —
    colorizacao semantica (LSP), navegacao, ferramentas de analise.

    Substitui a reimplementacao de regex nos consumidores: como os tokens
    vem da gramatica, construtos novos (keywords, modificadores) propagam
    automaticamente, sem edicao de listas paralelas.

Diferencas em relacao a parse_string():
    - NUNCA levanta excecao. Documento invalido e o estado normal durante
      digitacao; retorna os tokens obtidos ate o ponto de falha.
    - NAO passa pelo parser (apenas lexer), portanto nao valida gramatica.
    - NAO normaliza TABs. parse_string() converte TAB->4 espacos para
      estabilizar o Indenter, mas isso DESLOCA as colunas: o editor conta
      um TAB como 1 caractere. Normalizar produziria posicoes erradas.

Exemplo de uso:
    from synesis import lex_tokens
    for tok in lex_tokens(source):
        print(tok.type, tok.line, tok.column, tok.value)

Notas de implementacao:
    - Posicoes sao 1-based (linha e coluna), como no protocolo LSP antes da
      conversao para 0-based feita pelo consumidor.
    - Tokens de controle do Indenter (_INDENT/_DEDENT) sao preservados: quem
      nao precisa deles filtra por tipo.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List

from synesis.parser.lexer import create_parser

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LexToken:
    """
    Token posicional independente do backend de parsing.

    Nao expoe o objeto Token do Lark de proposito: se o backend mudar, apenas
    lex_tokens() muda, e nao todos os consumidores (Adapter / ACL).
    """

    type: str
    value: str
    line: int          # 1-based
    column: int        # 1-based
    end_line: int      # 1-based
    end_column: int    # 1-based, exclusivo (aponta apos o ultimo caractere)


def lex_tokens(source: str) -> List[LexToken]:
    """
    Tokeniza `source` retornando tokens com posicao.

    Nunca levanta excecao. Se o lexer falhar (indentacao inconsistente,
    caractere inesperado), retorna os tokens obtidos ate o ponto da falha e
    registra o ponto de truncamento em nivel debug.

    Retornar parcial em vez de vazio e deliberado: durante a digitacao o
    documento fica invalido a maior parte do tempo, e descartar tudo faria a
    colorizacao piscar a cada tecla.
    """
    if not source:
        return []

    tokens: List[LexToken] = []
    parser = create_parser()

    try:
        for tok in parser.lex(source):
            tokens.append(
                LexToken(
                    type=str(tok.type),
                    value=str(tok.value),
                    line=tok.line,
                    column=tok.column,
                    end_line=tok.end_line,
                    end_column=tok.end_column,
                )
            )
    except Exception as exc:  # noqa: BLE001 - tolerancia e o contrato desta funcao
        # Observabilidade: silencio total transformaria uma falha real em
        # "colorizacao some sem motivo". Nao propagar, mas nao esconder.
        last = tokens[-1] if tokens else None
        position = f"linha {last.end_line}, coluna {last.end_column}" if last else "inicio"
        logger.debug(
            "lex_tokens: tokenizacao truncada em %s apos %d tokens (%s: %s)",
            position,
            len(tokens),
            type(exc).__name__,
            exc,
        )

    return tokens
