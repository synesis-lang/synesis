"""
test_validator.py - Testes unitarios do SemanticValidator

Cobre: campos REQUIRED/OPTIONAL/FORBIDDEN, tipos, BUNDLE, CHAIN, ORDERED,
       ENUMERATED, SCALE, bibrefs e codigos indefinidos.

Gerado conforme: Especificacao Synesis v1.1
"""

import pytest
from pathlib import Path

from synesis.ast.nodes import (
    ChainNode,
    FieldSpec,
    FieldType,
    ItemNode,
    OntologyNode,
    Scope,
    SourceLocation,
    SourceNode,
    TemplateNode,
    OrderedValue,
)
from synesis.ast.results import (
    BundleCountMismatch,
    ChainArityViolation,
    ForbiddenFieldPresent,
    InvalidChainRelation,
    InvalidEnumeratedValue,
    InvalidOrderedValue,
    MalformedQualifiedChain,
    MissingBundleField,
    MissingRequiredField,
    ScaleOutOfRange,
    UndefinedCode,
    UnknownFieldName,
    UnregisteredSource,
)
from synesis.semantic.validator import SemanticValidator


# ===========================================================================
# Helpers
# ===========================================================================

LOC = SourceLocation(file=Path("test.syn"), line=1, column=1)


def make_field_spec(
    name: str,
    ftype: FieldType,
    scope: Scope = Scope.ITEM,
    relations: dict | None = None,
    values: list | None = None,
    arity: str | None = None,
    fmt: str | None = None,
) -> FieldSpec:
    return FieldSpec(
        name=name,
        type=ftype,
        scope=scope,
        relations=relations,
        values=values,
        arity=arity,
        format=fmt,
        description="",
        location=LOC,
    )


def make_template(
    field_specs: dict,
    required: dict | None = None,
    optional: dict | None = None,
    forbidden: dict | None = None,
    bundles: dict | None = None,
) -> TemplateNode:
    return TemplateNode(
        name="test",
        metadata={},
        field_specs=field_specs,
        required_fields=required or {},
        optional_fields=optional or {},
        forbidden_fields=forbidden or {},
        bundled_fields=bundles or {},
        location=LOC,
    )


def make_source(bibref: str = "@ref2024", fields: dict | None = None) -> SourceNode:
    return SourceNode(
        bibref=bibref,
        fields=fields or {},
        items=[],
        location=LOC,
    )


def make_item(
    bibref: str = "@ref2024",
    quote: str = "A quote.",
    codes: list | None = None,
    notes: list | None = None,
    chains: list | None = None,
    extra_fields: dict | None = None,
    field_names: list | None = None,
) -> ItemNode:
    return ItemNode(
        bibref=bibref,
        quote=quote,
        codes=codes or [],
        notes=notes or [],
        chains=chains or [],
        extra_fields=extra_fields or {},
        code_locations={},
        field_line_tokens={},
        field_names=field_names or [],
        location=LOC,
    )


def make_ontology(concept: str, fields: dict | None = None) -> OntologyNode:
    return OntologyNode(
        concept=concept,
        description="A definition.",
        fields=fields or {},
        parent_chains=[],
        field_names=list((fields or {}).keys()),
        location=LOC,
    )


def make_chain(nodes: list[str], location: SourceLocation | None = None) -> ChainNode:
    return ChainNode(
        nodes=nodes,
        relations=[],
        location=location or LOC,
    )


# ===========================================================================
# Bibref
# ===========================================================================

class TestBibref:

    def setup_method(self):
        specs = {"summary": make_field_spec("summary", FieldType.TEXT, Scope.SOURCE)}
        self.template = make_template(specs)

    def test_valid_bibref_no_error(self):
        bib = {"ref2024": {}}
        validator = SemanticValidator(self.template, bib, {})
        source = make_source("@ref2024")
        result = validator.validate_source(source)
        assert not result.has_errors()

    def test_invalid_bibref_generates_error(self):
        bib = {"ref2024": {}}
        validator = SemanticValidator(self.template, bib, {})
        source = make_source("@nonexistent9999")
        result = validator.validate_source(source)
        assert result.has_errors()
        assert any(isinstance(e, UnregisteredSource) for e in result.errors)

    def test_none_bibliography_skips_validation(self):
        validator = SemanticValidator(self.template, None, {})
        source = make_source("@anything")
        result = validator.validate_source(source)
        assert not result.has_errors()

    def test_empty_dict_bibliography_still_validates(self):
        # WI-1: distincao semantica entre None (sem INCLUDE BIBLIOGRAPHY -> nao valida)
        # e {} (bib declarada porem vazia -> ainda valida e reporta E001).
        validator = SemanticValidator(self.template, {}, {})
        source = make_source("@anything")
        result = validator.validate_source(source)
        assert any(isinstance(e, UnregisteredSource) for e in result.errors)


# ===========================================================================
# Campos desconhecidos
# ===========================================================================

class TestUnknownFields:

    def test_unknown_field_in_item_generates_error(self):
        specs = {"citation": make_field_spec("citation", FieldType.QUOTATION)}
        template = make_template(specs)
        validator = SemanticValidator(template, None, {})
        item = make_item(field_names=["citation", "nonexistent_field"])
        result = validator.validate_item(item)
        assert any(isinstance(e, UnknownFieldName) for e in result.errors)

    def test_known_field_no_error(self):
        specs = {"citation": make_field_spec("citation", FieldType.QUOTATION)}
        template = make_template(specs, required={Scope.ITEM: ["citation"]})
        validator = SemanticValidator(template, None, {})
        item = make_item(quote="A quote.", field_names=["citation"])
        result = validator.validate_item(item)
        unknown = [e for e in result.errors if isinstance(e, UnknownFieldName)]
        assert len(unknown) == 0


# ===========================================================================
# Campos REQUIRED
# ===========================================================================

class TestRequiredFields:

    def test_missing_required_field_generates_error(self):
        # Item com conteúdo presente mas campo obrigatório ausente
        specs = {
            "quotation": make_field_spec("quotation", FieldType.QUOTATION),
            "citation": make_field_spec("citation", FieldType.QUOTATION),
        }
        template = make_template(specs, required={Scope.ITEM: ["citation"]})
        validator = SemanticValidator(template, None, {})
        item = make_item(quote="Some content")  # item tem conteúdo mas não tem 'citation'
        result = validator.validate_item(item)
        assert any(isinstance(e, MissingRequiredField) for e in result.errors)

    def test_empty_item_generates_error(self):
        specs = {"citation": make_field_spec("citation", FieldType.QUOTATION)}
        template = make_template(specs, required={Scope.ITEM: ["citation"]})
        validator = SemanticValidator(template, None, {})
        from synesis.ast.results import EmptyItemBlock
        item = make_item(quote="")  # item vazio → EmptyItemBlock
        result = validator.validate_item(item)
        assert any(isinstance(e, EmptyItemBlock) for e in result.errors)

    def test_present_required_field_no_error(self):
        # O validator mapeia item.quote para os aliases 'quote' e 'quotation'
        # via _collect_fields. Se o template requer 'quotation', o campo é encontrado.
        specs = {"quotation": make_field_spec("quotation", FieldType.QUOTATION)}
        template = make_template(specs, required={Scope.ITEM: ["quotation"]})
        validator = SemanticValidator(template, None, {})
        item = make_item(quote="A valid quote.")
        result = validator.validate_item(item)
        missing = [e for e in result.errors if isinstance(e, MissingRequiredField)]
        assert len(missing) == 0


# ===========================================================================
# Campos FORBIDDEN
# ===========================================================================

class TestForbiddenFields:

    def test_forbidden_field_present_generates_error(self):
        specs = {
            "citation": make_field_spec("citation", FieldType.QUOTATION),
            "restricted": make_field_spec("restricted", FieldType.TEXT),
        }
        template = make_template(
            specs,
            required={Scope.ITEM: ["citation"]},
            forbidden={Scope.ITEM: ["restricted"]},
        )
        validator = SemanticValidator(template, None, {})
        item = make_item(
            quote="A quote.",
            extra_fields={"restricted": "some value"},
            field_names=["citation", "restricted"],
        )
        result = validator.validate_item(item)
        assert any(isinstance(e, ForbiddenFieldPresent) for e in result.errors)

    def test_forbidden_field_absent_no_error(self):
        specs = {
            "citation": make_field_spec("citation", FieldType.QUOTATION),
            "restricted": make_field_spec("restricted", FieldType.TEXT),
        }
        template = make_template(
            specs,
            required={Scope.ITEM: ["citation"]},
            forbidden={Scope.ITEM: ["restricted"]},
        )
        validator = SemanticValidator(template, None, {})
        item = make_item(quote="A quote.", field_names=["citation"])
        result = validator.validate_item(item)
        forbidden = [e for e in result.errors if isinstance(e, ForbiddenFieldPresent)]
        assert len(forbidden) == 0


# ===========================================================================
# Codigos indefinidos
# ===========================================================================

class TestUndefinedCodes:

    def test_defined_code_no_warning(self):
        specs = {"tag": make_field_spec("tag", FieldType.CODE)}
        template = make_template(specs)
        ontology_index = {"social_cohesion": make_ontology("Social_Cohesion")}
        validator = SemanticValidator(template, None, ontology_index)
        item = make_item(codes=["Social_Cohesion"])
        result = validator.validate_item(item)
        undefined = [e for e in result.warnings if isinstance(e, UndefinedCode)]
        assert len(undefined) == 0

    def test_undefined_code_generates_warning(self):
        specs = {"tag": make_field_spec("tag", FieldType.CODE)}
        template = make_template(specs)
        validator = SemanticValidator(template, None, {})
        item = make_item(codes=["Nonexistent_Code"])
        result = validator.validate_item(item)
        assert any(isinstance(e, UndefinedCode) for e in result.warnings)

    def test_code_normalization_case_insensitive(self):
        specs = {"tag": make_field_spec("tag", FieldType.CODE)}
        template = make_template(specs)
        ontology_index = {"social_cohesion": make_ontology("Social_Cohesion")}
        validator = SemanticValidator(template, None, ontology_index)
        item = make_item(codes=["SOCIAL_COHESION"])  # maiúsculas
        result = validator.validate_item(item)
        undefined = [e for e in result.warnings if isinstance(e, UndefinedCode)]
        assert len(undefined) == 0


# ===========================================================================
# CHAIN
# ===========================================================================

class TestChainValidation:

    def _make_chain_template(self, arity: str | None = None) -> tuple:
        relations = {"INFLUENCES": "Causal influence", "ENABLES": "Enabling condition"}
        chain_spec = make_field_spec("chain", FieldType.CHAIN, relations=relations, arity=arity)
        template = make_template({"chain": chain_spec})
        return template, chain_spec

    def test_valid_qualified_chain(self):
        template, chain_spec = self._make_chain_template()
        ontology_index = {
            "concept_a": make_ontology("Concept_A"),
            "concept_b": make_ontology("Concept_B"),
        }
        validator = SemanticValidator(template, None, ontology_index)
        chain = make_chain(["Concept_A", "INFLUENCES", "Concept_B"])
        result = validator.validate_chain(chain, chain_spec)
        assert not result.has_errors()

    def test_malformed_qualified_chain_even_elements(self):
        template, chain_spec = self._make_chain_template()
        validator = SemanticValidator(template, None, {})
        chain = make_chain(["A", "INFLUENCES", "B", "ENABLES"])  # par → malformado
        result = validator.validate_chain(chain, chain_spec)
        assert any(isinstance(e, MalformedQualifiedChain) for e in result.errors)

    def test_malformed_qualified_chain_too_short(self):
        template, chain_spec = self._make_chain_template()
        validator = SemanticValidator(template, None, {})
        chain = make_chain(["A", "INFLUENCES"])  # apenas 2 elementos → malformado
        result = validator.validate_chain(chain, chain_spec)
        assert any(isinstance(e, MalformedQualifiedChain) for e in result.errors)

    def test_invalid_relation_generates_error(self):
        template, chain_spec = self._make_chain_template()
        ontology_index = {
            "concept_a": make_ontology("Concept_A"),
            "concept_b": make_ontology("Concept_B"),
        }
        validator = SemanticValidator(template, None, ontology_index)
        chain = make_chain(["Concept_A", "NONEXISTENT_RELATION", "Concept_B"])
        result = validator.validate_chain(chain, chain_spec)
        assert any(isinstance(e, InvalidChainRelation) for e in result.errors)

    def test_arity_violation(self):
        template, chain_spec = self._make_chain_template(arity=">= 3")
        ontology_index = {"a": make_ontology("A"), "b": make_ontology("B")}
        validator = SemanticValidator(template, None, ontology_index)
        chain = make_chain(["A", "INFLUENCES", "B"])  # 2 códigos, exige >= 3
        result = validator.validate_chain(chain, chain_spec)
        assert any(isinstance(e, ChainArityViolation) for e in result.errors)

    def test_arity_satisfied(self):
        template, chain_spec = self._make_chain_template(arity=">= 2")
        ontology_index = {"a": make_ontology("A"), "b": make_ontology("B")}
        validator = SemanticValidator(template, None, ontology_index)
        chain = make_chain(["A", "INFLUENCES", "B"])  # 2 códigos, satisfaz >= 2
        result = validator.validate_chain(chain, chain_spec)
        arity_errors = [e for e in result.errors if isinstance(e, ChainArityViolation)]
        assert len(arity_errors) == 0

    def test_decimal_arity_value_generates_e060(self):
        # WI-5: ARITY = 2.0 deve gerar NonIntegerArityValue (E060) na validacao de
        # template, em vez de ser silenciosamente ignorado em _validate_chain_arity.
        from synesis.ast.results import NonIntegerArityValue
        from synesis.parser.template_loader import validate_template
        template, _ = self._make_chain_template(arity="= 2.0")
        result = validate_template(template)
        assert any(isinstance(e, NonIntegerArityValue) for e in result.errors)

    def test_integer_arity_value_no_e060(self):
        from synesis.ast.results import NonIntegerArityValue
        from synesis.parser.template_loader import validate_template
        template, _ = self._make_chain_template(arity=">= 2")
        result = validate_template(template)
        assert not any(isinstance(e, NonIntegerArityValue) for e in result.errors)


# ===========================================================================
# ORDERED
# ===========================================================================

class TestOrderedValidation:

    def _make_ordered_spec(self) -> FieldSpec:
        values = [
            OrderedValue(index=1, label="low", description="Low level", location=LOC),
            OrderedValue(index=2, label="medium", description="Medium level", location=LOC),
            OrderedValue(index=3, label="high", description="High level", location=LOC),
        ]
        return make_field_spec("priority", FieldType.ORDERED, values=values)

    def test_valid_label(self):
        spec = self._make_ordered_spec()
        validator = SemanticValidator(make_template({"priority": spec}), None, {})
        assert validator.validate_ordered_value(spec, "medium", LOC) is None

    def test_valid_index(self):
        spec = self._make_ordered_spec()
        validator = SemanticValidator(make_template({"priority": spec}), None, {})
        assert validator.validate_ordered_value(spec, 2, LOC) is None

    def test_invalid_label(self):
        spec = self._make_ordered_spec()
        validator = SemanticValidator(make_template({"priority": spec}), None, {})
        assert isinstance(validator.validate_ordered_value(spec, "extreme", LOC), InvalidOrderedValue)

    def test_invalid_index(self):
        spec = self._make_ordered_spec()
        validator = SemanticValidator(make_template({"priority": spec}), None, {})
        assert isinstance(validator.validate_ordered_value(spec, 99, LOC), InvalidOrderedValue)

    def test_case_insensitive_label(self):
        spec = self._make_ordered_spec()
        validator = SemanticValidator(make_template({"priority": spec}), None, {})
        assert validator.validate_ordered_value(spec, "MEDIUM", LOC) is None


# ===========================================================================
# SCALE
# ===========================================================================

class TestScaleValidation:

    def _make_scale_template(self) -> TemplateNode:
        spec = make_field_spec("confidence", FieldType.SCALE, fmt="[1..5]")
        return make_template({"confidence": spec})

    def test_value_within_range_no_error(self):
        template = self._make_scale_template()
        validator = SemanticValidator(template, None, {})
        item = make_item(extra_fields={"confidence": 3}, field_names=["confidence"])
        result = validator.validate_item(item)
        assert not any(isinstance(e, ScaleOutOfRange) for e in result.errors)

    def test_value_below_range_generates_error(self):
        template = self._make_scale_template()
        validator = SemanticValidator(template, None, {})
        item = make_item(extra_fields={"confidence": 0}, field_names=["confidence"])
        result = validator.validate_item(item)
        assert any(isinstance(e, ScaleOutOfRange) for e in result.errors)

    def test_value_above_range_generates_error(self):
        template = self._make_scale_template()
        validator = SemanticValidator(template, None, {})
        item = make_item(extra_fields={"confidence": 6}, field_names=["confidence"])
        result = validator.validate_item(item)
        assert any(isinstance(e, ScaleOutOfRange) for e in result.errors)

    def test_boundary_values_accepted(self):
        template = self._make_scale_template()
        validator = SemanticValidator(template, None, {})
        for boundary in [1, 5]:
            item = make_item(extra_fields={"confidence": boundary}, field_names=["confidence"])
            result = validator.validate_item(item)
            assert not any(isinstance(e, ScaleOutOfRange) for e in result.errors), \
                f"Boundary {boundary} should be accepted"


# ===========================================================================
# ENUMERATED
# ===========================================================================

class TestEnumeratedValidation:

    def _make_enum_template(self) -> TemplateNode:
        values = [
            OrderedValue(index=-1, label="positive", description="Positive sentiment", location=LOC),
            OrderedValue(index=-1, label="negative", description="Negative sentiment", location=LOC),
            OrderedValue(index=-1, label="neutral", description="Neutral sentiment", location=LOC),
        ]
        spec = make_field_spec("sentiment", FieldType.ENUMERATED, values=values)
        return make_template({"sentiment": spec})

    def test_valid_enumerated_value(self):
        template = self._make_enum_template()
        validator = SemanticValidator(template, None, {})
        item = make_item(extra_fields={"sentiment": "positive"}, field_names=["sentiment"])
        result = validator.validate_item(item)
        assert not any(isinstance(e, InvalidEnumeratedValue) for e in result.errors)

    def test_invalid_enumerated_value(self):
        template = self._make_enum_template()
        validator = SemanticValidator(template, None, {})
        item = make_item(extra_fields={"sentiment": "confused"}, field_names=["sentiment"])
        result = validator.validate_item(item)
        assert any(isinstance(e, InvalidEnumeratedValue) for e in result.errors)


# ===========================================================================
# BUNDLE
# ===========================================================================

class TestBundleValidation:

    def _make_bundle_template(self) -> TemplateNode:
        specs = {
            "memo": make_field_spec("memo", FieldType.MEMO),
            "chain": make_field_spec("chain", FieldType.CHAIN),
        }
        return make_template(
            specs,
            bundles={Scope.ITEM: [("memo", "chain")]},
        )

    def test_complete_bundle_no_error(self):
        template = self._make_bundle_template()
        validator = SemanticValidator(template, None, {})
        chain = make_chain(["A", "B"])
        item = make_item(notes=["A memo."], chains=[chain], field_names=["memo", "chain"])
        result = validator.validate_bundle(item, Scope.ITEM)
        assert not result.has_errors()

    def test_isolated_bundle_field_generates_error(self):
        template = self._make_bundle_template()
        validator = SemanticValidator(template, None, {})
        item = make_item(notes=["A memo."], field_names=["memo"])  # 'chain' ausente
        result = validator.validate_bundle(item, Scope.ITEM)
        assert any(isinstance(e, MissingBundleField) for e in result.errors)

    def test_bundle_count_mismatch_generates_error(self):
        template = self._make_bundle_template()
        validator = SemanticValidator(template, None, {})
        chain1 = make_chain(["A", "B"])
        chain2 = make_chain(["C", "D"])
        item = make_item(
            notes=["Only one memo."],    # 1 note
            chains=[chain1, chain2],    # 2 chains → mismatch
            field_names=["memo", "chain"],
        )
        result = validator.validate_bundle(item, Scope.ITEM)
        assert any(isinstance(e, BundleCountMismatch) for e in result.errors)


# ===========================================================================
# OPTIONAL BUNDLE (WI-4)
# ===========================================================================

class TestOptionalBundleValidation:

    def _make_optional_bundle_template(self) -> TemplateNode:
        specs = {
            "period": make_field_spec("period", FieldType.TEXT),
            "region": make_field_spec("region", FieldType.TEXT),
        }
        return TemplateNode(
            name="test",
            metadata={},
            field_specs=specs,
            required_fields={},
            optional_fields={},
            forbidden_fields={},
            bundled_fields={},
            optional_bundles={Scope.ITEM: [("period", "region")]},
            location=LOC,
        )

    def test_total_absence_is_valid(self):
        """Cenário A: nenhum campo do bundle presente → sem erros."""
        template = self._make_optional_bundle_template()
        validator = SemanticValidator(template, None, {})
        item = make_item(field_names=[])
        result = validator.validate_optional_bundle(item, Scope.ITEM)
        assert not result.has_errors()

    def test_partial_presence_generates_missing_bundle_field(self):
        """Cenário B: apenas um campo do bundle → MissingBundleField."""
        template = self._make_optional_bundle_template()
        validator = SemanticValidator(template, None, {})
        item = make_item(extra_fields={"period": "Século XXI"}, field_names=["period"])
        result = validator.validate_optional_bundle(item, Scope.ITEM)
        assert any(isinstance(e, MissingBundleField) for e in result.errors)

    def test_count_mismatch_generates_bundle_count_mismatch(self):
        """Cenário C: dois campos presentes em quantidades diferentes → BundleCountMismatch."""
        template = self._make_optional_bundle_template()
        validator = SemanticValidator(template, None, {})
        item = make_item(
            extra_fields={"period": ["Século XX", "Século XXI"], "region": "América do Sul"},
            field_names=["period", "region"],
        )
        result = validator.validate_optional_bundle(item, Scope.ITEM)
        assert any(isinstance(e, BundleCountMismatch) for e in result.errors)

    def test_complete_bundle_no_error(self):
        """Cenário D: ambos os campos presentes na mesma quantidade → sem erros."""
        template = self._make_optional_bundle_template()
        validator = SemanticValidator(template, None, {})
        item = make_item(
            extra_fields={"period": "Século XXI", "region": "Europa"},
            field_names=["period", "region"],
        )
        result = validator.validate_optional_bundle(item, Scope.ITEM)
        assert not result.has_errors()

    def test_required_bundle_still_requires_presence(self):
        """REQUIRED BUNDLE (validate_bundle) não é afetado pelo OPTIONAL BUNDLE: ausência gera erro."""
        specs = {
            "memo": make_field_spec("memo", FieldType.MEMO),
            "chain": make_field_spec("chain", FieldType.CHAIN),
        }
        template = make_template(specs, bundles={Scope.ITEM: [("memo", "chain")]})
        validator = SemanticValidator(template, None, {})
        item = make_item(field_names=[])
        result = validator.validate_bundle(item, Scope.ITEM)
        assert any(isinstance(e, MissingBundleField) for e in result.errors)
