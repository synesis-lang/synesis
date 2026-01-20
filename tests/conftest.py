"""
conftest.py - Fixtures compartilhadas para testes do Synesis

Propósito:
    Fornecer fixtures comuns para parsing, validação e exportação.

Componentes principais:
    - paths para fixtures
    - location padrão

Dependências críticas:
    - pytest: gerenciamento de fixtures

Gerado conforme: Especificação Synesis v1.1
"""

from __future__ import annotations

from pathlib import Path

import pytest

from synesis.ast.nodes import SourceLocation
from synesis.parser.template_loader import load_template


@pytest.fixture()
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture()
def base_location() -> SourceLocation:
    return SourceLocation(file=Path("test.syn"), line=1, column=1)


@pytest.fixture()
def minimal_template(fixtures_dir: Path):
    return load_template(fixtures_dir / "minimal.synt")


@pytest.fixture()
def energy_template(fixtures_dir: Path):
    return load_template(fixtures_dir / "energy.synt")
