"""
_helpers.py - Funcoes compartilhadas pelos exportadores Synesis.

Extraidas de json_export.py, csv_export.py e xls_export.py para evitar duplicacao.
As quatro funcoes abaixo eram identicas nos tres exportadores.
"""

from __future__ import annotations

from typing import Any, List

from synesis.ast.nodes import FieldType, ItemNode, OntologyNode, Scope, TemplateNode


def _get_field_names_for_scope(template: TemplateNode, scope: Scope) -> List[str]:
    """Retorna nomes de campos do template preservando a ordem de definicao."""
    return [
        name
        for name, spec in template.field_specs.items()
        if spec.scope == scope
    ]


def _get_field_names_for_scope_and_types(
    template: TemplateNode,
    scope: Scope,
    field_types: set[FieldType],
) -> List[str]:
    """Retorna nomes de campos do template por escopo e tipos, mantendo ordem."""
    return [
        name
        for name, spec in template.field_specs.items()
        if spec.scope == scope and spec.type in field_types
    ]


def _get_item_field_value(item: ItemNode, name: str) -> Any:
    value = item.extra_fields.get(name)
    if value is not None:
        return value

    lname = name.lower()
    if lname in {"quote", "quotation"}:
        return item.quote
    if lname in {"code", "codes"}:
        return item.codes
    if lname in {"note", "notes", "memo", "memos"}:
        return item.notes
    if lname in {"chain", "chains"}:
        return item.chains
    return ""


def _get_ontology_field_value(ontology: OntologyNode, name: str) -> Any:
    value = ontology.fields.get(name)
    if value is not None:
        return value

    lname = name.lower()
    if lname == "description":
        return ontology.description
    if lname == "concept":
        return ontology.concept
    return ""
