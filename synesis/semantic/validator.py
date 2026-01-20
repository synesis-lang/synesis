"""
validator.py - Validacoes semanticas basicas do Synesis

Proposito:
    Validar blocos SOURCE, ITEM e ONTOLOGY contra o TemplateNode.
    Retorna ValidationResult com erros e avisos estruturados.

Componentes principais:
    - SemanticValidator: valida referencias, campos e tipos basicos
    - validate_ordered_value: valida valores ORDERED por indice ou label

Dependencias criticas:
    - synesis.ast.nodes: nos e enums da AST
    - synesis.ast.results: tipos de erro e ValidationResult
    - synesis.parser.bib_loader: fuzzy matching para bibrefs

Exemplo de uso:
    validator = SemanticValidator(template, bibliography, ontology_index)
    result = validator.validate_item(item)

Notas de implementacao:
    - CHAIN e BUNDLE serao validados nas proximas etapas.
    - Validacoes de tipo sao basicas e focam nos tipos nucleares.

Gerado conforme: Especificacao Synesis v1.1
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Union

from synesis.ast.nodes import (
    ChainNode,
    FieldSpec,
    FieldType,
    ItemNode,
    OntologyNode,
    ProjectNode,
    Scope,
    SourceLocation,
    SourceNode,
    TemplateNode,
)
from synesis.ast.results import (
    ForbiddenFieldPresent,
    InvalidEnumeratedValue,
    InvalidFieldType,
    InvalidOrderedValue,
    BundleCountMismatch,
    MissingBundleField,
    MissingRequiredField,
    UnknownFieldName,
    ScaleOutOfRange,
    UndefinedCode,
    UnregisteredSource,
    ValidationError,
    ValidationResult,
    ChainArityViolation,
    InvalidChainRelation,
    MalformedQualifiedChain,
)
from synesis.parser.bib_loader import suggest_bibref


@dataclass
class SemanticValidator:
    template: TemplateNode
    bibliography: Dict[str, Any]
    ontology_index: Dict[str, Any]

    def __post_init__(self) -> None:
        self.ontology_index = {self._norm_code(key): value for key, value in self.ontology_index.items()}

    def validate_project(self, node: ProjectNode) -> ValidationResult:
        return ValidationResult()

    def validate_source(self, node: SourceNode) -> ValidationResult:
        result = ValidationResult()
        self._validate_bibref(node.bibref, node.location, result)
        self._validate_declared_fields(list(node.fields.keys()), Scope.SOURCE, node.location, result)
        self._validate_fields(node, Scope.SOURCE, result)
        bundle_result = self.validate_bundle(node, Scope.SOURCE)
        result.errors.extend(bundle_result.errors)
        result.warnings.extend(bundle_result.warnings)
        result.info.extend(bundle_result.info)
        return result

    def validate_item(self, node: ItemNode) -> ValidationResult:
        result = ValidationResult()
        self._validate_declared_fields(node.field_names, Scope.ITEM, node.location, result)
        self._validate_fields(node, Scope.ITEM, result)
        self._validate_codes_defined(node, result)
        self._validate_chains(node, result)
        bundle_result = self.validate_bundle(node, Scope.ITEM)
        result.errors.extend(bundle_result.errors)
        result.warnings.extend(bundle_result.warnings)
        result.info.extend(bundle_result.info)
        return result

    def validate_ontology(self, node: OntologyNode) -> ValidationResult:
        result = ValidationResult()
        self._validate_declared_fields(node.field_names, Scope.ONTOLOGY, node.location, result)
        self._validate_fields(node, Scope.ONTOLOGY, result)
        bundle_result = self.validate_bundle(node, Scope.ONTOLOGY)
        result.errors.extend(bundle_result.errors)
        result.warnings.extend(bundle_result.warnings)
        result.info.extend(bundle_result.info)
        return result

    def validate_ordered_value(
        self,
        field_spec: FieldSpec,
        value: Union[int, str],
        location: SourceLocation,
    ) -> Optional[ValidationError]:
        if not field_spec.values:
            return InvalidOrderedValue(
                location=location,
                field_name=field_spec.name,
                value=value,
                valid_options=[],
            )

        if isinstance(value, int):
            valid_indices = [v.index for v in field_spec.values]
            if value not in valid_indices:
                return InvalidOrderedValue(
                    location=location,
                    field_name=field_spec.name,
                    value=value,
                    valid_options=[v.label for v in field_spec.values],
                )
            return None

        if isinstance(value, str):
            value_lower = value.lower()
            matching = [v for v in field_spec.values if v.label.lower() == value_lower]
            if not matching:
                return InvalidOrderedValue(
                    location=location,
                    field_name=field_spec.name,
                    value=value,
                    valid_options=[v.label for v in field_spec.values],
                )
            return None

        return InvalidOrderedValue(
            location=location,
            field_name=field_spec.name,
            value=value,
            valid_options=[v.label for v in field_spec.values],
        )

    def validate_chain(self, chain: ChainNode, field_spec: FieldSpec) -> ValidationResult:
        """
        Valida estrutura e semantica de cadeias causais.
        """
        result = ValidationResult()
        elements = [node.strip() for node in chain.nodes if node.strip()]
        if not elements:
            return result

        has_relations = bool(field_spec.relations)
        codes: list[str] = []
        relations: list[str] = []

        if has_relations:
            # Extrai codigos (posicoes pares) e relacoes (posicoes impares)
            if len(elements) < 3 or len(elements) % 2 == 0:
                result.add(
                    MalformedQualifiedChain(
                        location=chain.location,
                        elements=elements,
                    )
                )
                return result

            for idx, element in enumerate(elements):
                if idx % 2 == 0:
                    codes.append(element)
                else:
                    relations.append(element)
                    if element not in field_spec.relations:
                        result.add(
                            InvalidChainRelation(
                                location=chain.location,
                                relation=element,
                                valid_relations=list(field_spec.relations.keys()),
                                relation_descriptions=field_spec.relations,
                            )
                        )
        else:
            # Chain simples: todos os elementos sao codigos
            codes = elements

        arity_error = self._validate_chain_arity(field_spec, len(codes), chain.location)
        if arity_error:
            result.add(arity_error)

        for code in codes:
            if self._norm_code(code) not in self.ontology_index:
                result.add(
                    UndefinedCode(
                        location=chain.location,
                        code=code,
                        context="CHAIN",
                    )
                )

        return result

    def validate_bundle(
        self,
        node: SourceNode | ItemNode | OntologyNode,
        scope: Scope,
    ) -> ValidationResult:
        """
        Valida regras de BUNDLE:
        1. Campos do bundle nunca aparecem isolados
        2. Todos campos do bundle tem mesma quantidade
        3. Minimo 1 ocorrencia do bundle completo
        """
        result = ValidationResult()
        bundles = self.template.bundled_fields.get(scope, [])
        if not bundles:
            return result

        field_values = self._collect_fields(node)
        location = node.location or SourceLocation(file=Path("<unknown>"), line=1, column=1)

        for bundle in bundles:
            counts: Dict[str, int] = {}
            present_fields = set()
            # Valida tipos antes de contar para evitar falsos positivos
            if not self._bundle_types_valid(bundle, field_values):
                continue
            # Conta ocorrencias para cada campo do bundle
            for field_name in bundle:
                value = field_values.get(field_name)
                if value is None:
                    continue
                present_fields.add(field_name)
                counts[field_name] = self._count_value(value)

            # Validacao 2: ausencia completa do bundle
            if not present_fields:
                result.add(
                    MissingBundleField(
                        location=location,
                        bundle_fields=bundle,
                        present_fields=set(),
                    )
                )
                continue

            # Validacao 1: campo isolado
            if len(present_fields) != len(bundle):
                result.add(
                    MissingBundleField(
                        location=location,
                        bundle_fields=bundle,
                        present_fields=present_fields,
                    )
                )
                continue

            # Validacao 3: contagens diferentes
            if len(set(counts.values())) > 1:
                result.add(
                    BundleCountMismatch(
                        location=location,
                        bundle_fields=bundle,
                        counts=counts,
                    )
                )

        return result

    def _validate_bibref(
        self,
        bibref: str,
        location: Optional[SourceLocation],
        result: ValidationResult,
    ) -> None:
        # Se bibliografia nao fornecida, nao valida bibrefs
        # (usado pelo LSP quando .bib nao disponivel)
        if self.bibliography is None:
            return

        normalized = bibref.lstrip("@").lower().strip()
        if normalized not in self.bibliography:
            suggestions = suggest_bibref(normalized, list(self.bibliography.keys()))
            result.add(
                UnregisteredSource(
                    location=location or SourceLocation(file=Path("<unknown>"), line=1, column=1),
                    bibref=normalized,
                    suggestions=suggestions,
                )
            )

    def _validate_declared_fields(
        self,
        field_names: list[str],
        scope: Scope,
        location: Optional[SourceLocation],
        result: ValidationResult,
    ) -> None:
        if not field_names:
            return

        loc = location or SourceLocation(file=Path("<unknown>"), line=1, column=1)
        for name in sorted(set(field_names)):
            if name not in self.template.field_specs:
                result.add(
                    UnknownFieldName(
                        location=loc,
                        field_name=name,
                        block_type=scope.value,
                    )
                )

    def _validate_fields(
        self,
        node: SourceNode | ItemNode | OntologyNode,
        scope: Scope,
        result: ValidationResult,
    ) -> None:
        required = self.template.required_fields.get(scope, [])
        forbidden = self.template.forbidden_fields.get(scope, [])

        field_values = self._collect_fields(node)
        location = node.location or SourceLocation(file=Path("<unknown>"), line=1, column=1)

        for field_name in required:
            if not self._has_value(field_values.get(field_name)):
                result.add(
                    MissingRequiredField(
                        location=location,
                        field_name=field_name,
                        block_type=scope.value,
                    )
                )

        for field_name in forbidden:
            if self._has_value(field_values.get(field_name)):
                result.add(
                    ForbiddenFieldPresent(
                        location=location,
                        field_name=field_name,
                        block_type=scope.value,
                    )
                )

        for field_name, value in field_values.items():
            field_spec = self.template.field_specs.get(field_name)
            if not field_spec:
                continue
            self._validate_value(field_spec, value, location, result)

    def _collect_fields(self, node: SourceNode | ItemNode | OntologyNode) -> Dict[str, Any]:
        fields: Dict[str, Any] = {}
        if isinstance(node, SourceNode):
            fields.update(node.fields)
            return fields
        if isinstance(node, OntologyNode):
            fields.update(node.fields)
            if node.description:
                fields.setdefault("description", node.description)
            return fields
        if isinstance(node, ItemNode):
            fields.update(node.extra_fields)
            if node.quote:
                fields.setdefault("quote", node.quote)
                fields.setdefault("quotation", node.quote)
            if node.codes:
                fields.setdefault("code", node.codes)
                fields.setdefault("codes", node.codes)
            if node.notes:
                fields.setdefault("note", node.notes)
                fields.setdefault("notes", node.notes)
                fields.setdefault("memo", node.notes)
                fields.setdefault("memos", node.notes)
            if node.chains:
                fields.setdefault("chain", node.chains)
                fields.setdefault("chains", node.chains)
            return fields
        return fields

    def _validate_value(
        self,
        field_spec: FieldSpec,
        value: Any,
        location: SourceLocation,
        result: ValidationResult,
    ) -> None:
        if isinstance(value, list):
            for item in value:
                self._validate_value(field_spec, item, location, result)
            return

        expected = field_spec.type

        if expected == FieldType.TOPIC:
            # Coerção automática: números → string
            if isinstance(value, (int, float)):
                return  # Aceita números como string implicitamente
            if not isinstance(value, str):
                result.add(
                    InvalidFieldType(
                        location=location,
                        field_name=field_spec.name,
                        expected="string",
                        actual=type(value).__name__,
                    )
                )
            return

        if expected in {
            FieldType.QUOTATION,
            FieldType.MEMO,
            FieldType.TEXT,
            FieldType.DATE,
        }:
            # Coerção automática: números → string para campos de texto
            if isinstance(value, (int, float)):
                return  # Aceita números como string implicitamente
            if not isinstance(value, str):
                result.add(
                    InvalidFieldType(
                        location=location,
                        field_name=field_spec.name,
                        expected="string",
                        actual=type(value).__name__,
                    )
                )
            return

        if expected == FieldType.CODE:
            # Coerção automática: números → string
            if isinstance(value, (int, float)):
                return  # Aceita números como string implicitamente
            if not isinstance(value, str):
                result.add(
                    InvalidFieldType(
                        location=location,
                        field_name=field_spec.name,
                        expected="string",
                        actual=type(value).__name__,
                    )
                )
            return

        if expected == FieldType.CHAIN:
            if not isinstance(value, ChainNode):
                result.add(
                    InvalidFieldType(
                        location=location,
                        field_name=field_spec.name,
                        expected="chain",
                        actual=type(value).__name__,
                    )
                )
            return

        if expected == FieldType.ENUMERATED:
            # Coerção automática: números → string
            if isinstance(value, (int, float)):
                value = str(value)
            if not isinstance(value, str):
                result.add(
                    InvalidFieldType(
                        location=location,
                        field_name=field_spec.name,
                        expected="string",
                        actual=type(value).__name__,
                    )
                )
                return
            valid = [v.label for v in field_spec.values or []]
            if value not in valid:
                result.add(
                    InvalidEnumeratedValue(
                        location=location,
                        field_name=field_spec.name,
                        value=value,
                        valid_values=valid,
                    )
                )
            return

        if expected == FieldType.ORDERED:
            error = self.validate_ordered_value(field_spec, value, location)
            if error:
                result.add(error)
            return

        if expected == FieldType.SCALE:
            if not isinstance(value, (int, float)):
                result.add(
                    InvalidFieldType(
                        location=location,
                        field_name=field_spec.name,
                        expected="number",
                        actual=type(value).__name__,
                    )
                )
                return
            scale_range = self._parse_scale_format(field_spec.format)
            if scale_range:
                min_value, max_value = scale_range
                if value < min_value or value > max_value:
                    result.add(
                        ScaleOutOfRange(
                            location=location,
                            field_name=field_spec.name,
                            value=float(value),
                            min_value=min_value,
                            max_value=max_value,
                        )
                    )
            return

    def _parse_scale_format(self, fmt: Optional[str]) -> Optional[tuple[float, float]]:
        if not fmt:
            return None
        if not fmt.startswith("[") or ".." not in fmt or not fmt.endswith("]"):
            return None
        try:
            inner = fmt[1:-1]
            left, right = inner.split("..", 1)
            return float(left), float(right)
        except ValueError:
            return None

    def _has_value(self, value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return value.strip() != ""
        if isinstance(value, list):
            return len(value) > 0
        return True

    def _norm_code(self, code: str) -> str:
        return " ".join(code.strip().split()).lower()

    def _extract_code_values(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            codes: list[str] = []
            for entry in value:
                codes.extend(self._extract_code_values(entry))
            return codes
        if isinstance(value, (int, float)):
            return [str(value)]
        if isinstance(value, str):
            return [value]
        return []

    def _collect_item_codes(self, node: ItemNode) -> list[str]:
        codes = list(node.codes)
        field_values = self._collect_fields(node)
        for name, spec in self.template.field_specs.items():
            if spec.scope != Scope.ITEM or spec.type != FieldType.CODE:
                continue
            lname = name.lower()
            if lname in {"code", "codes"}:
                continue
            codes.extend(self._extract_code_values(field_values.get(name)))
        return codes

    def _validate_codes_defined(self, node: ItemNode, result: ValidationResult) -> None:
        location = node.location or SourceLocation(file=Path("<unknown>"), line=1, column=1)
        for code in self._collect_item_codes(node):
            if self._norm_code(code) not in self.ontology_index:
                result.add(
                    UndefinedCode(
                        location=location,
                        code=code,
                        context="ITEM",
                    )
                )

        # Para chains, precisa separar códigos de relações
        field_spec = self.template.field_specs.get("chain")
        if not field_spec:
            return

        has_relations = bool(field_spec.relations)

        for chain in node.chains:
            elements = [elem.strip() for elem in chain.nodes if elem.strip()]
            codes = []

            if has_relations:
                # Chain qualificada: códigos nas posições pares (0, 2, 4, ...)
                if len(elements) >= 3 and len(elements) % 2 == 1:
                    codes = [elements[i] for i in range(0, len(elements), 2)]
            else:
                # Chain simples: todos os elementos são códigos
                codes = elements

            for code in codes:
                if self._norm_code(code) not in self.ontology_index:
                    result.add(
                        UndefinedCode(
                            location=location,
                            code=code,
                            context="CHAIN",
                        )
                    )

    def _validate_chain_arity(
        self,
        field_spec: FieldSpec,
        count: int,
        location: SourceLocation,
    ) -> Optional[ValidationError]:
        if not field_spec.arity:
            return None
        try:
            op, raw_value = field_spec.arity.split()
            target = int(raw_value)
        except ValueError:
            return None
        ok = False
        if op == "=":
            ok = count == target
        elif op == ">=":
            ok = count >= target
        elif op == "<=":
            ok = count <= target
        elif op == ">":
            ok = count > target
        elif op == "<":
            ok = count < target
        if not ok:
            return ChainArityViolation(
                location=location,
                expected=field_spec.arity,
                found=count,
            )
        return None

    def _validate_chains(self, node: ItemNode, result: ValidationResult) -> None:
        field_spec = self.template.field_specs.get("chain")
        if not field_spec:
            return
        for chain in node.chains:
            chain_result = self.validate_chain(chain, field_spec)
            result.errors.extend(chain_result.errors)
            result.warnings.extend(chain_result.warnings)
            result.info.extend(chain_result.info)

    def _count_value(self, value: Any) -> int:
        if isinstance(value, list):
            return len(value)
        return 1

    def _bundle_types_valid(self, bundle: Tuple[str, ...], field_values: Dict[str, Any]) -> bool:
        for field_name in bundle:
            value = field_values.get(field_name)
            if value is None:
                continue
            field_spec = self.template.field_specs.get(field_name)
            if field_spec and not self._is_valid_value_type(field_spec, value):
                return False
        return True

    def _is_valid_value_type(self, field_spec: FieldSpec, value: Any) -> bool:
        if isinstance(value, list):
            return all(self._is_valid_value_type(field_spec, item) for item in value)
        expected = field_spec.type
        if expected == FieldType.TOPIC:
            return isinstance(value, str)
        if expected in {
            FieldType.QUOTATION,
            FieldType.MEMO,
            FieldType.TEXT,
            FieldType.DATE,
            FieldType.CODE,
        }:
            return isinstance(value, str)
        if expected == FieldType.CHAIN:
            return isinstance(value, ChainNode)
        if expected == FieldType.ENUMERATED:
            return isinstance(value, str)
        if expected == FieldType.ORDERED:
            return isinstance(value, (int, str))
        if expected == FieldType.SCALE:
            return isinstance(value, (int, float))
        return True
