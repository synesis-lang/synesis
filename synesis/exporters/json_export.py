"""
json_export.py - Exportacao JSON analitico do projeto Synesis v3.0

Proposito:
    Gerar JSON analitico universal para Neo4j, analise bibliometrica,
    reconstrucao de workspace e dashboards. Usa template como fonte de
    verdade e enriquece com indices pre-computados.

Componentes principais:
    - export_json: funcao principal de escrita em JSON v3.0
    - Builders de secoes: metadata, project, template, bibliography, indices, ontology, corpus
    - Enriquecimentos: frequencias (diretas + chains), source_count, labels de campos ORDERED

Dependencias criticas:
    - json: serializacao
    - datetime: timestamp de exportacao
    - synesis.semantic.linker: LinkedProject consolidado
    - synesis.ast.nodes: TemplateNode, ProjectNode, OntologyNode
    - synesis.parser.bib_loader: BibEntry

Exemplo de uso:
    from synesis.exporters.json_export import export_json
    export_json(linked, Path("saida_v3.json"), template, bibliography)

Notas de implementacao (v3.0):
    - Estrutura: version, export_metadata, project, template, bibliography, indices, ontology, corpus
    - Breaking change v3.0: sem source_metadata por item (usar source_ref -> bibliography)
    - Breaking change v3.0: campos de ontologia aplanados (sem sub-dict "fields")
    - Breaking change v3.0: chains no corpus como lista de {from, relation, to}
    - Fix: frequency e source_count incluem uso via chains (nao apenas campos CODE)
    - Campos vazios/zerados omitidos na secao ontology

Gerado conforme: Especificacao Synesis v3.0
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
from synesis.exporters._helpers import (
    _get_field_names_for_scope,
    _get_field_names_for_scope_and_types,
    _get_item_field_value,
    _get_ontology_field_value,
)

_ITEM_INDEX_WIDTH = 4


def _build_export_metadata(linked: LinkedProject) -> Dict[str, Any]:
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
    return linked.project.to_dict()


def _build_template_section(template: Optional[TemplateNode]) -> Optional[Dict[str, Any]]:
    if template is None:
        return None
    return template.to_dict()


def _build_bibliography_section(
    bibliography: Optional[Dict[str, BibEntry]],
    linked: LinkedProject,
    template: Optional[TemplateNode],
) -> Dict[str, Dict[str, Any]]:
    """
    Constroi secao de bibliografia enriquecida com campos SOURCE (v3.0).

    Em v3.0, a bibliography inclui tanto as entradas BibTeX quanto os campos
    sintetizados do bloco SOURCE (description, epistemic_model, method, etc.),
    eliminando a necessidade de source_metadata por item no corpus.
    """
    result: Dict[str, Dict[str, Any]] = {}

    if bibliography:
        for key, entry in bibliography.items():
            cleaned = {k: v for k, v in entry.items() if k != "_original_key"}
            result[_normalize_bibref(key)] = cleaned

    # Enrich with SOURCE synthetic fields
    if template:
        source_field_names = _get_field_names_for_scope(template, Scope.SOURCE)
    else:
        source_field_names = None

    for bibref, source in linked.sources.items():
        norm_bibref = _normalize_bibref(bibref)
        entry = result.setdefault(norm_bibref, {})
        if source_field_names is not None:
            for name in source_field_names:
                val = _clean_value(source.fields.get(name))
                if val is not None:
                    entry[name] = val
        else:
            for name, value in source.fields.items():
                val = _clean_value(value)
                if val is not None:
                    entry[name] = val

    return result


def _build_chain_usage(
    linked: LinkedProject,
    template: Optional[TemplateNode],
) -> Dict[str, List[ItemNode]]:
    """
    Mapeia conceito normalizado -> lista de ItemNodes que o referenciam em chains.

    Necessario para corrigir frequency/source_count em projetos que usam
    conceitos exclusivamente via chains (sem campos CODE de scope ITEM).
    """
    has_relations = _has_chain_relations(template)
    usage: Dict[str, List[ItemNode]] = {}
    for source in linked.sources.values():
        for item in source.items:
            for chain in item.chains:
                for from_c, _rel, to_c in chain.to_triples(has_relations):
                    for concept in (from_c, to_c):
                        key = _normalize_code(concept)
                        usage.setdefault(key, []).append(item)
    return usage


def _build_code_frequency_index(
    linked: LinkedProject,
    chain_usage: Dict[str, List[ItemNode]],
) -> Dict[str, int]:
    """
    Calcula frequencia de uso de cada codigo (direto + via chains).
    """
    freq: Dict[str, int] = {}

    for code, items in linked.code_usage.items():
        freq[code] = len(items)

    for code, chain_items in chain_usage.items():
        direct_ids = {id(i) for i in linked.code_usage.get(code, [])}
        additional = sum(1 for i in chain_items if id(i) not in direct_ids)
        freq[code] = freq.get(code, 0) + additional

    return freq


def _has_chain_relations(template: Optional[TemplateNode]) -> bool:
    """
    Verifica se template define RELATIONS para campo chain.

    Se True, chain e qualificada (codigos alternados com relacoes).
    Se False, chain e simples (apenas codigos).
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
    Enriquece triplas com proveniencia (source_item, location).
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
    chain_usage: Dict[str, List[ItemNode]],
) -> Dict[str, Any]:
    return {
        "hierarchy": linked.hierarchy,
        "triples": _build_triples_index(linked, template),
        "topics": linked.topic_index,
        "code_frequency": _build_code_frequency_index(linked, chain_usage),
    }


def build_json_payload(
    linked: LinkedProject,
    template: Optional[TemplateNode] = None,
    bibliography: Optional[Dict[str, BibEntry]] = None,
) -> Dict[str, Any]:
    """
    Constroi payload JSON v3.0 em memoria (sem I/O).

    Ideal para uso em Jupyter Notebooks, LSP e integracao com APIs.
    Retorna dicionario Python que pode ser serializado ou manipulado.

    Args:
        linked: Projeto vinculado com indices construidos
        template: Template opcional (None = modo legado)
        bibliography: Entradas BibTeX opcionais

    Returns:
        Dict com estrutura JSON v3.0 contendo:
        - version: "3.0"
        - export_metadata: timestamp, estatisticas
        - project: dados do ProjectNode
        - template: esquema completo (field_specs, relations, arity)
        - bibliography: entradas BibTeX + campos SOURCE sintetizados
        - indices: hierarquia, triplas, topicos, frequencias
        - ontology: conceitos com campos aplanados e enriquecidos
        - corpus: items sem source_metadata (usar source_ref -> bibliography)

    Example:
        >>> payload = build_json_payload(linked, template, bib)
        >>> import json
        >>> print(json.dumps(payload, indent=2))
    """
    chain_usage = _build_chain_usage(linked, template)

    return {
        "version": "3.0",
        "export_metadata": _build_export_metadata(linked),
        "project": _build_project_section(linked),
        "template": _build_template_section(template),
        "bibliography": _build_bibliography_section(bibliography, linked, template),
        "indices": _build_indices_section(linked, template, chain_usage),
        "ontology": _build_ontology_schema(linked, template, chain_usage),
        "corpus": _build_corpus(linked, template),
    }


def export_json(
    linked: LinkedProject,
    path: Path,
    template: Optional[TemplateNode] = None,
    bibliography: Optional[Dict[str, BibEntry]] = None,
) -> None:
    """
    Exporta o projeto Synesis em JSON analitico v3.0.

    Usa build_json_payload() para construir os dados e escreve em disco.

    Args:
        linked: Projeto vinculado com indices construidos
        path: Caminho do arquivo JSON de saida
        template: Template opcional (None = modo legado)
        bibliography: Entradas BibTeX opcionais
    """
    if not isinstance(path, Path):
        path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    data = build_json_payload(linked, template, bibliography)
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
    entry: Dict[str, Any],
    template: TemplateNode,
) -> Dict[str, Any]:
    """
    Adiciona labels legiveis para campos ORDERED.

    Exemplo:
        aspect: 11 -> adiciona aspect_label: "Economic"
        dimension: 2 -> adiciona dimension_label: "Market_Acceptance"
    """
    for field_name, field_value in list(entry.items()):
        if not isinstance(field_value, int) or field_name in {
            "frequency", "source_count", "theoretical_significance"
        }:
            continue

        spec = template.field_specs.get(field_name)
        if not spec or spec.type != FieldType.ORDERED:
            continue

        if not spec.values:
            continue

        for ordered_value in spec.values:
            if ordered_value.index == field_value:
                entry[f"{field_name}_label"] = ordered_value.label
                break

    return entry


def _build_ontology_schema(
    linked: LinkedProject,
    template: Optional[TemplateNode],
    chain_usage: Dict[str, List[ItemNode]],
) -> Dict[str, Dict[str, Any]]:
    """
    Constroi secao de ontologia v3.0 com campos aplanados e enriquecidos.

    Mudancas em relacao a v2.0:
        - Campos aplanados: sem sub-dict "fields" (ontology_description, topic, etc. na raiz)
        - frequency e source_count incluem uso via chains (fix para projetos chain-based)
        - Campos vazios/zerados omitidos
        - aspect_label, dimension_label adicionados corretamente (antes eram perdidos)
    """
    schema: Dict[str, Dict[str, Any]] = {}
    for key in sorted(linked.ontology_index.keys()):
        ontology = linked.ontology_index[key]

        entry: Dict[str, Any] = {"concept": ontology.concept}
        if ontology.description:
            entry["description"] = ontology.description

        # Flat fields (v3.0: sem sub-dict "fields")
        for fname, fval in ontology.fields.items():
            cleaned = _clean_value(fval)
            if cleaned not in (None, "", []):
                entry[fname] = cleaned

        # parent_chains (preservado se nao-vazio)
        if ontology.parent_chains:
            entry["parent_chains"] = [chain.to_dict() for chain in ontology.parent_chains]

        # location
        if ontology.location:
            entry["location"] = ontology.location.to_dict()

        # frequency: direto + via chains (deduplica por id(item))
        direct_items = linked.code_usage.get(key, [])
        chain_items = chain_usage.get(key, [])
        direct_ids = {id(i) for i in direct_items}
        all_count = len(direct_ids) + sum(1 for i in chain_items if id(i) not in direct_ids)
        if all_count:
            entry["frequency"] = all_count

        # source_count: fontes unicas (direto + via chains)
        direct_sources = {item.bibref for item in direct_items}
        chain_sources = {item.bibref for item in chain_items}
        all_sources = direct_sources | chain_sources
        if all_sources:
            entry["source_count"] = len(all_sources)

        # Labels para campos ORDERED (funciona corretamente com campos aplanados)
        if template:
            entry = _add_ordered_field_labels(entry, template)

        schema[ontology.concept] = entry

    return schema


def _build_corpus(
    linked: LinkedProject,
    template: Optional[TemplateNode],
) -> List[Dict[str, Any]]:
    corpus: List[Dict[str, Any]] = []
    for source in linked.sources.values():
        for index, item in enumerate(source.items, start=1):
            corpus.append(
                _build_corpus_item(
                    source=source,
                    item=item,
                    index=index,
                    template=template,
                    linked=linked,
                )
            )
    return corpus


def _build_corpus_item(
    source: SourceNode,
    item: ItemNode,
    index: int,
    template: Optional[TemplateNode],
    linked: LinkedProject,
) -> Dict[str, Any]:
    """
    Constroi item do corpus v3.0.

    Mudanca em relacao a v2.0: sem source_metadata (usar source_ref -> bibliography).
    """
    location = item.location
    item_id = _format_item_id(source.bibref, index)
    return {
        "id": item_id,
        "source_ref": source.bibref,
        "data": _build_item_data(item, template, linked),
        "traceability": {
            "file": str(location.file) if location else None,
            "line": location.line if location else None,
        },
    }


def _build_item_data(
    item: ItemNode,
    template: Optional[TemplateNode],
    linked: LinkedProject,
) -> Dict[str, Any]:
    if not template:
        return _build_item_data_legacy(item)

    data: Dict[str, Any] = {}
    item_fields = _get_field_names_for_scope(template, Scope.ITEM)
    has_relations = _has_chain_relations(template)

    for name in item_fields:
        spec = template.field_specs.get(name)
        raw = _get_item_field_value(item, name)
        if spec and spec.type == FieldType.CHAIN:
            # v3.0: chains como lista de {from, relation, to}
            data[name] = _serialize_chain_as_triples(raw, has_relations)
        else:
            data[name] = _clean_value(raw)

    index_values = _collect_index_values(item, template)
    ontology_fields = _get_field_names_for_scope(template, Scope.ONTOLOGY)
    for name in ontology_fields:
        field_spec = template.field_specs.get(name)
        data[name] = _clean_value(
            _resolve_ontology_value(index_values, name, field_spec, linked)
        )
    return data


def _serialize_chain_as_triples(
    value: Any,
    has_relations: bool,
) -> Optional[List[Dict[str, Any]]]:
    """
    Converte ChainNode(s) para lista de {from, relation, to} (formato v3.0).
    """
    chains = value if isinstance(value, list) else ([value] if value else [])
    result: List[Dict[str, Any]] = []
    for chain in chains:
        if isinstance(chain, ChainNode):
            for from_c, rel, to_c in chain.to_triples(has_relations):
                result.append({"from": from_c, "relation": rel, "to": to_c})
    return result or None


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


def _clean_value(value: Any) -> Any:
    if isinstance(value, ChainNode):
        return value.to_dict()

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
