"""
test_error_coverage.py - Cobertura do catalogo de erros

Contexto: o compilador define 69 codigos SYNESIS_E/W/I. Cada um e uma
propriedade invariante da linguagem — "isto nao pode acontecer num projeto
valido". Uma auditoria encontrou 22 codigos (32%) sem nenhum teste: caminhos
que o usuario pode atingir e que ninguem exercitava.

Este arquivo tem dois papeis:

1. Testes nomeados para os codigos cujo gatilho foi confirmado empiricamente.
2. Um teste de inventario (`test_catalogo_de_erros_nao_regride`) que trava o
   numero de codigos sem cobertura, para que a divida nao cresca em silencio.

Por que inventario em vez de property-based (Hypothesis): cada codigo exige um
projeto Synesis estruturalmente especifico (template + anotacoes + ontologia
coerentes). Gerar isso aleatoriamente produziria quase sempre o mesmo punhado
de erros triviais (E020/E022) em vez dos casos raros. O gargalo aqui e
construir o gatilho certo, nao gerar volume.
"""

from __future__ import annotations

import inspect
import re
import subprocess
from pathlib import Path

import pytest

import synesis
import synesis.ast.results as results_module
from synesis.ast.results import ValidationError

from .conftest import (
    BIBLIOGRAPHY_BASIC,
    ONTOLOGY_VALID,
    PROJECT_CONTENT,
    TEMPLATE_BASIC,
)

TESTS_DIR = Path(__file__).parent

_SOURCE_ITEM_MINIMO = (
    "SOURCE @smith2024\n"
    "    summary: Estudo sobre resiliencia.\n"
    "END SOURCE\n"
    "ITEM @smith2024\n"
    "    citation: Trecho citado.\n"
    "END ITEM\n"
)


def compilar(
    annotations: str = _SOURCE_ITEM_MINIMO,
    template: str = TEMPLATE_BASIC,
    ontology: str = ONTOLOGY_VALID,
    project: str = PROJECT_CONTENT,
):
    """Compila um projeto em memoria e devolve o ValidationResult."""
    return synesis.load(
        project_content=project,
        template_content=template,
        annotation_contents={"annotations.syn": annotations},
        ontology_contents={"ontology.syno": ontology},
        bibliography_content=BIBLIOGRAPHY_BASIC,
    ).validation_result


def codigos(resultado) -> list[str]:
    """Todos os codigos emitidos (erros + warnings), como os testes de integracao."""
    return [e.CODE for e in resultado.errors] + [w.CODE for w in resultado.warnings]


# ------------------------------------------------- codigos confirmados

def test_e003_source_sem_items():
    """SOURCE declarado mas sem nenhum ITEM associado."""
    ann = "SOURCE @smith2024\n    summary: Sem items.\nEND SOURCE\n"
    assert "SYNESIS_E003" in codigos(compilar(annotations=ann))


def test_e022_nome_de_campo_desconhecido():
    """Campo que nao existe no template."""
    ann = (
        "SOURCE @smith2024\n    summary: x\nEND SOURCE\n"
        "ITEM @smith2024\n    campo_que_nao_existe: valor\nEND ITEM\n"
    )
    assert "SYNESIS_E022" in codigos(compilar(annotations=ann))


def test_w031_codigo_duplicado_no_mesmo_campo():
    """Mesmo codigo repetido num campo de lista."""
    ann = (
        "SOURCE @smith2024\n    summary: x\nEND SOURCE\n"
        "ITEM @smith2024\n"
        "    citation: q\n"
        "    tag: Social_Cohesion, Social_Cohesion\n"
        "END ITEM\n"
    )
    assert "SYNESIS_W031" in codigos(compilar(annotations=ann))


def test_e033_caractere_invalido_em_identificador():
    """Identificador com espaco/caractere fora de [letras, numeros, _ -]."""
    ann = (
        "SOURCE @smith2024\n    summary: x\nEND SOURCE\n"
        "ITEM @smith2024\n    tag: Social Cohesion\nEND ITEM\n"
    )
    assert "SYNESIS_E033" in codigos(compilar(annotations=ann))


# ------------------------------------------------------- inventario

def _codigos_definidos() -> dict[str, str]:
    """{codigo: nome_da_classe} para todo erro/warning do compilador."""
    encontrados: dict[str, str] = {}
    for nome, obj in vars(results_module).items():
        if (
            inspect.isclass(obj)
            and issubclass(obj, ValidationError)
            and obj is not ValidationError
        ):
            codigo = getattr(obj, "CODE", None)
            if codigo:
                encontrados[codigo] = nome
    return encontrados


def _codigos_citados_nos_testes() -> set[str]:
    """Codigos que aparecem em algum assert da suite."""
    saida = subprocess.run(
        ["grep", "-rho", "SYNESIS_[EWI][0-9]*", str(TESTS_DIR)],
        capture_output=True,
        text=True,
    ).stdout
    return set(saida.split())


# Divida conhecida: codigos sem teste no momento em que este inventario foi
# criado. Reduzir este numero e trabalho desejavel; aumenta-lo e regressao.
_LIMITE_SEM_COBERTURA = 15


def test_catalogo_de_erros_nao_regride():
    """
    Trava o tamanho da divida de cobertura do catalogo de erros.

    Falha se alguem adicionar um codigo novo sem teste. Ao cobrir codigos
    existentes, baixe `_LIMITE_SEM_COBERTURA` junto — o teste avisa quando isso
    e possivel.
    """
    definidos = _codigos_definidos()
    citados = _codigos_citados_nos_testes()
    sem_cobertura = sorted(c for c in definidos if c not in citados)

    assert len(sem_cobertura) <= _LIMITE_SEM_COBERTURA, (
        f"{len(sem_cobertura)} codigos sem teste (limite {_LIMITE_SEM_COBERTURA}). "
        f"Novos sem cobertura: {[f'{c} {definidos[c]}' for c in sem_cobertura]}"
    )

    if len(sem_cobertura) < _LIMITE_SEM_COBERTURA:
        pytest.fail(
            f"Cobertura melhorou: {len(sem_cobertura)} codigos sem teste. "
            f"Baixe _LIMITE_SEM_COBERTURA para {len(sem_cobertura)}."
        )


def test_todo_codigo_tem_formato_canonico():
    """SYNESIS_E/W/I seguido de 3 digitos — consumido por LSP e CLI."""
    padrao = re.compile(r"^SYNESIS_[EWI]\d{3}$")
    invalidos = [
        f"{codigo} ({classe})"
        for codigo, classe in _codigos_definidos().items()
        if not padrao.match(codigo)
    ]
    assert not invalidos, f"codigos fora do padrao: {invalidos}"


# Compartilhamentos de codigo ja existentes. Sao ambiguidade de diagnostico
# real — `SYNESIS_E064` nao distingue "projeto ausente" de "template ausente"
# de "projeto invalido" —, mas renumerar e mudanca quebra-contrato para LSP e
# CLI. Registrado aqui para nao crescer sem decisao explicita.
_CODIGOS_COMPARTILHADOS_CONHECIDOS = {
    "SYNESIS_E064": {"MissingProjectFile", "MissingTemplateFile", "InvalidProjectFile"},
}


def test_compartilhamento_de_codigo_nao_cresce():
    """
    Um codigo usado por varias classes torna o diagnostico ambiguo: o consumidor
    (LSP, CLI) nao consegue distinguir as situacoes pelo codigo.

    Este teste nao exige zero — trava o conjunto atual. Um compartilhamento novo
    deve ser decisao consciente, nao efeito colateral de copiar uma classe.
    """
    por_codigo: dict[str, set[str]] = {}
    for nome, obj in vars(results_module).items():
        if (
            inspect.isclass(obj)
            and issubclass(obj, ValidationError)
            and obj is not ValidationError
        ):
            codigo = getattr(obj, "CODE", None)
            if codigo:
                por_codigo.setdefault(codigo, set()).add(nome)

    compartilhados = {c: n for c, n in por_codigo.items() if len(n) > 1}
    assert compartilhados == _CODIGOS_COMPARTILHADOS_CONHECIDOS, (
        f"compartilhamento de codigos mudou.\n"
        f"  atual:    {compartilhados}\n"
        f"  esperado: {_CODIGOS_COMPARTILHADOS_CONHECIDOS}"
    )
