"""
hierarchy.py - Hierarquia adotada pelo projeto (papeis HIERARCHY) e rotulos

Proposito:
    A partir dos campos com papel HIERARCHY KIND/PART/INSTANCE dos blocos
    ONTOLOGY (ja interpretados pelo tipo), montar as relacoes por especie, o
    indice inverso pai -> filhos e a fundamentacao pelos descendentes; e
    conferir a coerencia da hierarquia e dos rotulos (Spec ROLE/EXPORT v7,
    §5.2 e §6).

Componentes principais:
    - Hierarchy.build: relacoes, indice inverso e diagnosticos de estrutura
    - Hierarchy.descendants: fechamento sob demanda, memoizado
    - grounding: conceitos sem mencao propria nem descendente mencionado
    - label_errors: diagnosticos de LABEL

Notas:
    As tres especies sao hierarquia para todo consumidor (broader = uniao).
    Uma relacao de CHAIN nunca entra aqui: a hierarquia adotada mora no .syno.
    O fechamento transitivo e calculado sob demanda (adjacencia + memo), para
    nao materializar pares num corpus de milhares de conceitos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

from synesis.ast.nodes import OntologyNode, SourceLocation, TemplateNode
from synesis.ast.normalize import normalize_code
from synesis.semantic.roles import HIERARCHY_SPECIES, fields_with_family

SPECIES_ORDER = ("KIND", "PART", "INSTANCE")


def _as_list(value) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    return [str(value)] if str(value).strip() else []


@dataclass
class Hierarchy:
    """Relacoes adotadas, por identidade de conceito (normalize_code)."""

    relations: Dict[str, List[Tuple[str, str]]] = field(default_factory=dict)  # especie -> [(filho, pai)]
    parents: Dict[str, Set[str]] = field(default_factory=dict)  # filho -> pais (uniao das especies)
    children: Dict[str, Set[str]] = field(default_factory=dict)  # pai -> filhos (indice inverso)
    names: Dict[str, str] = field(default_factory=dict)  # identidade -> nome do bloco
    errors: list = field(default_factory=list)
    _desc_memo: Dict[str, Set[str]] = field(default_factory=dict, repr=False)

    @classmethod
    def build(cls, ontology_index: Dict[str, OntologyNode], template: Optional[TemplateNode],
              aliases=None) -> "Hierarchy":
        """Relacoes sobre identidades RESOLVIDAS (etapa U): um pai preterido vale como o alvo."""
        from synesis.ast.results import (
            CyclicHierarchy,
            DuplicateHierarchySpecies,
            HierarchyCollapsedByUse,
            SelfReference,
        )

        resolve = aliases.resolve if aliases else (lambda k: k)

        h = cls(relations={s: [] for s in SPECIES_ORDER})
        specs = fields_with_family(template, "HIERARCHY")
        species_of = {s.name: HIERARCHY_SPECIES[s.role] for s in specs if s.role in HIERARCHY_SPECIES}
        if not species_of:
            return h
        seen_pair: Dict[Tuple[str, str], str] = {}
        for key, node in ontology_index.items():
            h.names[key] = node.concept
            if aliases and aliases.is_alias(key):
                continue  # o preterido nao tem posicao propria
            loc = node.location or SourceLocation(Path("<ontology>"), 1, 1)
            for fname, species in species_of.items():
                for parent in _as_list(node.fields.get(fname)):
                    written = normalize_code(parent)
                    pkey = resolve(written)
                    if pkey == key:
                        if written != key:
                            h.errors.append(HierarchyCollapsedByUse(
                                location=loc, concept=node.concept, field_name=fname, parent=parent,
                            ))
                        else:
                            h.errors.append(SelfReference(location=loc, concept=node.concept, field_name=fname))
                        continue
                    pair = (key, pkey)
                    if pair in seen_pair and seen_pair[pair] != species:
                        h.errors.append(DuplicateHierarchySpecies(
                            location=loc, child=node.concept, parent=parent,
                            first_species=seen_pair[pair], second_species=species,
                        ))
                        continue
                    if pair in seen_pair:
                        continue
                    seen_pair[pair] = species
                    h.relations[species].append(pair)
                    h.parents.setdefault(key, set()).add(pkey)
                    h.children.setdefault(pkey, set()).add(key)
        for species in SPECIES_ORDER:
            h.relations[species].sort()
        for cycle in h._cycles():
            first = cycle[0]
            cycle_node = ontology_index.get(first)
            loc = (cycle_node.location if cycle_node else None) or SourceLocation(Path("<ontology>"), 1, 1)
            path = [h.names.get(c, c) for c in cycle] + [h.names.get(first, first)]
            h.errors.append(CyclicHierarchy(location=loc, path=path))
        return h

    @property
    def is_empty(self) -> bool:
        return not any(self.relations.values())

    def _cycles(self) -> List[List[str]]:
        """Um ciclo por componente com ciclo (DFS iterativa, determinista)."""
        WHITE, GRAY, BLACK = 0, 1, 2
        color: Dict[str, int] = {}
        found: List[List[str]] = []
        for start in sorted(self.parents):
            if color.get(start, WHITE) != WHITE:
                continue
            stack: List[Tuple[str, List[str]]] = [(start, sorted(self.parents.get(start, ())))]
            path = [start]
            color[start] = GRAY
            while stack:
                node, pending = stack[-1]
                if not pending:
                    color[node] = BLACK
                    stack.pop()
                    path.pop()
                    continue
                nxt = pending.pop(0)
                state = color.get(nxt, WHITE)
                if state == GRAY:
                    found.append(path[path.index(nxt):])
                elif state == WHITE:
                    color[nxt] = GRAY
                    path.append(nxt)
                    stack.append((nxt, sorted(self.parents.get(nxt, ()))))
        return found

    def descendants(self, key: str) -> Set[str]:
        """Todos os descendentes (uniao das especies), sem o proprio conceito."""
        if key in self._desc_memo:
            return self._desc_memo[key]
        out: Set[str] = set()
        frontier = list(self.children.get(key, ()))
        while frontier:
            child = frontier.pop()
            if child in out or child == key:
                continue
            out.add(child)
            frontier.extend(self.children.get(child, ()))
        self._desc_memo[key] = out
        return out

    def tops(self, keys: Iterable[str]) -> List[str]:
        return sorted(k for k in keys if not self.parents.get(k))

    def max_kind_depth(self) -> int:
        kind_parents: Dict[str, Set[str]] = {}
        for child, parent in self.relations.get("KIND", []):
            kind_parents.setdefault(child, set()).add(parent)
        memo: Dict[str, int] = {}

        def depth(k: str, trail: frozenset) -> int:
            if k in memo:
                return memo[k]
            ps = [p for p in kind_parents.get(k, ()) if p not in trail]
            d = 0 if not ps else 1 + max(depth(p, trail | {k}) for p in ps)
            memo[k] = d
            return d

        return max((depth(k, frozenset()) for k in kind_parents), default=0)


def grounding(
    hierarchy: Hierarchy, ontology_index: Dict[str, OntologyNode], mentioned: Set[str]
) -> Dict[str, bool]:
    """Conceito fundamentado: mencionado (CODE ou CHAIN) ou com descendente mencionado."""
    return {
        key: key in mentioned or bool(hierarchy.descendants(key) & mentioned)
        for key in ontology_index
    }


def label_errors(ontology_index: Dict[str, OntologyNode], template: Optional[TemplateNode]) -> list:
    """MultiplePreferredLabels, LabelSpeciesOverlap, AmbiguousLabel, LabelConflictsWithConcept."""
    from synesis.ast.results import (
        AmbiguousLabel,
        LabelConflictsWithConcept,
        LabelSpeciesOverlap,
        MultiplePreferredLabels,
    )

    specs = fields_with_family(template, "LABEL")
    if not specs:
        return []
    errors: list = []
    owner: Dict[str, str] = {}  # termo -> conceito
    for key, node in ontology_index.items():
        loc = node.location or SourceLocation(Path("<ontology>"), 1, 1)
        per_concept: Dict[str, str] = {}  # termo -> especie
        for spec in specs:
            terms = _as_list(node.fields.get(spec.name))
            if spec.role == "LABEL PREFERRED" and len(terms) > 1:
                errors.append(MultiplePreferredLabels(location=loc, concept=node.concept, terms=terms))
            role = spec.role or ""
            for term in terms:
                tkey = normalize_code(term)
                if tkey in per_concept and per_concept[tkey] != role:
                    errors.append(LabelSpeciesOverlap(
                        location=loc, concept=node.concept, term=term,
                        first_role=per_concept[tkey], second_role=role,
                    ))
                    continue
                per_concept[tkey] = role
                if tkey != key and tkey in ontology_index and spec.role != "LABEL PREFERRED":
                    errors.append(LabelConflictsWithConcept(
                        location=loc, concept=node.concept, term=term,
                        other=ontology_index[tkey].concept,
                    ))
                    continue
                if tkey in owner and owner[tkey] != node.concept:
                    errors.append(AmbiguousLabel(
                        location=loc, term=term, concept=node.concept, other=owner[tkey],
                    ))
                else:
                    owner.setdefault(tkey, node.concept)
    return errors


def structural_profile(linked, template: Optional[TemplateNode], validation_result=None) -> List[str]:
    """Perfil estrutural (Spec §7): o que foi declarado, sobre os dados efetivos.

    Conta os conceitos que valem: um bloco preterido (USE, etapa U) nao e
    conceito. Os niveis sao classificacao do produto, nao criterio normativo,
    e nunca bloqueiam compilacao nem exportacao.
    """
    from synesis.semantic.roles import fields_with_family, fields_with_role

    aliases = getattr(linked, "aliases", None) or {}
    index = {k: v for k, v in linked.ontology_index.items() if k not in aliases}
    total = len(index)
    hierarchy = getattr(linked, "role_hierarchy", None)
    lines = [f"Concepts: {total}"]

    def used(field_names: List[str]) -> int:
        return sum(1 for n in index.values() if any(n.fields.get(f) for f in field_names))

    definition = [s.name for s in fields_with_role(template, "NOTE DEFINITION")]
    if definition:
        n = used(definition)
        lines.append(f"With definition: {n} ({(100 * n // total) if total else 0}%)")
    for spec in fields_with_family(template, "NOTE") + fields_with_family(template, "LABEL"):
        if spec.role != "NOTE DEFINITION":
            lines.append(f"{ROLE_PROFILE_LABELS.get(spec.role or '', spec.role)}: {used([spec.name])}")

    species_used = set()
    if hierarchy is not None and not hierarchy.is_empty:
        for species in SPECIES_ORDER:
            children = {c for c, _p in hierarchy.relations.get(species, [])}
            if children:
                species_used.add(species)
                lines.append(f"With {species} parent: {len(children)}")
        cyclic = any(e.CODE == "SYNESIS_E118" for e in hierarchy.errors)
        lines.append("Cycles: FOUND" if cyclic else "Cycles: none ✓")
        lines.append(f"Top concepts: {len(hierarchy.tops(index))}")
        lines.append(f"Max KIND depth: {hierarchy.max_kind_depth()}")
        warnings = getattr(validation_result, "warnings", None) or []
        ungrounded = sum(1 for w in warnings if getattr(w, "CODE", "") == "SYNESIS_E120")
        if ungrounded:
            lines.append(f"Ungrounded: {ungrounded}")

    # A linha diz de quem e o perfil: o modelo organizador (.syno). Os artefatos
    # (EXPORT SKOS) podem ter outro perfil, porque MAP RELATIONS acrescenta
    # relacoes das cadeias; a CLI os lista abaixo, um por bloco.
    if total == 0:
        lines.append("Organizing model: none (no ONTOLOGY blocks)")
    else:
        alternative = [s.name for s in fields_with_role(template, "LABEL ALTERNATIVE")]
        terminological = "With synonyms" if alternative and used(alternative) else "Controlled vocabulary"
        undeclared = len(used_concept_keys(linked) - set(linked.ontology_index))
        if undeclared:
            terminological += f" ({undeclared} code{'s' if undeclared != 1 else ''} without concept)"
        lines.append(f"Organizing model: Terminological: {terminological}  |  "
                     f"Conceptual: {conceptual_level(species_used)}")
    lines.append(PROFILE_NOTE)
    return lines


def used_concept_keys(linked) -> Set[str]:
    """Conceitos citados nas anotacoes (CODE e CHAIN), pela identidade resolvida (USE)."""
    aliases = getattr(linked, "aliases", None) or {}
    used = {aliases.get(k, k) for k in linked.code_usage}
    for a, _rel, b in linked.all_triples:
        for name in (a, b):
            key = normalize_code(name)
            used.add(aliases.get(key, key))
    return used


# Rótulos do perfil por papel (saída do compilador em inglês).
ROLE_PROFILE_LABELS = {
    "LABEL PREFERRED": "Preferred labels",
    "LABEL ALTERNATIVE": "Alternative labels",
    "LABEL HIDDEN": "Hidden labels",
    "NOTE USAGE": "Usage notes",
    "NOTE EXAMPLE": "Examples",
    "NOTE COUNTEREXAMPLE": "Counterexamples",
}

PROFILE_NOTE = (
    "Note: Describes declared structure only; does not verify semantic validity "
    "of relations. This is a descriptive profile, not a maturity score."
)


def conceptual_level(species_used) -> str:
    """Nível conceitual pelas espécies de hierarquia em uso (perfil e SKOS)."""
    species = set(species_used)
    if "KIND" in species and species & {"PART", "INSTANCE"}:
        # Mais de uma espécie de hierarquia. "Ontology" fica reservado para uma
        # exportação OWL: SKOS é um sistema de organização do conhecimento
        # (KOS), não uma ontologia formal (decisão de 2026-11-17).
        return "Multi-relation taxonomy"
    if "KIND" in species:
        return "Taxonomy"
    if species == {"PART"}:
        return "Partitive hierarchy"
    if species == {"INSTANCE"}:
        return "Instantial hierarchy"
    if species == {"PART", "INSTANCE"}:
        return "Partitive and instantial hierarchy"
    return "Flat list"

