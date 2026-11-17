"""
nodes.py - Dataclasses da AST do compilador Synesis

Propósito:
    Definir os nós principais da árvore sintática abstrata (AST) do Synesis.
    Centraliza tipos, enums e estruturas de dados para parsing e validação.

Componentes principais:
    - Nós de domínio: ProjectNode, SourceNode, ItemNode, OntologyNode
    - Nós de template: TemplateNode, FieldSpec, OrderedValue
    - Auxiliares: SourceLocation, ChainNode, IncludeNode, FieldEntry

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
    guidelines: Optional[str] = None
    identifies: Optional[str] = None
    refers_to: Optional[str] = None
    value_origin: str = "document"  # "document" | "bibliography" | "dataset"
    # ON DATASET "<caminho>": caminho JSON-Pointer-com-ponto no registro TOML.
    dataset_path: Optional[str] = None
    # CONTEXT ... FROM DATASET "<seção>"[, ...]: seções TOML injetadas como
    # contexto de geração deste campo (não são origem-de-valor).
    context_from_dataset: Optional[List[str]] = None
    location: Optional[SourceLocation] = None
    # ROLE <FAMILIA> [<ESPECIE>]: funcao do campo, na forma canonica
    # ("HIERARCHY KIND"). `role_repeats` guarda ROLE escrito de novo no mesmo
    # FIELD, para o diagnostico (DuplicateRole); nao vai para o JSON.
    role: Optional[str] = None
    role_repeats: Optional[List[str]] = None

    def to_dict(self) -> Dict[str, Any]:
        data = self._base_dict()
        # So com papel: o JSON de um template sem ROLE nao muda.
        if self.role is not None:
            data["role"] = self.role
        return data

    def _base_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type.value,
            "scope": self.scope.value,
            "format": self.format,
            "description": self.description,
            "values": [v.to_dict() for v in self.values] if self.values else None,
            "relations": self.relations,
            "arity": self.arity,
            "guidelines": self.guidelines,
            "identifies": self.identifies,
            "refers_to": self.refers_to,
            "value_origin": self.value_origin,
            "dataset_path": self.dataset_path,
            "context_from_dataset": self.context_from_dataset,
            "location": self.location.to_dict() if self.location else None,
        }


@dataclass
class ChainNode:
    nodes: List[str]
    relations: List[str]
    location: SourceLocation
    node_locations: Optional[List[SourceLocation]] = None

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
    shared: bool = False  # INCLUDE SHARED ONTOLOGY: autoriza path externo (rede/drive/..)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "include_type": self.include_type,
            "path": self.path,
            "shared": self.shared,
            "location": self.location.to_dict(),
        }


@dataclass
class QuestionNode:
    """Uma questao de competencia do bloco QUESTIONS (`Q1: texto`).

    `id` e `text` vazios guardam a linha que nao segue a forma `<id>: <texto>`;
    o compilador a acusa (QuestionWithoutId / QuestionWithoutText). `raw` e a
    linha como foi escrita, para a mensagem.
    """

    id: str
    text: str
    raw: str
    location: SourceLocation

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "text": self.text}


@dataclass
class ExportProp:
    """Uma propriedade de um bloco EXPORT (`OUTPUT "saida.json"`), como escrita."""

    name: str
    value: str
    location: SourceLocation


@dataclass
class MapNode:
    """Uma linha MAP de um bloco EXPORT.

    kind: "fields" (MAP campos TO alvo) ou "relations" (MAP RELATIONS ... TO alvo).
    target: forma canonica, palavras em maiusculas separadas por um espaco.
    """

    kind: str
    names: List[str]
    from_field: Optional[str]
    target: str
    location: SourceLocation


@dataclass
class ExportNode:
    """Bloco EXPORT <FORMATO> [nome] do .synp. Nao vai para o JSON."""

    format: str
    name: Optional[str]
    props: List[ExportProp]
    maps: List[MapNode]
    location: SourceLocation

    def prop(self, name: str) -> Optional[str]:
        """Valor da primeira ocorrencia da propriedade (sem distincao de caixa)."""
        key = name.upper()
        for prop in self.props:
            if prop.name.upper() == key:
                return prop.value
        return None

    @property
    def label(self) -> str:
        """Como o bloco e citado em mensagens: `EXPORT JSON painel`."""
        return f"EXPORT {self.format}" + (f" {self.name}" if self.name else "")


PHASE_LIST_PROPS = ("FIELDS", "INPUT", "RULES")


@dataclass
class PhaseNode:
    """Bloco PHASE <ANNOTATIONS|ONTOLOGY> <nome> do .synp. So validado pelo compilador."""

    scope: str  # "ANNOTATIONS" | "ONTOLOGY"
    name: str
    props: List[ExportProp]
    location: SourceLocation

    @property
    def label(self) -> str:
        return f"PHASE {self.scope} {self.name}"

    def prop(self, name: str) -> Optional[str]:
        key = name.upper()
        for prop in self.props:
            if prop.name.upper() == key:
                return prop.value
        return None

    def fields(self, name: str = "FIELDS") -> List[str]:
        """Campos de FIELDS, INPUT ou RULES, na ordem escrita."""
        value = self.prop(name)
        if not value:
            return []
        return [part.strip() for part in value.split(",") if part.strip()]

    @property
    def env_key(self) -> str:
        """Nome da fase na variavel de ambiente: SYNESIS_CODER_PHASE_<ENV_KEY>_MODEL."""
        return "".join(ch if ch.isalnum() else "_" for ch in self.name).upper()


@dataclass
class ProjectNode:
    name: str
    template_path: Path
    includes: List[IncludeNode]
    metadata: Dict[str, str]
    description: Optional[str]
    location: SourceLocation
    questions: List[QuestionNode] = field(default_factory=list)
    exports: List[ExportNode] = field(default_factory=list)
    # Blocos PHASE, na ordem do arquivo. Nao vao para o JSON (plano de producao).
    phases: List[PhaseNode] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "name": self.name,
            "template_path": str(self.template_path),
            "includes": [inc.to_dict() for inc in self.includes],
            "metadata": self.metadata,
            "description": self.description,
            "location": self.location.to_dict(),
        }
        # Só com o bloco: o JSON de um projeto sem QUESTIONS nao muda.
        # Os blocos EXPORT nao entram no JSON (configuram artefatos, nao dados).
        if self.questions:
            data["questions"] = [q.to_dict() for q in self.questions if q.id and q.text]
        return data


@dataclass(slots=True)
class FieldEntry:
    """Uma ocorrência de campo escrita num bloco, na ordem do arquivo.

    `value` é o valor como o transformer o produziu — texto, ChainNode ou lista
    de códigos já separada pela gramática —, antes de qualquer leitura pelo
    tipo do template, que o transformer não conhece. `lines` guarda os tokens
    brutos de um valor em texto (TEXT_LINE), para o linker reinterpretá-lo pelo
    tipo com a posição de cada código. Os atributos agregados dos nós (`fields`,
    `extra_fields`, `notes`...) fundem ocorrências; `entries` não.

    Forma compacta (arquivo compartilhado + linha/coluna, sem um SourceLocation
    por ocorrência): um projeto grande tem milhões de ocorrências, e os nós
    voltam serializados dos processos de parse (ProcessPoolExecutor).
    """

    name: str
    value: Any
    file: Path
    line: int
    column: int
    lines: Optional[List[Any]] = None
    code_locations: Optional[List[SourceLocation]] = None

    @property
    def location(self) -> SourceLocation:
        return SourceLocation(file=self.file, line=self.line, column=self.column)


@dataclass
class SourceNode:
    bibref: str
    fields: Dict[str, Any]
    items: List["ItemNode"] = field(default_factory=list)
    location: Optional[SourceLocation] = None
    entries: List[FieldEntry] = field(default_factory=list)

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
    code_locations: Dict[str, List[SourceLocation]] = field(default_factory=dict)
    field_line_tokens: Dict[str, List[List[Any]]] = field(default_factory=dict)
    field_names: List[str] = field(default_factory=list)
    location: Optional[SourceLocation] = None
    entries: List[FieldEntry] = field(default_factory=list)

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
    entries: List[FieldEntry] = field(default_factory=list)

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
    optional_bundles: Dict[Scope, List[Tuple[str, ...]]] = field(default_factory=dict)
    location: Optional[SourceLocation] = None
    # Erros detectados durante a construcao do TemplateNode (ex: campos duplicados).
    # Propagados para ValidationResult pelo validate_template() em template_loader.py.
    parse_errors: List[Any] = field(default_factory=list)

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
            "optional_bundles": {
                k.value: [list(bundle) for bundle in v]
                for k, v in self.optional_bundles.items()
            },
            "location": self.location.to_dict() if self.location else None,
        }
