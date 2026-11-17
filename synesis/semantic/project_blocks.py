"""
project_blocks.py - Validacao dos blocos QUESTIONS e EXPORT do .synp

Proposito:
    Conferir a forma das questoes de competencia e dos blocos EXPORT, e manter
    o registro dos formatos de exportacao usado por `synesis export`.

Componentes principais:
    - EXPORT_FORMATS: formatos disponiveis, com propriedades obrigatorias e aceitas
    - validate_project_blocks: diagnosticos de QUESTIONS e de EXPORT
    - export_block_errors: diagnosticos de um bloco (para `synesis export`)
    - select_exports: escolha dos blocos por formato ou por nome

Notas:
    Os erros de QUESTIONS sao do nucleo do projeto. Os de EXPORT sao locais ao
    bloco: na compilacao viram avisos; em `synesis export`, impedem so o bloco.
    A gramatica aceita qualquer palavra como formato e propriedade (S5); a
    validacao e semantica, aqui.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Sequence

from synesis.ast.nodes import ExportNode, FieldType, ProjectNode, Scope, TemplateNode
from synesis.ast.results import (
    AmbiguousExportName,
    AmbiguousRelation,
    DuplicateExportProperty,
    DuplicateQuestionId,
    InvalidGeneratedAt,
    InvalidLanguageTag,
    InvalidMinSources,
    InvalidNamespace,
    MapNotSupported,
    MapTargetNotAllowed,
    MissingExportProperty,
    QuestionWithoutId,
    QuestionWithoutText,
    RelationMappedTwice,
    UnknownExportFormat,
    UnknownExportProperty,
    UnknownRelation,
    ValidationError,
    ValidationResult,
)


@dataclass(frozen=True)
class ExportFormat:
    """Contrato de um formato: propriedades obrigatorias e opcionais."""

    name: str
    required: tuple[str, ...]
    optional: tuple[str, ...] = ()

    @property
    def allowed(self) -> tuple[str, ...]:
        return self.required + self.optional + ("DESCRIPTION",)


EXPORT_FORMATS: Dict[str, ExportFormat] = {
    "JSON": ExportFormat("JSON", ("OUTPUT",), ("GENERATED_AT",)),
    "CSV": ExportFormat("CSV", ("OUTPUT",)),
    "XLS": ExportFormat("XLS", ("OUTPUT",)),
    "ALPACA": ExportFormat("ALPACA", ("OUTPUT",)),
    "OKF": ExportFormat("OKF", ("OUTPUT",), ("GENERATED_AT",)),
    "SKOS": ExportFormat("SKOS", ("OUTPUT", "NAMESPACE", "LANGUAGE"),
                         ("GENERATED_AT", "MIN_SOURCES", "ALIAS_LABEL", "REGISTRY")),
}

# Previstos na especificacao, ainda sem exportador: o diagnostico diz "previsto".
PLANNED_FORMATS = frozenset({"CNA"})

# Formatos que aceitam `MAP RELATIONS` (visao de artefato) e alvos aceitos.
MAP_RELATIONS_FORMATS = frozenset({"SKOS"})
MAP_RELATIONS_TARGETS = ("HIERARCHY KIND", "HIERARCHY PART", "HIERARCHY INSTANCE", "RELATED")

_BCP47 = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$")


def validate_project_blocks(
    project: ProjectNode, template: Optional[TemplateNode] = None
) -> ValidationResult:
    """Diagnosticos de QUESTIONS (erros) e de EXPORT (avisos locais)."""
    result = ValidationResult()
    for error in _question_errors(project):
        result.add(error)
    for export in project.exports:
        for error in export_block_errors(export, template):
            result.add(error)
    for error in _export_name_errors(project.exports):
        result.add(error)
    for error in phase_errors(project, template):
        result.add(error)
    return result


# ------------------------------------------------------------------- PHASE

PHASE_PROPS = {"FIELDS", "INPUT", "RULES", "OUTPUT"}


def eligible_ontology_outputs(project: ProjectNode) -> List[str]:
    """.syno em que uma fase pode gravar: INCLUDE ONTOLOGY local citado como arquivo."""
    out = []
    for inc in project.includes:
        path = inc.path.replace("\\", "/")
        if (inc.include_type.upper() == "ONTOLOGY" and not inc.shared
                and path.lower().endswith(".syno") and not any(ch in path for ch in "*?[")):
            out.append(path)
    return out


def _norm_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("./").lower()


def _same_path(a: str, b: str) -> bool:
    return _norm_path(a) == _norm_path(b)


def phase_errors(project: ProjectNode, template: Optional[TemplateNode]) -> List[ValidationError]:
    """Diagnosticos do plano de fases (Estudo ROLE/EXPORT §6.2, §9)."""
    from synesis.ast.results import (
        AmbiguousPhaseOutput,
        BundleSplitAcrossPhases,
        DuplicatePhaseProperty,
        EmptyPhaseList,
        FieldInTwoPhases,
        FieldWithoutPhase,
        InputNotAvailable,
        PhaseNameCollision,
        PhaseOutputNotLocal,
        PhaseScopeMismatch,
        UnknownPhaseField,
        UnknownPhaseProperty,
    )

    errors: List[ValidationError] = []
    if not project.phases:
        return errors
    specs = template.field_specs if template else {}
    produced_by: Dict[str, str] = {}
    produced_so_far: set = set()
    env_seen: Dict[str, str] = {}
    eligible = eligible_ontology_outputs(project)
    planned = {f for p in project.phases for f in p.fields("FIELDS")}
    # Escopos que o plano cobre: sem PHASE ANNOTATIONS, os campos de SOURCE e
    # ITEM vêm das anotações existentes, e não há o que avisar sobre eles.
    covered = set()
    if any(p.scope == "ONTOLOGY" for p in project.phases):
        covered.add("ONTOLOGY")
    if any(p.scope == "ANNOTATIONS" for p in project.phases):
        covered.update({"SOURCE", "ITEM"})
    for phase in project.phases:
        label = phase.label
        loc = phase.location
        if phase.env_key in env_seen:
            errors.append(PhaseNameCollision(location=loc, phase=label, other=env_seen[phase.env_key]))
        else:
            env_seen[phase.env_key] = label
        seen_props: set = set()
        for prop in phase.props:
            if prop.name not in PHASE_PROPS or (prop.name == "OUTPUT" and phase.scope != "ONTOLOGY"):
                errors.append(UnknownPhaseProperty(location=prop.location, phase=label, prop=prop.name))
            elif prop.name in seen_props:
                errors.append(DuplicatePhaseProperty(location=prop.location, phase=label, prop=prop.name))
            seen_props.add(prop.name)
            if prop.name in ("FIELDS", "INPUT", "RULES") and not phase.fields(prop.name):
                errors.append(EmptyPhaseList(location=prop.location, phase=label, prop=prop.name))
        if "FIELDS" not in seen_props:
            errors.append(EmptyPhaseList(location=loc, phase=label, prop="FIELDS"))
        for prop_name in ("FIELDS", "INPUT", "RULES"):
            for fname in phase.fields(prop_name):
                if template is not None and fname not in specs:
                    errors.append(UnknownPhaseField(location=loc, phase=label, prop=prop_name, field_name=fname))
        for fname in phase.fields("FIELDS"):
            spec = specs.get(fname)
            if spec is not None:
                scope = spec.scope.value
                wrong = (phase.scope == "ONTOLOGY") != (scope == "ONTOLOGY")
                if wrong:
                    errors.append(PhaseScopeMismatch(
                        location=loc, phase=label, field_name=fname, field_scope=scope,
                    ))
            if fname in produced_by:
                errors.append(FieldInTwoPhases(
                    location=loc, phase=label, field_name=fname, first_phase=produced_by[fname],
                ))
            else:
                produced_by[fname] = label
        for fname in phase.fields("INPUT"):
            # Só a ORDEM é erro provável: o campo é produzido por uma fase
            # posterior. Um campo que nenhuma fase produz vem dos dados que já
            # existem (.syn, .syno) e não gera aviso.
            if fname in specs and fname not in produced_so_far and fname in planned:
                errors.append(InputNotAvailable(location=loc, phase=label, field_name=fname))
        produced_so_far.update(phase.fields("FIELDS"))
        if phase.scope == "ONTOLOGY":
            output = phase.prop("OUTPUT")
            if output is None and len(eligible) != 1:
                errors.append(AmbiguousPhaseOutput(location=loc, phase=label, eligible=len(eligible)))
            elif output is not None and not any(_same_path(output, e) for e in eligible):
                errors.append(PhaseOutputNotLocal(location=loc, phase=label, output=output))

    if template is not None:
        for bundles in list(template.bundled_fields.values()) + list(template.optional_bundles.values()):
            for bundle in bundles:
                owners = {produced_by.get(f) for f in bundle} - {None}
                if len(owners) > 1:
                    first = next(p for p in project.phases if p.label in owners)
                    errors.append(BundleSplitAcrossPhases(
                        location=first.location, phase=first.label, bundle=tuple(bundle),
                    ))
        for scope_fields in template.required_fields.values():
            for fname in scope_fields:
                spec = specs.get(fname)
                if spec is not None and spec.value_origin != "document":
                    continue  # ON BIBLIOGRAPHY / ON DATASET: valor fora do bloco
                if spec is not None and spec.scope.value not in covered:
                    continue  # escopo fora do plano: o valor vem dos dados existentes
                if fname not in produced_by:
                    errors.append(FieldWithoutPhase(location=project.location, field_name=fname))
    return errors


def _question_errors(project: ProjectNode) -> List[ValidationError]:
    errors: List[ValidationError] = []
    seen: Dict[str, int] = {}
    for question in project.questions:
        if not question.id:
            errors.append(QuestionWithoutId(location=question.location, line=question.raw))
            continue
        if not question.text:
            errors.append(QuestionWithoutText(location=question.location, question_id=question.id))
        key = question.id.casefold()
        if key in seen:
            errors.append(DuplicateQuestionId(
                location=question.location,
                question_id=question.id,
                first_line=seen[key],
            ))
        else:
            seen[key] = question.location.line
    return errors


def export_block_errors(
    export: ExportNode, template: Optional[TemplateNode] = None
) -> List[ValidationError]:
    """Erros de forma de um bloco, sem olhar os demais blocos do projeto."""
    block = export.label
    fmt = EXPORT_FORMATS.get(export.format)
    if fmt is None:
        return [UnknownExportFormat(
            location=export.location,
            block=block,
            export_format=export.format,
            known=tuple(EXPORT_FORMATS),
            planned=export.format in PLANNED_FORMATS,
        )]

    errors: List[ValidationError] = []
    seen: set[str] = set()
    for prop in export.props:
        if prop.name not in fmt.allowed:
            errors.append(UnknownExportProperty(
                location=prop.location, block=block, prop=prop.name, allowed=fmt.allowed,
            ))
        elif prop.name in seen:
            errors.append(DuplicateExportProperty(location=prop.location, block=block, prop=prop.name))
        seen.add(prop.name)
    for required in fmt.required:
        if required not in seen:
            errors.append(MissingExportProperty(location=export.location, block=block, prop=required))
    for map_node in export.maps:
        if map_node.kind == "relations" and export.format in MAP_RELATIONS_FORMATS:
            continue
        errors.append(MapNotSupported(location=map_node.location, block=block))
    if export.format in MAP_RELATIONS_FORMATS:
        errors.extend(_map_relations_errors(export, template))
    if export.format == "SKOS":
        errors.extend(_skos_property_errors(export))

    generated_at = export.prop("GENERATED_AT")
    if generated_at is not None and "GENERATED_AT" in fmt.allowed and not _is_iso_with_tz(generated_at):
        errors.append(InvalidGeneratedAt(location=export.location, block=block, value=generated_at))
    return errors


def chain_relations(template: Optional[TemplateNode]) -> Dict[str, List[str]]:
    """{relacao: [campos CHAIN do ITEM que a declaram]}, pela caixa escrita."""
    out: Dict[str, List[str]] = {}
    if template is None:
        return out
    for name, spec in template.field_specs.items():
        if spec.scope == Scope.ITEM and spec.type == FieldType.CHAIN:
            for relation in spec.relations or {}:
                out.setdefault(relation, []).append(name)
    return out


def _map_relations_errors(export: ExportNode, template: Optional[TemplateNode]) -> List[ValidationError]:
    errors: List[ValidationError] = []
    known = chain_relations(template)
    seen: Dict[str, bool] = {}
    for node in export.maps:
        if node.kind != "relations":
            continue
        if node.target not in MAP_RELATIONS_TARGETS:
            errors.append(MapTargetNotAllowed(location=node.location, block=export.label, target=node.target))
        for relation in node.names:
            if relation in seen:
                errors.append(RelationMappedTwice(location=node.location, block=export.label, relation=relation))
            seen[relation] = True
            if template is None:
                continue
            fields = known.get(relation, [])
            if node.from_field:
                if node.from_field not in fields:
                    errors.append(UnknownRelation(
                        location=node.location, block=export.label, relation=relation,
                        from_field=node.from_field,
                    ))
            elif not fields:
                errors.append(UnknownRelation(location=node.location, block=export.label, relation=relation))
            elif len(fields) > 1:
                errors.append(AmbiguousRelation(
                    location=node.location, block=export.label, relation=relation, fields=tuple(fields),
                ))
    return errors


def _skos_property_errors(export: ExportNode) -> List[ValidationError]:
    errors: List[ValidationError] = []
    namespace = export.prop("NAMESPACE")
    if namespace is not None and not re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://\S+[/#]$", namespace):
        errors.append(InvalidNamespace(location=export.location, block=export.label, value=namespace))
    language = export.prop("LANGUAGE")
    if language is not None and not _BCP47.match(language):
        errors.append(InvalidLanguageTag(location=export.location, block=export.label, value=language))
    min_sources = export.prop("MIN_SOURCES")
    if min_sources is not None and not (min_sources.isdigit() and int(min_sources) >= 1):
        errors.append(InvalidMinSources(location=export.location, block=export.label, value=min_sources))
    alias_label = export.prop("ALIAS_LABEL")
    if alias_label is not None and alias_label.strip().upper() not in ("HIDDEN", "ALTERNATIVE"):
        from synesis.ast.results import UnknownAliasLabel

        errors.append(UnknownAliasLabel(location=export.location, block=export.label, value=alias_label))
    return errors


def _export_name_errors(exports: Sequence[ExportNode]) -> List[ValidationError]:
    errors: List[ValidationError] = []
    by_format: Dict[str, List[ExportNode]] = {}
    for export in exports:
        by_format.setdefault(export.format, []).append(export)
    for fmt, blocks in by_format.items():
        if len(blocks) > 1:
            for export in blocks:
                if export.name is None:
                    errors.append(AmbiguousExportName(
                        location=export.location,
                        block=export.label,
                        reason=f"there are {len(blocks)} {fmt} blocks and this one has no name",
                    ))
    seen: Dict[str, ExportNode] = {}
    formats = set(EXPORT_FORMATS) | PLANNED_FORMATS
    for export in exports:
        if export.name is None:
            continue
        key = export.name.casefold()
        if export.name.upper() in formats:
            errors.append(AmbiguousExportName(
                location=export.location,
                block=export.label,
                reason=f"the name `{export.name}` matches a format",
            ))
        elif key in seen:
            errors.append(AmbiguousExportName(
                location=export.location,
                block=export.label,
                reason=f"the name `{export.name}` is already used by `{seen[key].label}`",
            ))
        else:
            seen[key] = export
    return errors


def _is_iso_with_tz(value: str) -> bool:
    # O fromisoformat do Python 3.10 nao aceita o sufixo "Z" (o 3.11+ aceita):
    # sem esta troca, `2026-11-16T00:00:00Z` era erro so no 3.10.
    if value[-1:] in ("Z", "z"):
        value = value[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None


def select_exports(project: ProjectNode, selector: Optional[str]) -> List[ExportNode]:
    """Blocos escolhidos por `synesis export projeto.synp [formato|nome]`.

    Sem seletor, todos, na ordem do arquivo. Com seletor, o bloco de mesmo nome
    ou, se nenhum tiver esse nome, os blocos daquele formato. Sem distincao de caixa.
    """
    if selector is None:
        return list(project.exports)
    by_name = [e for e in project.exports if e.name and e.name.casefold() == selector.casefold()]
    if by_name:
        return by_name
    return [e for e in project.exports if e.format == selector.upper()]
