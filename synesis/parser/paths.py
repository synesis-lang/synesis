"""
paths.py - Resolucao canonica de caminhos do Synesis

Proposito:
    Ponto unico de resolucao de caminhos para todo o ecossistema. Elimina as
    conversoes ad-hoc entre URI e Path que divergiam entre plataformas.

Componentes principais:
    - uri_to_path / path_to_uri: conversao URI <-> Path
    - normalize_include_path: canoniza o literal escrito em INCLUDE/TEMPLATE
    - resolve_include: resolve o literal contra o diretorio do projeto
    - IncludeResolution: resultado da resolucao (path canonico + motivo da falha)
    - expand_include: resolve arquivo, curinga OU pasta de um INCLUDE em lista de
      arquivos (IncludeExpansion) — ponto unico usado pelo compilador e pelo LSP

Notas de implementacao:
    - O literal do .synp aceita `/` e `\\` como separador; ambos sao canonizados
      para o separador nativo. Um .synp escrito no Windows compila no Linux.
    - Caminhos sao confinados ao diretorio do projeto: `..` que escape da raiz
      e recusado (ESCAPES_PROJECT).
    - `Path.resolve()` so normaliza a caixa de arquivos existentes. Em sistemas
      de arquivos case-insensitive (Windows, macOS) o literal `NOTES.SYN` abre o
      arquivo `notes.syn`, mas os dois paths comparam como distintos. Por isso
      resolve_include devolve sempre a caixa REAL do disco (_real_case), o que
      mantem SourceLocation.file consistente com a URI que o editor conhece.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlparse

__all__ = [
    "INCLUDE_EXTENSIONS",
    "IncludeError",
    "IncludeExpansion",
    "IncludeResolution",
    "canonical_path",
    "expand_include",
    "has_glob",
    "is_within",
    "normalize_include_path",
    "path_to_uri",
    "resolve_glob",
    "resolve_include",
    "uri_to_path",
]


class IncludeError(Enum):
    """Motivo pelo qual um caminho declarado no .synp nao pode ser usado."""

    NOT_FOUND = "not_found"
    ESCAPES_PROJECT = "escapes_project"
    NOT_A_FILE = "not_a_file"
    NO_MATCHES = "no_matches"  # curinga ou pasta que nao casou nenhum arquivo


# Extensao que uma PASTA declarada em cada tipo de INCLUDE seleciona. Um curinga
# explicito nao e filtrado: o autor ja escolheu o que casa.
INCLUDE_EXTENSIONS = {
    "BIBLIOGRAPHY": ".bib",
    "ANNOTATIONS": ".syn",
    "ONTOLOGY": ".syno",
    "DATASET": ".toml",
}


@dataclass(frozen=True)
class IncludeResolution:
    """Resultado da resolucao de um caminho declarado no .synp.

    Attributes:
        path: Caminho absoluto e canonico. Sempre presente, mesmo em falha, para
            que o chamador possa reporta-lo na mensagem de erro.
        error: None quando o arquivo existe e esta dentro do projeto.
    """

    path: Path
    error: Optional[IncludeError] = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass(frozen=True)
class IncludeExpansion:
    """Resultado da expansao de um literal de INCLUDE em arquivos.

    Attributes:
        files: Arquivos legiveis, em ordem deterministica (ordem de caminho).
        outside: Matches recusados por escaparem do projeto (para reporte E075).
        error: None quando ha arquivos; senao o motivo — NOT_FOUND/NOT_A_FILE/
            ESCAPES_PROJECT para literal, NO_MATCHES para curinga ou pasta vazios.
        kind: "file", "glob" ou "directory" — como o literal foi interpretado.
        path: Caminho canonico do literal (para mensagens de erro).
    """

    files: tuple[Path, ...]
    outside: tuple[Path, ...] = ()
    error: Optional[IncludeError] = None
    kind: str = "file"
    path: Optional[Path] = None

    @property
    def ok(self) -> bool:
        return self.error is None


def uri_to_path(uri: str) -> Path:
    """Converte URI `file://` em Path, ou devolve o proprio valor como Path.

    Trata os tres casos que quebravam no Windows:
      - barra sobrando antes da letra do drive (`/C:/x` -> `C:/x`);
      - percent-encoding (`%20` -> espaco, `%C3%A7` -> `c`-cedilha);
      - valores que ja sao caminhos e nao URIs.
    """
    if not uri.startswith("file://"):
        return Path(unquote(uri))

    parsed = urlparse(uri)
    path_str = unquote(parsed.path or "")

    # UNC: file://servidor/share -> \\servidor\share
    if parsed.netloc:
        return Path(f"//{parsed.netloc}{path_str}")

    # Windows: /C:/x -> C:/x
    if len(path_str) >= 3 and path_str[0] == "/" and path_str[2] == ":":
        path_str = path_str[1:]

    return Path(path_str)


def path_to_uri(path: Path | str) -> str:
    """Converte Path em URI `file://` percent-encoded.

    Usa a caixa real do disco quando o arquivo existe, para que a URI resultante
    seja identica a que o editor usa para o mesmo arquivo.
    """
    file_path = _real_case(Path(path))
    if not file_path.is_absolute():
        file_path = file_path.resolve()
    return file_path.as_uri()


def normalize_include_path(raw: str) -> str:
    """Canoniza o literal escrito em INCLUDE/TEMPLATE.

    Aceita `/` e `\\` como separador para que um `.synp` escrito no Windows
    compile no Linux (onde `\\` seria um caractere valido de nome de arquivo, e
    o INCLUDE falharia silenciosamente).
    """
    return raw.replace("\\", "/").strip()


def has_glob(value: str) -> bool:
    """Indica se o literal contem um padrao glob."""
    return any(ch in value for ch in ("*", "?", "["))


def resolve_include(project_dir: Path, raw: str, *, shared: bool = False) -> IncludeResolution:
    """Resolve um literal de INCLUDE/TEMPLATE contra o diretorio do projeto.

    Args:
        project_dir: Diretorio que contem o arquivo .synp.
        raw: Literal exatamente como escrito no .synp.
        shared: Quando True (`INCLUDE SHARED ONTOLOGY`), o autor autorizou
            explicitamente um alvo externo — a checagem de contencao e pulada,
            aceitando rede (`\\\\servidor\\...`), outro drive e `..`. Default
            False mantem `ESCAPES_PROJECT` byte-identico para todo o resto
            (esta funcao serve tambem ao LSP).

    Returns:
        IncludeResolution com o caminho canonico (caixa real do disco) e, em
        caso de falha, o motivo — nunca levanta excecao.
    """
    normalized = normalize_include_path(raw)
    base = project_dir.resolve()
    candidate = (base / normalized).resolve()

    if not shared and not is_within(candidate, base):
        return IncludeResolution(path=candidate, error=IncludeError.ESCAPES_PROJECT)

    if not candidate.exists():
        return IncludeResolution(path=candidate, error=IncludeError.NOT_FOUND)

    if not candidate.is_file():
        return IncludeResolution(path=candidate, error=IncludeError.NOT_A_FILE)

    return IncludeResolution(path=_real_case(candidate))


def resolve_glob(project_dir: Path, raw: str) -> tuple[list[Path], list[Path]]:
    """Expande um padrao glob confinado ao diretorio do projeto.

    `Path.glob` segue `..`, entao `../*.syn` escaparia do projeto. Esta funcao
    filtra o resultado pelo mesmo invariante de contencao de resolve_include.

    Returns:
        Tupla (arquivos_dentro, matches_fora): arquivos legiveis dentro do
        projeto e matches recusados por escaparem (para reporte E075).
    """
    normalized = normalize_include_path(raw)
    base = project_dir.resolve()

    inside: list[Path] = []
    outside: list[Path] = []
    for match in sorted(base.glob(normalized)):
        resolved = match.resolve()
        if is_within(resolved, base) and resolved.is_file():
            inside.append(_real_case(resolved))
        else:
            outside.append(resolved)
    return inside, outside


def _path_order(path: Path) -> tuple[str, str]:
    """Chave de ordenacao identica em todo sistema operacional.

    `sorted()` de Path compara sem caixa no Windows e com caixa no POSIX:
    `Kely.bib` vem antes de `face85.bib` no Linux e depois no Windows. Como a
    primeira ocorrencia de uma chave repetida e a que vale (E089), a ordem tem
    de ser a mesma nas duas plataformas.
    """
    posix = path.as_posix()
    return (posix.casefold(), posix)


def expand_include(
    project_dir: Path,
    raw: str,
    extension: Optional[str] = None,
    *,
    shared: bool = False,
) -> IncludeExpansion:
    """Expande o literal de um INCLUDE em arquivos: arquivo, curinga ou pasta.

    - Curinga (`fontes/*.bib`): os arquivos que casam, sem filtrar extensao.
    - Pasta (`fontes`): busca RECURSIVA pelos arquivos com `extension` (a mesma
      semantica da extensao do VS Code). Sem `extension`, pasta e NOT_A_FILE.
    - Arquivo: o proprio arquivo, com os erros de resolve_include.

    A contencao ao projeto (E075) vale para os tres casos; `shared=True`
    (INCLUDE SHARED ONTOLOGY) a desliga. A ordem e deterministica — ordem de
    caminho —, para que mensagens e exportacoes sejam estaveis entre maquinas.
    Nunca levanta excecao.
    """
    normalized = normalize_include_path(raw)
    base = project_dir.resolve()

    if has_glob(normalized):
        if shared:
            matches = [p.resolve() for p in base.glob(normalized) if p.is_file()]
            files = tuple(sorted((_real_case(p) for p in matches), key=_path_order))
            outside: tuple[Path, ...] = ()
        else:
            inside, out = resolve_glob(project_dir, normalized)
            files = tuple(sorted(inside, key=_path_order))
            outside = tuple(sorted(out, key=_path_order))
        error = IncludeError.NO_MATCHES if not files and not outside else None
        return IncludeExpansion(files=files, outside=outside, error=error, kind="glob",
                                path=base / normalized)

    candidate = (base / normalized).resolve()
    if not shared and not is_within(candidate, base):
        return IncludeExpansion(files=(), error=IncludeError.ESCAPES_PROJECT, path=candidate)
    if not candidate.exists():
        return IncludeExpansion(files=(), error=IncludeError.NOT_FOUND, path=candidate)

    if candidate.is_dir():
        if not extension:
            return IncludeExpansion(files=(), error=IncludeError.NOT_A_FILE,
                                    kind="directory", path=candidate)
        suffix = extension.lower()
        found: list[Path] = []
        escaped: list[Path] = []
        for match in candidate.rglob("*"):
            if not match.is_file() or match.suffix.lower() != suffix:
                continue
            resolved = match.resolve()
            # Link simbolico dentro da pasta pode apontar para fora do projeto.
            if not shared and not is_within(resolved, base):
                escaped.append(resolved)
            else:
                found.append(_real_case(resolved))
        error = IncludeError.NO_MATCHES if not found and not escaped else None
        return IncludeExpansion(files=tuple(sorted(found, key=_path_order)),
                                outside=tuple(sorted(escaped, key=_path_order)), error=error,
                                kind="directory", path=candidate)

    if not candidate.is_file():
        return IncludeExpansion(files=(), error=IncludeError.NOT_A_FILE, path=candidate)
    return IncludeExpansion(files=(_real_case(candidate),), path=candidate)


def canonical_path(path: Path | str) -> Path:
    """Caminho absoluto na caixa real do disco, para comparar paths entre si.

    Necessario porque `Path.resolve()` nao normaliza a caixa: em FS
    case-insensitive `NOTES.SYN` e `notes.syn` sao o mesmo arquivo mas comparam
    como paths distintos.
    """
    return _real_case(Path(path))


def is_within(candidate: Path, base: Path) -> bool:
    """Indica se `candidate` esta contido em `base` (bloqueia `..` que escapa)."""
    try:
        candidate.resolve().relative_to(base.resolve())
    except ValueError:
        return False
    return True


def _real_case(path: Path) -> Path:
    """Devolve o caminho com a caixa real do disco.

    Em FS case-insensitive (Windows, macOS) `Path("NOTES.SYN")` e `Path("notes.syn")`
    apontam para o mesmo arquivo mas comparam como diferentes. Sem esta
    normalizacao, a caixa escrita no .synp vaza para SourceLocation.file e o LSP
    publica diagnosticos numa URI que o editor nao reconhece.
    """
    resolved = path.resolve()
    if not resolved.exists():
        return resolved

    parent = resolved.parent
    if parent == resolved:  # raiz do sistema
        return resolved

    try:
        for entry in parent.iterdir():
            if entry.name == resolved.name:
                return entry  # ja e a caixa real
            if entry.name.lower() == resolved.name.lower():
                return entry
    except OSError:
        return resolved

    return resolved
