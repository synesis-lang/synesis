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

# API em memoria (NOVO)
from synesis.api import (
    load,
    compile_string,
    MemoryCompilationResult,
    CompilationStats,
)

# Compilador tradicional
from synesis.compiler import (
    SynesisCompiler,
    CompilationResult,
)

# AST Nodes
from synesis.ast.nodes import (
    Scope,
    FieldType,
    SourceLocation,
    ProjectNode,
    SourceNode,
    ItemNode,
    OntologyNode,
    TemplateNode,
    FieldSpec,
    ChainNode,
    IncludeNode,
    OrderedValue,
)

# Result types
from synesis.ast.results import (
    Ok,
    Err,
    ValidationResult,
    ValidationError,
)

# Semantic
from synesis.semantic.linker import LinkedProject

__version__ = "0.2.1"
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
