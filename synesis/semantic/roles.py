"""
roles.py - Catalogo de papeis (ROLE) e validacao do template

Proposito:
    Um unico catalogo executavel de papeis (Spec ROLE/EXPORT v7, §5.1), usado
    pelo compilador e reaproveitavel por LSP, coder e synesis-help, e as
    validacoes de template que dependem dele (§6).

Componentes principais:
    - CATALOG: papel -> tipo exigido e forma do valor
    - RESERVED: papeis previstos e ainda indisponiveis (DIVISION)
    - role_family / role_species: decomposicao da forma canonica
    - validate_template_roles: diagnosticos de papel no template

Notas:
    O papel e palavra comum (IDENTIFIER) validada aqui, nao palavra-chave da
    gramatica (S5). Forma canonica: palavras em maiusculas separadas por um
    espaco ("HIERARCHY KIND").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from synesis.ast.nodes import FieldSpec, FieldType, Scope, TemplateNode


@dataclass(frozen=True)
class RoleInfo:
    role: str
    field_type: FieldType
    single_value: bool = False  # LABEL PREFERRED: um termo por conceito


CATALOG: Dict[str, RoleInfo] = {
    "LABEL PREFERRED": RoleInfo("LABEL PREFERRED", FieldType.TEXT, single_value=True),
    "LABEL ALTERNATIVE": RoleInfo("LABEL ALTERNATIVE", FieldType.TEXT),
    "LABEL HIDDEN": RoleInfo("LABEL HIDDEN", FieldType.TEXT),
    "NOTE DEFINITION": RoleInfo("NOTE DEFINITION", FieldType.TEXT),
    "NOTE USAGE": RoleInfo("NOTE USAGE", FieldType.TEXT),
    "NOTE EXAMPLE": RoleInfo("NOTE EXAMPLE", FieldType.TEXT),
    "NOTE COUNTEREXAMPLE": RoleInfo("NOTE COUNTEREXAMPLE", FieldType.TEXT),
    "HIERARCHY KIND": RoleInfo("HIERARCHY KIND", FieldType.CODE),
    "HIERARCHY PART": RoleInfo("HIERARCHY PART", FieldType.CODE),
    "HIERARCHY INSTANCE": RoleInfo("HIERARCHY INSTANCE", FieldType.CODE),
    # Etapa U: o bloco com USE e preterido; o valor e o conceito que vale.
    "USE": RoleInfo("USE", FieldType.CODE, single_value=True),
}

# Familias que exigem especie.
FAMILIES = {"LABEL", "NOTE", "HIERARCHY", "DIVISION"}

# Previstos e indisponiveis: o motivo vai na mensagem (RoleNotAvailable).
RESERVED: Dict[str, str] = {
    "DIVISION EXCLUSIVE": "entra quando um corpus real usar categorias exclusivas",
    "DIVISION COMPLETE": "entra quando um corpus real usar categorias exclusivas",
}

# Papeis que sairam do desenho: a mensagem aponta a alternativa.
REMOVED = {"ASSOCIATION", "OPPOSITE"}

# Um campo por papel no template.
UNIQUE_ROLES = {"NOTE DEFINITION", "LABEL PREFERRED", "USE"}

HIERARCHY_SPECIES = {"HIERARCHY KIND": "KIND", "HIERARCHY PART": "PART", "HIERARCHY INSTANCE": "INSTANCE"}

# Chaves canonicas da entrada de um conceito no JSON: um campo do ONTOLOGY com
# esse nome sobrescrevia a chave (json_export). `description` e tratado a parte.
RESERVED_ONTOLOGY_NAMES = {"concept", "location", "frequency", "source_count", "parent_chains"}


def role_family(role: Optional[str]) -> Optional[str]:
    return role.split(" ", 1)[0] if role else None


def fields_with_role(template: Optional[TemplateNode], role: str) -> List[FieldSpec]:
    if template is None:
        return []
    return [s for s in template.field_specs.values() if s.role == role]


def fields_with_family(template: Optional[TemplateNode], family: str) -> List[FieldSpec]:
    if template is None:
        return []
    return [s for s in template.field_specs.values() if role_family(s.role) == family]


def definition_field(template: Optional[TemplateNode]) -> Optional[str]:
    """Nome do campo com papel NOTE DEFINITION, se houver."""
    specs = fields_with_role(template, "NOTE DEFINITION")
    return specs[0].name if specs else None


def has_roles(template: Optional[TemplateNode]) -> bool:
    return template is not None and any(s.role for s in template.field_specs.values())


def validate_template_roles(template: TemplateNode) -> list:
    """Diagnosticos de papel no template (erros), na ordem dos campos."""
    from synesis.ast.results import (
        DuplicateRole,
        DuplicateUniqueRole,
        RequiredHierarchy,
        ReservedOntologyFieldName,
        RoleNotAvailable,
        RoleOutsideOntology,
        RoleRequiresSpecies,
        RoleTypeMismatch,
        UnknownRole,
    )

    errors: list = []
    seen_unique: Dict[str, str] = {}
    required_ontology = set(template.required_fields.get(Scope.ONTOLOGY, []) or [])
    from pathlib import Path

    from synesis.ast.nodes import SourceLocation

    for spec in template.field_specs.values():
        role = spec.role
        loc = spec.location or SourceLocation(Path("<template>"), 1, 1)
        if role is None:
            continue
        for repeated in spec.role_repeats or []:
            errors.append(DuplicateRole(location=loc, field_name=spec.name, role=repeated))
        if role in RESERVED:
            errors.append(RoleNotAvailable(location=loc, field_name=spec.name, role=role, reason=RESERVED[role]))
            continue
        if role not in CATALOG:
            if role in FAMILIES:
                errors.append(RoleRequiresSpecies(location=loc, field_name=spec.name, role=role))
            else:
                errors.append(UnknownRole(
                    location=loc, field_name=spec.name, role=role, removed=role_family(role) in REMOVED,
                ))
            continue
        info = CATALOG[role]
        if spec.scope != Scope.ONTOLOGY:
            errors.append(RoleOutsideOntology(
                location=loc, field_name=spec.name, role=role, scope=spec.scope.value,
            ))
            continue
        if spec.type != info.field_type:
            errors.append(RoleTypeMismatch(
                location=loc, field_name=spec.name, role=role,
                expected=info.field_type.value, actual=spec.type.value,
            ))
        if role in UNIQUE_ROLES:
            if role in seen_unique:
                errors.append(DuplicateUniqueRole(
                    location=loc, field_name=spec.name, role=role, first_field=seen_unique[role],
                ))
            else:
                seen_unique[role] = spec.name
        if role in HIERARCHY_SPECIES and spec.name in required_ontology:
            errors.append(RequiredHierarchy(location=loc, field_name=spec.name, role=role))

    definition = seen_unique.get("NOTE DEFINITION")
    for spec in template.field_specs.values():
        if spec.scope != Scope.ONTOLOGY:
            continue
        lname = spec.name.lower()
        clash = lname in RESERVED_ONTOLOGY_NAMES or (
            lname == "description" and definition is not None and definition != spec.name
        )
        if clash:
            loc = spec.location or SourceLocation(Path("<template>"), 1, 1)
            errors.append(ReservedOntologyFieldName(location=loc, field_name=spec.name))
    return errors
