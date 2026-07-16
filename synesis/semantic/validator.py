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

import re
from dataclasses import dataclass, field
from difflib import get_close_matches
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

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
from synesis.ast.normalize import normalize_code
from synesis.ast.results import (
    BundleCountMismatch,
    ChainArityViolation,
    ChainWithoutArrowOperator,
    ConceptNameMatchesRelation,
    ConceptWithSpaces,
    DecimalInIntegerScale,
    DuplicateCodeInField,
    DuplicateIdentityValue,
    EmptyItemBlock,
    ExternalReferenceDeclared,
    ForbiddenFieldPresent,
    InvalidChainRelation,
    InvalidEnumeratedValue,
    InvalidFieldType,
    InvalidIdentifierCharacter,
    InvalidOrderedValue,
    MalformedQualifiedChain,
    MissingBibliographyValue,
    MissingBundleField,
    MissingRequiredField,
    OntologyWithoutTemplateFields,
    QualifiedChainWithoutRelations,
    ScaleOutOfRange,
    SimpleChainWithRelationsRequired,
    TopicWithSpaces,
    UndefinedCode,
    UnknownFieldName,
    UnregisteredSource,
    ValidationError,
    ValidationResult,
)
from synesis.parser.bib_loader import find_bibref, suggest_bibref


@dataclass
class SemanticValidator:
    template: TemplateNode
    bibliography: Dict[str, Any]
    ontology_index: Dict[str, Any]
    norm_cache: dict | None = None
    malformed_bib_keys: set = field(default_factory=set)

    def __post_init__(self) -> None:
        self.ontology_index = {normalize_code(key, self.norm_cache): value for key, value in self.ontology_index.items()}

        # Pre-indexar: nomes de fields CODE no scope ITEM, excluindo "code"/"codes"
        # Invariante por compilação — evita iterar template.field_specs por item
        self._code_field_names: list[str] = []
        if self.template:
            for name, spec in self.template.field_specs.items():
                if spec.scope == Scope.ITEM and spec.type == FieldType.CODE:
                    if name.lower() not in {"code", "codes"}:
                        self._code_field_names.append(name)

        # Pre-indexar: todos os fields CHAIN no scope ITEM (incluindo "chain"/"chains")
        self._chain_field_specs: list[tuple[str, Any]] = []
        if self.template:
            for name, spec in self.template.field_specs.items():
                if spec.scope == Scope.ITEM and spec.type == FieldType.CHAIN:
                    self._chain_field_specs.append((name, spec))

        # Regex para validar identificadores Synesis: letras Unicode, números, underscore e hífen.
        # \w com re.UNICODE cobre [a-zA-Z0-9_] + qualquer letra/dígito Unicode (ç, ã, é, etc.).
        self._identifier_invalid_re = re.compile(r"[^\w\-]", re.UNICODE)

    def _suggest_concept(self, code: str) -> list[str]:
        """Retorna até 1 conceito similar ao code usando get_close_matches."""
        candidates = list(self.ontology_index.keys())
        normalized = normalize_code(code, self.norm_cache)
        matches = get_close_matches(normalized, candidates, n=1, cutoff=0.6)
        # Desnormalizar: retornar a forma original do conceito, não a normalizada
        if matches:
            matched_key = matches[0]
            entry = self.ontology_index.get(matched_key)
            original = getattr(entry, "concept", matched_key)
            return [original]
        return []

    def validate_project(self, node: ProjectNode) -> ValidationResult:
        result = ValidationResult()
        # Erro 5: ontologias presentes mas template sem ONTOLOGY FIELDS
        if self.ontology_index and self.template:
            has_ontology_fields = bool(
                self.template.required_fields.get(Scope.ONTOLOGY)
                or self.template.optional_fields.get(Scope.ONTOLOGY)
                or self.template.forbidden_fields.get(Scope.ONTOLOGY)
                or self.template.bundled_fields.get(Scope.ONTOLOGY)
            )
            if not has_ontology_fields:
                result.add(OntologyWithoutTemplateFields(
                    location=node.location or SourceLocation(file=Path("<unknown>"), line=1, column=1)
                ))
        return result

    def validate_source(self, node: SourceNode) -> ValidationResult:
        result = ValidationResult()
        self._validate_bibref(node.bibref, node.location, result)
        self._validate_declared_fields(list(node.fields.keys()), Scope.SOURCE, node.location, result)
        self._validate_fields(node, Scope.SOURCE, result)
        bundle_result = self.validate_bundle(node, Scope.SOURCE)
        result.errors.extend(bundle_result.errors)
        result.warnings.extend(bundle_result.warnings)
        result.info.extend(bundle_result.info)
        opt_bundle_result = self.validate_optional_bundle(node, Scope.SOURCE)
        result.errors.extend(opt_bundle_result.errors)
        result.warnings.extend(opt_bundle_result.warnings)
        result.info.extend(opt_bundle_result.info)
        return result

    def validate_identity_uniqueness(self, sources: List[SourceNode]) -> ValidationResult:
        """Erro 77: unicidade dos campos IDENTIFIES (chave primaria de entidade).

        Cross-source: cada valor de um campo `IDENTIFIES` deve identificar um unico
        SOURCE. Roda uma vez sobre todos os SOURCEs do membro, antes de qualquer
        linkagem. Comparacao por igualdade exata pos-trim (sem case-folding, sem
        normalizacao) — coerente com a regra anti-fuzzy do link step.
        """
        result = ValidationResult()
        if not self.template:
            return result

        identity_fields = [
            (name, spec)
            for name, spec in self.template.field_specs.items()
            if spec.identifies and spec.scope == Scope.SOURCE
        ]
        if not identity_fields:
            return result

        for field_name, spec in identity_fields:
            seen: Dict[str, str] = {}  # valor -> bibref do primeiro SOURCE que o usou
            for source in sources:
                raw = source.fields.get(field_name)
                if not self._has_value(raw):
                    continue
                value = str(raw).strip()
                if value in seen:
                    result.add(DuplicateIdentityValue(
                        location=source.location or SourceLocation(
                            file=Path("<unknown>"), line=1, column=1
                        ),
                        field_name=field_name,
                        entity=spec.identifies,
                        value=value,
                        first_bibref=seen[value],
                        duplicate_bibref=source.bibref,
                    ))
                else:
                    seen[value] = source.bibref
        return result

    def validate_external_references(self) -> ValidationResult:
        """INFO 80: projeto declara REFERS TO — referencia externa nao resolvida.

        Emitido uma vez por entidade distinta referenciada. Severidade INFO (nao
        warning): a referencia externa e esperada na compilacao isolada; so se
        resolve num link step. Nunca polui o painel com warning recorrente.
        """
        result = ValidationResult()
        if not self.template:
            return result
        seen_entities: set = set()
        for name, spec in self.template.field_specs.items():
            if spec.refers_to and spec.refers_to not in seen_entities:
                seen_entities.add(spec.refers_to)
                result.add(ExternalReferenceDeclared(
                    location=spec.location or SourceLocation(
                        file=Path("<template>"), line=1, column=1
                    ),
                    entity=spec.refers_to,
                    field_name=name,
                ))
        return result

    def validate_bibliography_values(self, sources: List[SourceNode]) -> ValidationResult:
        """Erro 79: campo REQUIRED ... ON BIBLIOGRAPHY sem valor no .bib do SOURCE.

        O valor de um campo `ON BIBLIOGRAPHY` vem da entrada `.bib` do proprio
        SOURCE (via bibref), nao do texto. Se a entrada nao tem o campo, o
        REQUIRED nao pode ser satisfeito.
        """
        result = ValidationResult()
        if not self.template:
            return result

        bib_fields = [
            name
            for name, spec in self.template.field_specs.items()
            if spec.value_origin == "bibliography" and spec.scope == Scope.SOURCE
        ]
        if not bib_fields:
            return result

        for source in sources:
            key = source.bibref.lstrip("@")
            entry = find_bibref(self.bibliography, key) if self.bibliography else None
            for field_name in bib_fields:
                # valor pode vir do .bib OU ja estar no proprio SOURCE
                if self._has_value(source.fields.get(field_name)):
                    continue
                bib_val = entry.get(field_name) if entry else None
                if not self._has_value(bib_val):
                    result.add(MissingBibliographyValue(
                        location=source.location or SourceLocation(
                            file=Path("<unknown>"), line=1, column=1
                        ),
                        field_name=field_name,
                        bibref=source.bibref,
                    ))
        return result

    def validate_item(self, node: ItemNode) -> ValidationResult:
        result = ValidationResult()
        # Erro 23: ITEM vazio (sem campos)
        field_values = self._collect_fields(node)
        has_content = any(self._has_value(v) for v in field_values.values())
        if not has_content:
            result.add(EmptyItemBlock(
                location=node.location or SourceLocation(file=Path("<unknown>"), line=1, column=1)
            ))
            return result
        self._validate_declared_fields(node.field_names, Scope.ITEM, node.location, result)
        self._validate_fields(node, Scope.ITEM, result)
        self._validate_codes_defined(node, result)
        self._validate_chains(node, result)
        self._validate_code_fields_duplicates(node, result)
        bundle_result = self.validate_bundle(node, Scope.ITEM)
        result.errors.extend(bundle_result.errors)
        result.warnings.extend(bundle_result.warnings)
        result.info.extend(bundle_result.info)
        opt_bundle_result = self.validate_optional_bundle(node, Scope.ITEM)
        result.errors.extend(opt_bundle_result.errors)
        result.warnings.extend(opt_bundle_result.warnings)
        result.info.extend(opt_bundle_result.info)
        return result

    def validate_ontology(self, node: OntologyNode) -> ValidationResult:
        result = ValidationResult()
        self._validate_declared_fields(node.field_names, Scope.ONTOLOGY, node.location, result)
        self._validate_fields(node, Scope.ONTOLOGY, result)
        bundle_result = self.validate_bundle(node, Scope.ONTOLOGY)
        result.errors.extend(bundle_result.errors)
        result.warnings.extend(bundle_result.warnings)
        result.info.extend(bundle_result.info)
        opt_bundle_result = self.validate_optional_bundle(node, Scope.ONTOLOGY)
        result.errors.extend(opt_bundle_result.errors)
        result.warnings.extend(opt_bundle_result.warnings)
        result.info.extend(opt_bundle_result.info)
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

        # Erro 13 (defensivo): chain com elemento unico sem seta — parser normalmente captura antes
        if len(elements) == 1:
            result.add(ChainWithoutArrowOperator(
                location=chain.location,
                raw_value=elements[0],
            ))
            return result

        # Erro 15: conceito com espacos em algum elemento
        for elem in elements:
            if " " in elem:
                result.add(ConceptWithSpaces(
                    location=chain.location,
                    concept=elem,
                ))

        has_relations = bool(field_spec.relations)
        codes: list[str] = []
        relations_found: list[str] = []

        if has_relations:
            # Extrai codigos (posicoes pares) e relacoes (posicoes impares)
            if len(elements) < 3 or len(elements) % 2 == 0:
                # Antes de declarar malformada: se tem 2 elementos e nenhum deles é
                # uma relação reconhecida → chain simples com RELATIONS exigido (erro 9)
                if len(elements) == 2:
                    second_is_relation = elements[1] in field_spec.relations
                    if not second_is_relation:
                        result.add(SimpleChainWithRelationsRequired(
                            location=chain.location,
                            field_name=field_spec.name,
                            valid_relations=list(field_spec.relations.keys()),
                        ))
                        return result
                result.add(
                    MalformedQualifiedChain(
                        location=chain.location,
                        elements=elements,
                    )
                )
                return result

            # Verifica se os elementos em posição ímpar parecem ser códigos em vez de relações.
            # Heurística: se nenhum elemento ímpar está nas RELATIONS definidas e nenhum é
            # totalmente maiúsculo, a chain foi escrita sem relações → erro 9.
            odd_elements = [elements[i] for i in range(1, len(elements), 2)]
            all_odd_are_codes = all(
                e not in (field_spec.relations or {}) and not e.isupper()
                for e in odd_elements
            )
            if all_odd_are_codes:
                result.add(SimpleChainWithRelationsRequired(
                    location=chain.location,
                    field_name=field_spec.name,
                    valid_relations=list(field_spec.relations.keys()),
                ))
                return result

            for idx, element in enumerate(elements):
                if idx % 2 == 0:
                    codes.append(element)
                else:
                    relations_found.append(element)
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
            # Erro 8: se parece ter relações (número ímpar ≥ 3 com maiúsculas em posições ímpares)
            if len(elements) >= 3 and len(elements) % 2 == 1:
                odd_elements = [elements[i] for i in range(1, len(elements), 2)]
                if any(e.isupper() for e in odd_elements):
                    result.add(QualifiedChainWithoutRelations(
                        location=chain.location,
                        field_name=field_spec.name,
                    ))
                    return result
            codes = elements

        arity_error = self._validate_chain_arity(field_spec, len(codes), chain.location)
        if arity_error:
            result.add(arity_error)

        relation_names = set(field_spec.relations.keys()) if field_spec.relations else set()
        for code in codes:
            # Erro 33: caracteres inválidos no conceito de CHAIN
            self._validate_identifier(code, chain.location, result)
            # Erro 14: conceito com mesmo nome de uma relação
            if relation_names and code in relation_names:
                result.add(
                    ConceptNameMatchesRelation(
                        location=chain.location,
                        name=code,
                        field_name=field_spec.name,
                    )
                )
            if normalize_code(code, self.norm_cache) not in self.ontology_index:
                result.add(
                    UndefinedCode(
                        location=chain.location,
                        code=code,
                        context="CHAIN",
                        suggestions=self._suggest_concept(code),
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

    def validate_optional_bundle(
        self,
        node: SourceNode | ItemNode | OntologyNode,
        scope: Scope,
    ) -> ValidationResult:
        """
        Valida OPTIONAL BUNDLE: ausencia total e valida; presenca parcial ou
        contagens divergentes sao erro (mesma logica do validate_bundle, mas
        sem exigir presenca minima).
        """
        result = ValidationResult()
        bundles = self.template.optional_bundles.get(scope, [])
        if not bundles:
            return result

        field_values = self._collect_fields(node)
        location = node.location or SourceLocation(file=Path("<unknown>"), line=1, column=1)

        for bundle in bundles:
            counts: Dict[str, int] = {}
            present_fields = set()
            if not self._bundle_types_valid(bundle, field_values):
                continue
            for field_name in bundle:
                value = field_values.get(field_name)
                if value is None:
                    continue
                present_fields.add(field_name)
                counts[field_name] = self._count_value(value)

            # Ausencia total do bundle e valida (diferenca em relacao ao REQUIRED BUNDLE)
            if not present_fields:
                continue

            # Presenca parcial: erro
            if len(present_fields) != len(bundle):
                result.add(
                    MissingBundleField(
                        location=location,
                        bundle_fields=bundle,
                        present_fields=present_fields,
                    )
                )
                continue

            # Contagens divergentes: erro
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
        if normalized in self.malformed_bib_keys:
            return
        if normalized not in self.bibliography:
            clean_keys = [k.lstrip("@") for k in self.bibliography.keys()]
            suggestions = suggest_bibref(normalized, clean_keys)
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
            # Campos ON BIBLIOGRAPHY tem valor no .bib, nao no bloco SOURCE —
            # sua obrigatoriedade e verificada por validate_bibliography_values
            # (erro 79). Aqui os pulamos para nao emitir E020 espurio.
            spec = self.template.field_specs.get(field_name)
            if spec is not None and spec.value_origin == "bibliography":
                continue
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
            # Erro 32: TOPIC com espaços
            if " " in value:
                result.add(TopicWithSpaces(
                    location=location,
                    field_name=field_spec.name,
                    value=value,
                ))
                return
            # Erro 33: caracteres inválidos em TOPIC
            self._validate_identifier(value, location, result)
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
            # Erro 33: caracteres inválidos nos identificadores CODE
            for code_part in self._extract_code_values(value):
                self._validate_identifier(code_part, location, result)
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
                # Erro 26: decimal em intervalo inteiro
                if min_value == int(min_value) and max_value == int(max_value):
                    if isinstance(value, float) and value != int(value):
                        result.add(
                            DecimalInIntegerScale(
                                location=location,
                                field_name=field_spec.name,
                                value=str(value),
                                min_val=min_value,
                                max_val=max_value,
                            )
                        )
                        return
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
            # TEXT_LINE tem prioridade sobre CODE_ELEMENT no lexer contextual, então
            # "CREATOR, EARTH, HEAVENS" chega como string única. Fazemos o split aqui.
            if "," in value:
                return [part.strip() for part in value.split(",") if part.strip()]
            return [value]
        return []

    def _collect_item_codes(self, node: ItemNode) -> list[str]:
        codes = list(node.codes)
        if not self._code_field_names:
            return codes
        field_values = self._collect_fields(node)
        for name in self._code_field_names:
            codes.extend(self._extract_code_values(field_values.get(name)))
        return codes

    def _validate_codes_defined(self, node: ItemNode, result: ValidationResult) -> None:
        location = node.location or SourceLocation(file=Path("<unknown>"), line=1, column=1)
        for code in self._collect_item_codes(node):
            if normalize_code(code, self.norm_cache) not in self.ontology_index:
                result.add(
                    UndefinedCode(
                        location=location,
                        code=code,
                        context="ITEM",
                        suggestions=self._suggest_concept(code),
                    )
                )

        # Para chains, precisa separar códigos de relações — iterar todos os campos CHAIN
        field_values = self._collect_fields(node)
        for field_name, field_spec in self._chain_field_specs:
            has_relations = bool(field_spec.relations)
            raw = field_values.get(field_name)
            chain_nodes: list[ChainNode] = []
            if isinstance(raw, ChainNode):
                chain_nodes = [raw]
            elif isinstance(raw, list):
                chain_nodes = [v for v in raw if isinstance(v, ChainNode)]

            for chain in chain_nodes:
                elements = [elem.strip() for elem in chain.nodes if elem.strip()]
                codes: list[str] = []

                if has_relations:
                    # Chain qualificada: códigos nas posições pares (0, 2, 4, ...)
                    if len(elements) >= 3 and len(elements) % 2 == 1:
                        codes = [elements[i] for i in range(0, len(elements), 2)]
                else:
                    # Chain simples: todos os elementos são códigos
                    codes = elements

                for code in codes:
                    if normalize_code(code, self.norm_cache) not in self.ontology_index:
                        result.add(
                            UndefinedCode(
                                location=location,
                                code=code,
                                context="CHAIN",
                                suggestions=self._suggest_concept(code),
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
        field_values = self._collect_fields(node)
        for field_name, field_spec in self._chain_field_specs:
            raw = field_values.get(field_name)
            chain_nodes: list[ChainNode] = []
            if isinstance(raw, ChainNode):
                chain_nodes = [raw]
            elif isinstance(raw, list):
                chain_nodes = [v for v in raw if isinstance(v, ChainNode)]

            for chain in chain_nodes:
                chain_result = self.validate_chain(chain, field_spec)
                result.errors.extend(chain_result.errors)
                result.warnings.extend(chain_result.warnings)
                result.info.extend(chain_result.info)

    def _validate_identifier(
        self,
        name: str,
        location: SourceLocation,
        result: ValidationResult,
    ) -> None:
        """Erro 33: valida que o identificador contem apenas letras, numeros, underscore e hifen."""
        if not name:
            return
        match = self._identifier_invalid_re.search(name)
        if match:
            result.add(InvalidIdentifierCharacter(
                location=location,
                name=name,
                invalid_char=match.group(0),
            ))

    def _validate_code_fields_duplicates(
        self,
        node: ItemNode,
        result: ValidationResult,
    ) -> None:
        """Erro 31: mesmo codigo repetido na mesma ocorrencia de campo CODE."""
        location = node.location or SourceLocation(file=Path("<unknown>"), line=1, column=1)
        field_values = self._collect_fields(node)

        # Checar campo "code" padrao (node.codes)
        self._check_duplicate_codes_in_list("code", node.codes, location, result)

        # Checar campos CODE extras definidos no template
        for field_name in self._code_field_names:
            raw = field_values.get(field_name)
            if raw is not None:
                codes = self._extract_code_values(raw)
                self._check_duplicate_codes_in_list(field_name, codes, location, result)

    def _check_duplicate_codes_in_list(
        self,
        field_name: str,
        codes: List[str],
        location: SourceLocation,
        result: ValidationResult,
    ) -> None:
        """Detecta codigos duplicados em uma lista de codigos de um mesmo campo."""
        seen: set = set()
        for code in codes:
            normalized = normalize_code(code, self.norm_cache)
            if normalized in seen:
                result.add(DuplicateCodeInField(
                    location=location,
                    field_name=field_name,
                    code=code,
                ))
            seen.add(normalized)

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
