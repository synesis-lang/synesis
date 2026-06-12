"""
Synesis: Compilador para Pesquisa Qualitativa

A Domain-Specific Language (DSL) compiler that transforms qualitative
research annotations into canonical knowledge structures.

API em Memoria (synesis.load):
    >>> import synesis
    >>> result = synesis.load(
    ...     project_content='PROJECT Demo TEMPLATE "t.synt" END PROJECT',
    ...     template_content='TEMPLATE Demo ... END TEMPLATE',
    ... )
    >>> if result.success:
    ...     data = result.to_json_dict()
    ...     df = result.to_dataframe("items")

Compilador CLI (synesis.SynesisCompiler):
    >>> from synesis import SynesisCompiler
    >>> compiler = SynesisCompiler(Path("projeto.synp"))
    >>> result = compiler.compile()
    >>> result.to_json(Path("output.json"))

Gerado conforme: Especificacao Synesis v1.1
"""

import re
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path


def _read_version_from_pyproject() -> str:
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:
        return "0.0.0"
    match = re.search(r'(?m)^version = "([^"]+)"\s*$', text)
    return match.group(1) if match else "0.0.0"

# API em memoria (NOVO)
from synesis.api import (
    CompilationStats,
    MemoryCompilationResult,
    compile_string,
    load,
)

# AST Nodes
from synesis.ast.nodes import (
    ChainNode,
    FieldSpec,
    FieldType,
    IncludeNode,
    ItemNode,
    OntologyNode,
    OrderedValue,
    ProjectNode,
    Scope,
    SourceLocation,
    SourceNode,
    TemplateNode,
)

# Result types
from synesis.ast.results import (
    Err,
    Ok,
    ValidationError,
    ValidationResult,
)

# Compilador tradicional
from synesis.compiler import (
    CompilationResult,
    SynesisCompiler,
)

# Semantic
from synesis.semantic.linker import LinkedProject

try:
    __version__ = _pkg_version("synesis")
except PackageNotFoundError:
    __version__ = _read_version_from_pyproject()
__all__ = [
    # API em memoria
    "load",
    "compile_string",
    "MemoryCompilationResult",
    "CompilationStats",
    # Compilador
    "SynesisCompiler",
    "CompilationResult",
    # AST
    "Scope",
    "FieldType",
    "SourceLocation",
    "ProjectNode",
    "SourceNode",
    "ItemNode",
    "OntologyNode",
    "TemplateNode",
    "FieldSpec",
    "ChainNode",
    "IncludeNode",
    "OrderedValue",
    # Results
    "Ok",
    "Err",
    "ValidationResult",
    "ValidationError",
    # Semantic
    "LinkedProject",
]
