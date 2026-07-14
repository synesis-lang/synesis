"""
template_loader.py - Carregamento e validacao de templates Synesis

Proposito:
    Ler arquivos .synt, parsear com Lark e construir TemplateNode.
    Valida listas REQUIRED/OPTIONAL/FORBIDDEN e processa bundles.

Componentes principais:
    - load_template: funcao principal de carga e validacao
    - TemplateLoadError: erro com localizacao quando disponivel

Dependencias criticas:
    - synesis.parser.lexer: parser Lark
    - synesis.parser.transformer: conversao para AST parcial
    - synesis.ast.nodes: FieldSpec, TemplateNode, Scope, FieldType

Exemplo de uso:
    from synesis.parser.template_loader import load_template
    template = load_template("modelo.synt")

Notas de implementacao:
    - Campos em bundles nao entram em required_fields.
    - Campos listados devem existir em FIELD.

Gerado conforme: Especificacao Synesis v1.1
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Set, Tuple

from synesis.ast.nodes import FieldSpec, FieldType, Scope, SourceLocation, TemplateNode
from synesis.ast.results import (
    ArityOnNonChain,
    ArityRelationsMismatch,
    ChainWithoutArity,
    DuplicateValue,
    EnumeratedWithoutValues,
    FieldScopeListMismatch,
    FormatOnNonScale,
    InvalidArityOperator,
    InvalidFormatSyntax,
    NonIntegerArityValue,
    OrderedWithoutValues,
    OrphanFieldDefinition,
    RelationsOnNonChain,
    ScaleWithoutFormat,
    SingleFieldBundle,
    UndefinedFieldInScopeFields,
    ValidationResult,
    ValueWithWhitespace,
)
from synesis.parser.lexer import parse_string
from synesis.parser.transformer import SynesisTransformer


@dataclass
class TemplateLoadError(Exception):
    message: str
    location: SourceLocation

    def __str__(self) -> str:
        return f"{self.location}: {self.message}"


def load_template(path: Path | str) -> TemplateNode:
    """
    Carrega e valida arquivo .synt do disco.

    - Parseia usando a gramatica Lark
    - Construi dicionario de FieldSpec
    - Processa REQUIRED/OPTIONAL/FORBIDDEN e BUNDLE
    - Valida referencias a campos inexistentes

    Args:
        path: Caminho para o arquivo .synt

    Returns:
        TemplateNode validado e pronto para uso

    Raises:
        TemplateLoadError: Se houver erro de validacao no template
        SynesisSyntaxError: Se houver erro de sintaxe no arquivo
    """
    from synesis.parser.lexer import read_source_file

    file_path = Path(path)
    content = read_source_file(file_path)
    return _load_template_impl(content, str(file_path))


def load_template_from_string(content: str, filename: str = "<template>") -> TemplateNode:
    """
    Carrega e valida template a partir de string em memoria.

    Reutiliza a logica de load_template() sem dependencia de I/O em disco.
    Ideal para uso em Jupyter Notebooks, LSP e testes.

    Args:
        content: Conteudo do arquivo .synt como string
        filename: Nome virtual para mensagens de erro (default: "<template>")

    Returns:
        TemplateNode validado e pronto para uso

    Raises:
        TemplateLoadError: Se houver erro de validacao no template
        SynesisSyntaxError: Se houver erro de sintaxe no conteudo

    Example:
        >>> template = load_template_from_string('''
        ...     TEMPLATE Demo
        ...     SOURCE FIELDS
        ...         REQUIRED date
        ...     END SOURCE FIELDS
        ...     FIELD date TYPE DATE SCOPE SOURCE END FIELD
        ... ''')
    """
    return _load_template_impl(content, filename)


def _load_template_impl(content: str, filename: str) -> TemplateNode:
    """Implementacao compartilhada para load_template e load_template_from_string."""
    file_path = Path(filename)
    tree = parse_string(content, filename)
    transformer = SynesisTransformer(file_path)
    nodes = transformer.transform(tree)

    header = None
    field_specs: Dict[str, FieldSpec] = {}
    field_specs_order: List[FieldSpec] = []
    spec_blocks: List[Dict[str, object]] = []
    duplicate_errors: List = []

    for node in nodes:
        if isinstance(node, dict) and "name" in node and "metadata" in node:
            header = node
        elif isinstance(node, dict) and "scope" in node:
            spec_blocks.append(node)
        elif isinstance(node, FieldSpec):
            field_specs_order.append(node)

    for spec in field_specs_order:
        if spec.name in field_specs:
            location = spec.location or SourceLocation(file_path, 1, 1)
            # Acumula como ValidationError (erro 69) em vez de lancar excecao
            from synesis.ast.results import DuplicateFieldName
            duplicate_errors.append(DuplicateFieldName(
                location=location,
                field_name=spec.name,
            ))
            continue  # nao sobrescreve — usa a primeira definicao
        if spec.type == FieldType.ORDERED and spec.values:
            for value in spec.values:
                if value.index < 0:
                    raise TemplateLoadError(
                        message=f"ORDERED exige indice em VALUES: '{spec.name}'",
                        location=value.location,
                    )
        field_specs[spec.name] = spec

    required_fields: Dict[Scope, List[str]] = {
        Scope.SOURCE: [],
        Scope.ITEM: [],
        Scope.ONTOLOGY: [],
    }
    optional_fields: Dict[Scope, List[str]] = {
        Scope.SOURCE: [],
        Scope.ITEM: [],
        Scope.ONTOLOGY: [],
    }
    forbidden_fields: Dict[Scope, List[str]] = {
        Scope.SOURCE: [],
        Scope.ITEM: [],
        Scope.ONTOLOGY: [],
    }
    bundled_fields: Dict[Scope, List[Tuple[str, ...]]] = {
        Scope.SOURCE: [],
        Scope.ITEM: [],
        Scope.ONTOLOGY: [],
    }
    optional_bundles: Dict[Scope, List[Tuple[str, ...]]] = {
        Scope.SOURCE: [],
        Scope.ITEM: [],
        Scope.ONTOLOGY: [],
    }

    for block in spec_blocks:
        scope = block["scope"]
        required = block.get("required", [])
        optional = block.get("optional", [])
        forbidden = block.get("forbidden", [])
        bundles = block.get("bundles", [])
        opt_bundles = block.get("optional_bundles", [])

        for bundle in bundles:
            bundled_fields[scope].append(tuple(bundle))

        for bundle in opt_bundles:
            optional_bundles[scope].append(tuple(bundle))

        for name in required:
            required_fields[scope].append(name)

        for name in optional:
            optional_fields[scope].append(name)

        for name in forbidden:
            forbidden_fields[scope].append(name)

    if header is None:
        header = {"name": "", "metadata": {}, "location": SourceLocation(file_path, 1, 1)}

    return TemplateNode(
        name=header["name"],
        metadata=header["metadata"],
        field_specs=field_specs,
        required_fields=required_fields,
        optional_fields=optional_fields,
        forbidden_fields=forbidden_fields,
        bundled_fields=bundled_fields,
        optional_bundles=optional_bundles,
        location=header["location"],
        parse_errors=duplicate_errors,
    )


def validate_template(template: TemplateNode) -> ValidationResult:
    """
    Valida a estrutura interna do template apos parsing bem-sucedido.

    Verifica inconsistencias semanticas que nao podem ser capturadas pela
    gramatica Lark: campos indefinidos em FIELDS, campos orfaos, bundles
    invalidos, tipos sem configuracao obrigatoria, etc.

    Args:
        template: TemplateNode ja parseado e construido por load_template()

    Returns:
        ValidationResult com todos os erros/avisos encontrados (nunca lanca excecao)
    """
    result = ValidationResult()
    file_path = template.location.file if template.location else Path("<template>")
    loc = template.location or SourceLocation(file_path, 1, 1)

    # Propaga erros de duplicacao de FIELD detectados durante a construcao do TemplateNode
    for err in template.parse_errors:
        result.add(err)

    _check_fields_without_definition(template, loc, result)
    _check_field_scope_mismatch(template, loc, result)
    _check_orphan_field_definitions(template, loc, result)
    _check_single_field_bundle(template, result)
    _check_chain_without_arity(template, result)
    _check_arity_relations_mismatch(template, result)
    _check_ordered_without_values(template, result)
    _check_enumerated_without_values(template, result)
    _check_scale_without_format(template, result)
    _check_format_syntax(template, result)
    _check_invalid_arity_operator(template, result)
    _check_format_on_non_scale(template, result)
    _check_arity_on_non_chain(template, result)
    _check_relations_on_non_chain(template, result)
    _check_values_whitespace(template, result)
    _check_values_duplicates(template, result)

    return result


# ---------------------------------------------------------------------------
# Helpers internos para validate_template()
# ---------------------------------------------------------------------------

_ARITY_PATTERN = re.compile(r"^\s*(>=|<=|>|<|=)\s*(\d+)\s*$")
_VALID_ARITY_OPS = {">=", "<=", ">", "<", "="}
_FORMAT_PATTERN = re.compile(r"^\s*\[(-?\d+(?:\.\d+)?)\.\.(-?\d+(?:\.\d+)?)\]\s*$")


def _all_listed_names(template: TemplateNode) -> Dict[str, Set[str]]:
    """Retorna {scope_value: set_of_names} para todos os campos listados."""
    result: Dict[str, Set[str]] = {}
    for scope in Scope:
        names: Set[str] = set()
        names.update(template.required_fields.get(scope, []))
        names.update(template.optional_fields.get(scope, []))
        names.update(template.forbidden_fields.get(scope, []))
        for bundle in template.bundled_fields.get(scope, []):
            names.update(bundle)
        for bundle in template.optional_bundles.get(scope, []):
            names.update(bundle)
        result[scope.value] = names
    return result


def _check_fields_without_definition(
    template: TemplateNode, loc: SourceLocation, result: ValidationResult
) -> None:
    """Erros 39-41: campo listado em SCOPE FIELDS sem FIELD correspondente."""
    for scope in Scope:
        all_names: Set[str] = set()
        all_names.update(template.required_fields.get(scope, []))
        all_names.update(template.optional_fields.get(scope, []))
        all_names.update(template.forbidden_fields.get(scope, []))
        for bundle in template.bundled_fields.get(scope, []):
            all_names.update(bundle)
        for bundle in template.optional_bundles.get(scope, []):
            all_names.update(bundle)
        for name in sorted(all_names):
            if name not in template.field_specs:
                field_loc = SourceLocation(loc.file, loc.line, loc.column)
                result.add(UndefinedFieldInScopeFields(
                    location=field_loc,
                    field_name=name,
                    scope=scope.value,
                ))


def _check_field_scope_mismatch(
    template: TemplateNode, loc: SourceLocation, result: ValidationResult
) -> None:
    """Erro 6: campo listado em SCOPE FIELDS cujo FIELD tem SCOPE diferente."""
    for scope in Scope:
        all_names: Set[str] = set()
        all_names.update(template.required_fields.get(scope, []))
        all_names.update(template.optional_fields.get(scope, []))
        all_names.update(template.forbidden_fields.get(scope, []))
        for bundle in template.bundled_fields.get(scope, []):
            all_names.update(bundle)
        for bundle in template.optional_bundles.get(scope, []):
            all_names.update(bundle)
        for name in sorted(all_names):
            if name in template.field_specs:
                spec = template.field_specs[name]
                if spec.scope != scope:
                    spec_loc = spec.location or loc
                    result.add(FieldScopeListMismatch(
                        location=spec_loc,
                        field_name=name,
                        listed_scope=scope.value,
                        actual_scope=spec.scope.value,
                    ))


def _check_orphan_field_definitions(
    template: TemplateNode, loc: SourceLocation, result: ValidationResult
) -> None:
    """Erro 42: FIELD definido mas nao listado em nenhum SCOPE FIELDS."""
    all_listed: Set[str] = set()
    for scope in Scope:
        all_listed.update(template.required_fields.get(scope, []))
        all_listed.update(template.optional_fields.get(scope, []))
        all_listed.update(template.forbidden_fields.get(scope, []))
        for bundle in template.bundled_fields.get(scope, []):
            all_listed.update(bundle)
        for bundle in template.optional_bundles.get(scope, []):
            all_listed.update(bundle)

    for name, spec in sorted(template.field_specs.items()):
        if name not in all_listed:
            spec_loc = spec.location or loc
            result.add(OrphanFieldDefinition(
                location=spec_loc,
                field_name=name,
                scope=spec.scope.value,
            ))


def _check_single_field_bundle(template: TemplateNode, result: ValidationResult) -> None:
    """Erro 18: BUNDLE declarado com apenas um campo."""
    all_bundles = [
        bundle
        for scope in Scope
        for bundle in (
            list(template.bundled_fields.get(scope, []))
            + list(template.optional_bundles.get(scope, []))
        )
    ]
    for bundle in all_bundles:
        if len(bundle) < 2:
            if bundle and bundle[0] in template.field_specs:
                spec = template.field_specs[bundle[0]]
                loc = spec.location or template.location
            else:
                loc = template.location
            result.add(SingleFieldBundle(
                location=loc,
                bundle_fields=tuple(bundle),
            ))


def _check_chain_without_arity(template: TemplateNode, result: ValidationResult) -> None:
    """Erro 47: TYPE CHAIN sem declaracao ARITY."""
    for name, spec in template.field_specs.items():
        if spec.type == FieldType.CHAIN and not spec.arity:
            loc = spec.location or template.location
            result.add(ChainWithoutArity(location=loc, field_name=name))


def _check_arity_relations_mismatch(template: TemplateNode, result: ValidationResult) -> None:
    """Erro 48: ARITY incompativel com numero de RELATIONS declaradas."""
    for name, spec in template.field_specs.items():
        if spec.type != FieldType.CHAIN or not spec.arity or not spec.relations:
            continue
        m = _ARITY_PATTERN.match(spec.arity)
        if not m:
            continue
        op, val = m.group(1), int(m.group(2))
        # Apenas valida para >= e > (minimos)
        if op not in (">=", ">"):
            continue
        min_concepts = val if op == ">=" else val + 1
        n_relations = len(spec.relations)
        if n_relations < min_concepts - 1:
            loc = spec.location or template.location
            result.add(ArityRelationsMismatch(
                location=loc,
                field_name=name,
                arity=min_concepts,
                n_relations=n_relations,
            ))


def _check_ordered_without_values(template: TemplateNode, result: ValidationResult) -> None:
    """Erro 49: TYPE ORDERED sem bloco VALUES."""
    for name, spec in template.field_specs.items():
        if spec.type == FieldType.ORDERED and not spec.values:
            loc = spec.location or template.location
            result.add(OrderedWithoutValues(location=loc, field_name=name))


def _check_enumerated_without_values(template: TemplateNode, result: ValidationResult) -> None:
    """Erro 50: TYPE ENUMERATED sem bloco VALUES."""
    for name, spec in template.field_specs.items():
        if spec.type == FieldType.ENUMERATED and not spec.values:
            loc = spec.location or template.location
            result.add(EnumeratedWithoutValues(location=loc, field_name=name))


def _check_scale_without_format(template: TemplateNode, result: ValidationResult) -> None:
    """Erro 51: TYPE SCALE sem declaracao FORMAT."""
    for name, spec in template.field_specs.items():
        if spec.type == FieldType.SCALE and not spec.format:
            loc = spec.location or template.location
            result.add(ScaleWithoutFormat(location=loc, field_name=name))


def _check_format_syntax(template: TemplateNode, result: ValidationResult) -> None:
    """Erro 52: Sintaxe invalida na declaracao FORMAT de campo SCALE."""
    for name, spec in template.field_specs.items():
        if spec.type == FieldType.SCALE and spec.format:
            if not _FORMAT_PATTERN.match(spec.format):
                loc = spec.location or template.location
                result.add(InvalidFormatSyntax(
                    location=loc,
                    field_name=name,
                    format_str=spec.format,
                ))


def _check_invalid_arity_operator(template: TemplateNode, result: ValidationResult) -> None:
    """Erro 53: Operador invalido na declaracao ARITY."""
    for name, spec in template.field_specs.items():
        if not spec.arity:
            continue
        m = _ARITY_PATTERN.match(spec.arity)
        if not m:
            # Tenta extrair operador para mensagem mais precisa
            op_match = re.match(r"^\s*([^\d\s]+)", spec.arity)
            op = op_match.group(1) if op_match else spec.arity.strip()
            if op not in _VALID_ARITY_OPS:
                loc = spec.location or template.location
                result.add(InvalidArityOperator(
                    location=loc,
                    field_name=name,
                    operator=op,
                ))
            else:
                # Operador valido mas valor nao-inteiro (ex: "= 2.0"): erro 60.
                # Sem este check, _validate_chain_arity faz int("2.0") -> ValueError
                # capturado silenciosamente, desativando a validacao de ARITY.
                val_match = re.match(r"^\s*(?:>=|<=|>|<|=)\s*(.+?)\s*$", spec.arity)
                value = val_match.group(1) if val_match else spec.arity.strip()
                result.add(NonIntegerArityValue(
                    location=spec.location or template.location,
                    field_name=name,
                    value=value,
                ))


def _check_format_on_non_scale(template: TemplateNode, result: ValidationResult) -> None:
    """Erro 54: FORMAT declarado em campo que nao e TYPE SCALE."""
    for name, spec in template.field_specs.items():
        if spec.type != FieldType.SCALE and spec.format:
            loc = spec.location or template.location
            result.add(FormatOnNonScale(
                location=loc,
                field_name=name,
                field_type=spec.type.value,
            ))


def _check_arity_on_non_chain(template: TemplateNode, result: ValidationResult) -> None:
    """Erro 55: ARITY declarado em campo que nao e TYPE CHAIN."""
    for name, spec in template.field_specs.items():
        if spec.type != FieldType.CHAIN and spec.arity:
            loc = spec.location or template.location
            result.add(ArityOnNonChain(
                location=loc,
                field_name=name,
                field_type=spec.type.value,
            ))


def _check_relations_on_non_chain(template: TemplateNode, result: ValidationResult) -> None:
    """Erro 56: RELATIONS definido em campo que nao e TYPE CHAIN."""
    for name, spec in template.field_specs.items():
        if spec.type != FieldType.CHAIN and spec.relations:
            loc = spec.location or template.location
            result.add(RelationsOnNonChain(
                location=loc,
                field_name=name,
                field_type=spec.type.value,
            ))


def _check_values_whitespace(template: TemplateNode, result: ValidationResult) -> None:
    """Erro 58: Valor em bloco VALUES com espaco no inicio ou fim."""
    for name, spec in template.field_specs.items():
        if not spec.values:
            continue
        for val_obj in spec.values:
            label = val_obj.label if hasattr(val_obj, "label") else str(val_obj)
            if label != label.strip():
                val_loc = getattr(val_obj, "location", None) or spec.location or template.location
                result.add(ValueWithWhitespace(
                    location=val_loc,
                    field_name=name,
                    value=label,
                ))


def _check_values_duplicates(template: TemplateNode, result: ValidationResult) -> None:
    """Erro 59: Valores duplicados dentro de um mesmo bloco VALUES."""
    for name, spec in template.field_specs.items():
        if not spec.values:
            continue
        seen: Set[str] = set()
        for val_obj in spec.values:
            label = val_obj.label if hasattr(val_obj, "label") else str(val_obj)
            normalized = label.strip().lower()
            if normalized in seen:
                val_loc = getattr(val_obj, "location", None) or spec.location or template.location
                result.add(DuplicateValue(
                    location=val_loc,
                    field_name=name,
                    value=label,
                ))
            seen.add(normalized)


def _validate_field_names(
    file_path: Path,
    scope: Scope,
    names: List[str],
    field_specs: Dict[str, FieldSpec],
) -> None:
    for name in names:
        if name not in field_specs:
            location = SourceLocation(file_path, 1, 1)
            raise TemplateLoadError(
                message=f"Campo '{name}' listado em {scope.value} FIELDS nao definido em FIELD",
                location=location,
            )
