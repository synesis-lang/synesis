"""link_step.py — Etapa 2b: passo de linkagem multi-projeto (IDENTIFIES / REFERS TO).

Modelo do linker C/C++: cada projeto compila isolado e expoe seus simbolos
externos (REFERS TO) e publicos (IDENTIFIES). Este passo resolve os simbolos
entre unidades e produz o agregado. Disparado SO na CLI com N>1 projetos —
nunca no LSP (D2 do design; ver Planning/multiproject_key_ref.md).

Regras (nao reabrir sem motivo novo — §12.1):
  - IDENTIFIES = chave primaria: valor unico, corpus dono unico (E081).
  - REFERS TO = chave estrangeira: aponta, repete, nao cria no; orfao = warning (W083).
  - Tipos identicos por entidade (E082, erro duro).
  - Casamento por igualdade EXATA pos-trim; SEM normalizacao (D7). Quase-casamento
    (difere so em caixa/invisiveis) e detectado como suspeita e vira warning
    enriquecido — nunca funde.
  - Bibrefs sao locais ao membro; no agregado sao qualificados por alias (D10).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from synesis.ast.nodes import FieldType, SourceLocation, TemplateNode
from synesis.ast.results import (
    DuplicateEntityOwner,
    OrphanReference,
    TypeMismatchInLinkage,
    ValidationResult,
)
from synesis.parser.bib_loader import find_bibref

# Localizacao sintetica para diagnosticos do link step (nao ancoram numa linha de arquivo).
_LINK_LOCATION = SourceLocation(file=Path("<link>"), line=0, column=0)


def _member_alias(project_path: Path) -> str:
    """Alias do membro derivado do nome do arquivo .synp (linkedin.synp -> linkedin)."""
    return project_path.stem


def _trim(value: Any) -> str:
    """Valor comparavel: str + trim de bordas. SEM case-folding, SEM normalizacao (D7)."""
    return str(value).strip()


def _values_of(raw: Any) -> List[str]:
    """Um campo pode ser multi-valorado (lista) — cada valor gera uma aresta (§3)."""
    if isinstance(raw, (list, tuple)):
        return [_trim(v) for v in raw if _trim(v)]
    trimmed = _trim(raw)
    return [trimmed] if trimmed else []


@dataclass
class Member:
    """Um projeto compilado, pronto para linkagem."""

    alias: str
    template: TemplateNode
    sources: Dict[str, Any]  # bibref -> SourceNode
    path: Path
    bibliography: Dict[str, Any] = field(default_factory=dict)  # bibref normalizado -> BibEntry


def _resolve_field_values(member: "Member", bibref: str, field_name: str) -> List[str]:
    """Valores de um campo num SOURCE, respeitando a origem (documento ou .bib).

    ON BIBLIOGRAPHY (value_origin == "bibliography"): o valor vive no .bib, nao
    no bloco SOURCE — resolvido via find_bibref. Caso contrario, vem de
    source.fields (extraido do documento).
    """
    spec = member.template.field_specs.get(field_name)
    origin = getattr(spec, "value_origin", "document") if spec is not None else "document"
    source = member.sources.get(bibref)
    if origin == "bibliography":
        entry = find_bibref(member.bibliography, bibref.lstrip("@"))
        raw = entry.get(field_name) if entry else None
        if raw is None and source is not None:
            # tolera valor tambem presente no SOURCE (compilacao ja checou conflito)
            raw = source.fields.get(field_name)
        return _values_of(raw)
    if source is None:
        return []
    return _values_of(source.fields.get(field_name))


@dataclass
class ResolvedEdge:
    entity: str
    value: str
    from_member: str
    from_bibref: str  # ja qualificado por alias
    to_member: str
    to_bibref: str  # ja qualificado por alias


@dataclass
class LinkResult:
    edges: List[ResolvedEdge] = field(default_factory=list)
    orphans: List[Tuple[str, str, str]] = field(default_factory=list)  # (entity, value, member)
    validation: ValidationResult = field(default_factory=ValidationResult)
    entity_owners: Dict[str, str] = field(default_factory=dict)  # entity -> owner alias


def _identity_fields(template: TemplateNode) -> Dict[str, str]:
    """entity -> field_name para cada FIELD com IDENTIFIES <entity>."""
    out: Dict[str, str] = {}
    for name, spec in template.field_specs.items():
        if getattr(spec, "identifies", None):
            out[spec.identifies] = name
    return out


def _reference_fields(template: TemplateNode) -> Dict[str, str]:
    """entity -> field_name para cada FIELD com REFERS TO <entity>."""
    out: Dict[str, str] = {}
    for name, spec in template.field_specs.items():
        if getattr(spec, "refers_to", None):
            out[spec.refers_to] = name
    return out


def _type_str(template: TemplateNode, field_name: str) -> str:
    spec = template.field_specs.get(field_name)
    if spec is None:
        return "?"
    t = spec.type
    return t.value if isinstance(t, FieldType) else str(t)


def link_members(members: List[Member]) -> LinkResult:
    """Resolve arestas IDENTIFIES/REFERS TO entre membros compilados."""
    result = LinkResult()
    vr = result.validation

    # --- 1. Registrar donos de entidade (IDENTIFIES) e detectar dono duplicado (E081) ---
    owner_field: Dict[str, Tuple[str, str]] = {}  # entity -> (member_alias, field_name)
    for m in members:
        for entity, fname in _identity_fields(m.template).items():
            if entity in owner_field:
                first_member = owner_field[entity][0]
                vr.add(DuplicateEntityOwner(
                    location=_LINK_LOCATION,
                    entity=entity,
                    first_member=first_member,
                    duplicate_member=m.alias,
                ))
                continue
            owner_field[entity] = (m.alias, fname)
    result.entity_owners = {e: mf[0] for e, mf in owner_field.items()}

    # --- 2. Consistencia de tipo por entidade (E082): IDENTIFIES + todos os REFERS TO ---
    #     type_witness[entity] = (member, field, type_str) do primeiro campo visto.
    type_witness: Dict[str, Tuple[str, str, str]] = {}
    for m in members:
        fields = dict(_identity_fields(m.template))
        fields.update(_reference_fields(m.template))
        for entity, fname in fields.items():
            tstr = _type_str(m.template, fname)
            if entity not in type_witness:
                type_witness[entity] = (m.alias, fname, tstr)
                continue
            wit_member, _wit_field, wit_type = type_witness[entity]
            if tstr != wit_type:
                vr.add(TypeMismatchInLinkage(
                    location=_LINK_LOCATION,
                    entity=entity,
                    member_a=wit_member,
                    type_a=wit_type,
                    member_b=m.alias,
                    type_b=tstr,
                ))

    # --- 3. Indexar valores de PK por entidade: value -> (owner_alias, qualified_bibref) ---
    pk_index: Dict[str, Dict[str, Tuple[str, str]]] = {}  # entity -> {value: (member, qbibref)}
    for m in members:
        for entity, fname in _identity_fields(m.template).items():
            bucket = pk_index.setdefault(entity, {})
            for bibref in m.sources:
                for val in _resolve_field_values(m, bibref, fname):
                    # unicidade intra-membro ja validada na compilacao (E077);
                    # aqui apenas indexamos.
                    bucket.setdefault(val, (m.alias, _qualify(m.alias, bibref)))

    # --- 4. Resolver referencias (REFERS TO) -> arestas ou orfaos (W083) ---
    for m in members:
        for entity, fname in _reference_fields(m.template).items():
            bucket = pk_index.get(entity, {})
            for bibref in m.sources:
                for val in _resolve_field_values(m, bibref, fname):
                    hit = bucket.get(val)
                    if hit is not None:
                        owner_alias, owner_qbibref = hit
                        result.edges.append(ResolvedEdge(
                            entity=entity,
                            value=val,
                            from_member=m.alias,
                            from_bibref=_qualify(m.alias, bibref),
                            to_member=owner_alias,
                            to_bibref=owner_qbibref,
                        ))
                    else:
                        near = _near_match(val, bucket.keys())
                        vr.add(OrphanReference(
                            location=_LINK_LOCATION,
                            entity=entity,
                            value=val,
                            member=m.alias,
                            near_match=near,
                        ))
                        result.orphans.append((entity, val, m.alias))

    return result


def _qualify(alias: str, bibref: str) -> str:
    """Qualifica bibref por alias do membro (D10): linkedin + @x -> linkedin:@x.

    As chaves de LinkedProject.sources vem normalizadas SEM `@`; o formato
    canonico do agregado (D10, e o mesmo usado pelo synesis-graph) inclui o
    `@` — normaliza aqui para os dois artefatos falarem a mesma lingua.
    """
    raw = bibref if str(bibref).startswith("@") else f"@{bibref}"
    return f"{alias}:{raw}"


def _near_match(value: str, candidates: Any) -> Optional[str]:
    """Detecta quase-casamento (difere so em caixa/invisiveis) SEM fundir (D7).

    Retorna o valor-PK que casaria sob normalizacao, ou None. So deteccao —
    a heuristica jamais liga; vira warning enriquecido.
    """
    norm = value.casefold()
    for cand in candidates:
        if cand != value and cand.casefold() == norm:
            return cand
    return None
