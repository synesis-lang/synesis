"""
test_linker_ordered.py - Tipagem de campos ORDERED apos o link

Proposito:
    Garantir que o valor materializado de um campo ORDERED chega ao consumidor
    como `int`, nos tres escopos (SOURCE, ITEM, ONTOLOGY).

    Em ORDERED o indice E o dado. O linker faz apenas coercao de TIPO — indice
    escrito como texto ("11") vira int. Ele NAO resolve rotulo->indice: escrever
    o rotulo e erro de forma (E088), reportado pelo SemanticValidator. Normalizar
    em silencio manteria o arquivo no disco divergente do que o compilador
    entrega, e o arquivo nunca convergiria para a forma canonica.

    A validacao de E088 esta em test_validator.py (TestOrderedValidation).

Gerado conforme: Especificacao Synesis v1.1
"""

from pathlib import Path

from synesis.ast.nodes import (
    FieldSpec,
    FieldType,
    ItemNode,
    OntologyNode,
    OrderedValue,
    Scope,
    SourceLocation,
    SourceNode,
    TemplateNode,
)
from synesis.semantic.linker import Linker

LOC = SourceLocation(file=Path("test.syn"), line=1, column=1)


def _ordered_spec(name: str, scope: Scope) -> FieldSpec:
    return FieldSpec(
        name=name,
        type=FieldType.ORDERED,
        scope=scope,
        values=[
            OrderedValue(index=0, label="Indefinido", description="", location=LOC),
            OrderedValue(index=2, label="Espacial", description="", location=LOC),
            OrderedValue(index=11, label="Econômico", description="", location=LOC),
        ],
        description="",
        location=LOC,
    )


def _template(specs: dict) -> TemplateNode:
    return TemplateNode(
        name="t",
        metadata={},
        field_specs=specs,
        required_fields={},
        optional_fields={},
        forbidden_fields={},
        bundled_fields={},
        location=LOC,
    )


def _link(template, sources=None, items=None, ontologies=None):
    Linker(
        sources or [],
        items or [],
        ontologies or [],
        project=None,
        template=template,
    ).link()


def _source(fields: dict) -> SourceNode:
    return SourceNode(bibref="@r2024", fields=fields, items=[], location=LOC)


def _item(extra_fields: dict) -> ItemNode:
    return ItemNode(
        bibref="@r2024",
        quote="q",
        extra_fields=extra_fields,
        field_names=list(extra_fields.keys()),
        location=LOC,
    )


def _ontology(fields: dict) -> OntologyNode:
    return OntologyNode(
        concept="c",
        description="d",
        fields=fields,
        parent_chains=[],
        field_names=list(fields.keys()),
        location=LOC,
    )


class TestOrderedIsAlwaysInt:
    """O consumidor recebe sempre int, nos tres escopos."""

    def test_index_preserved_in_ontology(self):
        ont = _ontology({"aspect": 11})
        _link(_template({"aspect": _ordered_spec("aspect", Scope.ONTOLOGY)}), ontologies=[ont])
        assert ont.fields["aspect"] == 11

    def test_numeric_string_coerced_in_ontology(self):
        ont = _ontology({"aspect": "11"})
        _link(_template({"aspect": _ordered_spec("aspect", Scope.ONTOLOGY)}), ontologies=[ont])
        assert ont.fields["aspect"] == 11

    def test_numeric_string_coerced_in_item(self):
        # ItemNode guarda campos em extra_fields, nao em fields.
        item = _item({"aspect": "2"})
        _link(_template({"aspect": _ordered_spec("aspect", Scope.ITEM)}), items=[item])
        assert item.extra_fields["aspect"] == 2

    def test_numeric_string_coerced_in_source(self):
        source = _source({"aspect": " 11 "})
        _link(_template({"aspect": _ordered_spec("aspect", Scope.SOURCE)}), sources=[source])
        assert source.fields["aspect"] == 11

    def test_index_zero_is_preserved(self):
        # Indice 0 e falsy: nao pode ser confundido com ausencia de valor.
        ont = _ontology({"aspect": 0})
        _link(_template({"aspect": _ordered_spec("aspect", Scope.ONTOLOGY)}), ontologies=[ont])
        assert ont.fields["aspect"] == 0

    def test_zero_as_string_coerced(self):
        ont = _ontology({"aspect": "0"})
        _link(_template({"aspect": _ordered_spec("aspect", Scope.ONTOLOGY)}), ontologies=[ont])
        assert ont.fields["aspect"] == 0


class TestLinkerDoesNotResolveLabels:
    """O linker nao conserta forma errada — quem reporta e o validador (E088)."""

    def test_label_is_left_untouched(self):
        ont = _ontology({"aspect": "Econômico"})
        _link(_template({"aspect": _ordered_spec("aspect", Scope.ONTOLOGY)}), ontologies=[ont])
        assert ont.fields["aspect"] == "Econômico"

    def test_unknown_label_is_left_untouched(self):
        ont = _ontology({"aspect": "Gastronomico"})
        _link(_template({"aspect": _ordered_spec("aspect", Scope.ONTOLOGY)}), ontologies=[ont])
        assert ont.fields["aspect"] == "Gastronomico"

    def test_out_of_range_index_is_preserved(self):
        ont = _ontology({"aspect": 99})
        _link(_template({"aspect": _ordered_spec("aspect", Scope.ONTOLOGY)}), ontologies=[ont])
        assert ont.fields["aspect"] == 99


class TestOrderedDoesNotTouchOtherTypes:
    """A coercao e restrita a campos ORDERED."""

    def test_enumerated_label_is_preserved(self):
        spec = FieldSpec(
            name="zone",
            type=FieldType.ENUMERATED,
            scope=Scope.ONTOLOGY,
            values=[OrderedValue(index=-1, label="Aim", description="", location=LOC)],
            description="",
            location=LOC,
        )
        ont = _ontology({"zone": "Aim"})
        _link(_template({"zone": spec}), ontologies=[ont])
        assert ont.fields["zone"] == "Aim"

    def test_numeric_text_field_is_preserved_as_string(self):
        """TEXT com conteudo numerico nao e ORDERED: continua str."""
        spec = FieldSpec(
            name="note",
            type=FieldType.TEXT,
            scope=Scope.ONTOLOGY,
            description="",
            location=LOC,
        )
        ont = _ontology({"note": "11"})
        _link(_template({"note": spec}), ontologies=[ont])
        assert ont.fields["note"] == "11"

    def test_missing_template_is_tolerated(self):
        ont = _ontology({"aspect": "11"})
        Linker([], [], [ont], project=None, template=None).link()
        assert ont.fields["aspect"] == "11"
