"""
test_include_paths.py - Regressoes de resolucao de caminhos declarados no .synp

Cobre os defeitos corrigidos em synesis/parser/paths.py:

  - arquivos declarados em INCLUDE que nao existem derrubavam a compilacao com
    FileNotFoundError (ANNOTATIONS e ONTOLOGY nunca tiveram a checagem que
    TEMPLATE e BIBLIOGRAPHY ja tinham);
  - arquivos ilegiveis (encoding invalido) ou com erro de sintaxe escapavam como
    excecao em vez de virar diagnostico;
  - caminhos com `..` liam arquivos fora da pasta do projeto;
  - separador `\\` num .synp escrito no Windows nao resolvia no Linux;
  - divergencia de caixa entre o .synp e o disco produzia E061 falso-positivo em
    FS case-insensitive (Windows/macOS) e FileNotFoundError no Linux — o mesmo
    projeto se comportava de tres formas diferentes nos tres sistemas.

Os testes de caixa e de separador rodam nos tres sistemas: a assercao e que o
comportamento seja o mesmo em todos.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from synesis.ast.results import (
    IncludePathEscapesProject,
    MissingAnnotationsFile,
    MissingAnnotationsInclude,
    MissingOntologyFile,
    UnreadableIncludedFile,
)
from synesis.compiler import SynesisCompiler
from synesis.parser.paths import (
    IncludeError,
    canonical_path,
    has_glob,
    normalize_include_path,
    path_to_uri,
    resolve_include,
    uri_to_path,
)
from tests.conftest import (
    ANNOTATIONS_VALID,
    BIBLIOGRAPHY_BASIC,
    ONTOLOGY_VALID,
    TEMPLATE_BASIC,
)


def _fs_is_case_insensitive(directory: Path) -> bool:
    """Detecta em runtime se o FS distingue caixa (Linux) ou nao (Windows/macOS)."""
    probe = directory / "synesis_case_probe.tmp"
    try:
        probe.write_text("", encoding="utf-8")
        return (directory / "SYNESIS_CASE_PROBE.TMP").exists()
    finally:
        probe.unlink(missing_ok=True)


@pytest.fixture
def case_insensitive_fs(tmp_path) -> bool:
    return _fs_is_case_insensitive(tmp_path)


def _build_project(tmp_path: Path, project_content: str) -> Path:
    """Escreve um projeto valido em tmp_path e devolve o caminho do .synp."""
    (tmp_path / "template.synt").write_text(TEMPLATE_BASIC, encoding="utf-8")
    (tmp_path / "references.bib").write_text(BIBLIOGRAPHY_BASIC, encoding="utf-8")
    (tmp_path / "annotations.syn").write_text(ANNOTATIONS_VALID, encoding="utf-8")
    (tmp_path / "ontology.syno").write_text(ONTOLOGY_VALID, encoding="utf-8")

    synp = tmp_path / "project.synp"
    synp.write_text(project_content, encoding="utf-8")
    return synp


def _project(*, template: str = "template.synt", annotations: str = "annotations.syn",
             ontology: str = "ontology.syno", extra: str = "") -> str:
    return (
        "PROJECT test\n"
        f'    TEMPLATE "{template}"\n'
        '    INCLUDE BIBLIOGRAPHY "references.bib"\n'
        f'    INCLUDE ANNOTATIONS "{annotations}"\n'
        f"{extra}"
        f'    INCLUDE ONTOLOGY "{ontology}"\n'
        "END PROJECT\n"
    )


def _errors_of(result, error_type) -> list:
    return [e for e in result.validation_result.errors if isinstance(e, error_type)]


# ---------------------------------------------------------------------------
# Arquivos declarados mas ausentes — nao devem levantar excecao
# ---------------------------------------------------------------------------

def test_missing_annotations_file_reports_error(tmp_path):
    """INCLUDE ANNOTATIONS de arquivo inexistente vira E073, nao FileNotFoundError."""
    synp = _build_project(tmp_path, _project(annotations="ausente.syn"))

    result = SynesisCompiler(synp).compile()

    errors = _errors_of(result, MissingAnnotationsFile)
    assert len(errors) == 1
    assert errors[0].filename == "ausente.syn"
    assert not result.success


def test_missing_ontology_file_reports_error(tmp_path):
    """INCLUDE ONTOLOGY de arquivo inexistente vira E074, nao FileNotFoundError."""
    synp = _build_project(tmp_path, _project(ontology="ausente.syno"))

    result = SynesisCompiler(synp).compile()

    errors = _errors_of(result, MissingOntologyFile)
    assert len(errors) == 1
    assert errors[0].filename == "ausente.syno"
    assert not result.success


def test_missing_annotations_still_compiles_remaining_files(tmp_path):
    """Um INCLUDE quebrado nao impede o parsing dos demais arquivos."""
    synp = _build_project(
        tmp_path,
        _project(
            annotations="ausente.syn",
            extra='    INCLUDE ANNOTATIONS "annotations.syn"\n',
        ),
    )

    result = SynesisCompiler(synp).compile()

    assert _errors_of(result, MissingAnnotationsFile)
    # o arquivo valido foi parseado apesar do INCLUDE quebrado
    assert result.stats.source_count == 1
    assert result.stats.item_count == 1


# ---------------------------------------------------------------------------
# Arquivos ilegiveis — nao devem escapar como excecao
# ---------------------------------------------------------------------------

def test_invalid_encoding_reports_error(tmp_path):
    """Arquivo incluido com encoding invalido vira E076, nao UnicodeDecodeError."""
    synp = _build_project(tmp_path, _project(annotations="corrompido.syn"))
    (tmp_path / "corrompido.syn").write_bytes(b"\xff\xfe\x00SOURCE @smith2024\n")

    result = SynesisCompiler(synp).compile()

    errors = _errors_of(result, UnreadableIncludedFile)
    assert len(errors) == 1
    assert errors[0].filename == "corrompido.syn"
    assert not result.success


def test_syntax_error_in_included_file_reports_error(tmp_path):
    """Erro de sintaxe em .syn incluido vira diagnostico, nao SynesisSyntaxError."""
    synp = _build_project(tmp_path, _project(annotations="invalido.syn"))
    (tmp_path / "invalido.syn").write_text("ISTO NAO E SYNESIS {{{\n", encoding="utf-8")

    result = SynesisCompiler(synp).compile()

    errors = _errors_of(result, UnreadableIncludedFile)
    assert len(errors) == 1
    assert errors[0].filename == "invalido.syn"
    assert not result.success


# ---------------------------------------------------------------------------
# Containment — caminhos nao podem escapar da pasta do projeto
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "escaping",
    ["../fora.syn", "../../etc/passwd", "sub/../../fora.syn"],
)
def test_include_outside_project_is_refused(tmp_path, escaping):
    """Caminho que escapa da pasta do projeto vira E075 e o arquivo nao e lido."""
    outside = tmp_path.parent / "fora.syn"
    outside.write_text(ANNOTATIONS_VALID, encoding="utf-8")

    synp = _build_project(tmp_path, _project(annotations=escaping))

    result = SynesisCompiler(synp).compile()

    assert _errors_of(result, IncludePathEscapesProject)
    assert not result.success


def test_subdirectory_include_is_allowed(tmp_path):
    """Containment recusa `..`, mas subpastas continuam validas."""
    subdir = tmp_path / "entrevistas"
    subdir.mkdir()
    (subdir / "e01.syn").write_text(ANNOTATIONS_VALID, encoding="utf-8")

    synp = _build_project(tmp_path, _project(annotations="entrevistas/e01.syn"))

    result = SynesisCompiler(synp).compile()

    assert not _errors_of(result, IncludePathEscapesProject)
    assert not _errors_of(result, MissingAnnotationsFile)
    assert result.stats.item_count == 1


@pytest.mark.parametrize("pattern", ["../*.syn", "../*.sy?", "../[af]ora.syn"])
def test_glob_include_cannot_escape_project(tmp_path, pattern):
    """`Path.glob` segue `..`; o glob de INCLUDE nao pode ler arquivos de fora.

    Regressao do bypass do guard de path-traversal pela via do glob: um arquivo
    fora do projeto casado por `../*.syn` era parseado e podia ser exfiltrado por
    qualquer exportador.
    """
    outside = tmp_path.parent / "afora.syn"
    outside.write_text(
        "SOURCE @segredo\n    summary: dados de fora.\nEND SOURCE\n", encoding="utf-8"
    )

    synp = _build_project(
        tmp_path,
        _project(
            annotations=pattern,
            extra='    INCLUDE ANNOTATIONS "annotations.syn"\n',
        ),
    )

    result = SynesisCompiler(synp).compile()

    assert _errors_of(result, IncludePathEscapesProject)
    if result.linked_project:
        bibrefs = {s.bibref.lstrip("@") for s in result.linked_project.sources.values()}
        assert "segredo" not in bibrefs


def test_glob_include_within_project_still_works(tmp_path):
    """O filtro de containment do glob nao afeta matches legitimos."""
    (tmp_path / "extra.syn").write_text(
        "SOURCE @jones2023\n    summary: valido.\nEND SOURCE\n", encoding="utf-8"
    )

    synp = _build_project(tmp_path, _project(annotations="*.syn"))

    result = SynesisCompiler(synp).compile()

    assert not _errors_of(result, IncludePathEscapesProject)
    assert result.stats.source_count >= 2


# ---------------------------------------------------------------------------
# DoS: leitura de arquivo sem limite de tamanho
# ---------------------------------------------------------------------------

def test_oversized_included_file_is_refused(tmp_path, monkeypatch):
    """Arquivo acima do teto de tamanho vira E076, nao carga integral na memoria."""
    from synesis.parser import lexer

    # Rebaixa o teto para nao precisar escrever um arquivo real gigante.
    monkeypatch.setattr(lexer, "MAX_SOURCE_BYTES", 1024)

    synp = _build_project(tmp_path, _project(annotations="grande.syn"))
    (tmp_path / "grande.syn").write_text(
        "SOURCE @smith2024\n    summary: " + ("x" * 4096) + "\nEND SOURCE\n",
        encoding="utf-8",
    )

    result = SynesisCompiler(synp).compile()

    errors = _errors_of(result, UnreadableIncludedFile)
    assert len(errors) == 1
    assert "grande.syn" == errors[0].filename


def test_read_source_file_enforces_limit(tmp_path, monkeypatch):
    """read_source_file levanta SourceFileTooLarge (subclasse de OSError)."""
    from synesis.parser import lexer

    monkeypatch.setattr(lexer, "MAX_SOURCE_BYTES", 16)
    big = tmp_path / "big.syn"
    big.write_text("x" * 64, encoding="utf-8")

    with pytest.raises(OSError, match="acima do limite"):
        lexer.read_source_file(big)


# ---------------------------------------------------------------------------
# CSV injection / formula injection nos exportadores
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "payload",
    ['=HYPERLINK("http://evil")', "+1+1", "-2+3", "@SUM(A1)", "\tcmd", "\rx"],
)
def test_csv_cell_formula_injection_is_neutralized(payload):
    from synesis.exporters.csv_export import _sanitize_cell

    sanitized = _sanitize_cell(payload)
    assert sanitized.startswith("'")
    assert sanitized[1:] == payload


def test_csv_cell_safe_values_untouched():
    from synesis.exporters.csv_export import _sanitize_cell

    for safe in ["texto normal", "2026", "", "a=b", None, 42]:
        assert _sanitize_cell(safe) == safe


# ---------------------------------------------------------------------------
# Portabilidade entre sistemas: separador e caixa
# ---------------------------------------------------------------------------

def test_backslash_separator_resolves_on_every_platform(tmp_path):
    """Um .synp escrito no Windows (`sub\\a.syn`) tambem compila no Linux/macOS."""
    subdir = tmp_path / "entrevistas"
    subdir.mkdir()
    (subdir / "e01.syn").write_text(ANNOTATIONS_VALID, encoding="utf-8")

    synp = _build_project(tmp_path, _project(annotations="entrevistas\\e01.syn"))

    result = SynesisCompiler(synp).compile()

    assert not _errors_of(result, MissingAnnotationsFile)
    assert result.stats.item_count == 1


def test_case_divergence_does_not_produce_false_positive(tmp_path, case_insensitive_fs):
    """.synp que escreve "ANNOTATIONS.SYN" para o arquivo "annotations.syn".

    Em FS case-insensitive o arquivo abre normalmente; antes da correcao a
    comparacao de paths ainda emitia E061 (arquivo nao incluido) porque
    Path.resolve() nao normaliza a caixa. Em FS case-sensitive o arquivo
    realmente nao existe, e o esperado e o erro E073 — nunca uma excecao.
    """
    synp = _build_project(tmp_path, _project(annotations="ANNOTATIONS.SYN"))

    result = SynesisCompiler(synp).compile()

    if case_insensitive_fs:
        assert not _errors_of(result, MissingAnnotationsInclude)
        assert not _errors_of(result, MissingAnnotationsFile)
        assert result.success
    else:
        assert _errors_of(result, MissingAnnotationsFile)
        assert not result.success


def test_source_location_uses_real_disk_case(tmp_path, case_insensitive_fs):
    """SourceLocation.file carrega a caixa do disco, nao a escrita no .synp.

    Sem isso o LSP publica diagnosticos numa URI (`.../ANNOTATIONS.SYN`) que o
    editor nao reconhece — o usuario nao ve o squiggle.
    """
    if not case_insensitive_fs:
        pytest.skip("divergencia de caixa so e resolvivel em FS case-insensitive")

    synp = _build_project(tmp_path, _project(annotations="ANNOTATIONS.SYN"))

    compiler = SynesisCompiler(synp)
    project, _ = compiler.parse_project()
    sources, _items, _result = compiler.parse_annotations(project)

    assert sources
    assert sources[0].location.file.name == "annotations.syn"


# ---------------------------------------------------------------------------
# Unidade: synesis.parser.paths
# ---------------------------------------------------------------------------

def test_uri_to_path_strips_leading_slash_before_drive():
    """`file:///C:/x` -> `C:/x`, nao `/C:/x` (que nao existe no Windows)."""
    path = uri_to_path("file:///C:/projeto/anotacoes.syn")
    assert path.parts[0].rstrip("\\/").endswith(":") or path.is_absolute()
    assert "anotacoes.syn" == path.name
    assert not str(path).startswith("/C:")


def test_uri_to_path_decodes_percent_encoding():
    """Paths com espaco e acento — comuns em "Meus Documentos" — nao viram lixo."""
    path = uri_to_path("file:///C:/meu%20projeto/anota%C3%A7%C3%B5es.syn")
    assert path.name == "anotações.syn"
    assert path.parent.name == "meu projeto"


def test_uri_to_path_accepts_plain_path():
    assert uri_to_path("/home/user/a.syn").name == "a.syn"


def test_path_to_uri_roundtrips(tmp_path):
    target = tmp_path / "anotações com espaço.syn"
    target.write_text("", encoding="utf-8")

    assert uri_to_path(path_to_uri(target)) == canonical_path(target)


def test_normalize_include_path_canonizes_separator():
    assert normalize_include_path("sub\\a.syn") == "sub/a.syn"
    assert normalize_include_path("  sub/a.syn  ") == "sub/a.syn"


def test_has_glob():
    assert has_glob("*.syn")
    assert has_glob("e0?.syn")
    assert not has_glob("annotations.syn")


def test_resolve_include_reports_not_found(tmp_path):
    resolution = resolve_include(tmp_path, "ausente.syn")
    assert resolution.error is IncludeError.NOT_FOUND
    assert not resolution.ok


def test_resolve_include_reports_escape(tmp_path):
    resolution = resolve_include(tmp_path, "../fora.syn")
    assert resolution.error is IncludeError.ESCAPES_PROJECT
    assert not resolution.ok


def test_resolve_include_reports_directory(tmp_path):
    (tmp_path / "pasta").mkdir()
    resolution = resolve_include(tmp_path, "pasta")
    assert resolution.error is IncludeError.NOT_A_FILE


def test_resolve_include_ok(tmp_path):
    (tmp_path / "a.syn").write_text("", encoding="utf-8")
    resolution = resolve_include(tmp_path, "a.syn")
    assert resolution.ok
    assert resolution.path.name == "a.syn"
