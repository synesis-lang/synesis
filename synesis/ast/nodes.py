"""
nodes.py - Dataclasses da AST do compilador Synesis

Propósito:
    Definir os nós principais da árvore sintática abstrata (AST) do Synesis.
    Centraliza tipos, enums e estruturas de dados para parsing e validação.

Componentes principais:
    - Nós de domínio: ProjectNode, SourceNode, ItemNode, OntologyNode
    - Nós de template: TemplateNode, FieldSpec, OrderedValue
    - Auxiliares: SourceLocation, ChainNode, IncludeNode

Dependências críticas:
    - dataclasses: estruturação dos nós
    - enum: enums de escopo e tipo de campo
    - pathlib: referência a paths de arquivos

Exemplo de uso:
    from synesis.ast.nodes import ItemNode, ChainNode, SourceLocation
    item = ItemNode(bibref="silva2023", quote="...", location=SourceLocation(...))

Notas de implementação:
    - Todos os nós expõem to_dict() para serialização.
    - Enums são serializados por value (UPPERCASE).

Gerado conforme: Especificação Synesis v1.1
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class Scope(Enum):
    SOURCE = "SOURCE"
    ITEM = "ITEM"
    ONTOLOGY = "ONTOLOGY"


class FieldType(Enum):
    QUOTATION = "QUOTATION"
    MEMO = "MEMO"
    CODE = "CODE"
    CHAIN = "CHAIN"
    TEXT = "TEXT"
    DATE = "DATE"
    SCALE = "SCALE"
    ENUMERATED = "ENUMERATED"
    ORDERED = "ORDERED"
    TOPIC = "TOPIC"


@dataclass
class SourceLocation:
    file: Path
    line: int
    column: int

    def __str__(self) -> str:
        return f"{self.file}:{self.line}:{self.column}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file": str(self.file),
            "line": self.line,
            "column": self.column,
        }


@dataclass
class OrderedValue:
    index: int
    label: str
    description: str
    location: SourceLocation

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "label": self.label,
            "description": self.description,
            "location": self.location.to_dict(),
        }


@dataclass
class FieldSpec:
    name: str
    type: FieldType
    scope: Scope
    format: Optional[str] = None
    description: Optional[str] = None
    values: Optional[List[OrderedValue]] = None
    relations: Optional[Dict[str, str]] = None
    arity: Optional[str] = None
    location: Optional[SourceLocation] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type.value,
            "scope": self.scope.value,
            "format": self.format,
            "description": self.description,
            "values": [v.to_dict() for v in self.values] if self.values else None,
            "relations": self.relations,
            "arity": self.arity,
            "location": self.location.to_dict() if self.location else None,
        }


@dataclass
class ChainNode:
    nodes: List[str]
    relations: List[str]
    location: SourceLocation

    def to_triples(self, has_relations: bool = False) -> List[Tuple[str, str, str]]:
        """
        Converte cadeia em triplas (from, relation, to).

        Args:
            has_relations: Se True, nodes contem [code, rel, code, rel, ...]
                          Se False, nodes contem apenas [code, code, ...]

        Returns:
            Lista de triplas (codigo1, relacao, codigo2)
        """
        triples: List[Tuple[str, str, str]] = []
        elements = self.nodes

        if has_relations:
            # Chain qualificada: posicoes pares = codigos, impares = relacoes
            codes = [elements[i] for i in range(0, len(elements), 2)]
            rels = [elements[i] for i in range(1, len(elements), 2)]

            for i in range(len(codes) - 1):
                rel = rels[i] if i < len(rels) else "IMPLICIT"
                triples.append((codes[i], rel, codes[i + 1]))
        else:
            # Chain simples: todos sao codigos
            for i in range(len(elements) - 1):
                triples.append((elements[i], "IMPLICIT", elements[i + 1]))

        return triples

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": self.nodes,
            "relations": self.relations,
            "location": self.location.to_dict(),
        }


@dataclass
class IncludeNode:
    include_type: str
    path: str
    location: SourceLocation

    def to_dict(self) -> Dict[str, Any]:
        return {
            "include_type": self.include_type,
            "path": self.path,
            "location": self.location.to_dict(),
        }


@dataclass
class ProjectNode:
    name: str
    template_path: Path
    includes: List[IncludeNode]
    metadata: Dict[str, str]
    description: Optional[str]
    location: SourceLocation

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "template_path": str(self.template_path),
            "includes": [inc.to_dict() for inc in self.includes],
            "metadata": self.metadata,
            "description": self.description,
            "location": self.location.to_dict(),
        }


@dataclass
class SourceNode:
    bibref: str
    fields: Dict[str, Any]
    items: List["ItemNode"] = field(default_factory=list)
    location: Optional[SourceLocation] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bibref": self.bibref,
            "fields": self.fields,
            "items": [item.to_dict() for item in self.items],
            "location": self.location.to_dict() if self.location else None,
        }


@dataclass
class ItemNode:
    bibref: str
    quote: str
    codes: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    chains: List[ChainNode] = field(default_factory=list)
    extra_fields: Dict[str, Any] = field(default_factory=dict)
    field_names: List[str] = field(default_factory=list)
    location: Optional[SourceLocation] = None

    def note_chain_pairs(self) -> List[Tuple[str, ChainNode]]:
        return list(zip(self.notes, self.chains))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bibref": self.bibref,
            "quote": self.quote,
            "codes": self.codes,
            "notes": self.notes,
            "chains": [chain.to_dict() for chain in self.chains],
            "extra_fields": self.extra_fields,
            "location": self.location.to_dict() if self.location else None,
        }


@dataclass
class OntologyNode:
    concept: str
    description: str
    fields: Dict[str, Any] = field(default_factory=dict)
    parent_chains: List[ChainNode] = field(default_factory=list)
    field_names: List[str] = field(default_factory=list)
    location: Optional[SourceLocation] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "concept": self.concept,
            "description": self.description,
            "fields": self.fields,
            "parent_chains": [chain.to_dict() for chain in self.parent_chains],
            "location": self.location.to_dict() if self.location else None,
        }


@dataclass
class TemplateNode:
    name: str
    metadata: Dict[str, str]
    field_specs: Dict[str, FieldSpec]
    required_fields: Dict[Scope, List[str]]
    optional_fields: Dict[Scope, List[str]]
    forbidden_fields: Dict[Scope, List[str]]
    bundled_fields: Dict[Scope, List[Tuple[str, ...]]]
    location: Optional[SourceLocation] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "metadata": self.metadata,
            "field_specs": {k: v.to_dict() for k, v in self.field_specs.items()},
            "required_fields": {
                k.value: v for k, v in self.required_fields.items()
            },
            "optional_fields": {
                k.value: v for k, v in self.optional_fields.items()
            },
            "forbidden_fields": {
                k.value: v for k, v in self.forbidden_fields.items()
            },
            "bundled_fields": {
                k.value: [list(bundle) for bundle in v]
                for k, v in self.bundled_fields.items()
            },
            "location": self.location.to_dict() if self.location else None,
        }
