"""
test_dataset_loader.py - Fase 1: loader agnostico de datasets TOML

Cobre synesis/parser/dataset_loader.py:
  - carregamento e indexacao por chave CONFIGURAVEL (nao hardcoded);
  - navegacao de caminho JSON-Pointer-com-ponto e pre-filtro de igualdade (D6);
  - deteccao de TOML malformado;
  - erros de chave ausente/duplicada;
  - GENERICIDADE (D8): funciona com TOML de dominio arbitrario, nao so Lattes.

Os testes de Lattes usam os 3 curriculos reais do corpus Quinto Andar quando
disponiveis; caso o repositorio case-studies nao esteja presente ao lado de
synesis, esses testes sao pulados (skipif) — os testes agnosticos, que nao
dependem do corpus, sempre rodam.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from synesis.parser.dataset_loader import (
    DatasetKeyError,
    DatasetParseError,
    detect_malformed,
    find_record,
    load_dataset,
    load_dataset_from_records,
    resolve_path,
    suggest_record,
)

# Corpus Lattes real (opcional — pode nao existir no ambiente de CI isolado).
_LATTES_DIR = (
    Path(__file__).resolve().parents[2]
    / "case-studies"
    / "Quinto_Andar"
    / "Projetos_Unificados"
    / "Dados_Lattes"
    / "curriculos"
)
_HAS_LATTES = _LATTES_DIR.is_dir() and any(_LATTES_DIR.glob("*.toml"))
_lattes_only = pytest.mark.skipif(
    not _HAS_LATTES, reason="corpus Lattes (case-studies) nao disponivel"
)


# ---------------------------------------------------------------------------
# Genericidade (D8) — NAO depende do corpus Lattes
# ---------------------------------------------------------------------------


def test_generic_domain_indexing():
    """Dominio arbitrario (sensores): indexa por chave configuravel, sem Lattes."""
    records = {
        "a.toml": {"device": {"id": "Sensor-42"}, "readings": [{"v": 1}, {"v": 2}]},
        "b.toml": {"device": {"id": "sensor-7"}, "readings": [{"v": 9}]},
    }
    ds = load_dataset_from_records(records, key_path="device.id")
    # tolerante a caixa: chave "Sensor-42" acha por "sensor-42"
    assert find_record(ds, "sensor-42")["readings"][1]["v"] == 2
    assert find_record(ds, "SENSOR-7")["readings"][0]["v"] == 9


def test_resolve_path_scalar_and_subtree():
    rec = {"a": {"b": {"c": "leaf"}}, "list": [{"x": 1}]}
    assert resolve_path(rec, "a.b.c") == "leaf"
    assert resolve_path(rec, "a.b") == {"c": "leaf"}
    assert resolve_path(rec, "list") == [{"x": 1}]


def test_resolve_path_missing_returns_none():
    rec = {"a": {"b": 1}}
    assert resolve_path(rec, "a.z") is None
    assert resolve_path(rec, "a.b.c") is None  # b e escalar, nao dict
    assert resolve_path(rec, "nope.deep.path") is None


def test_prefilter_equality():
    rec = {
        "projetos": [
            {"nome": "P1", "ano_fim": "Atual"},
            {"nome": "P2", "ano_fim": "2019"},
            {"nome": "P3", "ano_fim": "Atual"},
        ]
    }
    hits = resolve_path(rec, "projetos[ano_fim=Atual]")
    assert [p["nome"] for p in hits] == ["P1", "P3"]


def test_prefilter_numeric_ordering():
    rec = {"pubs": [{"ano": 2018}, {"ano": 2021}, {"ano": 2025}]}
    hits = resolve_path(rec, "pubs[ano>=2020]")
    assert [p["ano"] for p in hits] == [2021, 2025]


def test_prefilter_on_nonlist_returns_none():
    rec = {"scalar": "x"}
    assert resolve_path(rec, "scalar[field=v]") is None


def test_missing_key_raises():
    records = {"a.toml": {"device": {}}}  # sem device.id
    with pytest.raises(DatasetKeyError):
        load_dataset_from_records(records, key_path="device.id")


def test_duplicate_key_raises():
    records = {
        "a.toml": {"k": "same"},
        "b.toml": {"k": "same"},
    }
    with pytest.raises(DatasetKeyError):
        load_dataset_from_records(records, key_path="k")


def test_load_from_disk_and_malformed(tmp_path: Path):
    good = tmp_path / "good.toml"
    good.write_text('[meta]\nid = "rec-1"\nvalue = 42\n', encoding="utf-8")
    bad = tmp_path / "bad.toml"
    bad.write_text('[meta\nid = "oops"\n', encoding="utf-8")  # colchete sem fechar

    # detect_malformed acha o ruim, ignora o bom
    malformed = detect_malformed("*.toml", base_dir=tmp_path)
    assert len(malformed) == 1
    assert "bad.toml" in malformed[0][0]

    # load_dataset sobre o ruim levanta DatasetParseError
    with pytest.raises(DatasetParseError):
        load_dataset("bad.toml", key_path="meta.id", base_dir=tmp_path)

    # load_dataset sobre o bom indexa por meta.id
    ds = load_dataset("good.toml", key_path="meta.id", base_dir=tmp_path)
    assert find_record(ds, "rec-1")["meta"]["value"] == 42


def test_suggest_record():
    assert "sensor-42" in suggest_record("sensor-43", ["sensor-42", "device-7"])


# ---------------------------------------------------------------------------
# Corpus Lattes real (D3/D5) — pulado se case-studies ausente
# ---------------------------------------------------------------------------


@_lattes_only
def test_lattes_glob_indexes_by_id_lattes():
    ds = load_dataset(
        "*.toml", key_path="informacoes_pessoais.id_lattes", base_dir=_LATTES_DIR
    )
    # 3 curriculos-piloto conhecidos
    assert len(ds) >= 3
    ravetti = find_record(ds, "3355559305779367")
    assert ravetti is not None
    assert ravetti["informacoes_pessoais"]["nome_completo"] == "Martín Gómez Ravetti"


@_lattes_only
def test_lattes_prefilter_active_projects():
    ds = load_dataset(
        "*.toml", key_path="informacoes_pessoais.id_lattes", base_dir=_LATTES_DIR
    )
    ravetti = find_record(ds, "3355559305779367")
    ativos = resolve_path(ravetti, "projetos_pesquisa[ano_conclusao=Atual]")
    concluidos = resolve_path(ravetti, "projetos_pesquisa[ano_conclusao=2021]")
    # ha projetos "Atual" e projetos concluidos em 2021 no arquivo real
    assert len(ativos) >= 1
    assert all(p["ano_conclusao"] == "Atual" for p in ativos)
    assert all(p["ano_conclusao"] == "2021" for p in concluidos)


@_lattes_only
def test_lattes_leaf_scalar_fields():
    ds = load_dataset(
        "*.toml", key_path="informacoes_pessoais.id_lattes", base_dir=_LATTES_DIR
    )
    ravetti = find_record(ds, "3355559305779367")
    assert resolve_path(ravetti, "informacoes_pessoais.bolsa_produtividade") == "Nível 1B"
