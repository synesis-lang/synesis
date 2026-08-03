"""
_helpers.py - Funcoes compartilhadas pelos exportadores Synesis.

Extraidas de json_export.py, csv_export.py e xls_export.py para evitar duplicacao.
As quatro funcoes abaixo eram identicas nos tres exportadores.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from synesis.ast.nodes import FieldType, ItemNode, OntologyNode, Scope, SourceNode, TemplateNode


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


def _chain_to_text(chain: Any) -> str:
    """Forma legivel de um ChainNode: "a -> REL -> b" (ou "a -> b" sem relacao).

    Sem isto, um ChainNode cai no `str()` padrao do dataclass e a planilha
    recebe o `repr()` inteiro — nodes, relations, SourceLocation e WindowsPath —
    ilegivel para quem abre o arquivo. O JSON ja serializa como triplas; aqui a
    cadeia vira uma linha de texto porque a celula e escalar.
    """
    nodes = getattr(chain, "nodes", None)
    if not nodes:
        return ""
    return " -> ".join(str(n) for n in nodes)


def _get_source_field_value(
    source: SourceNode,
    name: str,
    template: Optional[TemplateNode] = None,
    bibliography: Optional[Dict[str, Any]] = None,
    dataset: Optional[Dict[str, Any]] = None,
) -> Any:
    """Valor de um campo SCOPE SOURCE respeitando a origem-de-valor do template.

    Um campo pode ter valor fora do bloco SOURCE: `ON BIBLIOGRAPHY` le da
    entrada .bib do proprio bibref, `ON DATASET` le do registro TOML via
    resolve_path(spec.dataset_path). Ler `source.fields` direto — como os
    exportadores tabulares faziam — devolve vazio para esses campos, embora o
    compilador, o validador e o link step os resolvam corretamente.

    Espelha `_resolve_field_values` de semantic/link_step.py. Em ambos, o valor
    ja presente no bloco SOURCE prevalece (a compilacao ja checou conflito).
    Sem template/fonte externa, degrada para o comportamento anterior.
    """
    in_source = source.fields.get(name)
    if in_source is not None:
        return in_source

    spec = template.field_specs.get(name) if template else None
    origin = getattr(spec, "value_origin", "document") if spec is not None else "document"

    if origin == "bibliography" and bibliography:
        from synesis.parser.bib_loader import find_bibref

        entry = find_bibref(bibliography, source.bibref.lstrip("@"))
        if entry:
            value = entry.get(name)
            if value is not None:
                return value
    elif origin == "dataset" and dataset:
        from synesis.parser.dataset_loader import find_record, resolve_path

        record = find_record(dataset, source.bibref.lstrip("@"))
        path = getattr(spec, "dataset_path", None)
        if record is not None and path:
            value = resolve_path(record, path)
            if value is not None:
                return value

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
