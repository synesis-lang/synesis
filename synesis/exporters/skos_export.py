"""
skos_export.py - Exportacao SKOS (Turtle) do principio organizador

Proposito:
    Etapa A3 do plano ROLE/EXPORT (Spec v7, §10): gerar um arquivo SKOS a
    partir dos PAPEIS do template (LABEL, NOTE, HIERARCHY), dos tipos de
    agrupamento (TOPIC -> skos:Collection; ENUMERATED/ORDERED -> esquemas) e,
    so neste artefato, das relacoes da CHAIN lidas por `MAP RELATIONS`.

Componentes principais:
    - build_skos: monta o grafo e o texto Turtle, sem I/O nem relogio
    - export_skos: grava o arquivo quando nao ha erro
    - SkosResult: texto, contagens, diagnosticos e relatorio

Notas:
    - Visao canonica x visao de artefato: a hierarquia do .syno entra inteira;
      os pares mapeados da CHAIN entram depois, e o .syno prevalece (inclusive
      na especie). O que cai vai para o relatorio, nunca para erro.
    - MIN_SOURCES mede recorrencia (fontes distintas que afirmam o par), nao
      validade: varias fontes podem repetir uma afirmacao contextual ou errada.
    - Determinismo: recursos ordenados por IRI, propriedades numa ordem fixa,
      valores ordenados; sem GENERATED_AT, a saida nao tem data. Mesma entrada,
      mesmos bytes.
    - Escrita direta de Turtle, sem dependencia de execucao nova.
"""

from __future__ import annotations

import os
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from synesis.ast.nodes import ChainNode, ExportNode, FieldType, Scope, TemplateNode
from synesis.ast.normalize import normalize_code

PREFIXES: List[Tuple[str, str]] = [
    ("rdf", "http://www.w3.org/1999/02/22-rdf-syntax-ns#"),
    ("rdfs", "http://www.w3.org/2000/01/rdf-schema#"),
    ("owl", "http://www.w3.org/2002/07/owl#"),
    ("xsd", "http://www.w3.org/2001/XMLSchema#"),
    ("skos", "http://www.w3.org/2004/02/skos/core#"),
    ("dcterms", "http://purl.org/dc/terms/"),
    ("iso-thes", "http://purl.org/iso25964/skos-thes#"),
    ("syn", "https://synesis-lang.org/ns/syn#"),
]

SPECIES = ("KIND", "PART", "INSTANCE")
SPECIES_OF_TARGET = {"HIERARCHY KIND": "KIND", "HIERARCHY PART": "PART", "HIERARCHY INSTANCE": "INSTANCE"}
ISO_PROPS = {
    "KIND": ("iso-thes:broaderGeneric", "iso-thes:narrowerGeneric"),
    "PART": ("iso-thes:broaderPartitive", "iso-thes:narrowerPartitive"),
    "INSTANCE": ("iso-thes:broaderInstantial", "iso-thes:narrowerInstantial"),
}
NOTE_PROPS = {
    "NOTE DEFINITION": "skos:definition",
    "NOTE USAGE": "skos:scopeNote",
    "NOTE EXAMPLE": "skos:example",
    "NOTE COUNTEREXAMPLE": "syn:counterExample",
}

# Ordem das propriedades dentro de um recurso (Spec §10.4).
_ORDER = [
    "a", "skos:inScheme", "skos:topConceptOf", "dcterms:title", "dcterms:description",
    "dcterms:modified", "skos:hasTopConcept", "skos:prefLabel", "skos:altLabel",
    "skos:hiddenLabel", "rdfs:label", "skos:notation", "skos:definition", "skos:scopeNote",
    "skos:example", "skos:broader", "iso-thes:broaderGeneric", "iso-thes:broaderPartitive",
    "iso-thes:broaderInstantial", "skos:narrower", "iso-thes:narrowerGeneric",
    "iso-thes:narrowerPartitive", "iso-thes:narrowerInstantial", "skos:related",
    "skos:member", "syn:counterExample", "rdfs:subPropertyOf", "owl:deprecated",
    "dcterms:isReplacedBy",
]
_RANK = {p: i for i, p in enumerate(_ORDER)}

# Motivos de queda de um par mapeado (relatorio).
REASONS = {
    "support": "support below MIN_SOURCES",
    "no_block": "concept without block",
    "self": "links a concept to itself",
    "declared": "already declared in the .syno (same species)",
    "species": "the .syno declares the pair with another species",
    "inverse": "inverts a pair already present",
    "cycle": "would form a cycle",
    "same_line": "concepts in the same hierarchical line",
    "collapsed": "collapses after USE (both names are the same concept)",
}

# Rotulos curtos da coluna DROPPED da tabela do terminal (o JSON do relatorio
# mantem os textos longos de REASONS).
SHORT_REASONS = {
    "support": "below MIN_SOURCES",
    "no_block": "no block",
    "self": "self-link",
    "declared": "already in .syno",
    "species": "other species in .syno",
    "inverse": "inverse pair",
    "cycle": "would cycle",
    "same_line": "same hierarchy",
    "collapsed": "collapses after USE",
}


def enc(text: str) -> str:
    """Trecho de IRI: NFC, com codificacao percentual so do que a RFC 3987 nao permite."""
    out = []
    for ch in unicodedata.normalize("NFC", text):
        if ch.isalnum() or ch in "-._~" or ord(ch) > 127:
            out.append(ch)
        else:
            out.extend(f"%{b:02X}" for b in ch.encode("utf-8"))
    return "".join(out)


def literal(text: str, lang: Optional[str] = None, datatype: Optional[str] = None) -> str:
    esc = (
        str(text).replace("\\", "\\\\").replace('"', '\\"')
        .replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    )
    if datatype:
        return f'"{esc}"^^{datatype}'
    return f'"{esc}"@{lang}' if lang else f'"{esc}"'


def iri(value: str) -> str:
    return f"<{value}>"


@dataclass
class MapStats:
    relation: str
    target: str
    found: int = 0
    supported: int = 0
    accepted: int = 0
    dropped: Counter = field(default_factory=Counter)


@dataclass
class SkosResult:
    text: Optional[str]
    triple_count: int
    errors: list
    warnings: list
    report: Dict[str, Any]


class _Graph:
    def __init__(self) -> None:
        self.subjects: Dict[str, Dict[str, Set[str]]] = {}
        self.count = 0

    def add(self, s: str, p: str, o: str) -> None:
        objs = self.subjects.setdefault(s, {}).setdefault(p, set())
        if o not in objs:
            objs.add(o)
            self.count += 1

    def serialize(self) -> str:
        lines = [f"@prefix {name}: <{ns}> ." for name, ns in PREFIXES]
        for subject in sorted(self.subjects):
            props = self.subjects[subject]
            ordered = sorted(props, key=lambda p: (_RANK.get(p, len(_RANK)), p))
            body = []
            for p in ordered:
                values = " , ".join(sorted(props[p]))
                body.append(f"    {p} {values}")
            lines.append("")
            lines.append(f"{iri(subject)}\n" + " ;\n".join(body) + " .")
        return "\n".join(lines) + "\n"


def _as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    return [str(value)] if str(value).strip() else []


def _specs(template: TemplateNode, scope: Scope) -> List[Any]:
    return [s for s in template.field_specs.values() if s.scope == scope]


def build_skos(linked: Any, template: TemplateNode, export: ExportNode,
               published: Optional[Set[str]] = None) -> SkosResult:
    """Grafo SKOS do projeto; funcao pura (sem I/O, sem relogio).

    `published`: IRIs do REGISTRY (C7). Um preterido (USE) cujo IRI foi
    publicado sai como conceito obsoleto, com isReplacedBy; os demais
    preteridos viram so rotulo do alvo (Spec_USE_Etapa_U.md, §4).
    """
    from synesis.ast.results import (
        AliasLabelCollision,
        DerivedLabelConflict,
        DerivedLabelOverlap,
        IriCollision,
        PublishedIriWithoutBlock,
        TopicCaseVariant,
    )
    from synesis.semantic.occurrences import item_field_value
    from synesis.semantic.project_blocks import chain_relations

    block = export.label
    loc = export.location
    N = export.prop("NAMESPACE") or ""
    L = export.prop("LANGUAGE") or ""
    min_sources = int(export.prop("MIN_SOURCES") or 1)
    generated_at = export.prop("GENERATED_AT")
    g = _Graph()
    errors: list = []
    warnings: list = []
    full_index = linked.ontology_index
    aliases: Dict[str, str] = dict(getattr(linked, "aliases", None) or {})
    # Os preteridos nao sao conceitos: tudo abaixo trabalha sobre os que valem.
    index = {k: v for k, v in full_index.items() if k not in aliases}
    published = set(published or ())
    alias_kind = (export.prop("ALIAS_LABEL") or "HIDDEN").strip().upper()
    ont_specs = _specs(template, Scope.ONTOLOGY)
    by_role: Dict[str, List[str]] = {}
    for spec in ont_specs:
        if spec.role:
            by_role.setdefault(spec.role, []).append(spec.name)

    # ------------------------------------------------------------- conceitos
    concept_iri: Dict[str, str] = {}
    seen_iri: Dict[str, str] = {}
    for key, node in index.items():
        c_iri = N + "concept/" + enc(node.concept)
        if c_iri in seen_iri:
            errors.append(IriCollision(location=loc, block=block, iri=c_iri))
        seen_iri[c_iri] = key
        concept_iri[key] = c_iri

    pref: Dict[str, str] = {}
    derived: Set[str] = set()
    alt: Dict[str, List[str]] = {}
    hidden: Dict[str, List[str]] = {}
    for key, node in index.items():
        explicit = [t for f in by_role.get("LABEL PREFERRED", []) for t in _as_list(node.fields.get(f))]
        if explicit:
            pref[key] = explicit[0]
        else:
            pref[key] = node.concept.replace("_", " ")
            derived.add(key)
        alt[key] = [t for f in by_role.get("LABEL ALTERNATIVE", []) for t in _as_list(node.fields.get(f))]
        hidden[key] = [t for f in by_role.get("LABEL HIDDEN", []) for t in _as_list(node.fields.get(f))]

    # Nome preterido -> rotulo do alvo (ALIAS_LABEL), sem repetir rotulo do alvo.
    deprecated: Dict[str, str] = {}
    alias_labels = 0
    for akey, tkey in sorted(aliases.items()):
        if tkey not in index:
            continue
        name = full_index[akey].concept
        label = name.replace("_", " ")
        taken = {normalize_code(t) for t in [pref[tkey]] + alt[tkey] + hidden[tkey]}
        if normalize_code(label) in taken:
            warnings.append(AliasLabelCollision(location=loc, block=block, alias=name,
                                                target=index[tkey].concept))
        else:
            (alt if alias_kind == "ALTERNATIVE" else hidden)[tkey].append(label)
            alias_labels += 1
        a_iri = N + "concept/" + enc(name)
        if a_iri in published:
            deprecated[akey] = a_iri

    owners: Dict[str, Set[str]] = {}
    for key in index:
        for term in [pref[key]] + alt[key] + hidden[key]:
            owners.setdefault(normalize_code(term), set()).add(key)
    for key in sorted(derived):
        ident = normalize_code(pref[key])
        if ident in {normalize_code(t) for t in alt[key] + hidden[key]}:
            errors.append(DerivedLabelOverlap(location=loc, block=block, concept=index[key].concept, label=pref[key]))
        others = owners.get(ident, set()) - {key}
        if others:
            other = index[sorted(others)[0]].concept
            errors.append(DerivedLabelConflict(
                location=loc, block=block, concept=index[key].concept, label=pref[key], other=other,
            ))

    for key, node in index.items():
        c = concept_iri[key]
        g.add(c, "a", "skos:Concept")
        g.add(c, "skos:inScheme", iri(N))
        g.add(c, "skos:prefLabel", literal(pref[key], L))
        for t in alt[key]:
            g.add(c, "skos:altLabel", literal(t, L))
        for t in hidden[key]:
            g.add(c, "skos:hiddenLabel", literal(t, L))
        for role_name, prop in NOTE_PROPS.items():
            for fname in by_role.get(role_name, []):
                for text in _as_list(node.fields.get(fname)):
                    g.add(c, prop, literal(text, L))

    for akey, a_iri in sorted(deprecated.items()):
        # IRI publicado nao some (C7): conceito obsoleto que aponta o alvo.
        g.add(a_iri, "a", "skos:Concept")
        g.add(a_iri, "skos:inScheme", iri(N))
        g.add(a_iri, "skos:prefLabel", literal(full_index[akey].concept.replace("_", " "), L))
        g.add(a_iri, "owl:deprecated", literal("true", datatype="xsd:boolean"))
        g.add(a_iri, "dcterms:isReplacedBy", iri(concept_iri[aliases[akey]]))
    emitted = set(concept_iri.values()) | set(deprecated.values())
    outside: List[str] = []
    for p_iri in sorted(published):
        if not p_iri.startswith(N):
            outside.append(p_iri)
        elif p_iri.startswith(N + "concept/") and p_iri not in emitted:
            warnings.append(PublishedIriWithoutBlock(location=loc, block=block, iri=p_iri))
    if outside:
        # O NAMESPACE e decisao do pesquisador: mudar de namespace NAO bloqueia
        # a exportacao nem a publicacao (decisao de 2026-11-17). Os IRIs antigos
        # ficam fora da conferencia — o aviso diz quantos e quais.
        from synesis.ast.results import RegistryOutsideNamespace

        warnings.append(RegistryOutsideNamespace(location=loc, block=block, namespace=N,
                                                 count=len(outside), examples=tuple(outside[:3])))

    # ----------------------------------------------- hierarquia (visao canonica)
    parents: Dict[str, Set[str]] = {}
    species_of: Dict[Tuple[str, str], str] = {}
    canonical: Dict[str, int] = {s: 0 for s in SPECIES}
    hierarchy = getattr(linked, "role_hierarchy", None)
    if hierarchy is not None:
        for species, pairs in hierarchy.relations.items():
            for child, parent in pairs:
                if child in index and parent in index:
                    species_of[(child, parent)] = species
                    parents.setdefault(child, set()).add(parent)
                    canonical[species] += 1

    def ancestors(k: str) -> Set[str]:
        out: Set[str] = set()
        stack = list(parents.get(k, ()))
        while stack:
            x = stack.pop()
            if x not in out:
                out.add(x)
                stack.extend(parents.get(x, ()))
        return out

    # --------------------------------------------- relacoes mapeadas da CHAIN
    known = chain_relations(template)
    item_specs = {s.name: s for s in _specs(template, Scope.ITEM) if s.type == FieldType.CHAIN}
    mapped_species: Dict[str, int] = {s: 0 for s in SPECIES}
    related: Set[Tuple[str, str]] = set()
    stats: List[MapStats] = []
    hier_candidates: List[Tuple[int, str, str, str, MapStats]] = []
    rel_candidates: List[Tuple[int, str, str, MapStats]] = []
    for node in export.maps:
        if node.kind != "relations":
            continue
        for relation in node.names:
            st = MapStats(relation=relation, target=node.target)
            stats.append(st)
            fields = [node.from_field] if node.from_field else known.get(relation, [])
            support: Dict[Tuple[str, str], Set[str]] = {}
            collapsed: Set[Tuple[str, str]] = set()
            for source in linked.sources.values():
                for item in source.items:
                    for fname in fields:
                        spec = item_specs.get(fname)
                        if spec is None:
                            continue
                        raw = item_field_value(item, fname)
                        for chain in raw if isinstance(raw, list) else [raw]:
                            if not isinstance(chain, ChainNode):
                                continue
                            for a, r, b in chain.to_triples(has_relations=bool(spec.relations)):
                                if r != relation:
                                    continue
                                written = (normalize_code(a), normalize_code(b))
                                # Projecao resolvida: o preterido vale como o alvo.
                                pair = (aliases.get(written[0], written[0]), aliases.get(written[1], written[1]))
                                if pair[0] == pair[1] and written[0] != written[1]:
                                    collapsed.add(written)
                                    continue
                                support.setdefault(pair, set()).add(item.bibref.lstrip("@").lower())
            st.found = len(support) + len(collapsed)
            if collapsed:
                st.dropped["collapsed"] += len(collapsed)
            for (a, b), refs in sorted(support.items()):
                if len(refs) < min_sources:
                    st.dropped["support"] += 1
                    continue
                st.supported += 1
                if node.target in SPECIES_OF_TARGET:
                    hier_candidates.append((-len(refs), a, b, SPECIES_OF_TARGET[node.target], st))
                else:
                    rel_candidates.append((-len(refs), a, b, st))

    for _neg, a, b, species, st in sorted(hier_candidates, key=lambda x: x[:4]):
        if a not in index or b not in index:
            st.dropped["no_block"] += 1
        elif a == b:
            st.dropped["self"] += 1
        elif (a, b) in species_of:
            st.dropped["declared" if species_of[(a, b)] == species else "species"] += 1
        elif (b, a) in species_of:
            st.dropped["inverse"] += 1
        elif a in ancestors(b):
            st.dropped["cycle"] += 1
        else:
            species_of[(a, b)] = species
            parents.setdefault(a, set()).add(b)
            mapped_species[species] += 1
            st.accepted += 1

    for _neg, a, b, st in sorted(rel_candidates, key=lambda x: x[:3]):
        if a not in index or b not in index:
            st.dropped["no_block"] += 1
        elif a == b:
            st.dropped["self"] += 1
        elif a in ancestors(b) or b in ancestors(a):
            st.dropped["same_line"] += 1
        else:
            if (a, b) not in related and (b, a) not in related:
                related.add((a, b))
            st.accepted += 1

    for (child, parent), species in species_of.items():
        c, p = concept_iri[child], concept_iri[parent]
        broader, narrower = ISO_PROPS[species]
        g.add(c, "skos:broader", iri(p))
        g.add(c, broader, iri(p))
        g.add(p, "skos:narrower", iri(c))
        g.add(p, narrower, iri(c))
    for a, b in related:
        g.add(concept_iri[a], "skos:related", iri(concept_iri[b]))
        g.add(concept_iri[b], "skos:related", iri(concept_iri[a]))

    tops = sorted(k for k in index if not parents.get(k))
    for key in tops:
        g.add(concept_iri[key], "skos:topConceptOf", iri(N))
        g.add(N, "skos:hasTopConcept", iri(concept_iri[key]))

    # ------------------------------------------------ esquema do projeto
    # prefLabel com idioma, alem do dcterms:title: sem ele o esquema aparece
    # como "recurso sem rotulo" no VocBench/ICV (validacao de 2026-11-17).
    # Nome editorial: `title` do METADATA quando existe; senao, o do PROJECT.
    metadata = getattr(linked.project, "metadata", None) or {}
    scheme_name = str(metadata.get("title") or "").strip() or linked.project.name
    g.add(N, "a", "skos:ConceptScheme")
    g.add(N, "dcterms:title", literal(scheme_name))
    g.add(N, "skos:prefLabel", literal(scheme_name, L))
    description = getattr(linked.project, "description", None)
    if description:
        g.add(N, "dcterms:description", literal(description, L))
    if generated_at:
        g.add(N, "dcterms:modified", literal(generated_at, datatype="xsd:dateTime"))

    # ---------------------------------------------- TOPIC -> skos:Collection
    collections = 0
    for spec in ont_specs:
        if spec.type != FieldType.TOPIC:
            continue
        groups: Dict[str, Counter] = {}
        members: Dict[str, Set[str]] = {}
        for key, node in index.items():
            for value in _as_list(node.fields.get(spec.name)):
                ident = normalize_code(value)
                groups.setdefault(ident, Counter())[value] += 1
                members.setdefault(ident, set()).add(key)
        for ident in sorted(groups):
            spellings = groups[ident]
            chosen = sorted(spellings.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
            if len(spellings) > 1:
                warnings.append(TopicCaseVariant(
                    location=loc, block=block, field_name=spec.name,
                    spellings=tuple(sorted(spellings)), chosen=chosen,
                ))
            t = N + "collection/" + enc(spec.name) + "/" + enc(ident)
            if t in seen_iri:
                errors.append(IriCollision(location=loc, block=block, iri=t))
            seen_iri[t] = ident
            collections += 1
            g.add(t, "a", "skos:Collection")
            g.add(t, "skos:prefLabel", literal(chosen, L))
            for key in members[ident]:
                g.add(t, "skos:member", iri(concept_iri[key]))

    # ---------------------------------- ENUMERATED / ORDERED -> esquemas
    schemes = 1
    for spec in ont_specs:
        if spec.type not in (FieldType.ENUMERATED, FieldType.ORDERED) or not spec.values:
            continue
        schemes += 1
        v_scheme = N + "vocab/" + enc(spec.name)
        prop = N + "property/" + enc(spec.name)
        g.add(v_scheme, "a", "skos:ConceptScheme")
        g.add(v_scheme, "skos:prefLabel", literal(spec.name, L))
        g.add(prop, "a", "owl:ObjectProperty")
        g.add(prop, "rdfs:subPropertyOf", "syn:classifiedBy")
        g.add(prop, "rdfs:label", literal(spec.name))
        value_iri: Dict[str, str] = {}
        for value in spec.values:
            if spec.type == FieldType.ORDERED:
                v = v_scheme + "/" + str(value.index)
                value_iri[str(value.index)] = v
                value_iri[normalize_code(value.label)] = v
                g.add(v, "skos:notation", literal(str(value.index)))
            else:
                v = v_scheme + "/" + enc(value.label)
                value_iri[normalize_code(value.label)] = v
            g.add(v, "a", "skos:Concept")
            g.add(v, "skos:inScheme", iri(v_scheme))
            # Vocabulario fechado e lista plana: cada valor e topo do seu
            # esquema. A ordem de um ORDERED fica em skos:notation e NAO vira
            # broader — ordenar e subordinar sao relacoes diferentes.
            g.add(v, "skos:topConceptOf", iri(v_scheme))
            g.add(v_scheme, "skos:hasTopConcept", iri(v))
            g.add(v, "skos:prefLabel", literal(value.label, L))
            if value.description:
                g.add(v, "skos:definition", literal(value.description, L))
        for key, node in index.items():
            for raw in _as_list(node.fields.get(spec.name)):
                value_ref = value_iri.get(raw.strip()) or value_iri.get(normalize_code(raw))
                if value_ref:
                    g.add(concept_iri[key], iri(prop), iri(value_ref))

    # ------------------------------------------------------------ relatorio
    exported = {n for names in by_role.values() for n in names}
    not_exported = sorted(
        (s.name, s.type.value) for s in ont_specs
        if s.name not in exported and s.type not in (FieldType.TOPIC, FieldType.ENUMERATED, FieldType.ORDERED)
    )
    from synesis.semantic.hierarchy import conceptual_level

    species_used = {s for s in SPECIES if canonical[s] + mapped_species[s]}
    conceptual = conceptual_level(species_used)
    has_alt = any(alt.values())
    if has_alt and species_used and related:
        terminological = "Thesaurus"
    elif has_alt:
        terminological = "With synonyms"
    else:
        terminological = "Controlled vocabulary"
    report = {
        "concepts": len(index),
        "tops": len(tops),
        "collections": collections,
        "schemes": schemes,
        "canonical": canonical,
        "mapped": mapped_species,
        "related": len(related),
        "maps": [
            {"relation": s.relation, "target": s.target, "found": s.found, "supported": s.supported,
             "accepted": s.accepted, "dropped": {REASONS[k]: v for k, v in sorted(s.dropped.items())},
             "dropped_codes": dict(sorted(s.dropped.items()))}
            for s in stats
        ],
        "derived_labels": len(derived),
        "aliases": len(aliases),
        "alias_labels": alias_labels,
        "deprecated": len(deprecated),
        "concept_iris": sorted(concept_iri.values()),
        "not_exported": not_exported,
        "profile": f"Terminological: {terminological}  |  Conceptual: {conceptual}",
    }
    # ------------------------------------------- verificacao antes de gravar
    from synesis.ast.results import SkosIntegrityViolation, SkosQualityNotice
    from synesis.exporters.skos_check import check_skos, summary_lines

    check = check_skos(g.subjects, L)
    for condition, cases in sorted(check.integrity.items()):
        errors.append(SkosIntegrityViolation(location=loc, block=block, condition=condition,
                                             count=len(cases), examples=tuple(cases[:5])))
    for condition, cases in sorted(check.quality.items()):
        warnings.append(SkosQualityNotice(location=loc, block=block, condition=condition,
                                          count=len(cases), examples=tuple(cases[:5])))
    report["check"] = summary_lines(check)
    report["check_counts"] = {
        "integrity": {k: len(v) for k, v in sorted(check.integrity.items())},
        "quality": {k: len(v) for k, v in sorted(check.quality.items())},
    }

    turtle: Optional[str] = None if errors else g.serialize()
    return SkosResult(text=turtle, triple_count=g.count, errors=errors, warnings=warnings, report=report)


def read_registry(path: Optional[Path]) -> Tuple[Set[str], bool]:
    """(IRIs publicados, registro utilizavel?). Registro ausente = nada publicado."""
    if path is None:
        return set(), True
    if path.is_dir():
        return set(), False
    if not path.exists():
        return set(), True
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return set(), False
    return {line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")}, True


def export_skos(linked: Any, template: TemplateNode, export: ExportNode, path: Path,
                registry: Optional[Path] = None, publish: bool = False) -> SkosResult:
    """Grava o Turtle em `path` quando nao ha erro; devolve o resultado.

    `registry`: arquivo de IRIs publicados (REGISTRY, C7). Com `publish`, os
    IRIs de conceito deste arquivo entram no registro (que so cresce).

    Duas politicas (R5 da avaliacao de 2026-11-17):
      - export local: um IRI registrado sem bloco nem USE e AVISO (E153); o
        arquivo e gravado — serve para trabalhar, nao para publicar;
      - `publish`: o mesmo caso e ERRO. Nem o artefato nem o registro sao
        gravados, porque a publicacao promete que um IRI publicado nunca some.
    """
    from synesis.ast.results import PublishedIriWithoutBlock, RegistryIsOutput, RegistryNotFound

    # OUTPUT e REGISTRY no mesmo arquivo: um sobrescreveria o outro. Recusado
    # antes de ler ou gravar, com e sem --publish (revisao de 2026-11-17, 1.3).
    if registry is not None and _same_file(path, registry):
        return SkosResult(text=None, triple_count=0, warnings=[],
                          errors=[RegistryIsOutput(location=export.location, block=export.label,
                                                   path=str(path))],
                          report={})

    published, usable = read_registry(registry)
    if not usable and registry is not None:
        unusable = RegistryNotFound(location=export.location, block=export.label,
                                    path=str(export.prop("REGISTRY")))
        if publish:
            # Publicar sem conseguir ler o registro tornaria a conferencia de
            # IRIs publicados vazia e silenciosa: erro antes de qualquer escrita.
            return SkosResult(text=None, triple_count=0, warnings=[], errors=[unusable], report={})
    result = build_skos(linked, template, export, published)
    if not usable and registry is not None:
        result.warnings.append(unusable)
    if publish:
        missing = [w for w in result.warnings if isinstance(w, PublishedIriWithoutBlock)]
        if missing:
            result.warnings = [w for w in result.warnings if not isinstance(w, PublishedIriWithoutBlock)]
            result.errors.extend(missing)
            result.text = None
            return result
    if result.text is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(result.text, encoding="utf-8", newline="\n")
        if publish and registry is not None and usable:
            merged = sorted(published | set(result.report.get("concept_iris", [])))
            registry.parent.mkdir(parents=True, exist_ok=True)
            registry.write_text(
                "# Published IRIs (C7): this list only grows; an IRI here never vanishes from the SKOS.\n"
                + "\n".join(merged) + "\n", encoding="utf-8", newline="\n")
            result.report["registered"] = len(merged)
    return result


def _same_file(a: Path, b: Path) -> bool:
    """Os dois caminhos levam ao mesmo arquivo? (grafias equivalentes, links)."""
    try:
        if a.exists() and b.exists():
            return os.path.samefile(a, b)
    except OSError:
        pass
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def _plain(text: str, _role: str) -> str:
    return text


def report_lines(result: SkosResult, path: Path,
                 style: Callable[[str, str], str] = _plain) -> List[str]:
    """Relatorio do terminal (Spec §10.6), em secoes: metricas, mapeamento, validacao.

    `style(texto, papel)` colore um trecho; papeis: `title` (titulo de secao),
    `header` (cabecalho da tabela), `label`, `total`, `ok`, `bad`, `warn`,
    `value`, `dim`. O padrao devolve texto puro (testes, saida redirecionada);
    a CLI passa a paleta do ecossistema. Larguras sao medidas antes do estilo.
    `path` fica por compatibilidade: a linha "Wrote" e da CLI.
    """
    r = result.report
    t = style

    def row(label: str, value: str) -> str:
        return "  " + t(f"{label + ':':<12}", "label") + value

    def total(n: int) -> str:
        return t(f"{n:,}", "total")

    lines = [t("Model metrics:", "title")]
    lines.append(row("Concepts", f"{total(r['concepts'])} ({r['tops']:,} top) | "
                                 f"Collections: {total(r['collections'])} | Schemes: {total(r['schemes'])}"))
    if r["derived_labels"]:
        lines.append(row("Labels", f"{total(r['derived_labels'])} prefLabel derived from the name"))
    if r.get("aliases"):
        lines.append(row("Aliases", f"{total(r['aliases'])} (USE) | name as label of the target: "
                                    f"{r['alias_labels']} | deprecated (published IRI): {r['deprecated']}"))
    mapped_targets = {m["target"].split()[-1] for m in r["maps"]}
    links = []
    for species in SPECIES:
        c, m = r["canonical"][species], r["mapped"][species]
        if c or m or species in mapped_targets or species == "KIND":
            links.append(f"{total(c + m)} {species} ({c} .syno, {m} mapped)" if c + m
                         else t(f"0 {species}", "dim"))
    if r["related"] or "RELATED" in mapped_targets:
        links.append(f"{total(r['related'])} RELATED (mapped)")
    lines.append(row("Links", " | ".join(links)))
    if r.get("registered") is not None:
        lines.append(row("Registry", f"{total(r['registered'])} published IRI(s)"))
    if r["not_exported"]:
        fields = ", ".join(f"{name} ({kind})" for name, kind in r["not_exported"])
        lines.append(row("Not exported", t(fields, "warn")))

    if r["maps"]:
        rows = [("SOURCE", "TARGET", "PAIRS", "SUPPORTED", "ACCEPTED")]
        dropped_cells = ["DROPPED"]
        for m in r["maps"]:
            rows.append((m["relation"], m["target"], f"{m['found']:,}", f"{m['supported']:,}",
                         f"{m['accepted']:,}"))
            codes = m.get("dropped_codes") or {}
            parts = [f"{v} ({SHORT_REASONS.get(k, k)})"
                     for k, v in sorted(codes.items(), key=lambda kv: (-kv[1], kv[0]))]
            dropped_cells.append(t(", ".join(parts), "warn") if parts else t("—", "dim"))
        widths = [max(len(rw[i]) for rw in rows) for i in range(5)]
        lines.append("")
        lines.append(t("Relation mapping (MAP RELATIONS):", "title"))
        for n, rw in enumerate(rows):
            cells = [rw[0].ljust(widths[0]), rw[1].ljust(widths[1])]
            cells += [rw[i].rjust(widths[i]) for i in (2, 3, 4)]
            if n == 0:
                lines.append("  " + t("   ".join(cells) + "   " + dropped_cells[0], "header"))
                continue
            cells[0] = t(cells[0], "value")
            cells[4] = t(cells[4], "ok" if rw[4] != "0" else "dim")
            lines.append("  " + "   ".join(cells) + "   " + dropped_cells[n])

    counts = r.get("check_counts") or {"integrity": {}, "quality": {}}
    lines.append("")
    lines.append(t("SKOS validation and profile:", "title"))
    if counts["integrity"]:
        found = ", ".join(f"{k} {v}" for k, v in counts["integrity"].items())
        lines.append(row("Integrity", t(f"VIOLATIONS — {found} (file not written)", "bad")))
    else:
        lines.append(row("Integrity", t("OK", "ok") + t(" (SKOS S9, S13, S14, S27, S37; "
                                                       "Synesis rule: acyclic broader)", "dim")))
    if counts["quality"]:
        notices = "; ".join(f"{k}: {v}" for k, v in counts["quality"].items())
        lines.append(row("Quality", t(notices, "warn")))
    else:
        lines.append(row("Quality", t("OK", "ok") + t(" (prefLabel, language, scheme, position, top concepts)", "dim")))
    lines.append(row("Profile", t(r["profile"], "value")))
    return lines
