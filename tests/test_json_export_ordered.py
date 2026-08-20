"""
test_json_export_ordered.py - Enriquecimento de labels ORDERED no export JSON

Proposito:
    Garantir que o JSON exportado acrescente `<campo>_label` para TODA entrada
    com campo ORDERED, produzindo um schema regular, e que nao invente labels
    para chaves numericas que nao sao ORDERED.

Contexto:
    O dado de ORDERED e sempre o indice (canonizado no Linker). O rotulo vive na
    declaracao do template e e reconstituido aqui para quem consome o JSON sem
    ter o template em maos.

    Antes da canonizacao, o enriquecimento so agia quando o valor era `int` — o
    que produzia schema irregular (no corpus face85: 26 entradas com label e 184
    sem). A selecao passou a ser feita pelos FieldSpecs ORDERED do template, e
    nao pelas chaves da entrada.

Gerado conforme: Especificacao Synesis v1.1
"""

from pathlib import Path

from synesis.ast.nodes import (
    FieldSpec,
    FieldType,
    OrderedValue,
    Scope,
    SourceLocation,
    TemplateNode,
)
from synesis.exporters.json_export import _add_ordered_field_labels

LOC = SourceLocation(file=Path("test.syn"), line=1, column=1)


def _spec(name: str, ftype: FieldType, values=None, fmt=None) -> FieldSpec:
    return FieldSpec(
        name=name,
        type=ftype,
        scope=Scope.ONTOLOGY,
        values=values,
        format=fmt,
        description="",
        location=LOC,
    )


def _aspect_spec() -> FieldSpec:
    return _spec(
        "aspect",
        FieldType.ORDERED,
        values=[
            OrderedValue(index=0, label="Indefinido", description="", location=LOC),
            OrderedValue(index=2, label="Espacial", description="", location=LOC),
            OrderedValue(index=11, label="Econômico", description="", location=LOC),
        ],
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


class TestOrderedLabelEnrichment:

    def test_label_added_for_index(self):
        out = _add_ordered_field_labels({"aspect": 11}, _template({"aspect": _aspect_spec()}))
        assert out["aspect_label"] == "Econômico"

    def test_index_zero_gets_label(self):
        # Indice 0 e falsy: nao pode ser tratado como ausencia de valor.
        out = _add_ordered_field_labels({"aspect": 0}, _template({"aspect": _aspect_spec()}))
        assert out["aspect_label"] == "Indefinido"

    def test_original_value_is_preserved(self):
        out = _add_ordered_field_labels({"aspect": 2}, _template({"aspect": _aspect_spec()}))
        assert out["aspect"] == 2
        assert out["aspect_label"] == "Espacial"

    def test_schema_is_regular_across_entries(self):
        """Toda entrada com o campo recebe label — nao apenas algumas."""
        template = _template({"aspect": _aspect_spec()})
        entries = [{"aspect": 0}, {"aspect": 2}, {"aspect": 11}]
        out = [_add_ordered_field_labels(e, template) for e in entries]
        assert all("aspect_label" in e for e in out)

    def test_out_of_range_index_gets_no_label(self):
        out = _add_ordered_field_labels({"aspect": 99}, _template({"aspect": _aspect_spec()}))
        assert "aspect_label" not in out

    def test_absent_field_is_skipped(self):
        out = _add_ordered_field_labels({"other": 1}, _template({"aspect": _aspect_spec()}))
        assert "aspect_label" not in out


class TestNoSpuriousLabels:
    """Chaves numericas que nao sao ORDERED nunca recebem label."""

    def test_exporter_injected_counters_get_no_label(self):
        # frequency/source_count sao injetados pelo exporter; nao estao no template.
        template = _template({"aspect": _aspect_spec()})
        out = _add_ordered_field_labels(
            {"aspect": 11, "frequency": 7, "source_count": 3}, template
        )
        assert "frequency_label" not in out
        assert "source_count_label" not in out

    def test_scale_field_gets_no_label(self):
        template = _template(
            {
                "aspect": _aspect_spec(),
                "theoretical_significance": _spec(
                    "theoretical_significance", FieldType.SCALE, fmt="[1..5]"
                ),
            }
        )
        out = _add_ordered_field_labels(
            {"aspect": 11, "theoretical_significance": 4}, template
        )
        assert "theoretical_significance_label" not in out

    def test_enumerated_field_gets_no_label(self):
        template = _template(
            {
                "zone": _spec(
                    "zone",
                    FieldType.ENUMERATED,
                    values=[OrderedValue(index=-1, label="Aim", description="", location=LOC)],
                )
            }
        )
        out = _add_ordered_field_labels({"zone": "Aim"}, template)
        assert "zone_label" not in out

    def test_bool_is_not_treated_as_index(self):
        # bool e subclasse de int em Python.
        out = _add_ordered_field_labels({"aspect": True}, _template({"aspect": _aspect_spec()}))
        assert "aspect_label" not in out

    def test_ordered_without_values_is_skipped(self):
        template = _template({"aspect": _spec("aspect", FieldType.ORDERED, values=None)})
        out = _add_ordered_field_labels({"aspect": 11}, template)
        assert "aspect_label" not in out
