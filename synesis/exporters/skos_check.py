"""
skos_check.py - Verificacao do SKOS gerado, antes de gravar.

Proposito:
    Conferir o grafo que o exportador montou contra as condicoes de
    integridade do SKOS (W3C SKOS Reference) e contra as verificacoes de
    qualidade editorial que ferramentas como o VocBench (ICV) e o qSKOS aplicam.
    Roda sobre o grafo em memoria (`skos_export._Graph`), sem dependencia nova.

Dois niveis, como a propria referencia distingue (§1.8: SKOS nao define
conformidade unica; separa inconsistencia logica de escolha de modelagem):

    INTEGRIDADE (erro: o arquivo nao e gravado)
        S9   recurso ao mesmo tempo skos:Concept e skos:ConceptScheme
        S13  o mesmo literal em prefLabel/altLabel/hiddenLabel do mesmo recurso
        S14  mais de um prefLabel no mesmo idioma no mesmo recurso
        S27  related entre conceitos ligados por broader transitivo
        S37  skos:Collection tambem Concept ou ConceptScheme
        regra do SYNESIS, nao do SKOS: hierarquia sem ciclo (o SKOS admite
        ciclos, §8.6.8; o compilador ja os impede — aqui e defesa)

    QUALIDADE (aviso agregado: o arquivo e gravado)
        recurso (Concept, ConceptScheme, Collection) sem prefLabel
        rotulo sem idioma (quando o EXPORT declara LANGUAGE)
        conceito sem skos:inScheme
        conceito sem pai no seu esquema e sem topConceptOf ("sem posicao")
        esquema sem hasTopConcept

Origem: validacao do `ufg-fraudes` no VocBench (2026-11-17,
synesis-planning/synesis/Validacao_SKOS_VocBench_2026-11-17.md) — SHACL e
condicoes S limpos; o ICV acusou dois grupos editoriais, ambos do exportador.
Passar aqui nao certifica a qualidade conceitual da taxonomia.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple

_LITERAL = re.compile(r'^"(?P<text>(?:[^"\\]|\\.)*)"(?:@(?P<lang>[A-Za-z0-9-]+)|\^\^(?P<dt>\S+))?$')
_LABELS = ("skos:prefLabel", "skos:altLabel", "skos:hiddenLabel")

#: Condicoes de integridade NORMATIVAS do SKOS verificadas aqui.
SKOS_CONDITIONS = ("S9", "S13", "S14", "S27", "S37")
#: Regra propria do Synesis (o SKOS admite ciclos hierarquicos, §8.6.8).
CYCLE_RULE = "Synesis rule: acyclic broader"


@dataclass
class SkosCheck:
    """Resultado: violacoes de integridade e avisos de qualidade, por condicao."""

    integrity: Dict[str, List[str]] = field(default_factory=dict)
    quality: Dict[str, List[str]] = field(default_factory=dict)

    def add(self, level: str, condition: str, detail: str) -> None:
        getattr(self, level).setdefault(condition, []).append(detail)

    @property
    def ok(self) -> bool:
        return not self.integrity


def _unwrap(obj: str) -> str:
    return obj[1:-1] if obj.startswith("<") and obj.endswith(">") else obj


def _literal(obj: str) -> Tuple[str, str]:
    """(texto, idioma) de um literal; idioma vazio quando nao ha."""
    m = _LITERAL.match(obj)
    if not m:
        return obj, ""
    return m.group("text"), m.group("lang") or ""


def check_skos(subjects: Dict[str, Dict[str, Set[str]]], language: str = "") -> SkosCheck:
    """Confere o grafo `{sujeito: {predicado: {objetos}}}` do exportador."""
    out = SkosCheck()
    types: Dict[str, Set[str]] = {s: props.get("a", set()) for s, props in subjects.items()}
    concepts = {s for s, t in types.items() if "skos:Concept" in t}
    schemes = {s for s, t in types.items() if "skos:ConceptScheme" in t}
    collections = {s for s, t in types.items() if "skos:Collection" in t}

    # ------------------------------------------------------- integridade
    for s in sorted(concepts & schemes):
        out.add("integrity", "S9", f"<{s}> is both skos:Concept and skos:ConceptScheme")
    for s in sorted(collections & (concepts | schemes)):
        out.add("integrity", "S37", f"<{s}> is a skos:Collection and also a Concept or ConceptScheme")

    for s, props in sorted(subjects.items()):
        by_lang: Dict[str, List[str]] = {}
        seen: Dict[Tuple[str, str], str] = {}
        for prop in _LABELS:
            for obj in props.get(prop, ()):
                text, lang = _literal(obj)
                if prop == "skos:prefLabel":
                    by_lang.setdefault(lang, []).append(text)
                key = (text, lang)
                if key in seen and seen[key] != prop:
                    out.add("integrity", "S13", f"<{s}>: \"{text}\" in {seen[key]} and {prop}")
                seen.setdefault(key, prop)
        for lang, texts in by_lang.items():
            if len(texts) > 1:
                out.add("integrity", "S14", f"<{s}>: {len(texts)} prefLabels in \"{lang or 'no language'}\"")

    broader: Dict[str, Set[str]] = {c: {_unwrap(o) for o in subjects[c].get("skos:broader", ())} for c in concepts}

    # Ciclo: regra do SYNESIS (hierarquia aciclica), nao condicao normativa — o
    # SKOS admite ciclos hierarquicos (W3C SKOS Reference, §8.6.8). Busca em
    # profundidade iterativa: linear em conceitos + arestas, sem fechamento.
    state: Dict[str, int] = {}  # 1 = na pilha, 2 = concluido
    for root in sorted(concepts):
        if root in state:
            continue
        state[root] = 1
        stack = [(root, iter(sorted(broader.get(root, ()))))]
        while stack:
            node, parents = stack[-1]
            parent = next(parents, None)
            if parent is None:
                state[node] = 2
                stack.pop()
            elif state.get(parent) == 1:
                out.add("integrity", CYCLE_RULE, f"<{node}> skos:broader <{parent}> closes a cycle")
            elif parent not in state:
                state[parent] = 1
                stack.append((parent, iter(sorted(broader.get(parent, ())))))

    def reaches(start: str, target: str) -> bool:
        """`target` e ancestral de `start` por broader? Busca sob demanda."""
        seen: Set[str] = set()
        pending = list(broader.get(start, ()))
        while pending:
            node = pending.pop()
            if node == target:
                return True
            if node not in seen:
                seen.add(node)
                pending.extend(broader.get(node, ()))
        return False

    # S27: so os pares associativos que existem — nada e materializado.
    for c in sorted(concepts):
        for o in sorted(subjects[c].get("skos:related", ())):
            r = _unwrap(o)
            if reaches(c, r) or reaches(r, c):
                out.add("integrity", "S27", f"<{c}> skos:related <{r}>, but one is broader of the other")

    # --------------------------------------------------------- qualidade
    for s in sorted(concepts | schemes | collections):
        if not subjects[s].get("skos:prefLabel"):
            out.add("quality", "no prefLabel", f"<{s}>")
    if language:
        for s, props in sorted(subjects.items()):
            for prop in _LABELS:
                for obj in props.get(prop, ()):
                    if not _literal(obj)[1]:
                        out.add("quality", "label without language", f"<{s}> {prop}")
    in_scheme: Dict[str, Set[str]] = {c: {_unwrap(o) for o in subjects[c].get("skos:inScheme", ())} for c in concepts}
    top_of: Dict[str, Set[str]] = {c: {_unwrap(o) for o in subjects[c].get("skos:topConceptOf", ())} for c in concepts}
    for c in sorted(concepts):
        if not in_scheme[c]:
            out.add("quality", "concept without scheme", f"<{c}>")
            continue
        for scheme in sorted(in_scheme[c]):
            has_parent = any(scheme in in_scheme.get(p, ()) for p in broader.get(c, ()))
            if not has_parent and scheme not in top_of[c]:
                out.add("quality", "concept without position", f"<{c}> in <{scheme}>")
    for s in sorted(schemes):
        if not subjects[s].get("skos:hasTopConcept"):
            out.add("quality", "scheme without top concept", f"<{s}>")
    return out


def summary_lines(result: SkosCheck) -> List[str]:
    """Linhas do relatorio do terminal."""
    checked = f"{', '.join(SKOS_CONDITIONS)}; Synesis rule: acyclic broader"
    if result.integrity:
        parts = ", ".join(f"{k} {len(v)}" for k, v in sorted(result.integrity.items()))
        lines = [f"SKOS check: INTEGRITY VIOLATIONS ({parts}) — checked {checked}"]
    else:
        lines = [f"SKOS check: integrity OK ({checked})"]
    if result.quality:
        parts = "; ".join(f"{k}: {len(v)}" for k, v in sorted(result.quality.items()))
        lines.append(f"SKOS quality notices: {parts}")
    else:
        lines.append("SKOS quality: no notice (prefLabel, language, scheme, position, top concepts)")
    return lines
