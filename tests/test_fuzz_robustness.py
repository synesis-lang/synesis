"""
test_fuzz_robustness.py - Fuzzing de mutacao sobre fixtures reais

Motivacao: fixtures curados testam o que alguem pensou em testar. Este arquivo
testa o que ninguem pensou — muta arquivos validos e verifica que o compilador
degrada de forma previsivel.

O contrato exercitado e simples e forte:

    Para QUALQUER entrada, compile_string() ou compila, ou levanta
    SynesisSyntaxError. Nunca vaza excecao de biblioteca (lark.*, IndexError,
    AttributeError...) para o chamador.

Esse contrato importa porque a API e consumida por processos de longa duracao
(o LSP) e pela CLI: uma excecao crua vira traceback no terminal do usuario ou
derruba um handler do servidor.

Encontrado por este arquivo: `lark.indenter.DedentError` vazava em indentacao
inconsistente — erro comum de usuario. Corrigido em parse_string().

Determinismo: seeds fixas. Um caso novo que falhe deve ser promovido a teste
nomeado em test_parser.py, nao deixado so aqui.
"""

from __future__ import annotations

import random
from pathlib import Path

import pytest

import synesis
from synesis.parser.lexer import SynesisSyntaxError, create_parser

FIXTURES = Path(__file__).parent / "fixtures"

# Caracteres que exercitam a estrutura da linguagem (delimitadores, indentacao,
# operadores) em vez de bytes aleatorios — mutacoes mais proximas de erros reais.
_ALFABETO = "\n :@#->ABCabc\t,\"[]"

_SEEDS = (7, 11, 23)
_MUTACOES_POR_SEED = 250


def _fontes_reais() -> list[str]:
    """Conteudo de todas as fixtures .synt/.syn do repositorio."""
    arquivos = [
        p
        for p in FIXTURES.rglob("*")
        if p.suffix in {".syn", ".synt", ".syno", ".synp"}
    ]
    return [p.read_text(encoding="utf-8", errors="ignore") for p in arquivos[:12]]


def _mutar(base: str, rng: random.Random) -> str:
    s = list(base)
    if not s:
        return base
    for _ in range(rng.randint(1, 5)):
        i = rng.randrange(len(s))
        s[i] = rng.choice(_ALFABETO)
    return "".join(s)


@pytest.mark.parametrize("seed", _SEEDS)
def test_compile_string_nunca_vaza_excecao_de_biblioteca(seed):
    """
    Contrato: compile_string ou compila, ou levanta SynesisSyntaxError.

    Qualquer outro tipo indica um caminho de erro nao tratado — o usuario veria
    um traceback de biblioteca em vez de uma mensagem do compilador.
    """
    rng = random.Random(seed)
    fontes = _fontes_reais()
    assert fontes, "nenhuma fixture encontrada"

    vazamentos: list[tuple[str, str]] = []
    for _ in range(_MUTACOES_POR_SEED):
        mutado = _mutar(rng.choice(fontes), rng)
        try:
            synesis.compile_string(mutado, "fuzz.synt")
        except SynesisSyntaxError:
            pass  # contrato cumprido
        except Exception as exc:  # noqa: BLE001 - é isso que estamos caçando
            vazamentos.append((type(exc).__module__ + "." + type(exc).__name__, str(exc)[:80]))

    assert not vazamentos, (
        f"{len(vazamentos)} excecoes fora do contrato (seed={seed}): "
        f"{sorted(set(v[0] for v in vazamentos))}\n"
        f"exemplo: {vazamentos[0][1]}"
    )


@pytest.mark.parametrize("seed", _SEEDS)
def test_lexer_nunca_trava(seed):
    """
    O lexer alimenta a colorizacao semantica, chamada a cada tecla. Excecoes
    inesperadas ali apagam as cores do editor.
    """
    rng = random.Random(seed)
    parser = create_parser()
    fontes = _fontes_reais()

    inesperadas: list[str] = []
    for _ in range(_MUTACOES_POR_SEED):
        mutado = _mutar(rng.choice(fontes), rng)
        try:
            list(parser.lex(mutado))
        except Exception as exc:  # noqa: BLE001
            nome = type(exc).__name__
            # Erros lexicais legitimos: o lexer rejeitando entrada invalida
            if nome not in {
                "UnexpectedCharacters",
                "UnexpectedToken",
                "UnexpectedInput",
                "DedentError",
            }:
                inesperadas.append(nome)

    assert not inesperadas, f"lexer levantou {sorted(set(inesperadas))} (seed={seed})"


@pytest.mark.parametrize("seed", _SEEDS)
def test_lex_tokens_e_totalmente_tolerante(seed):
    """
    lex_tokens() promete NUNCA levantar — é a base da colorizacao. Aqui a
    tolerancia é absoluta, sem excecoes permitidas.
    """
    rng = random.Random(seed)
    fontes = _fontes_reais()

    for _ in range(_MUTACOES_POR_SEED):
        mutado = _mutar(rng.choice(fontes), rng)
        resultado = synesis.lex_tokens(mutado)  # não deve levantar
        assert isinstance(resultado, list)


# ---------------------------------------------- regressao encontrada por fuzz

def test_indentacao_inconsistente_gera_erro_pedagogico():
    """
    Regressao: `lark.indenter.DedentError` vazava cru pela API publica.

    parse_string() capturava UnexpectedToken e UnexpectedCharacters, mas nao
    DedentError — que nao carrega linha/coluna nem passa pelo error_handler.
    """
    src = "ITEM @x\n        a: 1\n    b: 2\nEND ITEM\n"

    with pytest.raises(SynesisSyntaxError) as info:
        synesis.compile_string(src, "t.syn")

    erro = info.value
    assert erro.location is not None
    assert erro.location.line == 3, "deve apontar a linha que nao alinha"
    assert "indenta" in str(erro).lower()


def test_indentacao_com_tab_e_espaco_misturados():
    """TAB e espaco no mesmo bloco: parse_string normaliza, nao deve vazar."""
    src = "ITEM @x\n\ttext: a\n    note: b\nEND ITEM\n"
    try:
        synesis.compile_string(src, "t.syn")
    except SynesisSyntaxError:
        pass  # aceitavel — o que nao pode e vazar outro tipo
