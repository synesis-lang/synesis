"""
test_lex_tokens.py - Contrato de synesis.lex_tokens()

Cobre as garantias que os consumidores (LSP, graph, coder) dependem:
  - posicoes corretas (1-based, TAB nao normalizado)
  - tolerancia total a documento invalido (nunca levanta)
  - blocos de texto livre nao produzem keywords
"""

from __future__ import annotations

import logging

import pytest

from synesis import LexToken, lex_tokens

# Tokens estruturais emitidos pelo Indenter/lexer que nao representam texto
# escrito pelo usuario. Filtrados quando o teste inspeciona o conteudo de uma
# linha especifica.
_CONTROLE = {"NEWLINE", "_INDENT", "_DEDENT"}


# ---------------------------------------------------------------- posicoes

def test_posicoes_sao_1_based():
    toks = lex_tokens("SOURCE @silva2020\nEND SOURCE\n")
    primeiro = toks[0]
    assert primeiro.type == "KW_SOURCE"
    assert primeiro.value == "SOURCE"
    assert primeiro.line == 1
    assert primeiro.column == 1


def test_end_position_preenchida():
    toks = lex_tokens("SOURCE @x\nEND SOURCE\n")
    kw = toks[0]
    # 'SOURCE' ocupa colunas 1..6; end_column e exclusivo
    assert kw.end_line == 1
    assert kw.end_column == 7


def test_colunas_batem_com_offset_real():
    """Coluna reportada deve indexar o texto original corretamente."""
    linha = "    SCOPE SOURCE"
    source = f"FIELD x TYPE TEXT\n{linha}\nEND FIELD\n"
    scope = next(t for t in lex_tokens(source) if t.type == "KW_SCOPE")
    assert scope.line == 2
    # column e 1-based: converter para indice 0-based ao fatiar
    assert linha[scope.column - 1 : scope.column - 1 + len(scope.value)] == "SCOPE"


def test_tab_nao_e_normalizado():
    """
    parse_string() converte TAB->4 espacos para estabilizar o Indenter, mas
    isso deslocaria as colunas: o editor conta um TAB como 1 caractere.
    lex_tokens() precisa reportar a coluna do texto original.
    """
    toks = lex_tokens("FIELD x TYPE TEXT\n\tSCOPE SOURCE\nEND FIELD\n")
    scope = next(t for t in toks if t.type == "KW_SCOPE")
    # Com TAB cru: coluna 2. Se fosse normalizado para 4 espacos, seria 5.
    assert scope.column == 2


# ------------------------------------------------- texto livre vs keywords

def test_description_nao_produz_keywords():
    """
    Regressao do bug que motivou esta API: dentro de DESCRIPTION o conteudo e
    texto livre, e a colorizacao por regex marcava FIELD/TYPE como keywords.
    """
    source = (
        "FIELD x TYPE TEXT\n"
        "    DESCRIPTION\n"
        "    Aqui FIELD e TYPE sao texto comum\n"
        "    END DESCRIPTION\n"
        "END FIELD\n"
    )
    toks = lex_tokens(source)
    linha3 = [t for t in toks if t.line == 3 and t.type not in _CONTROLE]
    assert len(linha3) == 1
    assert linha3[0].type == "TEXT_LINE"
    assert "FIELD" in linha3[0].value  # texto preservado, mas nao tokenizado


def test_guidelines_nao_produz_keywords():
    source = (
        "FIELD x TYPE TEXT\n"
        "    GUIDELINES\n"
        "        Use SCOPE e TYPE conforme o manual\n"
        "    END GUIDELINES\n"
        "END FIELD\n"
    )
    toks = lex_tokens(source)
    linha3 = [t for t in toks if t.line == 3 and t.type not in _CONTROLE]
    assert len(linha3) == 1
    assert linha3[0].type == "TEXT_LINE"


# ------------------------------------------- keywords novas da gramatica

@pytest.mark.parametrize(
    "source,esperado",
    [
        ("FIELD x TYPE TEXT\n    IDENTIFIES researcher\nEND FIELD\n", "KW_IDENTIFIES"),
        ("FIELD x TYPE TEXT\n    REFERS TO abstract\nEND FIELD\n", "KW_REFERS"),
    ],
)
def test_modificadores_multiprojeto_sao_tokens(source, esperado):
    """
    IDENTIFIES/REFERS TO existem na gramatica; devem aparecer como tokens
    proprios sem nenhum tratamento especial nesta funcao.
    """
    tipos = {t.type for t in lex_tokens(source)}
    assert esperado in tipos


# ------------------------------------------------------------ tolerancia

@pytest.mark.parametrize(
    "nome,source",
    [
        ("vazio", ""),
        ("so whitespace", "\n   \n\t\n"),
        ("bloco nao fechado", "FIELD x TYPE TEXT\n    SCOPE SOU"),
        ("lixo", "FIELD x TYPE TEXT\n    @@@ !!! ###\nEND FIELD\n"),
        ("palavra solta", "IDENT"),
        ("dedent inconsistente", "ITEM @x\n        a: 1\n    b: 2\nEND ITEM\n"),
        ("nul bytes", "ITEM @x\n    text: ok\n\x00\x01bad\nEND ITEM\n"),
    ],
)
def test_nunca_levanta(nome, source):
    """Documento invalido e o estado normal durante digitacao."""
    resultado = lex_tokens(source)
    assert isinstance(resultado, list)
    assert all(isinstance(t, LexToken) for t in resultado)


def test_vazio_retorna_lista_vazia():
    assert lex_tokens("") == []


def test_falha_retorna_tokens_parciais():
    """
    Ao truncar, devolver o que ja foi tokenizado (nao lista vazia): descartar
    tudo faria a colorizacao piscar a cada tecla durante a digitacao.
    """
    # Indentacao inconsistente faz o Indenter falhar apos alguns tokens
    toks = lex_tokens("ITEM @x\n        a: 1\n    b: 2\nEND ITEM\n")
    assert len(toks) > 0
    assert toks[0].type == "KW_ITEM"


def test_falha_e_registrada_em_debug(caplog):
    """Tolerancia nao pode virar failure masking silencioso."""
    with caplog.at_level(logging.DEBUG, logger="synesis.parser.lex_tokens"):
        lex_tokens("ITEM @x\n        a: 1\n    b: 2\nEND ITEM\n")
    assert any("truncada" in r.getMessage() for r in caplog.records)


# ----------------------------------------------------------- propagacao

def test_toda_keyword_da_gramatica_e_tokenizavel():
    """
    Contrato de propagacao: os terminais KW_* sao a fonte de verdade. Este
    teste ancora a expectativa de que a gramatica os expoe — se um consumidor
    (LSP) mapeia terminais para cores, novas keywords aparecem aqui primeiro.
    """
    from synesis.parser.lexer import create_parser

    terminais = {t.name for t in create_parser().terminals}
    keywords = {n for n in terminais if n.startswith("KW_")}
    # Ancoras: se algum destes sumir, houve mudanca incompativel na gramatica
    assert {"KW_SOURCE", "KW_ITEM", "KW_FIELD", "KW_END"} <= keywords
    assert {"KW_IDENTIFIES", "KW_REFERS", "KW_TO"} <= keywords
