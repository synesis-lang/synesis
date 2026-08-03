"""
dataset_loader.py - Carregamento de datasets estruturados em TOML

Proposito:
    Ler arquivos .toml (um registro por arquivo), indexar por uma chave
    CONFIGURAVEL e oferecer navegacao de caminho (JSON-Pointer com notacao de
    ponto) e pre-filtro deterministico de igualdade. Espelha bib_loader.py,
    mas para a origem-de-valor `ON DATASET`.

    AGNOSTICO DE DOMINIO (Fase 0, decisao D8): este modulo NAO conhece
    curriculos Lattes nem qualquer schema especifico. A chave de indexacao e um
    PARAMETRO (key_path) fornecido por quem chama (o compilador, a partir do
    campo IDENTIFIES + ON DATASET do template). Nenhuma string de dominio
    (id_lattes, informacoes_pessoais, zonas) aparece aqui.

Componentes principais:
    - load_dataset: carrega e indexa registros TOML de um glob/arquivo
    - load_dataset_from_records: indexa registros ja parseados (I/O-free, testes)
    - find_record: busca registro por chave (tolerante a caixa)
    - suggest_record: sugestoes por fuzzy matching
    - resolve_path: navega um caminho "a.b.c" (+ pre-filtro "[campo=valor]")
    - detect_malformed: localiza .toml sintaticamente invalidos

Dependencias criticas:
    - tomllib (stdlib >= 3.11) OU tomli (fallback; requires-python do projeto e
      >=3.10, entao tomli e obrigatorio como dep condicional no pyproject).

Exemplo (agnostico de dominio):
    >>> records = load_dataset_from_records({
    ...     "s.toml": {"device": {"id": "sensor-42"}, "readings": [{"v": 1}]},
    ... }, key_path="device.id")
    >>> find_record(records, "sensor-42")["readings"][0]["v"]
    1
"""

from __future__ import annotations

import re
from difflib import get_close_matches
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:  # tomllib e stdlib em >=3.11; o projeto suporta >=3.10 -> fallback tomli
    import tomllib as _toml
except ModuleNotFoundError:  # pragma: no cover - depende da versao de runtime
    import tomli as _toml  # type: ignore[no-redef]


# Chave interna que preserva o caminho de origem do registro (analogo a
# _original_key do bib_loader). Nao colide com chaves de dominio.
SOURCE_FILE_KEY = "_source_file"

# Pre-filtro: "[campo<op>valor]" com op em {=, >=, <=} (contrato D6).
# Um unico predicado; sem and/or/wildcard. `>=`/`<=` antes de `=` no alternation.
_FILTER_RE = re.compile(r"^(?P<field>[^\[\]<>=]+?)\s*(?P<op>>=|<=|=)\s*(?P<value>.*)$")
_SEGMENT_FILTER_RE = re.compile(r"^(?P<name>[^\[\]]+?)\[(?P<pred>[^\[\]]+)\]$")


def _expand_glob(glob_or_path: Path | str, base_dir: Optional[Path]) -> List[Path]:
    """Expande um glob/arquivo para arquivos, aceitando padrao absoluto OU relativo.

    Usa glob.glob (stdlib), que — ao contrario de Path.glob — aceita padroes
    absolutos (ex.: "C:/corpus/*.toml"). Padroes relativos sao resolvidos contra
    base_dir (cwd por padrao). Um arquivo unico existente e retornado direto.
    """
    import glob as _glob

    base = Path(base_dir) if base_dir is not None else Path.cwd()
    pattern = str(glob_or_path)
    single = Path(pattern)

    if single.is_file():
        return [single]

    if single.is_absolute():
        return sorted(Path(p) for p in _glob.glob(pattern))

    matched = sorted(base.glob(pattern))
    if matched:
        return matched
    candidate = base / pattern
    return [candidate] if candidate.is_file() else []


# ---------------------------------------------------------------------------
# Carregamento e indexacao
# ---------------------------------------------------------------------------


def load_dataset(
    glob_or_path: Path | str,
    key_path: str,
    base_dir: Optional[Path] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Carrega registros TOML de um glob ou arquivo unico e indexa por key_path.

    Um arquivo .toml = um registro. A chave de indexacao e o valor em key_path
    dentro de cada registro (ex.: "informacoes_pessoais.id_lattes" no Lattes,
    "device.id" em outro dominio) — o loader nao presume qual e.

    Args:
        glob_or_path: Padrao glob (ex.: "curriculos/*.toml") ou arquivo unico.
        key_path: Caminho JSON-Pointer-com-ponto da chave de indexacao.
        base_dir: Diretorio-base para resolver o glob (default: cwd).

    Returns:
        Dict {chave_normalizada -> registro (dict aninhado)}.
        Cada registro carrega SOURCE_FILE_KEY com o caminho de origem.

    Raises:
        DatasetKeyError: registro sem valor em key_path, ou chave duplicada.
        DatasetParseError: TOML sintaticamente invalido.
    """
    paths = _expand_glob(glob_or_path, base_dir)

    raw_records: Dict[str, Dict[str, Any]] = {}
    for path in paths:
        try:
            with open(path, "rb") as fh:
                data = _toml.load(fh)
        except Exception as exc:  # noqa: BLE001 - reembrulha com contexto de arquivo
            raise DatasetParseError(str(path), str(exc)) from exc
        data[SOURCE_FILE_KEY] = str(path)
        raw_records[str(path)] = data

    return _index_records(raw_records, key_path)


def load_dataset_from_records(
    records: Dict[str, Dict[str, Any]],
    key_path: str,
) -> Dict[str, Dict[str, Any]]:
    """
    Indexa registros ja parseados (sem I/O). Ideal para testes, LSP e notebooks.

    Args:
        records: {origem -> registro (dict aninhado)}. `origem` e so rotulo.
        key_path: Caminho da chave de indexacao.

    Returns:
        Dict {chave_normalizada -> registro}, com SOURCE_FILE_KEY preenchido.
    """
    prepared: Dict[str, Dict[str, Any]] = {}
    for origin, record in records.items():
        rec = dict(record)
        rec.setdefault(SOURCE_FILE_KEY, origin)
        prepared[origin] = rec
    return _index_records(prepared, key_path)


def _index_records(
    raw_records: Dict[str, Dict[str, Any]],
    key_path: str,
) -> Dict[str, Dict[str, Any]]:
    """Indexa por resolve_path(record, key_path); valida presenca e unicidade."""
    index: Dict[str, Dict[str, Any]] = {}
    for origin, record in raw_records.items():
        raw_key = resolve_path(record, key_path)
        if isinstance(raw_key, (list, dict)) or raw_key is None or str(raw_key).strip() == "":
            raise DatasetKeyError(
                origin=record.get(SOURCE_FILE_KEY, origin),
                key_path=key_path,
                reason="ausente ou nao-escalar",
            )
        norm = str(raw_key).strip().lower()
        if norm in index:
            raise DatasetKeyError(
                origin=record.get(SOURCE_FILE_KEY, origin),
                key_path=key_path,
                reason=f"chave duplicada '{raw_key}' (ja definida por "
                f"{index[norm].get(SOURCE_FILE_KEY)})",
            )
        index[norm] = record
    return index


# ---------------------------------------------------------------------------
# Busca
# ---------------------------------------------------------------------------


def find_record(
    dataset: Dict[str, Dict[str, Any]],
    key: str,
) -> Optional[Dict[str, Any]]:
    """Busca registro por chave, tolerante a caixa/trim (espelha find_bibref)."""
    return dataset.get(str(key).strip().lower())


def suggest_record(
    key: str,
    available_keys: List[str],
    max_suggestions: int = 3,
) -> List[str]:
    """Sugere chaves proximas por fuzzy matching (espelha suggest_bibref)."""
    return get_close_matches(key, available_keys, n=max_suggestions, cutoff=0.6)


# ---------------------------------------------------------------------------
# Navegacao de caminho (JSON-Pointer com ponto) + pre-filtro (D6)
# ---------------------------------------------------------------------------


def resolve_path(record: Dict[str, Any], path: str) -> Any:
    """
    Resolve um caminho "a.b.c" dentro de um registro TOML aninhado.

    Semantica JSON-Pointer (RFC 6901) com `.` no lugar de `/`: enderaca UM no ou
    uma sub-arvore, sem wildcards. Um segmento pode carregar um pre-filtro de
    igualdade `nome[campo<op>valor]` (contrato D6), aplicado quando o segmento
    resolve para uma LISTA de tabelas.

    Args:
        record: Registro (dict aninhado) ja carregado.
        path: Caminho, ex.: "informacoes_pessoais.id_lattes" ou
              "projetos[ano_conclusao=Atual]".

    Returns:
        O valor no caminho (escalar, lista ou dict), ou None se qualquer
        segmento nao existir. Listas pre-filtradas retornam a sublista casada.
    """
    current: Any = record
    for segment in path.split("."):
        if current is None:
            return None
        name, predicate = _split_segment(segment)

        if isinstance(current, dict):
            current = current.get(name)
        else:
            # Segmento nomeado sobre nao-dict: caminho invalido para este registro.
            return None

        if predicate is not None:
            if not isinstance(current, list):
                # Pre-filtro so faz sentido sobre lista de tabelas (D6).
                return None
            current = [
                item
                for item in current
                if isinstance(item, dict) and _matches(item, predicate)
            ]
    return current


def _split_segment(segment: str) -> Tuple[str, Optional[Tuple[str, str, str]]]:
    """Separa "nome[campo=valor]" em (nome, (campo, op, valor)) ou (nome, None)."""
    m = _SEGMENT_FILTER_RE.match(segment.strip())
    if not m:
        return segment.strip(), None
    name = m.group("name").strip()
    pred = _parse_predicate(m.group("pred"))
    return name, pred


def _parse_predicate(pred: str) -> Optional[Tuple[str, str, str]]:
    """Parseia "campo<op>valor" -> (campo, op, valor). None se malformado."""
    m = _FILTER_RE.match(pred.strip())
    if not m:
        return None
    return (m.group("field").strip(), m.group("op"), m.group("value").strip())


def _matches(item: Dict[str, Any], predicate: Tuple[str, str, str]) -> bool:
    """Aplica um predicado de igualdade/ordem a uma entrada de lista (D6)."""
    field, op, expected = predicate
    actual = item.get(field)
    if actual is None:
        return False
    if op == "=":
        return str(actual).strip() == expected
    # >= e <=: tenta numerico, cai para comparacao de string se nao-numerico.
    try:
        a_num, e_num = float(actual), float(expected)
        return a_num >= e_num if op == ">=" else a_num <= e_num
    except (TypeError, ValueError):
        a_str, e_str = str(actual).strip(), expected
        return a_str >= e_str if op == ">=" else a_str <= e_str


# ---------------------------------------------------------------------------
# Deteccao de arquivos malformados
# ---------------------------------------------------------------------------


def detect_malformed(glob_or_path: Path | str, base_dir: Optional[Path] = None) -> List[Tuple[str, str]]:
    """
    Localiza arquivos .toml sintaticamente invalidos (espelha detect_malformed_entries).

    Returns:
        Lista de (caminho, mensagem_de_erro), uma por arquivo que falha o parse.
        Vazia quando todos parseiam.
    """
    malformed: List[Tuple[str, str]] = []
    for path in _expand_glob(glob_or_path, base_dir):
        try:
            with open(path, "rb") as fh:
                _toml.load(fh)
        except Exception as exc:  # noqa: BLE001
            malformed.append((str(path), str(exc)))
    return malformed


# ---------------------------------------------------------------------------
# Erros
# ---------------------------------------------------------------------------


class DatasetError(Exception):
    """Base para erros de carregamento de dataset."""


class DatasetParseError(DatasetError):
    """TOML sintaticamente invalido."""

    def __init__(self, path: str, detail: str) -> None:
        self.path = path
        self.detail = detail
        super().__init__(f"Arquivo TOML invalido '{path}': {detail}")


class DatasetKeyError(DatasetError):
    """Registro sem chave de indexacao ou chave duplicada."""

    def __init__(self, origin: str, key_path: str, reason: str) -> None:
        self.origin = origin
        self.key_path = key_path
        self.reason = reason
        super().__init__(
            f"Registro em '{origin}': chave '{key_path}' {reason}."
        )
