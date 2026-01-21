"""
csv_export.py - Exportacao CSV do projeto Synesis

Proposito:
    Gerar tabelas CSV com rastreabilidade completa para analise.
    Produz arquivos separados por tipo de bloco e indices auxiliares.

Componentes principais:
    - export_csv: funcao principal de exportacao

Dependencias criticas:
    - csv: escrita de arquivos CSV
    - synesis.semantic.linker: LinkedProject consolidado
    - synesis.ast.nodes: TemplateNode para introspeccao

Exemplo de uso:
    from synesis.exporters.csv_export import export_csv
    export_csv(linked, template, Path("saida_csv"))

Notas de implementacao:
    - Cabecalhos CSV sao dinamicos, baseados no template.
    - Apenas gera arquivos se houver dados e campos relevantes.
    - Todos os CSVs principais incluem source_file, source_line, source_column.

Gerado conforme: Especificacao Synesis v1.1
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List, Optional

from synesis.ast.nodes import (
    FieldType,
    ItemNode,
    OntologyNode,
    Scope,
    SourceNode,
    TemplateNode,
)
from synesis.semantic.linker import LinkedProject


CsvTable = tuple[List[str], List[Dict[str, Any]]]


def build_csv_tables(
    linked: LinkedProject,
    template: Optional[TemplateNode],
) -> Dict[str, CsvTable]:
    """
    Constroi tabelas CSV em memoria (sem I/O).

    Ideal para uso em Jupyter Notebooks, Pandas e integracao com APIs.
    Cada tabela e uma tupla (headers, rows) onde rows e lista de dicts.

    Args:
        linked: Projeto vinculado com indices construidos
        template: Template opcional (None = modo legado)

    Returns:
        Dict mapeando nome da tabela -> (headers, rows):
        - "sources": Fontes bibliograficas com campos
        - "items": Items anotados (expandidos por bundles)
        - "ontologies": Conceitos de ontologia
        - "chains": Triplas relacionais (from, relation, to)
        - "codes": Frequencia de codigos (apenas modo legado)

    Example:
        >>> tables = build_csv_tables(linked, template)
        >>> headers, rows = tables["items"]
        >>> import pandas as pd
        >>> df = pd.DataFrame(rows, columns=headers)
    """
    tables: Dict[str, CsvTable] = {}

    # Sources
    if template and _has_fields_for_scope(template, Scope.SOURCE):
        tables["sources"] = _build_sources_table(linked, template)
    elif not template:
        tables["sources"] = _build_sources_table(linked, None)

    # Items
    if template and _has_fields_for_scope(template, Scope.ITEM):
        tables["items"] = _build_items_table(linked, template)
    elif not template:
        tables["items"] = _build_items_table(linked, None)

    # Ontologies
    if template and _has_fields_for_scope(template, Scope.ONTOLOGY):
        tables["ontologies"] = _build_ontologies_table(linked, template)
    elif not template:
        tables["ontologies"] = _build_ontologies_table(linked, None)

    # Chains
    if _has_chain_data(linked):
        has_relations = _detect_chain_relations(linked)
        tables["chains"] = _build_chains_table(linked, has_relations)

    # Codes (modo legado)
    if not template and linked.code_usage:
        tables["codes"] = _build_codes_table(linked)

    return tables


def export_csv(linked: LinkedProject, template: Optional[TemplateNode], output_dir: Path) -> None:
    """
    Exporta tabelas CSV do projeto Synesis baseado no template.

    Usa build_csv_tables() para construir os dados e escreve em disco.
    Apenas gera arquivos se houver campos relevantes no template e dados no projeto.
    """
    if not isinstance(output_dir, Path):
        output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    tables = build_csv_tables(linked, template)

    for table_name, (headers, rows) in tables.items():
        if rows:
            path = output_dir / f"{table_name}.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=headers)
                writer.writeheader()
                for row in rows:
                    writer.writerow(row)


def _has_fields_for_scope(template: TemplateNode, scope: Scope) -> bool:
    """Verifica se template define campos para escopo especificado."""
    for spec in template.field_specs.values():
        if spec.scope == scope:
            return True
    return False


def _has_chain_data(linked: LinkedProject) -> bool:
    """Verifica se projeto tem chains."""
    for source in linked.sources.values():
        for item in source.items:
            if item.chains:
                return True
    return False


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


def _collect_item_bundle_fields(template: TemplateNode) -> set[str]:
    bundles = template.bundled_fields.get(Scope.ITEM, [])
    return {name for bundle in bundles for name in bundle}


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _expand_item_rows(
    item: ItemNode,
    field_names: List[str],
    bundle_fields: set[str],
) -> List[Dict[str, Any]]:
    if not bundle_fields:
        return [{name: _get_item_field_value(item, name) for name in field_names}]

    values_by_field: Dict[str, List[Any]] = {}
    max_count = 0
    for name in bundle_fields:
        values = _as_list(_get_item_field_value(item, name))
        values_by_field[name] = values
        if len(values) > max_count:
            max_count = len(values)

    row_count = max(max_count, 1)
    rows: List[Dict[str, Any]] = []
    for idx in range(row_count):
        row: Dict[str, Any] = {}
        for name in field_names:
            if name in bundle_fields:
                values = values_by_field.get(name, [])
                row[name] = values[idx] if idx < len(values) else ""
            else:
                row[name] = _get_item_field_value(item, name)
        rows.append(row)
    return rows


def _build_sources_table(linked: LinkedProject, template: Optional[TemplateNode]) -> CsvTable:
    """Constroi tabela de sources em memoria."""
    sources = list(linked.sources.values())
    if not sources:
        return ([], [])

    if template:
        field_names = _get_field_names_for_scope(template, Scope.SOURCE)
    else:
        field_names = _collect_source_fields(sources)

    headers = ["bibref"] + field_names + [
        "source_file",
        "source_line",
        "source_column",
    ]

    rows: List[Dict[str, Any]] = []
    for source in sources:
        location = source.location
        row = {
            "bibref": source.bibref,
            "source_file": str(location.file) if location else "",
            "source_line": location.line if location else "",
            "source_column": location.column if location else "",
        }
        for name in field_names:
            row[name] = _stringify_value(source.fields.get(name, ""))
        rows.append(row)

    return (headers, rows)


def _write_sources_csv(linked: LinkedProject, template: Optional[TemplateNode], path: Path) -> None:
    """Escreve tabela de sources em arquivo CSV."""
    headers, rows = _build_sources_table(linked, template)
    if not rows:
        return

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _build_items_table(linked: LinkedProject, template: Optional[TemplateNode]) -> CsvTable:
    """Constroi tabela de items em memoria."""
    if template:
        field_names = _get_field_names_for_scope(template, Scope.ITEM)
        headers = ["bibref"] + field_names + [
            "source_file",
            "source_line",
            "source_column",
        ]
    else:
        headers = [
            "bibref",
            "quote",
            "codes",
            "note_count",
            "chain_count",
            "source_file",
            "source_line",
            "source_column",
        ]
        field_names = []

    bundle_fields = _collect_item_bundle_fields(template) if template else set()

    rows: List[Dict[str, Any]] = []
    for source in linked.sources.values():
        for item in source.items:
            location = item.location
            base = {
                "bibref": item.bibref,
                "source_file": str(location.file) if location else "",
                "source_line": location.line if location else "",
                "source_column": location.column if location else "",
            }

            if template:
                for row_fields in _expand_item_rows(item, field_names, bundle_fields):
                    row = dict(base)
                    for name in field_names:
                        row[name] = _stringify_value(row_fields.get(name, ""))
                    rows.append(row)
            else:
                row = dict(base)
                row["quote"] = item.quote
                row["codes"] = ";".join(item.codes)
                row["note_count"] = len(item.notes)
                row["chain_count"] = len(item.chains)
                rows.append(row)

    return (headers, rows)


def _write_items_csv(linked: LinkedProject, template: Optional[TemplateNode], path: Path) -> None:
    """Escreve tabela de items em arquivo CSV."""
    headers, rows = _build_items_table(linked, template)
    if not rows:
        return

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _build_ontologies_table(linked: LinkedProject, template: Optional[TemplateNode]) -> CsvTable:
    """Constroi tabela de ontologies em memoria."""
    if not linked.ontology_index:
        return ([], [])

    if template:
        index_fields = _get_field_names_for_scope_and_types(
            template,
            Scope.ITEM,
            {FieldType.CODE, FieldType.CHAIN},
        )
        ontology_fields = _get_field_names_for_scope(template, Scope.ONTOLOGY)
        headers = index_fields + ontology_fields + [
            "source_file",
            "source_line",
            "source_column",
        ]
        field_names_legacy: List[str] = []
    else:
        headers = [
            "concept",
            "description",
            "topic",
            "aspect",
            "dimension",
            "confidence",
            "source_file",
            "source_line",
            "source_column",
        ]
        index_fields = []
        ontology_fields = []
        field_names_legacy = ["topic", "aspect", "dimension", "confidence"]

    rows: List[Dict[str, Any]] = []
    for ontology in linked.ontology_index.values():
        location = ontology.location
        row: Dict[str, Any] = {
            "source_file": str(location.file) if location else "",
            "source_line": location.line if location else "",
            "source_column": location.column if location else "",
        }

        if template:
            for name in index_fields:
                row[name] = _stringify_value(ontology.concept)
            for name in ontology_fields:
                row[name] = _stringify_value(_get_ontology_field_value(ontology, name))
        else:
            row["concept"] = ontology.concept
            row["description"] = ontology.description
            for name in field_names_legacy:
                row[name] = _stringify_value(ontology.fields.get(name, ""))

        rows.append(row)

    return (headers, rows)


def _write_ontologies_csv(linked: LinkedProject, template: Optional[TemplateNode], path: Path) -> None:
    """Escreve tabela de ontologies em arquivo CSV."""
    headers, rows = _build_ontologies_table(linked, template)
    if not rows:
        return

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _build_chains_table(linked: LinkedProject, has_relations: bool = False) -> CsvTable:
    """Constroi tabela de chains em memoria."""
    headers = [
        "bibref",
        "from_code",
        "relation",
        "to_code",
        "source_file",
        "source_line",
        "source_column",
    ]

    rows: List[Dict[str, Any]] = []
    for source in linked.sources.values():
        for item in source.items:
            for chain in item.chains:
                for from_code, relation, to_code in chain.to_triples(has_relations=has_relations):
                    location = chain.location
                    row = {
                        "bibref": item.bibref,
                        "from_code": from_code,
                        "relation": relation,
                        "to_code": to_code,
                        "source_file": str(location.file) if location else "",
                        "source_line": location.line if location else "",
                        "source_column": location.column if location else "",
                    }
                    rows.append(row)

    return (headers, rows)


def _write_chains_csv(linked: LinkedProject, path: Path, has_relations: bool = False) -> None:
    """Escreve tabela de chains em arquivo CSV."""
    headers, rows = _build_chains_table(linked, has_relations)
    if not rows:
        return

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _build_codes_table(linked: LinkedProject) -> CsvTable:
    """Constroi tabela de codes em memoria (modo legado)."""
    headers = ["concept", "usage_count", "sources"]

    rows: List[Dict[str, Any]] = []
    for concept, items in linked.code_usage.items():
        sources = sorted({item.bibref for item in items})
        row = {
            "concept": concept,
            "usage_count": len(items),
            "sources": ";".join(sources),
        }
        rows.append(row)

    return (headers, rows)


def _write_codes_csv(linked: LinkedProject, path: Path) -> None:
    """Escreve tabela de codes em arquivo CSV."""
    headers, rows = _build_codes_table(linked)
    if not rows:
        return

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_topics_csv(linked: LinkedProject, path: Path) -> None:
    headers = ["topic", "concept_count", "concepts"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for topic, concepts in linked.topic_index.items():
            row = {
                "topic": topic,
                "concept_count": len(concepts),
                "concepts": ";".join(sorted(concepts)),
            }
            writer.writerow(row)


def _collect_source_fields(sources: List[SourceNode]) -> List[str]:
    """Coleta dinamicamente campos de sources (modo legado)."""
    fields = set()
    for source in sources:
        fields.update(source.fields.keys())
    fields.discard("description")
    return sorted(fields)


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


def _stringify_value(value) -> str:
    """Converte valor para string CSV."""
    if isinstance(value, list):
        return ";".join(str(v) for v in value)
    if value is None:
        return ""
    return str(value)


def _detect_chain_relations(linked: LinkedProject) -> bool:
    """
    Detecta se chains do projeto usam relacoes qualificadas.

    Heuristica: se alguma chain tem numero impar de elementos >= 3,
    provavelmente e qualificada (code -> REL -> code -> REL -> code).
    """
    for source in linked.sources.values():
        for item in source.items:
            for chain in item.chains:
                num_elements = len(chain.nodes)
                # Chain qualificada tem numero impar de elementos >= 3
                if num_elements >= 3 and num_elements % 2 == 1:
                    return True
    return False
