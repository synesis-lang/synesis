"""
transformer.py - Conversao de parse tree para AST Synesis

Proposito:
    Transformar a arvore concreta do Lark em nos tipados da AST Synesis.
    Normaliza keywords e valores, preservando localizacao de origem.

Componentes principais:
    - SynesisTransformer: Transformer principal do Lark
    - Helpers para normalizacao de valores e acumulacao de campos

Dependencias criticas:
    - lark: Transformer, Token e metadados de parsing
    - synesis.ast.nodes: definicoes dos nos da AST

Exemplo de uso:
    from synesis.parser.transformer import SynesisTransformer
    ast_nodes = SynesisTransformer("arquivo.syn").transform(tree)

Notas de implementacao:
    - Chains sao armazenadas com elementos planos em ChainNode.nodes.
    - Valores multilinha sao dedentados e preservam quebras.

Gerado conforme: Especificacao Synesis v1.1
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any, Dict, List, Tuple

from lark import Token, Transformer, v_args

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
)
from synesis.parser.lexer import SynesisSyntaxError

def _source_location(file_path: Path, meta: Any) -> SourceLocation:
    return SourceLocation(file=file_path, line=meta.line, column=meta.column)


def _strip_quotes(value: str) -> str:
    if value.startswith('"') and value.endswith('"') and len(value) >= 2:
        return value[1:-1]
    return value


def _dedent_text(text: str) -> str:
    return textwrap.dedent(text).rstrip()


def _ensure_non_empty(value: str, location: SourceLocation, field_name: str) -> str:
    if value.strip() == "":
        raise SynesisSyntaxError(
            message=f"Empty value for field '{field_name}'",
            location=location,
        )
    return value


def _add_field(fields: Dict[str, Any], name: str, value: Any) -> None:
    if name in fields:
        existing = fields[name]
        if isinstance(existing, list):
            existing.append(value)
        else:
            fields[name] = [existing, value]
    else:
        fields[name] = value


def _field_type_from_kw(value: str | FieldType) -> FieldType:
    if isinstance(value, FieldType):
        return value
    mapping = {
        "QUOTATION": FieldType.QUOTATION,
        "MEMO": FieldType.MEMO,
        "CODE": FieldType.CODE,
        "CHAIN": FieldType.CHAIN,
        "TEXT": FieldType.TEXT,
        "DATE": FieldType.DATE,
        "SCALE": FieldType.SCALE,
        "ENUMERATED": FieldType.ENUMERATED,
        "ORDERED": FieldType.ORDERED,
        "TOPIC": FieldType.TOPIC,
    }
    return mapping[value]


def _scope_from_kw(value: str) -> Scope:
    mapping = {
        "SOURCE": Scope.SOURCE,
        "ITEM": Scope.ITEM,
        "ONTOLOGY": Scope.ONTOLOGY,
    }
    return mapping[value]


def _normalize_field_name(name: str) -> str:
    if name.isupper() and len(name) > 1:
        return name.lower()
    return name


class SynesisTransformer(Transformer):
    def __init__(self, filename: str | Path):
        super().__init__()
        self.file_path = Path(filename)

    def start(self, items: List[Any]) -> List[Any]:
        return [
            item
            for item in items
            if not (isinstance(item, Token) and item.type == "NEWLINE")
        ]

    def block(self, items: List[Any]) -> Any:
        return items[0]

    def IDENTIFIER(self, token: Token) -> str:  # noqa: N802
        return token.value

    def FIELD_NAME(self, token: Token) -> str:  # noqa: N802
        return token.value

    def STRING(self, token: Token) -> str:  # noqa: N802
        return token.value

    def NUMBER(self, token: Token) -> int | float:  # noqa: N802
        value = token.value
        return int(value) if value.isdigit() else float(value)

    def TEXT_LINE(self, token: Token) -> str:  # noqa: N802
        return token.value

    def CONCEPT_NAME(self, token: Token) -> str:  # noqa: N802
        return token.value

    def BIBREF(self, token: Token) -> str:  # noqa: N802
        return token.value

    def CHAIN_ELEMENT(self, token: Token) -> str:  # noqa: N802
        return token.value

    def CODE_ELEMENT(self, token: Token) -> str:  # noqa: N802
        return token.value

    def KW_PROJECT(self, token: Token) -> str:  # noqa: N802
        return token.value.upper()

    def KW_SOURCE(self, token: Token) -> str:  # noqa: N802
        return token.value.upper()

    def KW_ITEM(self, token: Token) -> str:  # noqa: N802
        return token.value.upper()

    def KW_ONTOLOGY(self, token: Token) -> str:  # noqa: N802
        return token.value.upper()

    def KW_TEMPLATE(self, token: Token) -> str:  # noqa: N802
        return token.value.upper()

    def KW_FIELD(self, token: Token) -> str:  # noqa: N802
        return token.value.upper()

    def KW_END(self, token: Token) -> str:  # noqa: N802
        return token.value.upper()

    def KW_INCLUDE(self, token: Token) -> str:  # noqa: N802
        return token.value.upper()

    def KW_BIBLIOGRAPHY(self, token: Token) -> str:  # noqa: N802
        return token.value.upper()

    def KW_ANNOTATIONS(self, token: Token) -> str:  # noqa: N802
        return token.value.upper()

    def KW_FIELDS(self, token: Token) -> str:  # noqa: N802
        return token.value.upper()

    def KW_REQUIRED(self, token: Token) -> str:  # noqa: N802
        return token.value.upper()

    def KW_OPTIONAL(self, token: Token) -> str:  # noqa: N802
        return token.value.upper()

    def KW_FORBIDDEN(self, token: Token) -> str:  # noqa: N802
        return token.value.upper()

    def KW_BUNDLE(self, token: Token) -> str:  # noqa: N802
        return token.value.upper()

    def KW_TYPE(self, token: Token) -> str:  # noqa: N802
        return token.value.upper()

    def KW_SCOPE(self, token: Token) -> str:  # noqa: N802
        return token.value.upper()

    def KW_FORMAT(self, token: Token) -> str:  # noqa: N802
        return token.value.upper()

    def KW_DESCRIPTION(self, token: Token) -> str:  # noqa: N802
        return token.value.upper()

    def KW_ARITY(self, token: Token) -> str:  # noqa: N802
        return token.value.upper()

    def KW_VALUES(self, token: Token) -> str:  # noqa: N802
        return token.value.upper()

    def KW_RELATIONS(self, token: Token) -> str:  # noqa: N802
        return token.value.upper()

    def KW_METADATA(self, token: Token) -> str:  # noqa: N802
        return token.value.upper()

    def KW_QUOTATION(self, token: Token) -> str:  # noqa: N802
        return token.value.upper()

    def KW_MEMO(self, token: Token) -> str:  # noqa: N802
        return token.value.upper()

    def KW_CODE(self, token: Token) -> str:  # noqa: N802
        return token.value.upper()

    def KW_CHAIN(self, token: Token) -> str:  # noqa: N802
        return token.value.upper()

    def KW_TEXT(self, token: Token) -> str:  # noqa: N802
        return token.value.upper()

    def KW_DATE(self, token: Token) -> str:  # noqa: N802
        return token.value.upper()

    def KW_SCALE(self, token: Token) -> str:  # noqa: N802
        return token.value.upper()

    def KW_ENUMERATED(self, token: Token) -> str:  # noqa: N802
        return token.value.upper()

    def KW_ORDERED(self, token: Token) -> str:  # noqa: N802
        return token.value.upper()

    def KW_TOPIC(self, token: Token) -> str:  # noqa: N802
        return token.value.upper()

    def COMPARATOR(self, token: Token) -> str:  # noqa: N802
        return token.value

    @v_args(meta=True)
    def project_block(self, meta: Any, items: List[Any]) -> ProjectNode:
        name = items[1]
        template_path: Optional[Path] = None
        include_nodes: List[IncludeNode] = []
        metadata: Dict[str, str] = {}
        description = None

        flattened: List[Any] = []
        for item in items[2:]:
            if isinstance(item, list):
                flattened.extend(item)
                continue
            if isinstance(item, Token) and item.type in {"NEWLINE", "_INDENT", "_DEDENT"}:
                continue
            flattened.append(item)

        keywords = {"PROJECT", "END", "TEMPLATE", "INCLUDE", "METADATA", "DESCRIPTION"}
        for item in flattened:
            if isinstance(item, tuple) and item[0] == "TEMPLATE":
                template_path = Path(item[1])
            elif isinstance(item, IncludeNode):
                include_nodes.append(item)
            elif isinstance(item, dict):
                metadata = item
            elif isinstance(item, str):
                if not item.strip():
                    continue
                if item.upper() in keywords:
                    continue
                description = item

        if template_path is None:
            template_path = Path("")

        return ProjectNode(
            name=name,
            template_path=template_path,
            includes=include_nodes,
            metadata=metadata,
            description=description,
            location=_source_location(self.file_path, meta),
        )

    def project_body(self, items: List[Any]) -> List[Any]:
        cleaned = [
            item
            for item in items
            if not (isinstance(item, Token) and item.type in {"_INDENT", "_DEDENT", "NEWLINE"})
        ]
        if len(cleaned) == 1 and isinstance(cleaned[0], list):
            return cleaned[0]
        return cleaned

    def project_items(self, items: List[Any]) -> List[Any]:
        return [
            item
            for item in items
            if not (isinstance(item, Token) and item.type == "NEWLINE")
        ]

    def includes(self, items: List[Any]) -> Tuple[Optional[Path], List[IncludeNode]]:
        """
        Grammar: includes: include_stmt+
        Processes include_stmt results and separates TEMPLATE from INCLUDE
        """
        template_path = None
        include_nodes: List[IncludeNode] = []

        for item in items:
            if isinstance(item, tuple) and item[0] == "TEMPLATE":
                template_path = Path(item[1])
            elif isinstance(item, IncludeNode):
                include_nodes.append(item)

        return (template_path, include_nodes)

    @v_args(meta=True)
    def include_stmt(self, meta: Any, items: List[Any]) -> Any:
        """
        Grammar: include_stmt: KW_TEMPLATE STRING NEWLINE | KW_INCLUDE include_type STRING NEWLINE
        For TEMPLATE: items = [KW_TEMPLATE, STRING, NEWLINE] = ["TEMPLATE", string, newline]
        For INCLUDE: items = [KW_INCLUDE, include_type, STRING, NEWLINE] = ["INCLUDE", type_str, string, newline]
        """
        if items[0] == "TEMPLATE":
            return ("TEMPLATE", _strip_quotes(items[1]), _source_location(self.file_path, meta))
        # items = ["INCLUDE", include_type_result, STRING]
        include_type = items[1]  # Result from include_type rule
        path = _strip_quotes(items[2])  # STRING token
        return IncludeNode(
            include_type=include_type,
            path=path,
            location=_source_location(self.file_path, meta),
        )

    def include_type(self, items: List[Any]) -> str:
        return items[0]

    def metadata(self, items: List[Any]) -> Dict[str, str]:
        metadata: Dict[str, str] = {}
        for entry in items:
            if not isinstance(entry, tuple):
                continue
            name, value = entry
            metadata[name] = str(value)
        return metadata

    def metadata_line(self, items: List[Any]) -> Optional[tuple[str, str]]:
        if not items:
            return None
        line = str(items[0])
        if ":" not in line:
            return None
        key, value = line.split(":", 1)
        return key.strip(), value.strip()

    def description(self, items: List[Any]) -> str:
        lines: List[str] = []
        pending_blank = False
        keywords = {"DESCRIPTION", "END"}
        flattened: List[Any] = []
        for item in items:
            if isinstance(item, list):
                flattened.extend(item)
            else:
                flattened.append(item)
        for item in flattened:
            if isinstance(item, Token) and item.type == "NEWLINE":
                if pending_blank:
                    lines.append("")
                    pending_blank = False
                else:
                    pending_blank = True
                continue
            if isinstance(item, str):
                if item.upper() in keywords:
                    continue
                lines.append(item)
                pending_blank = False
        return "\n".join(lines).strip()

    def description_lines(self, items: List[Any]) -> List[Any]:
        return items

    @v_args(meta=True)
    def source_block(self, meta: Any, items: List[Any]) -> SourceNode:
        bibref = items[1]
        field_entries = items[2:-2]
        fields: Dict[str, Any] = {}
        for entry in field_entries:
            if isinstance(entry, Token) and entry.type == "NEWLINE":
                continue
            if not isinstance(entry, tuple):
                continue
            name, value, _location = entry
            _add_field(fields, name, value)
        return SourceNode(
            bibref=bibref,
            fields=fields,
            items=[],
            location=_source_location(self.file_path, meta),
        )

    @v_args(meta=True)
    def item_block(self, meta: Any, items: List[Any]) -> ItemNode:
        bibref = items[1]
        field_entries = items[2:-2]
        quote = ""
        codes: List[str] = []
        notes: List[str] = []
        chains: List[ChainNode] = []
        extra_fields: Dict[str, Any] = {}
        field_names: List[str] = []
        for entry in field_entries:
            if isinstance(entry, Token) and entry.type == "NEWLINE":
                continue
            if not isinstance(entry, tuple):
                continue
            name, value, _location = entry
            field_names.append(name)
            lname = name.lower()
            if lname in {"quote", "quotation"}:
                quote = str(value)
                continue
            if lname in {"code", "codes"}:
                if isinstance(value, list):
                    codes.extend([str(v) for v in value])
                else:
                    codes.append(str(value))
                continue
            if lname in {"note", "notes", "memo", "memos"}:
                if isinstance(value, list):
                    notes.extend([str(v) for v in value])
                else:
                    notes.append(str(value))
                continue
            if lname in {"chain", "chains"}:
                if isinstance(value, list):
                    chains.extend([v for v in value if isinstance(v, ChainNode)])
                elif isinstance(value, ChainNode):
                    chains.append(value)
                continue
            _add_field(extra_fields, name, value)
        return ItemNode(
            bibref=bibref,
            quote=quote,
            codes=codes,
            notes=notes,
            chains=chains,
            extra_fields=extra_fields,
            field_names=field_names,
            location=_source_location(self.file_path, meta),
        )

    @v_args(meta=True)
    def ontology_block(self, meta: Any, items: List[Any]) -> OntologyNode:
        concept = items[1].strip()
        field_entries = items[2:-2]
        description = ""
        fields: Dict[str, Any] = {}
        parent_chains: List[ChainNode] = []
        field_names: List[str] = []
        for entry in field_entries:
            if isinstance(entry, Token) and entry.type == "NEWLINE":
                continue
            if not isinstance(entry, tuple):
                continue
            name, value, _location = entry
            field_names.append(name)
            lname = name.lower()
            if lname == "description":
                description = str(value)
                continue
            if lname in {"parent", "parents", "is_a", "isa"}:
                if isinstance(value, list):
                    parent_chains.extend([v for v in value if isinstance(v, ChainNode)])
                elif isinstance(value, ChainNode):
                    parent_chains.append(value)
                continue
            _add_field(fields, name, value)
        return OntologyNode(
            concept=concept,
            description=description,
            fields=fields,
            parent_chains=parent_chains,
            field_names=field_names,
            location=_source_location(self.file_path, meta),
        )

    def concept_name(self, items: List[Any]) -> str:
        return str(items[0]).strip()

    @v_args(meta=True)
    def template_header(self, meta: Any, items: List[Any]) -> Dict[str, Any]:
        name = items[1]
        metadata: Dict[str, Any] = {}
        for item in items[2:]:
            if isinstance(item, tuple):
                key, value = item
                metadata[key] = value
        return {
            "name": name,
            "metadata": metadata,
            "location": _source_location(self.file_path, meta),
        }

    def template_meta(self, items: List[Any]) -> Tuple[str, Any]:
        return items[0], items[1]

    def field_spec_block(self, items: List[Any]) -> Dict[str, Any]:
        scope = _scope_from_kw(items[0])
        clauses = next((item for item in items if isinstance(item, list)), [])
        required: List[str] = []
        optional: List[str] = []
        forbidden: List[str] = []
        bundles: List[Tuple[str, ...]] = []
        for clause in clauses:
            if clause[0] == "required":
                if clause[1]:
                    bundles.append(tuple(clause[2]))
                else:
                    required.extend(clause[2])
            elif clause[0] == "optional":
                optional.extend(clause[1])
            elif clause[0] == "forbidden":
                forbidden.extend(clause[1])
        return {
            "scope": scope,
            "required": required,
            "optional": optional,
            "forbidden": forbidden,
            "bundles": bundles,
        }

    def field_list(self, items: List[Any]) -> List[Any]:
        return [
            item
            for item in items
            if not (isinstance(item, Token) and item.type == "NEWLINE")
        ]

    def requirement_clause(self, items: List[Any]) -> Tuple[str, Any, Any]:
        if items[0] == "REQUIRED":
            has_bundle = "BUNDLE" in items
            names = items[-1]
            return ("required", has_bundle, names)
        if items[0] == "OPTIONAL":
            return ("optional", items[1])
        return ("forbidden", items[1])

    def bundle_modifier(self, items: List[Any]) -> str:
        return items[0]

    def field_names(self, items: List[Any]) -> List[str]:
        return [_normalize_field_name(item) for item in items]

    def field_key(self, items: List[Any]) -> str:
        return items[0]

    @v_args(meta=True)
    def field_def_block(self, meta: Any, items: List[Any]) -> FieldSpec:
        name = _normalize_field_name(items[1])
        type_spec = next(item for item in items if isinstance(item, FieldType))
        props = [item for item in items if isinstance(item, tuple)]
        scope = None
        fmt = None
        description = None
        values = None
        relations = None
        arity = None
        for prop in props:
            key, value = prop
            if key == "scope":
                scope = value
            elif key == "format":
                fmt = value
            elif key == "description":
                description = value
            elif key == "values":
                values = value
            elif key == "relations":
                relations = value
            elif key == "arity":
                arity = value
        if scope is None:
            scope = Scope.ITEM
        return FieldSpec(
            name=name,
            type=type_spec,
            scope=scope,
            format=fmt,
            description=description,
            values=values,
            relations=relations,
            arity=arity,
            location=_source_location(self.file_path, meta),
        )

    def type_spec(self, items: List[Any]) -> FieldType:
        return _field_type_from_kw(items[0])

    def simple_type(self, items: List[Any]) -> FieldType:
        return _field_type_from_kw(items[0])

    def field_props(self, items: List[Any]) -> Tuple[str, Any]:
        if items[0] == "SCOPE":
            return ("scope", _scope_from_kw(items[1]))
        if items[0] == "FORMAT":
            return ("format", items[1])
        if items[0] == "DESCRIPTION":
            return ("description", items[1])
        if items[0] == "ARITY":
            return ("arity", f"{items[1]} {items[2]}")
        if items[0] == "VALUES":
            return ("values", items[1])
        return ("relations", items[1])

    def scope_type(self, items: List[Any]) -> str:
        return items[0]

    def format_spec(self, items: List[Any]) -> str:
        return items[0]

    def scale_format(self, items: List[Any]) -> str:
        return f"[{items[0]}..{items[1]}]"

    def value_list(self, items: List[Any]) -> List[OrderedValue]:
        return [
            item
            for item in items
            if not (isinstance(item, Token) and item.type in {"NEWLINE", "_INDENT", "_DEDENT"})
        ]

    @v_args(meta=True)
    def value_entry(self, meta: Any, items: List[Any]) -> OrderedValue:
        index = -1
        if len(items) == 3:
            index = int(items[0])
            label = items[1]
            description = items[2]
        else:
            label = items[0]
            description = items[1]
        return OrderedValue(
            index=index,
            label=label,
            description=description,
            location=_source_location(self.file_path, meta),
        )

    def index_prefix(self, items: List[Any]) -> str:
        return items[0]

    def relation_list(self, items: List[Any]) -> Dict[str, str]:
        relations: Dict[str, str] = {}
        for item in items:
            if isinstance(item, Token) and item.type in {"NEWLINE", "_INDENT", "_DEDENT"}:
                continue
            name, description = item
            relations[name] = description
        return relations

    def relation_entry(self, items: List[Any]) -> Tuple[str, str]:
        return items[0], items[1]

    @v_args(meta=True)
    def field_entry(self, meta: Any, items: List[Any]) -> Tuple[str, Any, SourceLocation]:
        name = _normalize_field_name(items[0])
        location = _source_location(self.file_path, meta)
        cleaned = [
            item
            for item in items[1:]
            if not (isinstance(item, Token) and item.type == "NEWLINE")
        ]
        if not cleaned:
            raise SynesisSyntaxError(
                message=f"Empty value for field '{name}'",
                location=location,
            )
        if len(cleaned) == 1 and isinstance(cleaned[0], list):
            text = "\n".join(cleaned[0])
            text = _ensure_non_empty(_dedent_text(text), location, name)
            return (name, text, location)
        value = cleaned[0]
        if len(cleaned) > 1 and isinstance(cleaned[1], list):
            if not isinstance(value, str):
                raise SynesisSyntaxError(
                    message=f"Invalid multiline value for field '{name}'",
                    location=location,
                )
            merged = "\n".join([value] + cleaned[1])
            merged = _ensure_non_empty(_dedent_text(merged), location, name)
            return (name, merged, location)
        if isinstance(value, str):
            value = _ensure_non_empty(value, location, name)
            lname = name.lower()
            if lname in {"code", "codes"} and "," in value:
                value = [part.strip() for part in value.split(",") if part.strip()]
            if lname in {"chain", "chains"} and "->" in value:
                elements = [part.strip() for part in value.split("->") if part.strip()]
                value = ChainNode(nodes=elements, relations=[], location=location)
        return (name, value, location)

    def value(self, items: List[Any]) -> Any:
        if len(items) == 2 and isinstance(items[0], (int, float)) and isinstance(items[1], str):
            return f"{items[0]}{items[1]}".strip()
        value = items[0]
        if isinstance(value, str):
            value = _strip_quotes(value).strip()
            return value
        if isinstance(value, list):
            return [str(v).strip() for v in value]
        return value

    def code_list(self, items: List[Any]) -> List[str]:
        return [str(item).strip() for item in items]

    def text_block(self, items: List[Any]) -> List[str]:
        return [
            str(item)
            for item in items
            if not (isinstance(item, Token) and item.type == "NEWLINE")
        ]

    @v_args(meta=True)
    def chain_expr(self, meta: Any, items: List[Any]) -> ChainNode:
        """
        Parseia chain_expr da gramatica.

        Chain pode ser:
        - Simples: A -> B -> C (apenas codigos)
        - Qualificada: A -> REL -> B -> REL -> C (codigos e relacoes alternados)

        A separacao entre codigos e relacoes e feita durante validacao semantica,
        pois depende do template (se define RELATIONS ou nao).

        Por ora, armazenamos todos os elementos em nodes e deixamos relations vazio.
        O validator.validate_chain() faz a separacao correta.
        """
        elements = [str(item).strip() for item in items]
        return ChainNode(
            nodes=elements,
            relations=[],
            location=_source_location(self.file_path, meta),
        )
