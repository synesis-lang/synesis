"""
aliases.py - Conceitos preteridos (ROLE USE) e a projeção resolvida (etapa U)

Propósito:
    Um bloco ONTOLOGY com o campo de papel USE é PRETERIDO: o conceito que vale
    é o alvo. A forma escrita (.syn, corpus) não muda; os índices analíticos
    usam a identidade resolvida (Spec_USE_Etapa_U.md, §2 e §3).

Componentes principais:
    - Aliases: preterido -> alvo, por identidade (normalize_code)
    - build_aliases: lê o campo USE dos blocos e diagnostica (E145–E148)
    - resolve_usage: une as menções do preterido às do alvo (sem contar duas
      vezes o ITEM que cita os dois)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from synesis.ast.nodes import OntologyNode, SourceLocation, TemplateNode
from synesis.ast.normalize import normalize_code
from synesis.semantic.roles import fields_with_role


def _as_list(value) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    return [str(value)] if str(value).strip() else []


def use_field(template: Optional[TemplateNode]) -> Optional[str]:
    specs = fields_with_role(template, "USE")
    return specs[0].name if specs else None


@dataclass
class Aliases:
    """Preteridos e seus alvos, por identidade."""

    target: Dict[str, str] = field(default_factory=dict)  # preterido -> alvo
    field_name: Optional[str] = None

    def __bool__(self) -> bool:
        return bool(self.target)

    def resolve(self, key: str) -> str:
        return self.target.get(key, key)

    def of(self, target_key: str) -> List[str]:
        return sorted(a for a, t in self.target.items() if t == target_key)

    def is_alias(self, key: str) -> bool:
        return key in self.target


def build_aliases(
    ontology_index: Dict[str, OntologyNode], template: Optional[TemplateNode]
) -> Tuple[Aliases, list]:
    """Mapa de preteridos e os diagnósticos do campo USE."""
    from synesis.ast.results import AliasWithContent, UseChain, UseMultipleTargets, UseSelf

    fname = use_field(template)
    aliases = Aliases(field_name=fname)
    errors: list = []
    if fname is None:
        return aliases, errors
    for key, node in ontology_index.items():
        values = _as_list(node.fields.get(fname))
        if not values:
            continue
        loc = node.location or SourceLocation(Path("<ontology>"), 1, 1)
        if len(values) > 1:
            errors.append(UseMultipleTargets(location=loc, concept=node.concept, field_name=fname,
                                             targets=tuple(values)))
            continue
        tkey = normalize_code(values[0])
        if tkey == key:
            errors.append(UseSelf(location=loc, concept=node.concept, field_name=fname))
            continue
        others = tuple(sorted(
            f for f, v in node.fields.items()
            if f != fname and v not in (None, "", []) and _as_list(v)
        ))
        if others:
            errors.append(AliasWithContent(location=loc, concept=node.concept, fields=others))
        if tkey in ontology_index:  # alvo sem bloco: UndeclaredConcept (E101) já acusa
            aliases.target[key] = tkey
    for key, tkey in sorted(aliases.target.items()):
        if tkey in aliases.target:
            node = ontology_index[key]
            errors.append(UseChain(
                location=node.location or SourceLocation(Path("<ontology>"), 1, 1),
                concept=node.concept, target=ontology_index[tkey].concept,
                final=ontology_index.get(aliases.target[tkey], ontology_index[tkey]).concept,
            ))
    return aliases, errors


def resolve_usage(usage: Dict[str, list], aliases: Aliases) -> Dict[str, list]:
    """Menções do preterido somadas às do alvo; um ITEM conta uma vez."""
    if not aliases:
        return usage
    out: Dict[str, list] = {}
    seen: Dict[str, set] = {}
    for key, items in usage.items():
        target = aliases.resolve(key)
        bucket = out.setdefault(target, [])
        ids = seen.setdefault(target, set())
        for item in items:
            if id(item) not in ids:
                ids.add(id(item))
                bucket.append(item)
    return out
