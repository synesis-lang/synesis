"""
test_grammar_differential.py - Gramatica fonte vs parser gerado

O compilador roda o parser STANDALONE (`synesis/grammar/synesis_standalone.py`,
gerado) e cai para `synesis.lark` (fonte) apenas se o standalone faltar. Os dois
precisam concordar.

Modo de falha real que isto previne: editar `synesis.lark` sem regenerar o
standalone. A suite continua verde — porque o standalone antigo ainda parseia as
fixtures existentes — mas a mudanca da gramatica simplesmente nao tem efeito. O
sintoma aparece depois, longe da causa.

Differential testing pega isso: qualquer divergencia estrutural entre as duas
implementacoes falha, sem precisar que alguem antecipe o caso especifico.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from lark import Lark

from synesis.parser.lexer import SynesisIndenter, create_parser, load_grammar

FIXTURES = Path(__file__).parent / "fixtures"


def _parser_da_fonte() -> Lark:
    """Parser construido diretamente de synesis.lark (nao o standalone)."""
    return Lark(
        load_grammar(),
        parser="lalr",
        lexer="contextual",
        regex=True,
        maybe_placeholders=False,
        postlex=SynesisIndenter(),
        propagate_positions=True,
    )


def _tokens(parser: Lark, source: str):
    return [(t.type, str(t.value), t.line, t.column) for t in parser.lex(source)]


def _fontes_de_fixture() -> list[Path]:
    return sorted(
        p
        for p in FIXTURES.rglob("*")
        if p.suffix in {".syn", ".synt", ".syno", ".synp"}
    )


def test_gramatica_compila_sem_conflitos_lalr():
    """
    Verificacao exaustiva sobre a ESTRUTURA da gramatica (nao sobre exemplos):
    o gerador LALR recusa a build se houver conflito shift/reduce ou
    reduce/reduce nao resolvido. Mais forte que qualquer teste de fixture.
    """
    parser = _parser_da_fonte()  # levanta GrammarError se houver conflito
    assert parser is not None


def _assinatura(parser: Lark) -> dict[str, str]:
    """
    {nome_do_terminal: padrao} — a definicao, nao so o nome.

    Comparar apenas nomes nao basta: alterar o REGEX de um terminal existente
    (caso mais comum de edicao da gramatica) mantem o conjunto de nomes igual.
    Verificado empiricamente: trocar o padrao de KW_IDENTIFIES fazia os dois
    parsers divergirem de fato, e um teste por nomes passava mesmo assim.
    """
    return {t.name: str(t.pattern.to_regexp()) for t in parser.terminals}


def test_mesma_assinatura_de_terminais_na_fonte_e_no_standalone():
    """
    Terminal adicionado, removido ou com padrao alterado no .lark sem regenerar
    o standalone — o modo de falha que esta suite existe para pegar.
    """
    fonte = _assinatura(_parser_da_fonte())
    gerado = _assinatura(create_parser())

    if fonte == gerado:
        return

    so_fonte = sorted(set(fonte) - set(gerado))
    so_gerado = sorted(set(gerado) - set(fonte))
    padrao_mudou = sorted(
        f"{n}: .lark={fonte[n]!r} standalone={gerado[n]!r}"
        for n in set(fonte) & set(gerado)
        if fonte[n] != gerado[n]
    )

    pytest.fail(
        "synesis.lark e synesis_standalone.py divergem — regenere o standalone.\n"
        f"  so no .lark:      {so_fonte}\n"
        f"  so no standalone: {so_gerado}\n"
        f"  padrao alterado:  {padrao_mudou}"
    )


def test_mesmas_regras_na_fonte_e_no_standalone():
    """Regra de sintaxe adicionada/removida sem regenerar o standalone."""
    fonte = {str(r) for r in _parser_da_fonte().rules}
    gerado = {str(r) for r in create_parser().rules}

    assert fonte == gerado, (
        "conjunto de regras divergiu — regenere o standalone.\n"
        f"  so no .lark:      {sorted(fonte - gerado)}\n"
        f"  so no standalone: {sorted(gerado - fonte)}"
    )


@pytest.mark.parametrize(
    "fixture", _fontes_de_fixture(), ids=lambda p: f"{p.parent.name}/{p.name}"
)
def test_tokenizacao_identica_nas_fixtures(fixture: Path):
    """
    Mesma entrada, mesma sequencia de tokens (tipo, valor E posicao).

    Comparar posicao tambem importa: a colorizacao semantica e a navegacao
    dependem de linha/coluna, entao um deslocamento silencioso seria um bug
    visivel no editor.
    """
    source = fixture.read_text(encoding="utf-8", errors="ignore")

    fonte_parser = _parser_da_fonte()
    gerado_parser = create_parser()

    try:
        esperado = _tokens(fonte_parser, source)
    except Exception:
        # Fixture invalida de proposito (casos de erro): basta que as duas
        # implementacoes falhem juntas.
        with pytest.raises(Exception):
            _tokens(gerado_parser, source)
        return

    obtido = _tokens(gerado_parser, source)
    assert obtido == esperado, f"tokenizacao divergiu em {fixture.name}"
