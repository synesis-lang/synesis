"""
alpaca_mapped.py - Exportador Alpaca com composicao declarada no EXPORT ALPACA

Proposito:
    Gerar pares instruction/input/output a partir de um bloco
    `EXPORT ALPACA` que declara, com `MAP <campos> TO INSTRUCTION|INPUT|OUTPUT`,
    quais campos formam cada chave. O formato Alpaca nao muda: as tres chaves
    sao strings.

Componentes principais:
    - build_mapped_pairs: pares em memoria e o cartao do dataset
    - export_alpaca_mapped: escreve o JSONL e o cartao `<saida>.card.json`

Regras (estudo Estudo_Alpaca_Composicao_Declarada_MAP_TO.md, rev. 4):
    - Unidade: um BUNDLE de ITEM no mapa define as linhas (uma por ocorrencia);
      campos fora dele sao contexto, repetido inteiro em cada linha do ITEM e
      nunca multiplicam linhas. Sem bundle no mapa, uma linha por ITEM.
    - Formato unico: texto puro. Um campo na chave: so o valor. Varios: um
      bloco por campo, rotulado pelo nome, na ordem do MAP. Campo vazio na
      unidade nao aparece (sem rotulo orfao).
    - OUTPUT vazio e avaliado sobre os valores; sem tamanho minimo.
    - Deduplicacao so do trio identico (instruction, input, output), contada.
    - Ordem deterministica: arquivo, linha e coluna do ITEM.

Dependencias criticas:
    - synesis.semantic.project_blocks.alpaca_plan: a mesma composicao que a
      validacao confere
    - synesis.semantic.occurrences.field_occurrences: valor por ocorrencia
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from synesis.ast.nodes import ChainNode, ExportNode, FieldType, ItemNode, SourceNode, TemplateNode
from synesis.exporters._helpers import project_base_dir, relative_to_project
from synesis.semantic.linker import LinkedProject
from synesis.semantic.occurrences import field_occurrences
from synesis.semantic.project_blocks import ALPACA_TARGETS, AlpacaPlan, alpaca_plan

AlpacaPair = Dict[str, str]

# Tipos cujo texto vai na linha seguinte ao rotulo (podem ter varias linhas).
_BLOCK_TYPES = (FieldType.TEXT, FieldType.MEMO, FieldType.QUOTATION, FieldType.CHAIN)
_COUNTED_TYPES = (FieldType.ENUMERATED, FieldType.ORDERED)


def build_mapped_pairs(
    linked: LinkedProject,
    template: TemplateNode,
    plan: AlpacaPlan,
) -> Tuple[List[AlpacaPair], Dict[str, Any]]:
    """Pares do modo declarado e as contagens do cartao."""
    counts = {
        "items": 0,
        "units": 0,
        "lines": 0,
        "skipped_empty_output": 0,
        "items_without_bundle": 0,
        "items_misaligned_bundle": 0,
        "duplicates_removed": 0,
    }
    qualifier_counts: Dict[str, Dict[str, int]] = {
        name: {} for name in plan.targets.get("OUTPUT", [])
        if template.field_specs[name].type in _COUNTED_TYPES
    }
    pairs: List[AlpacaPair] = []
    seen: set = set()
    iterator = [n for n in (plan.iterator or ()) if n in plan.fields()]

    for item, source in _ordered_items(linked):
        counts["items"] += 1
        context = {name: _values(item, source, name, template) for name in plan.context}
        if iterator:
            per_field = {name: field_occurrences(item, name, template) for name in iterator}
            sizes = {len(v) for v in per_field.values()}
            if sizes == {0}:
                counts["items_without_bundle"] += 1
                continue
            if len(sizes) > 1:
                counts["items_misaligned_bundle"] += 1
                continue
            units = [
                {**context, **{name: [per_field[name][k]] for name in iterator}}
                for k in range(sizes.pop())
            ]
        else:
            units = [context]

        for unit in units:
            counts["units"] += 1
            output = _render_key(plan.targets.get("OUTPUT", []), unit, template)
            if not output:
                counts["skipped_empty_output"] += 1
                continue
            instruction = plan.instruction or _render_key(plan.targets.get("INSTRUCTION", []), unit, template)
            input_text = _render_key(plan.targets.get("INPUT", []), unit, template)
            key = (instruction, input_text, output)
            if key in seen:
                counts["duplicates_removed"] += 1
                continue
            seen.add(key)
            pairs.append({"instruction": instruction, "input": input_text, "output": output})
            for name, bucket in qualifier_counts.items():
                for value in unit.get(name, []):
                    text = _render_value(template, name, value)
                    if text:
                        bucket[text] = bucket.get(text, 0) + 1

    counts["lines"] = len(pairs)
    card = {
        "counts": counts,
        "qualifier_counts": {k: dict(sorted(v.items())) for k, v in qualifier_counts.items()},
    }
    return pairs, card


def export_alpaca_mapped(
    linked: LinkedProject,
    path: Path,
    template: TemplateNode,
    export: ExportNode,
) -> Dict[str, Any]:
    """Escreve o JSONL e o cartao ao lado (`<nome>.card.json`). Devolve o cartao."""
    plan = alpaca_plan(export, template)
    if plan is None:
        raise ValueError(f"{export.label}: no MAP or INSTRUCTION; not in declared mode")
    pairs, partial = build_mapped_pairs(linked, template, plan)

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for pair in pairs:
            fh.write(json.dumps(pair, ensure_ascii=False) + "\n")

    card = _card(linked, template, export, plan, partial, path)
    card_path = path.with_name(path.stem + ".card.json")
    card_path.write_text(json.dumps(card, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return card


# ---------------------------------------------------------------------------
# Leitura e renderizacao
# ---------------------------------------------------------------------------

def _ordered_items(linked: LinkedProject) -> List[Tuple[ItemNode, SourceNode]]:
    pairs = [(item, source) for source in linked.sources.values() for item in source.items]

    def key(entry: Tuple[ItemNode, SourceNode]) -> Tuple[str, int, int]:
        loc = entry[0].location
        if loc is None:
            return ("", 0, 0)
        return (Path(loc.file).as_posix(), loc.line, loc.column)

    return sorted(pairs, key=key)


def _values(item: ItemNode, source: SourceNode, name: str, template: TemplateNode) -> List[Any]:
    spec = template.field_specs[name]
    node = source if spec.scope.value == "SOURCE" else item
    return field_occurrences(node, name, template)


def _render_value(template: TemplateNode, name: str, value: Any) -> str:
    spec = template.field_specs[name]
    if value is None:
        return ""
    if spec.type == FieldType.CHAIN:
        if not isinstance(value, ChainNode):
            return str(value).strip()
        lines = []
        for a, rel, b in value.to_triples(bool(spec.relations)):
            lines.append(f"{a} → {b}" if rel == "IMPLICIT" else f"{a} → {rel} → {b}")
        return "\n".join(lines)
    if isinstance(value, (list, tuple)):
        return "; ".join(s for s in (str(v).strip() for v in value) if s)
    return str(value).strip()


def _render_field(template: TemplateNode, name: str, values: List[Any]) -> str:
    texts = [_render_value(template, name, v) for v in values]
    return "\n".join(t for t in texts if t)


def _render_key(names: List[str], unit: Dict[str, List[Any]], template: TemplateNode) -> str:
    """Texto de uma chave. Vazio quando todos os campos estao vazios na unidade."""
    rendered = [(name, _render_field(template, name, unit.get(name, []))) for name in names]
    rendered = [(name, text) for name, text in rendered if text]
    if not rendered:
        return ""
    if len(names) == 1:
        return rendered[0][1]
    blocks = []
    for name, text in rendered:
        if template.field_specs[name].type in _BLOCK_TYPES:
            blocks.append(f"{name}:\n{text}")
        else:
            blocks.append(f"{name}: {text}")
    return "\n".join(blocks)


# ---------------------------------------------------------------------------
# Cartao do dataset
# ---------------------------------------------------------------------------

def _sha256(file: Optional[Any]) -> Optional[str]:
    if not file:
        return None
    try:
        return hashlib.sha256(Path(file).read_bytes()).hexdigest()
    except OSError:
        return None


def _card(
    linked: LinkedProject,
    template: TemplateNode,
    export: ExportNode,
    plan: AlpacaPlan,
    partial: Dict[str, Any],
    path: Path,
) -> Dict[str, Any]:
    from synesis import __version__

    base = project_base_dir(linked)
    project_file = getattr(getattr(linked.project, "location", None), "file", None)
    template_file = getattr(template.location, "file", None) if template.location else None
    mapped = set(plan.fields())
    excluded = [
        name for name, spec in template.field_specs.items()
        if spec.scope.value in ("SOURCE", "ITEM") and name not in mapped
    ]
    return {
        "format": "alpaca",
        "synesis_version": __version__,
        "block": export.label,
        "output": relative_to_project(path, base),
        "project": {
            "file": relative_to_project(project_file, base) if project_file else None,
            "sha256": _sha256(project_file),
        },
        "template": {
            "file": relative_to_project(template_file, base) if template_file else None,
            "sha256": _sha256(template_file),
        },
        "composition": {
            "instruction": plan.instruction,
            "targets": {t: plan.targets.get(t, []) for t in ALPACA_TARGETS},
            "iterator_bundle": list(plan.iterator) if plan.iterator else None,
            "context_fields": plan.context,
            "unit": "bundle occurrence" if plan.iterator else "item",
        },
        **partial,
        "excluded_fields": excluded,
        "limitations": [
            "Indirect leakage (an OUTPUT text that repeats the INPUT) is not detected.",
            "Fields with an empty value in a unit are left out of the key text.",
        ],
    }
