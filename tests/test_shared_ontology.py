"""test_shared_ontology.py - Etapa 3: INCLUDE SHARED ONTOLOGY.

Cobre:
  - parsing de `INCLUDE SHARED ONTOLOGY` (IncludeNode.shared);
  - resolucao de path externo autorizado (`..`, rede, outro drive);
  - NAO-REGRESSAO: `INCLUDE ONTOLOGY` sem SHARED mantem ESCAPES_PROJECT (E075);
  - E084 (SharedOnlyForOntology): SHARED com tipo != ONTOLOGY.

A autorizacao mora na DECLARACAO (keyword), nao na geometria do path (D13) —
por isso rede/drive, que nenhuma ancora de pasta conseguiria autorizar, passam.
"""
import os
from pathlib import Path

from synesis.ast.nodes import ProjectNode
from synesis.compiler import SynesisCompiler
from synesis.parser.lexer import parse_string
from synesis.parser.paths import resolve_include
from synesis.parser.transformer import SynesisTransformer

FIXTURES = Path(__file__).parent / "fixtures"


def _parse_project(src: str) -> ProjectNode:
    out = SynesisTransformer(Path("p.synp")).transform(parse_string(src, "p.synp"))
    return next(x for x in out if isinstance(x, ProjectNode))


def _compile(rel: str):
    return SynesisCompiler(FIXTURES / rel).compile().validation_result


def _ecodes(r): return [e.CODE for e in r.errors]


# --------------------------------------------------------------------------
# Parsing / AST
# --------------------------------------------------------------------------

def test_shared_ontology_sets_flag():
    proj = _parse_project(
        'PROJECT p\n\nTEMPLATE "t.synt"\n'
        'INCLUDE SHARED ONTOLOGY "../shared/onto.syno"\n\nEND PROJECT\n'
    )
    inc = proj.includes[0]
    assert inc.include_type == "ONTOLOGY"
    assert inc.shared is True


def test_plain_ontology_shared_defaults_false():
    proj = _parse_project(
        'PROJECT p\n\nTEMPLATE "t.synt"\n'
        'INCLUDE ONTOLOGY "local.syno"\n\nEND PROJECT\n'
    )
    assert proj.includes[0].shared is False


def test_shared_serialized_in_to_dict():
    proj = _parse_project(
        'PROJECT p\n\nTEMPLATE "t.synt"\n'
        'INCLUDE SHARED ONTOLOGY "../x.syno"\n\nEND PROJECT\n'
    )
    assert proj.includes[0].to_dict()["shared"] is True


def test_shared_accepted_before_any_type_in_grammar():
    """Gramatica e permissiva; a restricao "so ONTOLOGY" e semantica (E084)."""
    proj = _parse_project(
        'PROJECT p\n\nTEMPLATE "t.synt"\n'
        'INCLUDE SHARED BIBLIOGRAPHY "b.bib"\n\nEND PROJECT\n'
    )
    assert proj.includes[0].include_type == "BIBLIOGRAPHY"
    assert proj.includes[0].shared is True


# --------------------------------------------------------------------------
# resolve_include — a autorizacao e a keyword, nao a geometria do path
# --------------------------------------------------------------------------

_BASE = FIXTURES / "T23-Shared-Ontology" / "projeto"


def test_resolve_include_shared_default_is_containment():
    """Default shared=False mantem o comportamento atual (9 call sites intactos)."""
    r = resolve_include(_BASE, "../shared/vocabulario.syno")
    assert r.error is not None
    assert r.error.name == "ESCAPES_PROJECT"


def test_resolve_include_shared_true_resolves_parent_escape():
    r = resolve_include(_BASE, "../shared/vocabulario.syno", shared=True)
    assert r.ok
    assert r.error is None


def test_shared_authorizes_network_and_drive_paths():
    """Rede/outro drive: nenhuma ancora de PASTA autorizaria — a keyword autoriza.

    O alvo nao existe nesta maquina, entao o esperado e NOT_FOUND (passou da
    contencao), nunca ESCAPES_PROJECT.

    Os literais sao escolhidos por PLATAFORMA porque "escapar do projeto" e uma
    propriedade do sistema de arquivos, nao do texto. `Z:/estudo/onto.syno` e
    absoluto no Windows, mas no POSIX e apenas um diretorio chamado `Z:` — cai
    DENTRO do projeto e o resultado legitimo passa a ser ESCAPES_PROJECT, nao
    NOT_FOUND. Usar o mesmo literal nos dois sistemas quebrava a suite em
    Linux/macOS enquanto passava no Windows.
    """
    externos = [r"\\servidor\equipe\ontologia.syno"]  # normaliza p/ /servidor/... : absoluto em ambos
    externos.append("Z:/estudo/onto.syno" if os.name == "nt" else "/mnt/equipe/onto.syno")

    for raw in externos:
        sem = resolve_include(_BASE, raw)
        com = resolve_include(_BASE, raw, shared=True)
        assert sem.error.name == "ESCAPES_PROJECT", raw
        assert com.error.name == "NOT_FOUND", raw


# --------------------------------------------------------------------------
# Compilacao ponta-a-ponta
# --------------------------------------------------------------------------

def test_shared_ontology_project_compiles_clean():
    """Ontologia externa carrega: os codes do .syn compartilhado sao validos."""
    r = _compile("T23-Shared-Ontology/projeto/t23.synp")
    assert r.errors == []
    assert r.warnings == []


def test_ontology_escape_without_keyword_still_e075():
    """NAO-REGRESSAO: sem SHARED, o mesmo path externo continua recusado."""
    r = _compile("T23-Shared-Escape-NoKeyword/t23.synp")
    assert "SYNESIS_E075" in _ecodes(r)


def test_shared_with_wrong_type_is_e084():
    r = _compile("T23-Shared-Wrong-Type/t23.synp")
    assert "SYNESIS_E084" in _ecodes(r)


def test_e084_message_mentions_type_and_ontology():
    r = _compile("T23-Shared-Wrong-Type/t23.synp")
    err = next(e for e in r.errors if e.CODE == "SYNESIS_E084")
    cli = err.to_cli_line()
    assert "BIBLIOGRAPHY" in cli
    assert "ONTOLOGY" in cli
