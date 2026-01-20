"""
json_export.py - Exportacao JSON analitico do projeto Synesis v2.0

Proposito:
    Gerar JSON analitico universal para Neo4j, analise bibliometrica,
    reconstrucao de workspace e dashboards. Usa template como fonte de
    verdade e enriquece com indices pre-computados.

Componentes principais:
    - export_json: funcao principal de escrita em JSON v2.0
    - Builders de secoes: metadata, project, template, bibliography, indices, ontology, corpus
    - Enriquecimentos: frequencias, source_count, labels de campos ORDERED, triplas com proveniencia

Dependencias criticas:
    - json: serializacao
    - datetime: timestamp de exportacao
    - synesis.semantic.linker: LinkedProject consolidado
    - synesis.ast.nodes: TemplateNode, ProjectNode, OntologyNode
    - synesis.parser.bib_loader: BibEntry

Exemplo de uso:
    from synesis.exporters.json_export import export_json
    export_json(linked, Path("saida_v2.json"), template, bibliography)

Notas de implementacao (v2.0):
    - Estrutura: version, export_metadata, project, template, bibliography, indices, ontology, corpus
    - Breaking change: Chains agora sao objetos {nodes, relations, location} (nao arrays)
    - Indices pre-computados: hierarchy, triples (com proveniencia), topics, code_frequency
    - Ontologia enriquecida: frequency, source_count, aspect_label, dimension_label
    - Rastreabilidade expandida: triplas incluem source_item e location
    - Sem template, usa modo legado com campos brutos (mantido para compatibilidade)

Gerado conforme: Especificacao Synesis v2.0
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from synesis.ast.nodes import (
    ChainNode,
    FieldSpec,
    FieldType,
    ItemNode,
    OntologyNode,
    Scope,
    SourceNode,
    TemplateNode,
)
from synesis.parser.bib_loader import BibEntry
from synesis.semantic.linker import LinkedProject

_ITEM_INDEX_WIDTH = 4


def _build_export_metadata(linked: LinkedProject) -> Dict[str, Any]:
    """
    Constrói metadados de exportação para versionamento e estatísticas.

    Args:
        linked: Projeto vinculado

    Returns:
        Dict com timestamp, versão, modo e contadores
    """
    from datetime import datetime, timezone

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "compiler_version": "1.1",
        "export_mode": "universal",
        "chain_count": len(linked.all_triples),
        "item_count": sum(len(source.items) for source in linked.sources.values()),
        "source_count": len(linked.sources),
        "concept_count": len(linked.ontology_index),
    }


def _build_project_section(linked: LinkedProject) -> Dict[str, Any]:
    """
    Constrói seção de projeto usando ProjectNode.to_dict().

    Args:
        linked: Projeto vinculado

    Returns:
        Dict com name, template_path, includes[], metadata, description
    """
    return linked.project.to_dict()


def _build_template_section(template: Optional[TemplateNode]) -> Optional[Dict[str, Any]]:
    """
    Constrói seção de template usando TemplateNode.to_dict().

    Args:
        template: Template opcional (None = modo legado)

    Returns:
        Dict com field_specs completos (VALUES, RELATIONS, arity) ou None
    """
    if template is None:
        return None
    return template.to_dict()


def _build_bibliography_section(
    bibliography: Optional[Dict[str, BibEntry]]
) -> Dict[str, Dict[str, Any]]:
    """
    Constrói seção de bibliografia separada de source_metadata.

    Args:
        bibliography: Entradas BibTeX opcionais

    Returns:
        Dict mapeando bibref normalizado -> entrada BibTeX completa
    """
    if not bibliography:
        return {}

    result: Dict[str, Dict[str, Any]] = {}
    for key, entry in bibliography.items():
        cleaned = {k: v for k, v in entry.items() if k != "_original_key"}
        result[_normalize_bibref(key)] = cleaned

    return result


def _build_code_frequency_index(linked: LinkedProject) -> Dict[str, int]:
    """
    Calcula frequência de uso de cada código.

    Args:
        linked: Projeto vinculado

    Returns:
        Dict mapeando código normalizado -> contagem de itens
    """
    return {
        code: len(items)
        for code, items in linked.code_usage.items()
    }


def _has_chain_relations(template: Optional[TemplateNode]) -> bool:
    """
    Verifica se template define RELATIONS para campo chain.

    Se True, chain é qualificada (códigos alternados com relações).
    Se False, chain é simples (apenas códigos).

    Args:
        template: Template opcional

    Returns:
        True se template define relations para chain, False caso contrário
    """
    if not template:
        return False

    chain_spec = template.field_specs.get("chain")
    if not chain_spec:
        return False

    return bool(chain_spec.relations)


def _build_triples_index(
    linked: LinkedProject,
    template: Optional[TemplateNode],
) -> List[Dict[str, Any]]:
    """
    Enriquece triplas com proveniência (source_item, location).

    Problema atual:
        LinkedProject.all_triples é List[Tuple[str, str, str]] sem proveniência.

    Solução:
        Percorrer sources -> items -> chains novamente e adicionar contexto.

    Args:
        linked: Projeto vinculado
        template: Template para detectar se chains têm relações explícitas

    Returns:
        Lista de dicts com {from, relation, to, source_item, location}
    """
    has_relations = _has_chain_relations(template)
    triples: List[Dict[str, Any]] = []

    for bibref, source in linked.sources.items():
        for index, item in enumerate(source.items, start=1):
            item_id = _format_item_id(bibref, index)

            for chain in item.chains:
                for from_code, relation, to_code in chain.to_triples(has_relations):
                    triples.append({
                        "from": from_code,
                        "relation": relation,
                        "to": to_code,
                        "source_item": item_id,
                        "location": chain.location.to_dict() if chain.location else None,
                    })

    return triples


def _build_indices_section(
    linked: LinkedProject,
    template: Optional[TemplateNode],
) -> Dict[str, Any]:
    """
    Constrói seção de índices pré-computados.

    Args:
        linked: Projeto vinculado
        template: Template opcional

    Returns:
        Dict com hierarchy, triples, topics, code_frequency
    """
    return {
        "hierarchy": linked.hierarchy,
        "triples": _build_triples_index(linked, template),
        "topics": linked.topic_index,
        "code_frequency": _build_code_frequency_index(linked),
    }


def export_json(
    linked: LinkedProject,
    path: Path,
    template: Optional[TemplateNode] = None,
    bibliography: Optional[Dict[str, BibEntry]] = None,
) -> None:
    """
    Exporta o projeto Synesis em JSON analitico v2.0.

    Mudanças em relação a v1.0:
        - Adiciona seção 'version' com valor "2.0"
        - Adiciona seção 'export_metadata' com timestamp e estatísticas
        - Renomeia seção 'meta' para 'project' com dados completos do ProjectNode
        - Adiciona seção 'template' com esquema completo (field_specs, relations, arity)
        - Adiciona seção 'bibliography' separada de source_metadata
        - Adiciona seção 'indices' com hierarquia, triplas enriquecidas, tópicos, frequências
        - Renomeia seção 'ontology_schema' para 'ontology' com enriquecimentos
        - Preserva seção 'corpus' com chains como objetos to_dict()

    Args:
        linked: Projeto vinculado com índices construídos
        path: Caminho do arquivo JSON de saída
        template: Template opcional (None = modo legado)
        bibliography: Entradas BibTeX opcionais
    """
    if not isinstance(path, Path):
        path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "version": "2.0",
        "export_metadata": _build_export_metadata(linked),
        "project": _build_project_section(linked),
        "template": _build_template_section(template),
        "bibliography": _build_bibliography_section(bibliography),
        "indices": _build_indices_section(linked, template),
        "ontology": _build_ontology_schema(linked, template),
        "corpus": _build_corpus(linked, template, bibliography),
    }

    payload = json.dumps(data, indent=2, ensure_ascii=False)
    path.write_text(payload, encoding="utf-8")


def _build_meta(linked: LinkedProject, template: Optional[TemplateNode]) -> Dict[str, Any]:
    meta: Dict[str, Any] = {}
    project_name = linked.project.name
    if template and template.name:
        project_name = template.name
    meta["project"] = project_name

    if linked.project.metadata:
        meta.update(linked.project.metadata)
    if template and template.metadata:
        meta.update(template.metadata)
    return meta


def _add_ordered_field_labels(
    fields: Dict[str, Any],
    template: TemplateNode,
) -> Dict[str, Any]:
    """
    Adiciona labels legíveis para campos ORDERED.

    Exemplo:
        aspect: 11 → adiciona aspect_label: "Economic"
        dimension: 2 → adiciona dimension_label: "Market_Acceptance"

    Args:
        fields: Campos do conceito de ontologia
        template: Template com field_specs

    Returns:
        Campos enriquecidos com *_label para cada campo ORDERED
    """
    for field_name, field_value in list(fields.items()):
        # Skip non-integer values and enriched fields
        if not isinstance(field_value, int) or field_name in {
            "frequency", "source_count", "theoretical_significance"
        }:
            continue

        # Check if ORDERED type
        spec = template.field_specs.get(field_name)
        if not spec or spec.type != FieldType.ORDERED:
            continue

        # Lookup label from VALUES
        if not spec.values:
            continue

        for ordered_value in spec.values:
            if ordered_value.index == field_value:
                fields[f"{field_name}_label"] = ordered_value.label
                break

    return fields


def _build_ontology_schema(
    linked: LinkedProject,
    template: Optional[TemplateNode],
) -> Dict[str, Dict[str, Any]]:
    """
    Constrói seção de ontologia com campos enriquecidos (v2.0).

    Enriquecimentos:
        - frequency: len(code_usage[code])
        - source_count: len(unique sources using code)
        - aspect_label, dimension_label: Labels de valores ORDERED
        - parent_chains: Preservado de OntologyNode.to_dict()

    Args:
        linked: Projeto vinculado
        template: Template opcional

    Returns:
        Dict mapeando conceito -> campos enriquecidos
    """
    schema: Dict[str, Dict[str, Any]] = {}
    for key in sorted(linked.ontology_index.keys()):
        ontology = linked.ontology_index[key]

        # Base fields via to_dict()
        fields = ontology.to_dict()

        # Enrich with frequency
        frequency = len(linked.code_usage.get(key, []))
        fields["frequency"] = frequency

        # Enrich with source_count
        items_using_code = linked.code_usage.get(key, [])
        unique_sources = len(set(item.bibref for item in items_using_code))
        fields["source_count"] = unique_sources

        # Enrich with ordered field labels
        if template:
            fields = _add_ordered_field_labels(fields, template)

        schema[ontology.concept] = fields

    return schema


def _build_corpus(
    linked: LinkedProject,
    template: Optional[TemplateNode],
    bibliography: Optional[Dict[str, BibEntry]],
) -> List[Dict[str, Any]]:
    corpus: List[Dict[str, Any]] = []
    for source in linked.sources.values():
        source_meta = _build_source_metadata(source, template, bibliography)
        for index, item in enumerate(source.items, start=1):
            corpus.append(
                _build_corpus_item(
                    source=source,
                    item=item,
                    index=index,
                    template=template,
                    linked=linked,
                    source_metadata=source_meta,
                )
            )
    return corpus


def _build_corpus_item(
    source: SourceNode,
    item: ItemNode,
    index: int,
    template: Optional[TemplateNode],
    linked: LinkedProject,
    source_metadata: Dict[str, Any],
) -> Dict[str, Any]:
    location = item.location
    item_id = _format_item_id(source.bibref, index)
    return {
        "id": item_id,
        "source_ref": source.bibref,
        "source_metadata": dict(source_metadata),
        "data": _build_item_data(item, template, linked),
        "traceability": {
            "file": str(location.file) if location else None,
            "line": location.line if location else None,
        },
    }


def _build_source_metadata(
    source: SourceNode,
    template: Optional[TemplateNode],
    bibliography: Optional[Dict[str, BibEntry]],
) -> Dict[str, Any]:
    metadata = _get_bib_metadata(bibliography, source.bibref)
    for key in ("author", "year", "title"):
        metadata.setdefault(key, None)

    if template:
        field_names = _get_field_names_for_scope(template, Scope.SOURCE)
        for name in field_names:
            metadata[name] = _clean_value(source.fields.get(name))
    else:
        for name, value in source.fields.items():
            metadata[name] = _clean_value(value)
    return metadata


def _build_item_data(
    item: ItemNode,
    template: Optional[TemplateNode],
    linked: LinkedProject,
) -> Dict[str, Any]:
    if not template:
        return _build_item_data_legacy(item)

    data: Dict[str, Any] = {}
    item_fields = _get_field_names_for_scope(template, Scope.ITEM)
    for name in item_fields:
        data[name] = _clean_value(_get_item_field_value(item, name))

    index_values = _collect_index_values(item, template)
    ontology_fields = _get_field_names_for_scope(template, Scope.ONTOLOGY)
    for name in ontology_fields:
        field_spec = template.field_specs.get(name)
        data[name] = _clean_value(
            _resolve_ontology_value(index_values, name, field_spec, linked)
        )
    return data


def _build_item_data_legacy(item: ItemNode) -> Dict[str, Any]:
    data: Dict[str, Any] = dict(item.extra_fields)
    if item.quote:
        data.setdefault("quote", item.quote)
    if item.codes:
        data.setdefault("codes", item.codes)
    if item.notes:
        data.setdefault("notes", item.notes)
    if item.chains:
        data.setdefault("chains", item.chains)
    return {name: _clean_value(value) for name, value in data.items()}


def _build_ontology_fields(
    ontology: OntologyNode,
    template: TemplateNode,
    linked: LinkedProject,
) -> Dict[str, Any]:
    fields: Dict[str, Any] = {}
    ontology_fields = _get_field_names_for_scope(template, Scope.ONTOLOGY)
    for name in ontology_fields:
        spec = template.field_specs.get(name)
        fields[name] = _clean_value(
            _resolve_ontology_field(ontology, name, spec, linked)
        )
    return fields


def _build_ontology_fields_legacy(ontology: OntologyNode) -> Dict[str, Any]:
    fields: Dict[str, Any] = dict(ontology.fields)
    if ontology.description:
        fields.setdefault("description", ontology.description)
    return {name: _clean_value(value) for name, value in fields.items()}


def _resolve_ontology_field(
    ontology: OntologyNode,
    field_name: str,
    field_spec: Optional[FieldSpec],
    linked: LinkedProject,
) -> Any:
    if field_spec and field_spec.type == FieldType.CHAIN:
        value = ontology.fields.get(field_name)
        if value is not None:
            return value
        return _resolve_hierarchy_chain(ontology.concept, linked)
    return _get_ontology_field_value(ontology, field_name)


def _resolve_ontology_value(
    index_values: List[str],
    field_name: str,
    field_spec: Optional[FieldSpec],
    linked: LinkedProject,
) -> Any:
    if not index_values:
        return None
    if len(index_values) == 1:
        return _resolve_ontology_value_for_code(index_values[0], field_name, field_spec, linked)
    return [
        _resolve_ontology_value_for_code(code, field_name, field_spec, linked)
        for code in index_values
    ]


def _resolve_ontology_value_for_code(
    code: str,
    field_name: str,
    field_spec: Optional[FieldSpec],
    linked: LinkedProject,
) -> Any:
    ontology = _find_ontology(linked, code)
    if not ontology:
        return None
    if field_spec and field_spec.type == FieldType.CHAIN:
        value = ontology.fields.get(field_name)
        if value is not None:
            return value
        return _resolve_hierarchy_chain(code, linked)
    return _get_ontology_field_value(ontology, field_name)


def _resolve_hierarchy_chain(code: str, linked: LinkedProject) -> List[str]:
    chain: List[str] = []
    current = _normalize_code(code)
    fallback = code.strip()
    visited = set()
    while current and current not in visited:
        visited.add(current)
        node = linked.ontology_index.get(current)
        if node:
            chain.append(node.concept)
        elif fallback:
            chain.append(fallback)
            fallback = ""
        parent = linked.hierarchy.get(current)
        if not parent:
            break
        current = parent
    return chain


def _collect_index_values(item: ItemNode, template: TemplateNode) -> List[str]:
    index_fields = _get_field_names_for_scope_and_types(
        template,
        Scope.ITEM,
        {FieldType.CODE, FieldType.CHAIN},
    )
    values: List[str] = []
    for name in index_fields:
        spec = template.field_specs.get(name)
        raw = _get_item_field_value(item, name)
        values.extend(_extract_index_values(raw, spec))
    return values


def _extract_index_values(value: Any, field_spec: Optional[FieldSpec]) -> List[str]:
    if isinstance(value, list):
        values: List[str] = []
        for entry in value:
            values.extend(_extract_index_values(entry, field_spec))
        return values
    if isinstance(value, ChainNode):
        return _extract_chain_codes(value, field_spec)
    if isinstance(value, str):
        return [value]
    return []


def _extract_chain_codes(chain: ChainNode, field_spec: Optional[FieldSpec]) -> List[str]:
    elements = [element.strip() for element in chain.nodes if element.strip()]
    if not elements:
        return []
    if field_spec and field_spec.type == FieldType.CHAIN and field_spec.relations:
        if len(elements) >= 3 and len(elements) % 2 == 1:
            return elements[::2]
    return elements


def _get_field_names_for_scope(template: TemplateNode, scope: Scope) -> List[str]:
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


def _clean_value(value: Any) -> Any:
    """
    Limpa valores para serialização JSON.

    Mudanças em v2.0:
        ChainNode: Retorna to_dict() com {nodes, relations, location}
        (antes retornava apenas value.nodes)

    Args:
        value: Valor a ser limpo

    Returns:
        Valor limpo ou None se vazio
    """
    if isinstance(value, ChainNode):
        return value.to_dict()  # Changed from: return value.nodes

    if isinstance(value, list):
        if not value:
            return None
        return [_clean_value(item) for item in value]

    if value is None:
        return None

    if isinstance(value, str):
        return value if value.strip() else None

    return value


def _find_ontology(linked: LinkedProject, code: str) -> Optional[OntologyNode]:
    return linked.ontology_index.get(_normalize_code(code))


def _normalize_code(code: str) -> str:
    return " ".join(code.strip().split()).lower()


def _normalize_bibref(bibref: str) -> str:
    return bibref.lstrip("@").strip().lower()


def _format_item_id(bibref: str, index: int) -> str:
    source = _normalize_bibref(bibref)
    source = re.sub(r"\s+", "", source)
    return f"{source}_item{index:0{_ITEM_INDEX_WIDTH}d}"


def _get_bib_metadata(
    bibliography: Optional[Dict[str, BibEntry]],
    bibref: str,
) -> Dict[str, Any]:
    if not bibliography:
        return {}
    entry = bibliography.get(_normalize_bibref(bibref))
    if not entry:
        return {}
    return {key: value for key, value in entry.items() if key != "_original_key"}
