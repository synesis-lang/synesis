"""
xls_export.py - Exportacao XLS do projeto Synesis

Proposito:
    Gerar arquivo XLS unico com multiplas abas, cada aba correspondendo
    a um arquivo CSV que seria gerado pela exportacao CSV.
    Produz rastreabilidade completa para analise em formato Excel.

Componentes principais:
    - export_xls: funcao principal de exportacao

Dependencias criticas:
    - openpyxl: escrita de arquivos Excel (.xlsx)
    - synesis.semantic.linker: LinkedProject consolidado
    - synesis.ast.nodes: TemplateNode para introspeccao

Exemplo de uso:
    from synesis.exporters.xls_export import export_xls
    export_xls(linked, template, Path("saida.xlsx"))

Notas de implementacao:
    - Cada aba corresponde a um CSV (sources, items, ontologies, chains, codes).
    - Apenas gera abas se houver dados e campos relevantes.
    - Todas as abas principais incluem source_file, source_line, source_column.
    - Reutiliza logica do csv_export para consistencia.

Gerado conforme: Especificacao Synesis v1.1
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter
except ImportError:
    raise ImportError(
        "openpyxl nao encontrado. Instale com: pip install openpyxl"
    )

from synesis.ast.nodes import (
    FieldType,
    ItemNode,
    OntologyNode,
    Scope,
    SourceNode,
    TemplateNode,
)
from synesis.semantic.linker import LinkedProject


def build_xls_workbook(
    linked: LinkedProject,
    template: Optional[TemplateNode],
) -> "Workbook":
    """
    Constroi Workbook Excel em memoria (sem salvar em disco).

    Ideal para manipulacao programatica, streaming ou integracao com APIs.
    O Workbook retornado pode ser salvo posteriormente com wb.save(path).

    Args:
        linked: Projeto vinculado com indices construidos
        template: Template opcional (None = modo legado)

    Returns:
        Workbook (openpyxl) com abas:
        - sources: Fontes bibliograficas
        - items: Items anotados
        - ontologies: Conceitos de ontologia
        - chains: Triplas relacionais
        - codes: Frequencia de codigos (modo legado)

    Example:
        >>> wb = build_xls_workbook(linked, template)
        >>> wb.save("output.xlsx")  # Salva quando quiser
        >>> # Ou manipula programaticamente
        >>> ws = wb["items"]
        >>> for row in ws.iter_rows(min_row=2):
        ...     print(row[0].value)  # bibref
    """
    wb = Workbook()
    # Remove a aba padrao criada automaticamente
    if 'Sheet' in wb.sheetnames:
        wb.remove(wb['Sheet'])

    # Exporta sources se houver campos SOURCE no template
    if template and _has_fields_for_scope(template, Scope.SOURCE):
        _write_sources_sheet(wb, linked, template)
    elif not template:
        _write_sources_sheet(wb, linked, None)

    # Exporta items se houver campos ITEM no template
    if template and _has_fields_for_scope(template, Scope.ITEM):
        _write_items_sheet(wb, linked, template)
    elif not template:
        _write_items_sheet(wb, linked, None)

    # Exporta ontologies se houver campos ONTOLOGY no template
    if template and _has_fields_for_scope(template, Scope.ONTOLOGY):
        _write_ontologies_sheet(wb, linked, template)
    elif not template:
        _write_ontologies_sheet(wb, linked, None)

    # Exporta chains apenas se houver dados de chains no projeto
    has_relations = _detect_chain_relations(linked)
    if _has_chain_data(linked):
        _write_chains_sheet(wb, linked, has_relations)

    # Exporta codes apenas em modo legado
    if not template and linked.code_usage:
        _write_codes_sheet(wb, linked)

    # Se nenhuma aba foi criada, cria uma aba vazia para evitar erro
    if len(wb.sheetnames) == 0:
        wb.create_sheet("Empty")

    return wb


def export_xls(linked: LinkedProject, template: Optional[TemplateNode], output_path: Path) -> None:
    """
    Exporta projeto Synesis para arquivo XLS unico com multiplas abas.

    Usa build_xls_workbook() para construir os dados e salva em disco.
    Cada aba corresponde a um arquivo CSV que seria gerado pela exportacao CSV.
    """
    if not isinstance(output_path, Path):
        output_path = Path(output_path)

    # Garante extensao .xlsx
    if output_path.suffix.lower() not in ['.xlsx', '.xls']:
        output_path = output_path.with_suffix('.xlsx')

    wb = build_xls_workbook(linked, template)
    wb.save(output_path)


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


def _write_sources_sheet(wb: Workbook, linked: LinkedProject, template: Optional[TemplateNode]) -> None:
    sources = list(linked.sources.values())
    if not sources:
        return

    ws = wb.create_sheet("sources")

    if template:
        # Usa campos do template
        field_names = _get_field_names_for_scope(template, Scope.SOURCE)
    else:
        # Modo legado: coleta campos dinamicamente
        field_names = _collect_source_fields(sources)

    headers = ["bibref"] + field_names + [
        "source_file",
        "source_line",
        "source_column",
    ]

    # Escreve cabecalho
    ws.append(headers)

    # Escreve dados
    for source in sources:
        location = source.location
        row = [
            source.bibref,
        ]
        for name in field_names:
            row.append(_stringify_value(source.fields.get(name, "")))
        row.extend([
            str(location.file) if location else "",
            location.line if location else "",
            location.column if location else "",
        ])
        ws.append(row)

    # Auto-ajusta largura das colunas
    _auto_size_columns(ws)


def _write_items_sheet(wb: Workbook, linked: LinkedProject, template: Optional[TemplateNode]) -> None:
    ws = wb.create_sheet("items")

    if template:
        # Usa campos do template
        field_names = _get_field_names_for_scope(template, Scope.ITEM)
        headers = ["bibref"] + field_names + [
            "source_file",
            "source_line",
            "source_column",
        ]
    else:
        # Modo legado: hardcoded
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

    # Escreve cabecalho
    ws.append(headers)

    bundle_fields = _collect_item_bundle_fields(template) if template else set()

    # Escreve dados
    for source in linked.sources.values():
        for item in source.items:
            location = item.location
            if template:
                # Preenche campos do template (expande bundles quando existirem)
                for row_fields in _expand_item_rows(item, field_names, bundle_fields):
                    row = [item.bibref]
                    for name in field_names:
                        row.append(_stringify_value(row_fields.get(name, "")))
                    row.extend([
                        str(location.file) if location else "",
                        location.line if location else "",
                        location.column if location else "",
                    ])
                    ws.append(row)
            else:
                # Modo legado: campos fixos
                row = [item.bibref]
                row.extend([
                    item.quote,
                    ";".join(item.codes),
                    len(item.notes),
                    len(item.chains),
                ])
                row.extend([
                    str(location.file) if location else "",
                    location.line if location else "",
                    location.column if location else "",
                ])
                ws.append(row)

    # Auto-ajusta largura das colunas
    _auto_size_columns(ws)


def _write_ontologies_sheet(wb: Workbook, linked: LinkedProject, template: Optional[TemplateNode]) -> None:
    if not linked.ontology_index:
        return

    ws = wb.create_sheet("ontologies")

    if template:
        # Usa campos do template
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
    else:
        # Modo legado: hardcoded
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
        field_names = ["topic", "aspect", "dimension", "confidence"]

    # Escreve cabecalho
    ws.append(headers)

    # Escreve dados
    for ontology in linked.ontology_index.values():
        location = ontology.location
        row = []

        if template:
            for name in index_fields:
                row.append(_stringify_value(ontology.concept))
            for name in ontology_fields:
                row.append(_stringify_value(_get_ontology_field_value(ontology, name)))
        else:
            row.extend([
                ontology.concept,
                ontology.description,
            ])
            for name in field_names:
                row.append(_stringify_value(ontology.fields.get(name, "")))

        row.extend([
            str(location.file) if location else "",
            location.line if location else "",
            location.column if location else "",
        ])
        ws.append(row)

    # Auto-ajusta largura das colunas
    _auto_size_columns(ws)


def _write_chains_sheet(wb: Workbook, linked: LinkedProject, has_relations: bool = False) -> None:
    ws = wb.create_sheet("chains")

    headers = [
        "bibref",
        "from_code",
        "relation",
        "to_code",
        "source_file",
        "source_line",
        "source_column",
    ]

    # Escreve cabecalho
    ws.append(headers)

    # Escreve dados
    for source in linked.sources.values():
        for item in source.items:
            for chain in item.chains:
                for from_code, relation, to_code in chain.to_triples(has_relations=has_relations):
                    location = chain.location
                    row = [
                        item.bibref,
                        from_code,
                        relation,
                        to_code,
                        str(location.file),
                        location.line,
                        location.column,
                    ]
                    ws.append(row)

    # Auto-ajusta largura das colunas
    _auto_size_columns(ws)


def _write_codes_sheet(wb: Workbook, linked: LinkedProject) -> None:
    ws = wb.create_sheet("codes")

    headers = ["concept", "usage_count", "sources"]

    # Escreve cabecalho
    ws.append(headers)

    # Escreve dados
    for concept, items in linked.code_usage.items():
        sources = sorted({item.bibref for item in items})
        row = [
            concept,
            len(items),
            ";".join(sources),
        ]
        ws.append(row)

    # Auto-ajusta largura das colunas
    _auto_size_columns(ws)


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
    """Converte valor para string."""
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


def _auto_size_columns(ws) -> None:
    """Auto-ajusta largura das colunas baseado no conteudo."""
    for column in ws.columns:
        max_length = 0
        column_letter = get_column_letter(column[0].column)

        for cell in column:
            try:
                if cell.value:
                    max_length = max(max_length, len(str(cell.value)))
            except:
                pass

        adjusted_width = min(max_length + 2, 50)  # Limita a 50 caracteres
        ws.column_dimensions[column_letter].width = adjusted_width
