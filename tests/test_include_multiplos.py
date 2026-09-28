"""
test_include_multiplos.py - Varios arquivos, curingas e pastas nos INCLUDE do .synp

Cobre a Fase A do estudo synesis-planning/synesis/Estudo_Includes_Multiplos_Pastas_e_Lotes.md:

  - INCLUDE BIBLIOGRAPHY aceitava UM arquivo: uma segunda linha era ignorada em
    silencio, e curinga/pasta davam E063. Agora linhas, curingas e pastas se
    somam (arquivo, curinga ou pasta, em todos os tipos de INCLUDE);
  - chave repetida entre arquivos era sombreada em silencio (no .bib do coder e
    no dataset do compilador). Agora e E089, e vale a primeira ocorrencia;
  - curinga ou pasta sem nenhum .bib ganha texto proprio no E063;
  - a mesma regra vale para o lsp_adapter e para synesis.load().
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import synesis
from synesis.ast.results import (
    DuplicateKeyAcrossFiles,
    IncludePathEscapesProject,
    MissingBibliographyFile,
    MissingOntologyInclude,
    UnregisteredSource,
)
from synesis.compiler import SynesisCompiler
from synesis.exporters.json_export import build_json_payload
from synesis.lsp_adapter import _load_context_from_project
from synesis.parser.bib_loader import merge_bibliographies
from synesis.parser.paths import IncludeError, expand_include
from tests.conftest import ONTOLOGY_VALID, TEMPLATE_BASIC

BIB_A = """@article{alpha2020,
    author = {Alpha, Ana},
    title = {Primeiro},
    year = {2020}
}
"""

BIB_B = """@article{beta2021,
    author = {Beta, Bia},
    title = {Segundo},
    year = {2021}
}
"""


def _annotation(bibref: str) -> str:
    return (
        f"SOURCE @{bibref}\n"
        f"    summary: estudo {bibref}.\n"
        "END SOURCE\n\n"
        f"ITEM @{bibref}\n"
        "    citation: trecho literal.\n"
        "    memo: nota.\n"
        "    tag: Social_Cohesion\n"
        "END ITEM\n"
    )


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _project(tmp_path: Path, includes: str, bibrefs=("alpha2020", "beta2021")) -> Path:
    """Projeto com template, ontologia e anotacoes citando `bibrefs`; os .bib
    ficam a cargo de cada teste. `includes` sao as linhas INCLUDE BIBLIOGRAPHY."""
    _write(tmp_path / "template.synt", TEMPLATE_BASIC)
    _write(tmp_path / "ontology.syno", ONTOLOGY_VALID)
    _write(tmp_path / "annotations.syn", "\n".join(_annotation(b) for b in bibrefs))
    synp = tmp_path / "project.synp"
    _write(synp, (
        "PROJECT test\n"
        '    TEMPLATE "template.synt"\n'
        f"{includes}"
        '    INCLUDE ANNOTATIONS "annotations.syn"\n'
        '    INCLUDE ONTOLOGY "ontology.syno"\n'
        "END PROJECT\n"
    ))
    return synp


def _errors(result, error_type) -> list:
    return [e for e in result.validation_result.errors if isinstance(e, error_type)]


# ---------------------------------------------------------------------------
# BIBLIOGRAPHY: linhas, curinga e pasta se somam
# ---------------------------------------------------------------------------

def test_duas_linhas_bibliography_se_somam(tmp_path):
    """Antes a segunda linha era ignorada e @beta2021 virava E001."""
    _write(tmp_path / "fontes" / "a.bib", BIB_A)
    _write(tmp_path / "fontes" / "b.bib", BIB_B)
    synp = _project(tmp_path, (
        '    INCLUDE BIBLIOGRAPHY "fontes/a.bib"\n'
        '    INCLUDE BIBLIOGRAPHY "fontes/b.bib"\n'
    ))

    result = SynesisCompiler(synp).compile()

    assert not _errors(result, UnregisteredSource)
    assert set(result.bibliography) == {"alpha2020", "beta2021"}
    assert result.success


def test_curinga_bibliography_expande(tmp_path):
    _write(tmp_path / "fontes" / "a.bib", BIB_A)
    _write(tmp_path / "fontes" / "b.bib", BIB_B)
    synp = _project(tmp_path, '    INCLUDE BIBLIOGRAPHY "fontes/*.bib"\n')

    result = SynesisCompiler(synp).compile()

    assert set(result.bibliography) == {"alpha2020", "beta2021"}
    assert result.success


def test_pasta_bibliography_e_recursiva_e_filtra_extensao(tmp_path):
    """Pasta = busca recursiva pelos .bib; outros arquivos sao ignorados."""
    _write(tmp_path / "fontes" / "a.bib", BIB_A)
    _write(tmp_path / "fontes" / "docente" / "b.bib", BIB_B)
    _write(tmp_path / "fontes" / "leia-me.txt", "@article{intruso2000, title={x}}")
    synp = _project(tmp_path, '    INCLUDE BIBLIOGRAPHY "fontes"\n')

    result = SynesisCompiler(synp).compile()

    assert set(result.bibliography) == {"alpha2020", "beta2021"}
    assert result.success


def test_entrada_guarda_arquivo_e_linha_de_origem(tmp_path):
    _write(tmp_path / "fontes" / "a.bib", "\n\n" + BIB_A)
    synp = _project(tmp_path, '    INCLUDE BIBLIOGRAPHY "fontes"\n', bibrefs=("alpha2020",))

    entry = SynesisCompiler(synp).compile().bibliography["alpha2020"]

    assert entry["_source_file"] == "fontes/a.bib"
    assert entry["_source_line"] == 3


def test_pasta_sem_bib_e_e063_com_texto_proprio(tmp_path):
    (tmp_path / "vazia").mkdir()
    synp = _project(tmp_path, '    INCLUDE BIBLIOGRAPHY "vazia"\n')

    result = SynesisCompiler(synp).compile()

    errors = _errors(result, MissingBibliographyFile)
    assert len(errors) == 1
    assert errors[0].no_matches
    assert "nenhum arquivo" in errors[0].to_diagnostic()
    # declarada mas vazia: bibliografia {} (bibrefs continuam validados)
    assert result.bibliography == {}
    assert _errors(result, UnregisteredSource)


def test_curinga_sem_match_e_e063(tmp_path):
    synp = _project(tmp_path, '    INCLUDE BIBLIOGRAPHY "fontes/*.bib"\n')

    result = SynesisCompiler(synp).compile()

    errors = _errors(result, MissingBibliographyFile)
    assert len(errors) == 1 and errors[0].no_matches


def test_arquivo_ausente_mantem_e063_classico(tmp_path):
    synp = _project(tmp_path, '    INCLUDE BIBLIOGRAPHY "ausente.bib"\n')

    errors = _errors(SynesisCompiler(synp).compile(), MissingBibliographyFile)

    assert len(errors) == 1 and not errors[0].no_matches


def test_sem_include_bibliography_desliga_validacao(tmp_path):
    """Contrato de tres estados: sem INCLUDE BIBLIOGRAPHY, bibliografia None."""
    synp = _project(tmp_path, "")

    result = SynesisCompiler(synp).compile()

    assert result.bibliography is None
    assert not _errors(result, UnregisteredSource)


# ---------------------------------------------------------------------------
# E089: chave repetida entre arquivos
# ---------------------------------------------------------------------------

def test_chave_repetida_entre_bib_e_e089_e_vale_a_primeira(tmp_path):
    _write(tmp_path / "fontes" / "a.bib", BIB_A)
    _write(tmp_path / "fontes" / "b.bib", BIB_B + "\n" + BIB_A.replace("Primeiro", "Outro"))
    synp = _project(tmp_path, '    INCLUDE BIBLIOGRAPHY "fontes"\n')

    result = SynesisCompiler(synp).compile()

    errors = _errors(result, DuplicateKeyAcrossFiles)
    assert len(errors) == 1
    err = errors[0]
    assert err.CODE == "SYNESIS_E089"
    assert err.key == "alpha2020"
    assert err.first_file == "fontes/a.bib" and err.first_line == 1
    assert err.duplicate_file == "fontes/b.bib"
    assert err.location.file.name == "b.bib" and err.location.line == 7
    assert "fontes/a.bib:1" in err.to_diagnostic()
    # a primeira ocorrencia (ordem de caminho) e a que vale
    assert result.bibliography["alpha2020"]["title"] == "Primeiro"
    assert not result.success


def test_mesmo_arquivo_por_dois_includes_nao_e_duplicata(tmp_path):
    """Pasta e literal cobrindo o mesmo .bib: lido uma vez, sem E089."""
    _write(tmp_path / "fontes" / "a.bib", BIB_A)
    _write(tmp_path / "fontes" / "b.bib", BIB_B)
    synp = _project(tmp_path, (
        '    INCLUDE BIBLIOGRAPHY "fontes"\n'
        '    INCLUDE BIBLIOGRAPHY "fontes/a.bib"\n'
    ))

    result = SynesisCompiler(synp).compile()

    assert not _errors(result, DuplicateKeyAcrossFiles)
    assert result.success


def test_merge_bibliographies_ordem_e_duplicata():
    merged, dups = merge_bibliographies([("x.bib", BIB_A), ("y.bib", BIB_A.replace("Primeiro", "Z"))])

    assert merged["alpha2020"]["title"] == "Primeiro"
    assert [(d.key, d.first_file, d.duplicate_file) for d in dups] == [("alpha2020", "x.bib", "y.bib")]


# ---------------------------------------------------------------------------
# Contencao e determinismo
# ---------------------------------------------------------------------------

def test_curinga_de_bib_fora_do_projeto_e_e075(tmp_path):
    projeto = tmp_path / "projeto"
    _write(tmp_path / "fora" / "x.bib", BIB_A)
    synp = _project(projeto, '    INCLUDE BIBLIOGRAPHY "../fora/*.bib"\n')

    result = SynesisCompiler(synp).compile()

    assert _errors(result, IncludePathEscapesProject)
    assert "alpha2020" not in (result.bibliography or {})


def test_ordem_de_expansao_e_por_caminho(tmp_path):
    for nome in ("c.bib", "a.bib", "b.bib"):
        _write(tmp_path / "fontes" / nome, "")

    expansion = expand_include(tmp_path, "fontes", ".bib")

    assert [p.name for p in expansion.files] == ["a.bib", "b.bib", "c.bib"]
    assert expansion.kind == "directory"


def test_ordem_ignora_caixa_em_qualquer_sistema(tmp_path):
    """No Linux, sorted() poria `Kely.bib` antes de `face85.bib`; no Windows,
    depois. A ordem decide qual duplicata vale — tem de ser a mesma nos dois."""
    for nome in ("Kely.bib", "face85.bib", "Anderson.bib"):
        _write(tmp_path / "fontes" / nome, "")

    por_pasta = expand_include(tmp_path, "fontes", ".bib")
    por_curinga = expand_include(tmp_path, "fontes/*.bib")

    esperado = ["Anderson.bib", "face85.bib", "Kely.bib"]
    assert [p.name for p in por_pasta.files] == esperado
    assert [p.name for p in por_curinga.files] == esperado


def test_pasta_sem_extensao_declarada_e_not_a_file(tmp_path):
    (tmp_path / "pasta").mkdir()

    assert expand_include(tmp_path, "pasta").error is IncludeError.NOT_A_FILE


# ---------------------------------------------------------------------------
# ANNOTATIONS e ONTOLOGY por pasta/curinga; E061/E062
# ---------------------------------------------------------------------------

def test_anotacoes_e_ontologia_por_pasta_e_curinga(tmp_path):
    _write(tmp_path / "template.synt", TEMPLATE_BASIC)
    _write(tmp_path / "refs.bib", BIB_A + BIB_B)
    _write(tmp_path / "anotacoes" / "lote1" / "a.syn", _annotation("alpha2020"))
    _write(tmp_path / "anotacoes" / "lote2" / "b.syn", _annotation("beta2021"))
    _write(tmp_path / "ontologia.syno", ONTOLOGY_VALID)
    synp = tmp_path / "project.synp"
    _write(synp, (
        "PROJECT test\n"
        '    TEMPLATE "template.synt"\n'
        '    INCLUDE BIBLIOGRAPHY "refs.bib"\n'
        '    INCLUDE ANNOTATIONS "anotacoes"\n'
        '    INCLUDE ONTOLOGY "*.syno"\n'
        "END PROJECT\n"
    ))

    result = SynesisCompiler(synp).compile()

    assert result.stats.source_count == 2
    assert result.stats.ontology_count == 2
    # a ontologia na raiz esta coberta pelo curinga: sem E062 falso
    assert not [w for w in result.validation_result.errors if isinstance(w, MissingOntologyInclude)]
    assert result.success


# ---------------------------------------------------------------------------
# DATASET: linhas somadas e E089 no lugar da sobrescrita silenciosa
# ---------------------------------------------------------------------------

_DATASET_TEMPLATE = """
TEMPLATE demo

SOURCE FIELDS
    REQUIRED researcher_id ON DATASET "meta.id"
END SOURCE FIELDS

ITEM FIELDS
    REQUIRED quote
END ITEM FIELDS

FIELD researcher_id TYPE TEXT
    SCOPE SOURCE
    IDENTIFIES researcher
END FIELD

FIELD quote TYPE QUOTATION
    SCOPE ITEM
END FIELD
"""


def _dataset_project(tmp_path: Path, includes: str) -> Path:
    _write(tmp_path / "demo.synt", _DATASET_TEMPLATE)
    _write(tmp_path / "dados.syn", "SOURCE @rec-1\nEND SOURCE\nITEM @rec-1\n    quote: trecho\nEND ITEM\n")
    synp = tmp_path / "demo.synp"
    _write(synp, f'PROJECT demo\nTEMPLATE "demo.synt"\n{includes}INCLUDE ANNOTATIONS "dados.syn"\nEND PROJECT\n')
    return synp


def test_dataset_varias_linhas_se_somam(tmp_path):
    _write(tmp_path / "lote1" / "r1.toml", '[meta]\nid = "rec-1"\n')
    _write(tmp_path / "lote2" / "r2.toml", '[meta]\nid = "rec-2"\n')
    synp = _dataset_project(tmp_path, 'INCLUDE DATASET "lote1"\nINCLUDE DATASET "lote2/*.toml"\n')

    compiler = SynesisCompiler(synp)
    project, _ = compiler.parse_project()
    template = compiler.load_template(project)
    index, result = compiler.load_dataset_index(project, template)

    assert set(index) == {"rec-1", "rec-2"}
    assert not result.errors


def test_dataset_chave_repetida_e_e089_e_nao_sobrescreve(tmp_path):
    """Antes o compilador ficava com o ultimo .toml em silencio."""
    _write(tmp_path / "d" / "a.toml", '[meta]\nid = "rec-1"\nnome = "primeiro"\n')
    _write(tmp_path / "d" / "b.toml", '[meta]\nid = "rec-1"\nnome = "segundo"\n')
    synp = _dataset_project(tmp_path, 'INCLUDE DATASET "d"\n')

    result = SynesisCompiler(synp).compile()

    errors = _errors(result, DuplicateKeyAcrossFiles)
    assert len(errors) == 1
    assert errors[0].kind == "DATASET"
    assert errors[0].first_file == "d/a.toml" and errors[0].duplicate_file == "d/b.toml"
    assert result.dataset["rec-1"]["meta"]["nome"] == "primeiro"


# ---------------------------------------------------------------------------
# synesis.load (em memoria), exportacao JSON e lsp_adapter
# ---------------------------------------------------------------------------

_PROJECT_MEM = 'PROJECT t\nTEMPLATE "t.synt"\nINCLUDE BIBLIOGRAPHY "refs.bib"\nEND PROJECT\n'


def test_load_aceita_varios_bib():
    result = synesis.load(
        project_content=_PROJECT_MEM,
        template_content=TEMPLATE_BASIC,
        annotation_contents={"a.syn": _annotation("alpha2020") + _annotation("beta2021")},
        ontology_contents={"o.syno": ONTOLOGY_VALID},
        bibliography_contents={"a.bib": BIB_A, "b.bib": BIB_B},
    )

    assert set(result.bibliography) == {"alpha2020", "beta2021"}
    assert result.success


def test_load_reporta_e089():
    result = synesis.load(
        project_content=_PROJECT_MEM,
        template_content=TEMPLATE_BASIC,
        bibliography_contents={"a.bib": BIB_A, "b.bib": BIB_A},
    )

    codes = [e.CODE for e in result.validation_result.errors]
    assert "SYNESIS_E089" in codes


def test_load_forma_antiga_continua_valendo():
    result = synesis.load(
        project_content=_PROJECT_MEM,
        template_content=TEMPLATE_BASIC,
        annotation_contents={"a.syn": _annotation("alpha2020")},
        ontology_contents={"o.syno": ONTOLOGY_VALID},
        bibliography_content=BIB_A,
    )

    assert result.success
    assert result.bibliography["alpha2020"]["_source_file"] == "<bibliography>"


def test_load_recusa_as_duas_formas_juntas():
    with pytest.raises(ValueError):
        synesis.load(
            project_content=_PROJECT_MEM,
            template_content=TEMPLATE_BASIC,
            bibliography_content=BIB_A,
            bibliography_contents={"b.bib": BIB_B},
        )


def test_json_nao_exporta_campos_internos(tmp_path):
    _write(tmp_path / "fontes" / "a.bib", BIB_A)
    synp = _project(tmp_path, '    INCLUDE BIBLIOGRAPHY "fontes"\n', bibrefs=("alpha2020",))
    result = SynesisCompiler(synp).compile()

    payload = build_json_payload(result.linked_project, result.template, result.bibliography)
    entry = payload["bibliography"]["alpha2020"]

    assert entry["title"] == "Primeiro"
    assert not [k for k in entry if k.startswith("_")]
    json.dumps(payload)  # continua serializavel


def test_lsp_adapter_carrega_todos_os_bib(tmp_path):
    _write(tmp_path / "fontes" / "a.bib", BIB_A)
    _write(tmp_path / "fontes" / "extra" / "b.bib", BIB_B)
    synp = _project(tmp_path, '    INCLUDE BIBLIOGRAPHY "fontes"\n')
    project, _ = SynesisCompiler(synp).parse_project()

    context, errors = _load_context_from_project(tmp_path, project)

    assert not errors
    assert set(context.bibliography) == {"alpha2020", "beta2021"}
