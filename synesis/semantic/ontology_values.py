"""
ontology_values.py - Valor dos campos do ONTOLOGY interpretado pelo tipo

Propósito:
    Projeção única do valor de cada campo de um bloco ONTOLOGY pelo tipo
    declarado no template (Spec ROLE/EXPORT v7, §3). O transformer não conhece
    o template e decide a forma pelo conteúdo: um TEXT com `->` vira cadeia, e
    listas só são separadas em campos chamados `code`/`codes`. Aqui o tipo
    decide, com ou sem ROLE:
        TEXT  -> o texto como foi escrito (`->` é texto)
        CODE  -> lista de conceitos, uma por ocorrência acumulada
        demais tipos -> como o transformer produziu

Componentes principais:
    - projected_fields: campos do nó já interpretados (para o validador)
    - project_ontology: cópia do nó com os campos interpretados (para o linker)

Notas:
    A projeção é calculada ANTES da validação de forma e é lida pelos três
    caminhos que validam ONTOLOGY (compilação em disco, `synesis.load` e o
    adaptador do LSP). Nada aqui altera o nó: o parse_cache devolve o mesmo nó
    na compilação seguinte, e uma mutação faria o resultado depender de quantas
    vezes o projeto já foi compilado.
"""

from __future__ import annotations

import unicodedata
from dataclasses import replace
from typing import Any, Dict, Optional

from synesis.ast.nodes import ChainNode, FieldEntry, FieldType, OntologyNode, TemplateNode
from synesis.semantic.occurrences import resolve_occurrence

# Nomes que o transformer desvia para atributos próprios do OntologyNode.
_ROUTED = {"description", "parent", "parents", "is_a", "isa"}


def _raw_text(entry: FieldEntry) -> Optional[str]:
    """Texto escrito de uma ocorrência que o transformer converteu."""
    if not entry.lines:
        return None
    from synesis.parser.transformer import _dedent_text, _line_texts

    text = _dedent_text("\n".join(_line_texts(entry.lines))).strip()
    return text or None


def project_value(
    entry: FieldEntry, field_type: Optional[FieldType], role: Optional[str] = None
) -> Any:
    """Valor de UMA ocorrência do ONTOLOGY pelo tipo (e pelo papel) do campo."""
    if field_type == FieldType.TEXT and role and role.startswith("LABEL"):
        # LABEL: lista de termos livres, separados por virgula, em NFC.
        text = project_value(entry, FieldType.TEXT)
        return [unicodedata.normalize("NFC", t.strip()) for t in str(text).split(",") if t.strip()]
    if field_type == FieldType.TEXT:
        value = entry.value
        if isinstance(value, (ChainNode, list)):
            raw = _raw_text(entry)
            if raw is not None:
                return raw
            if isinstance(value, ChainNode):
                return " -> ".join(value.nodes)
            return ", ".join(str(v) for v in value)
        return value
    if field_type == FieldType.CODE:
        return resolve_occurrence(entry, FieldType.CODE)
    return entry.value


def _types(template: Optional[TemplateNode]) -> Dict[str, FieldType]:
    if template is None:
        return {}
    return {name: spec.type for name, spec in template.field_specs.items()}


def _roles(template: Optional[TemplateNode]) -> Dict[str, Optional[str]]:
    if template is None:
        return {}
    return {name: getattr(spec, "role", None) for name, spec in template.field_specs.items()}


def _accumulate(fields: Dict[str, Any], name: str, value: Any, field_type: Optional[FieldType]) -> None:
    """Acumula como o transformer; CODE repetido junta as listas."""
    if name not in fields:
        fields[name] = list(value) if isinstance(value, list) else value
        return
    existing = fields[name]
    if field_type == FieldType.CODE and isinstance(existing, list):
        existing.extend(value if isinstance(value, list) else [value])
    elif isinstance(existing, list) and field_type != FieldType.CODE:
        existing.append(value)
    else:
        fields[name] = [existing, value]


def projected_fields(node: OntologyNode, template: Optional[TemplateNode]) -> Optional[Dict[str, Any]]:
    """Campos do bloco (sem os desviados por nome) interpretados pelo tipo.

    Devolve None quando o nó não tem `entries` (construído à mão): quem chama
    usa então `node.fields`, como antes.
    """
    entries = getattr(node, "entries", None)
    if not entries:
        return None
    types = _types(template)
    roles = _roles(template)
    fields: Dict[str, Any] = {}
    for entry in entries:
        if entry.name.lower() in _ROUTED:
            continue
        field_type = types.get(entry.name)
        role = roles.get(entry.name)
        value = project_value(entry, field_type, role)
        # LABEL acumula como lista (as ocorrencias juntam termos), como CODE.
        acc_type = FieldType.CODE if (role or "").startswith("LABEL") else field_type
        _accumulate(fields, entry.name, value, acc_type)
    return fields


def projected_description(node: OntologyNode, template: Optional[TemplateNode]) -> str:
    """O campo `description` (rota por nome) também lido pelo tipo."""
    types = _types(template)
    for entry in getattr(node, "entries", None) or []:
        if entry.name.lower() == "description":
            value = project_value(entry, types.get(entry.name, FieldType.TEXT))
            return str(value) if value is not None else ""
    return node.description


def project_ontology(node: OntologyNode, template: Optional[TemplateNode]) -> OntologyNode:
    """Cópia do nó com os campos interpretados; o próprio nó se nada muda."""
    fields = projected_fields(node, template)
    if fields is None:
        return node
    description = projected_description(node, template)
    # Com ROLE NOTE DEFINITION, a definicao e esse campo (Spec §5.2, item 7); a
    # rota pelo nome `description` so vale em templates sem o papel.
    from synesis.semantic.roles import definition_field

    definition = definition_field(template)
    if definition and definition in fields:
        value = fields[definition]
        description = "\n\n".join(map(str, value)) if isinstance(value, list) else str(value)
    if fields == node.fields and description == node.description:
        return node
    return replace(node, fields=fields, description=description)
