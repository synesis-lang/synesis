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
from synesis.ast.normalize import normalize_bibref, normalize_code
from synesis.ast.results import (
    DeprecatedNameBasedHierarchy,
    DuplicateOntologyConcept,
    DuplicateOntologyDescription,
    DuplicateSourceBibref,
    IdentityCollision,
    OrphanItem,
    SourceWithoutItems,
    UngroundedConcept,
    ValidationResult,
)
from synesis.semantic.occurrences import (
    _parse_chain_lines,
    _parse_code_lines,
    entries_named,
    item_chains,
    item_field_value,
)
from synesis.semantic.ontology_values import project_ontology


def _merge_code_values(extra_fields: Dict[str, Any], field_name: str, values: List[str]) -> None:
    if not values:
        return
    existing = extra_fields.get(field_name)
    if existing is None or isinstance(existing, str):
        extra_fields[field_name] = list(values)
        return
    if isinstance(existing, list):
        existing.extend(values)
        return
    extra_fields[field_name] = [existing, *values]


def _merge_chain_value(extra_fields: Dict[str, Any], field_name: str, chain: ChainNode) -> None:
    existing = extra_fields.get(field_name)
    if existing is None or isinstance(existing, str):
        extra_fields[field_name] = chain
        return
    if isinstance(existing, list):
        existing.append(chain)
        return
    extra_fields[field_name] = [existing, chain]


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
    # Hierarquia adotada pelos papeis HIERARCHY (semantic.hierarchy.Hierarchy);
    # None num template sem papeis. `hierarchy` acima e a rota antiga por nome.
    role_hierarchy: Any = None
    # Etapa U: preterido -> alvo (identidades). `code_usage` ja vem resolvido;
    # a forma escrita (itens, triplas) nao muda.
    aliases: Dict[str, str] = field(default_factory=dict)


@dataclass
class Linker:
    sources: List[SourceNode]
    items: List[ItemNode]
    ontologies: List[OntologyNode]
    project: ProjectNode | None = None
    template: TemplateNode | None = None
    validation_result: ValidationResult = field(default_factory=ValidationResult)
    norm_cache: dict | None = None

    def link(self) -> LinkedProject:
        # Forma canonica de ORDERED: o dado materializado e sempre o indice.
        # Roda antes de qualquer consumo (topic_index, code_usage, export).
        self._normalize_ordered_values()

        # Erro 70: bibrefs duplicados em blocos SOURCE (mesmo arquivo ou arquivos diferentes)
        self._check_duplicate_source_bibrefs()

        sources_by_bibref = {normalize_bibref(s.bibref): s for s in self.sources}
        items_by_bibref: Dict[str, List[ItemNode]] = {}

        for item in self.items:
            if self.template:
                self._augment_item_field_locations(item)
            key = normalize_bibref(item.bibref)
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

        # Erros 68 e 71: conceitos ontológicos duplicados e descrições duplicadas
        self._check_duplicate_ontology_concepts()
        self._check_duplicate_ontology_descriptions()

        # Copias com o valor pelo TIPO declarado (ontology_values): exportadores,
        # LSP e grafo leem o mesmo valor que o validador conferiu. O no parseado
        # nao muda (parse_cache).
        ontology_index = {
            normalize_code(o.concept, self.norm_cache): project_ontology(o, self.template)
            for o in self.ontologies
        }
        from synesis.semantic.aliases import build_aliases, resolve_usage

        aliases, alias_errors = build_aliases(ontology_index, self.template)
        for error in alias_errors:
            self.validation_result.add(error)
        code_usage: Dict[str, List[ItemNode]] = {}
        all_triples: List[Tuple[str, str, str]] = []
        relation_index: Dict[Tuple[str, str, str], Dict[str, Any]] = {}

        # Hoist invariantes: computar UMA VEZ antes do loop de items
        has_relations = self._has_chain_relations()

        # Código sem conceito (E004/E090) é diagnosticado pelo SemanticValidator;
        # emiti-lo também aqui contava cada código de ITEM duas vezes.
        for item in self.items:
            for code in self._collect_item_codes(item):
                norm_code = normalize_code(code, self.norm_cache)
                code_usage.setdefault(norm_code, []).append(item)

            for chain, qualified in self._collect_item_chains(item, has_relations):
                triples = chain.to_triples(has_relations=qualified)
                all_triples.extend(triples)

                chain_location = chain.location or item.location or SourceLocation(Path("<unknown>"), 1, 1)
                for triple in triples:
                    if triple not in relation_index:
                        relation_index[triple] = {
                            "location": chain_location,
                            "type": "qualified" if qualified else "simple",
                        }

        hierarchy: Dict[str, str] = {}
        for ontology in self.ontologies:
            for chain in ontology.parent_chains:
                # Relacoes IS_A entre nos consecutivos da cadeia
                for child, parent in self._is_a_pairs(chain):
                    hierarchy[normalize_code(child, self.norm_cache)] = normalize_code(parent, self.norm_cache)

        topic_index: Dict[str, List[str]] = {}
        for ontology in self.ontologies:
            topics = self._extract_topics(ontology)
            for topic in topics:
                topic_index.setdefault(topic, []).append(ontology.concept)

        # Projecao analitica: mencoes do preterido contam para o alvo.
        code_usage = resolve_usage(code_usage, aliases)
        role_hierarchy = self._link_roles(ontology_index, code_usage, all_triples, aliases)

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
            role_hierarchy=role_hierarchy,
            aliases=dict(aliases.target),
        )

    def _link_roles(self, ontology_index, code_usage, all_triples, aliases=None):
        """Hierarquia por papel, rotulos e fundamentacao (Spec §5.2, §6).

        Le os valores ja interpretados pelo tipo (copias do ontology_index).
        Com papel HIERARCHY, avisa os blocos sem mencao (CODE ou CHAIN) e sem
        descendente mencionado. A rota por nome (`parent`/`is_a`) recebe aviso.
        """
        from synesis.semantic.hierarchy import Hierarchy, grounding, label_errors
        from synesis.semantic.roles import fields_with_family, has_roles

        for ontology in self.ontologies:
            for name in ontology.field_names:
                if name.lower() in {"parent", "parents", "is_a", "isa"}:
                    self.validation_result.add(DeprecatedNameBasedHierarchy(
                        location=ontology.location or SourceLocation(Path("<unknown>"), 1, 1),
                        concept=ontology.concept,
                        field_name=name,
                    ))
        if not has_roles(self.template):
            return None
        hierarchy = Hierarchy.build(ontology_index, self.template, aliases)
        for error in hierarchy.errors + label_errors(ontology_index, self.template):
            self.validation_result.add(error)
        if fields_with_family(self.template, "HIERARCHY"):
            resolve = aliases.resolve if aliases else (lambda k: k)
            mentioned = {resolve(k) for k in code_usage}
            for a, _rel, b in all_triples:
                mentioned.add(resolve(normalize_code(a, self.norm_cache)))
                mentioned.add(resolve(normalize_code(b, self.norm_cache)))
            for key, grounded in grounding(hierarchy, ontology_index, mentioned).items():
                if aliases and aliases.is_alias(key):
                    continue  # o preterido nao e conceito: o alvo responde por ele
                if not grounded:
                    node = ontology_index[key]
                    self.validation_result.add(UngroundedConcept(
                        location=node.location or SourceLocation(Path("<unknown>"), 1, 1),
                        concept=node.concept,
                    ))
        return hierarchy

    def _is_a_pairs(self, chain: ChainNode) -> List[Tuple[str, str]]:
        pairs: List[Tuple[str, str]] = []
        nodes = [n.strip() for n in chain.nodes if n.strip()]
        for idx in range(len(nodes) - 1):
            pairs.append((nodes[idx], nodes[idx + 1]))
        return pairs

    def _normalize_ordered_values(self) -> None:
        """Tipa valores de campos ORDERED escritos como texto numerico ("11" -> 11).

        NAO resolve rotulo->indice: em ORDERED o dado E o indice, e escrever o
        rotulo e erro de forma (E088, reportado pelo SemanticValidator, que roda
        antes deste ponto). Normalizar o rotulo em silencio manteria o arquivo no
        disco divergente do que o compilador entrega e deixaria a grafia livre se
        acumular no corpus — o arquivo nunca convergiria para a forma canonica.

        O que resta aqui e apenas coercao de TIPO: o valor ja esta na forma certa
        (um indice), so nao chegou como int. Assim o consumidor recebe sempre int.

        Os tres escopos guardam campos em atributos distintos — SourceNode.fields,
        OntologyNode.fields e ItemNode.extra_fields.
        """
        if not self.template:
            return

        ordered_names = [
            name
            for name, spec in (self.template.field_specs or {}).items()
            if spec.type == FieldType.ORDERED and spec.values
        ]
        if not ordered_names:
            return

        for source in self.sources:
            self._coerce_ordered_in(source.fields, ordered_names)
        for item in self.items:
            self._coerce_ordered_in(item.extra_fields, ordered_names)
        for ontology in self.ontologies:
            self._coerce_ordered_in(ontology.fields, ordered_names)

    @staticmethod
    def _coerce_ordered_in(
        fields: Dict[str, Any] | None,
        ordered_names: List[str],
    ) -> None:
        """Converte indice escrito como texto para int, nos campos ORDERED."""
        if not fields:
            return

        for field_name in ordered_names:
            value = fields.get(field_name)
            if not isinstance(value, str):
                continue
            stripped = value.strip()
            if stripped.lstrip("-").isdigit():
                fields[field_name] = int(stripped)

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
        Verifica se template define RELATIONS para algum campo CHAIN.
        Se True, chain e qualificada (codigos alternados com relacoes).
        Se False, chain e simples (apenas codigos).
        """
        if not self.template:
            return False

        for spec in self.template.field_specs.values():
            if spec.type == FieldType.CHAIN and spec.relations:
                return True
        return False

    def _collect_item_chains(
        self, item: ItemNode, default_qualified: bool
    ) -> List[Tuple[ChainNode, bool]]:
        """Cadeias do ITEM, de TODOS os campos CHAIN do template, pelo TIPO.

        Espelho de `_collect_item_codes`. O parser só põe em `item.chains` os
        campos chamados `chain`/`chains`; um CHAIN com outro nome ia para
        `extra_fields` e ficava fora de `all_triples` e de `relation_index` —
        e, por eles, do LSP (relações, grafo) e da lista de conceitos do coder.

        Cada cadeia sai com o modo do SEU campo (qualificada se o campo declara
        RELATIONS); a regra mora em `occurrences.item_chains`, que o exportador
        JSON também usa.

        Returns:
            Lista de (cadeia, qualificada), sem repetir a mesma cadeia.
        """
        return item_chains(item, self.template, default_qualified)

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

    def _augment_item_field_locations(self, item: ItemNode) -> None:
        if not self.template:
            return
        field_specs = self.template.field_specs or {}
        line_tokens = getattr(item, "field_line_tokens", None) or {}
        if not line_tokens:
            return

        if item.location and getattr(item.location, "file", None):
            file_path = item.location.file
        else:
            file_path = Path("<unknown>")

        if item.entries:
            self._rebuild_typed_item_fields(item, field_specs, file_path)
            return

        for field_name, spec in field_specs.items():
            if spec.scope != Scope.ITEM:
                continue
            if spec.type not in {FieldType.CODE, FieldType.CHAIN}:
                continue
            raw_lines = line_tokens.get(field_name)
            if not raw_lines:
                continue

            for lines in raw_lines:
                if spec.type == FieldType.CODE:
                    values, locations = _parse_code_lines(file_path, lines)
                    if values:
                        _merge_code_values(item.extra_fields, field_name, values)
                    if locations:
                        # Deduplicar localizações antes de estender (previne duplicatas do transformer)
                        existing = item.code_locations.get(field_name, [])
                        existing_keys = {(loc.file, loc.line, loc.column) for loc in existing}
                        new_locs = [loc for loc in locations
                                   if (loc.file, loc.line, loc.column) not in existing_keys]
                        if new_locs:
                            item.code_locations.setdefault(field_name, []).extend(new_locs)
                    continue

                chain_location = item.location or SourceLocation(file_path, 1, 1)
                chain_node = _parse_chain_lines(file_path, lines, chain_location)
                if chain_node.nodes:
                    _merge_chain_value(item.extra_fields, field_name, chain_node)

    def _rebuild_typed_item_fields(
        self, item: ItemNode, field_specs: Dict[str, Any], file_path: Path
    ) -> None:
        """Reinterpreta CODE/CHAIN de nome livre pelo tipo, a partir das ocorrências.

        O transformer não conhece o template: um CODE de nome livre chega como
        texto ("X, Y") e uma CHAIN escrita sem seta na 1a linha, como texto. O
        valor tipado é RECONSTRUÍDO das ocorrências (`item.entries`) a cada
        link, em vez de estender o que já está em `extra_fields`. Estender
        duplicava os códigos de um campo escrito mais de uma vez no ITEM e, como
        o parse_cache devolve os mesmos nós, multiplicava-os a cada recompilação
        no mesmo processo (LSP). Reconstruir é idempotente.

        Só reconstrói campos com alguma ocorrência em texto bruto (`lines`),
        o mesmo gatilho de antes; a forma do valor é a de sempre (lista plana de
        códigos; ChainNode, ou lista se o campo foi escrito mais de uma vez).
        """
        for field_name, spec in field_specs.items():
            if spec.scope != Scope.ITEM:
                continue
            if spec.type not in {FieldType.CODE, FieldType.CHAIN}:
                continue
            occurrences = entries_named(item, field_name)
            if not any(entry.lines for entry in occurrences):
                continue

            if spec.type == FieldType.CODE:
                codes: List[Any] = []
                base_locations: List[SourceLocation] = []
                parsed_locations: List[SourceLocation] = []
                for entry in occurrences:
                    base_locations.extend(entry.code_locations or [])
                    if entry.lines:
                        values, locations = _parse_code_lines(file_path, entry.lines)
                        codes.extend(values)
                        parsed_locations.extend(locations)
                    elif isinstance(entry.value, list):
                        codes.extend(entry.value)
                    else:
                        codes.append(entry.value)
                if codes:
                    item.extra_fields[field_name] = codes
                seen = {(loc.file, loc.line, loc.column) for loc in base_locations}
                locations_out = list(base_locations)
                for loc in parsed_locations:
                    key = (loc.file, loc.line, loc.column)
                    if key not in seen:
                        seen.add(key)
                        locations_out.append(loc)
                if locations_out:
                    item.code_locations[field_name] = locations_out
                continue

            chain_location = item.location or SourceLocation(file_path, 1, 1)
            chains: List[Any] = []
            for entry in occurrences:
                if entry.lines and not isinstance(entry.value, ChainNode):
                    chain_node = _parse_chain_lines(file_path, entry.lines, chain_location)
                    chains.append(chain_node if chain_node.nodes else entry.value)
                else:
                    chains.append(entry.value)
            item.extra_fields[field_name] = chains[0] if len(chains) == 1 else chains

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
            # TEXT_LINE tem prioridade sobre CODE_ELEMENT no lexer contextual, então
            # "CREATOR, EARTH, HEAVENS" chega como string única. Fazemos o split aqui.
            if "," in value:
                return [part.strip() for part in value.split(",") if part.strip()]
            return [value]
        return []

    def _get_item_field_value(self, item: ItemNode, name: str) -> Any:
        return item_field_value(item, name)

    def _check_duplicate_source_bibrefs(self) -> None:
        """Erro 70: mesma bibref declarada em mais de um bloco SOURCE."""
        seen: Dict[str, SourceNode] = {}
        for source in self.sources:
            key = normalize_bibref(source.bibref)
            if key in seen:
                location = source.location or SourceLocation(Path("<unknown>"), 1, 1)
                self.validation_result.add(
                    DuplicateSourceBibref(
                        location=location,
                        bibref=key,
                        filename=str(location.file),
                    )
                )
            else:
                seen[key] = source

    def _check_duplicate_ontology_concepts(self) -> None:
        """Erro 68: mesmo conceito definido em dois arquivos de ontologia distintos."""
        seen: Dict[str, OntologyNode] = {}
        for ontology in self.ontologies:
            key = normalize_code(ontology.concept, self.norm_cache)
            if key in seen:
                location = ontology.location or SourceLocation(Path("<unknown>"), 1, 1)
                file_a = str(seen[key].location.file) if seen[key].location else "<unknown>"
                file_b = str(location.file)
                first = seen[key].concept
                # Nomes que so coincidem pela forma Unicode (NFC): o leitor ve dois
                # nomes "iguais" e diferentes ao mesmo tempo; a mensagem explica.
                if " ".join(first.split()).lower() != " ".join(ontology.concept.split()).lower():
                    self.validation_result.add(
                        IdentityCollision(
                            location=location,
                            first_name=first,
                            second_name=ontology.concept,
                            first_file=file_a,
                        )
                    )
                    continue
                self.validation_result.add(
                    DuplicateOntologyConcept(
                        location=location,
                        concept_name=ontology.concept,
                        file_a=file_a,
                        file_b=file_b,
                    )
                )
            else:
                seen[key] = ontology

    def _check_duplicate_ontology_descriptions(self) -> None:
        """Erro 71 (AVISO): dois conceitos distintos com descrição idêntica."""
        seen: Dict[str, OntologyNode] = {}
        for ontology in self.ontologies:
            desc = ontology.description
            if not desc or not desc.strip():
                continue
            key = desc.strip().lower()
            if key in seen:
                location = ontology.location or SourceLocation(Path("<unknown>"), 1, 1)
                self.validation_result.add(
                    DuplicateOntologyDescription(
                        location=location,
                        concept_a=seen[key].concept,
                        concept_b=ontology.concept,
                    )
                )
            else:
                seen[key] = ontology

    def _default_project(self) -> ProjectNode:
        return ProjectNode(
            name="",
            template_path=Path(""),
            includes=[],
            metadata={},
            description=None,
            location=SourceLocation(Path("<unknown>"), 1, 1),
        )
