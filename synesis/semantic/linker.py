"""
linker.py - Vinculacao entre fontes, itens e ontologias Synesis

Proposito:
    Associar ITEMs a SOURCEs, construir indices e coletar relacoes.
    Produz LinkedProject com estrutura consolidada para exportacao.

Componentes principais:
    - Linker: classe de vinculacao principal
    - LinkedProject: resultado consolidado do link

Dependencias criticas:
    - synesis.ast.nodes: nos da AST
    - synesis.ast.results: erros de vinculacao

Exemplo de uso:
    linker = Linker(sources, items, ontologies)
    linked = linker.link()

Notas de implementacao:
    - Grafo IS_A usa parent_chains em ontologias.
    - Diagnostics ficam disponiveis em Linker.validation_result.

Gerado conforme: Especificacao Synesis v1.1
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple

from synesis.ast.nodes import (
    ChainNode,
    FieldType,
    ItemNode,
    OntologyNode,
    ProjectNode,
    Scope,
    SourceLocation,
    SourceNode,
    TemplateNode,
)
from synesis.ast.results import (
    OrphanItem,
    SourceWithoutItems,
    UndefinedCode,
    ValidationResult,
)


@dataclass
class LinkedProject:
    project: ProjectNode
    sources: Dict[str, SourceNode]
    ontology_index: Dict[str, OntologyNode]
    code_usage: Dict[str, List[ItemNode]]
    hierarchy: Dict[str, str]
    all_triples: List[Tuple[str, str, str]]
    topic_index: Dict[str, List[str]]
    relation_index: Dict[Tuple[str, str, str], Dict[str, Any]] = field(default_factory=dict)


@dataclass
class Linker:
    sources: List[SourceNode]
    items: List[ItemNode]
    ontologies: List[OntologyNode]
    project: ProjectNode | None = None
    template: TemplateNode | None = None
    validation_result: ValidationResult = field(default_factory=ValidationResult)

    def link(self) -> LinkedProject:
        sources_by_bibref = {self._norm_bibref(s.bibref): s for s in self.sources}
        items_by_bibref: Dict[str, List[ItemNode]] = {}

        for item in self.items:
            key = self._norm_bibref(item.bibref)
            items_by_bibref.setdefault(key, []).append(item)

        for bibref, items in items_by_bibref.items():
            source = sources_by_bibref.get(bibref)
            if not source:
                location = items[0].location or SourceLocation(Path("<unknown>"), 1, 1)
                self.validation_result.add(
                    OrphanItem(
                        location=location,
                        bibref=bibref,
                    )
                )
                continue
            source.items = items

        for bibref, source in sources_by_bibref.items():
            if not source.items:
                location = source.location or SourceLocation(Path("<unknown>"), 1, 1)
                self.validation_result.add(
                    SourceWithoutItems(
                        location=location,
                        bibref=bibref,
                    )
                )

        ontology_index = {self._norm_code(o.concept): o for o in self.ontologies}
        code_usage: Dict[str, List[ItemNode]] = {}
        all_triples: List[Tuple[str, str, str]] = []
        relation_index: Dict[Tuple[str, str, str], Dict[str, Any]] = {}

        for item in self.items:
            for code in self._collect_item_codes(item):
                norm_code = self._norm_code(code)
                code_usage.setdefault(norm_code, []).append(item)
                if norm_code not in ontology_index:
                    location = item.location or SourceLocation(Path("<unknown>"), 1, 1)
                    self.validation_result.add(
                        UndefinedCode(
                            location=location,
                            code=norm_code,
                            context="ITEM",
                        )
                    )

            for chain in item.chains:
                # Detecta se template define RELATIONS (chain qualificada)
                has_relations = self._has_chain_relations()
                triples = chain.to_triples(has_relations=has_relations)
                all_triples.extend(triples)

                relation_type = "qualified" if has_relations else "simple"
                chain_location = chain.location or item.location or SourceLocation(Path("<unknown>"), 1, 1)
                for triple in triples:
                    if triple not in relation_index:
                        relation_index[triple] = {
                            "location": chain_location,
                            "type": relation_type,
                        }

        hierarchy: Dict[str, str] = {}
        for ontology in self.ontologies:
            for chain in ontology.parent_chains:
                # Relacoes IS_A entre nos consecutivos da cadeia
                for child, parent in self._is_a_pairs(chain):
                    hierarchy[self._norm_code(child)] = self._norm_code(parent)

        topic_index: Dict[str, List[str]] = {}
        for ontology in self.ontologies:
            topics = self._extract_topics(ontology)
            for topic in topics:
                topic_index.setdefault(topic, []).append(ontology.concept)

        project = self.project or self._default_project()
        return LinkedProject(
            project=project,
            sources=sources_by_bibref,
            ontology_index=ontology_index,
            code_usage=code_usage,
            hierarchy=hierarchy,
            all_triples=all_triples,
            topic_index=topic_index,
            relation_index=relation_index,
        )

    def _is_a_pairs(self, chain: ChainNode) -> List[Tuple[str, str]]:
        pairs: List[Tuple[str, str]] = []
        nodes = [n.strip() for n in chain.nodes if n.strip()]
        for idx in range(len(nodes) - 1):
            pairs.append((nodes[idx], nodes[idx + 1]))
        return pairs

    def _extract_topics(self, ontology: OntologyNode) -> List[str]:
        if not self.template:
            value = ontology.fields.get("topic")
            if isinstance(value, list):
                return [str(v) for v in value]
            if isinstance(value, str):
                return [value]
            return []

        topics: List[str] = []
        for field_name, value in ontology.fields.items():
            spec = self.template.field_specs.get(field_name)
            if spec and spec.type == FieldType.TOPIC:
                if isinstance(value, list):
                    topics.extend([str(v) for v in value])
                else:
                    topics.append(str(value))
        return topics

    def _has_chain_relations(self) -> bool:
        """
        Verifica se template define RELATIONS para campo chain.
        Se True, chain e qualificada (codigos alternados com relacoes).
        Se False, chain e simples (apenas codigos).
        """
        if not self.template:
            return False

        chain_spec = self.template.field_specs.get("chain")
        if not chain_spec:
            return False

        return bool(chain_spec.relations)

    def _collect_item_codes(self, item: ItemNode) -> List[str]:
        if not self.template:
            return list(item.codes)

        code_fields = [
            name
            for name, spec in self.template.field_specs.items()
            if spec.scope == Scope.ITEM and spec.type == FieldType.CODE
        ]
        if not code_fields:
            return list(item.codes)

        codes: List[str] = []
        for name in code_fields:
            raw = self._get_item_field_value(item, name)
            codes.extend(self._extract_code_values(raw))
        return codes

    def _extract_code_values(self, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, list):
            codes: List[str] = []
            for entry in value:
                codes.extend(self._extract_code_values(entry))
            return codes
        if isinstance(value, (int, float)):
            return [str(value)]
        if isinstance(value, str):
            return [value]
        return []

    def _get_item_field_value(self, item: ItemNode, name: str) -> Any:
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
        return None

    def _norm_bibref(self, bibref: str) -> str:
        return bibref.lstrip("@").strip().lower()

    def _norm_code(self, code: str) -> str:
        return " ".join(code.strip().split()).lower()

    def _default_project(self) -> ProjectNode:
        return ProjectNode(
            name="",
            template_path=Path(""),
            includes=[],
            metadata={},
            description=None,
            location=SourceLocation(Path("<unknown>"), 1, 1),
        )
