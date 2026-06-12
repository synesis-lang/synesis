"""
alpaca_export.py - Exportador Alpaca JSONL do projeto Synesis (Camada 1)

Proposito:
    Gerar pares instrucao/input/output para fine-tuning de LLMs a partir
    de qualquer projeto Synesis. Opera deterministicamente sobre o LinkedProject
    sem dependencia de IA (Camada 1 estatica).

Componentes principais:
    - build_alpaca_pairs: gera lista de pares em memoria
    - export_alpaca: escreve JSONL em disco

Logica de geracao:
    - Template-driven: percorre cada FieldSpec e aplica padrao por tipo
    - BUNDLE-aware: emparelha campos posicionalmente (CHAIN+MEMO, QUOTATION+MEMO)
    - Agrega pares de indices pre-computados (all_triples, topic_index)
    - Instructions em ingles; descriptions dos campos preservadas no enunciado

Regras de descarte:
    - output vazio, None ou < 5 caracteres
    - par (instruction, output) ja gerado (deduplicacao exata)

Dependencias criticas:
    - synesis.semantic.linker: LinkedProject consolidado
    - synesis.ast.nodes: TemplateNode, FieldSpec, FieldType, Scope
    - synesis.exporters._helpers: funcoes compartilhadas

Gerado conforme: Especificacao Synesis v3.0
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from synesis.ast.nodes import (
    ChainNode,
    FieldSpec,
    FieldType,
    ItemNode,
    Scope,
    TemplateNode,
)
from synesis.exporters._helpers import (
    _get_item_field_value,
    _get_ontology_field_value,
)
from synesis.parser.bib_loader import BibEntry
from synesis.semantic.linker import LinkedProject

AlpacaPair = Dict[str, str]
_MIN_OUTPUT_LEN = 5


# ===========================================================================
# API publica
# ===========================================================================

def build_alpaca_pairs(
    linked: LinkedProject,
    template: Optional[TemplateNode] = None,
    bibliography: Optional[Dict[str, BibEntry]] = None,
) -> List[AlpacaPair]:
    """
    Gera pares Alpaca a partir do LinkedProject.

    Args:
        linked: Projeto vinculado com indices construidos
        template: Template opcional (None = modo legado, retorna lista vazia)
        bibliography: Entradas BibTeX (nao usado diretamente — campos SOURCE
                      estao em linked.sources[].fields)

    Returns:
        Lista de dicts {"instruction": str, "input": str, "output": str}
    """
    if not template:
        return []

    pairs: List[AlpacaPair] = []
    seen: Set[Tuple[str, str]] = set()

    bundle_map = _build_bundle_map(template, Scope.ITEM)
    quotation_field = _find_field_by_type(template, Scope.ITEM, FieldType.QUOTATION)
    chain_memo_bundles = _find_chain_memo_bundles(template, bundle_map)
    memo_in_chain_bundle = {memo for _chain, memo in chain_memo_bundles}

    # --- ITEM scope ---
    for name, spec in template.field_specs.items():
        if spec.scope != Scope.ITEM:
            continue

        if spec.type == FieldType.QUOTATION:
            # Gera pares QUOTATION+MEMO se existir bundle
            memo_partners = [
                p for p in bundle_map.get(name, [])
                if template.field_specs.get(p, None) and
                template.field_specs[p].type == FieldType.MEMO
            ]
            if memo_partners:
                _gen_quotation_memo_pairs(
                    linked, template, spec, name, memo_partners[0], pairs, seen
                )

        elif spec.type == FieldType.CHAIN:
            # Gera pares de chain (com memo bundled se existir)
            memo_partner = next(
                (p for p in bundle_map.get(name, [])
                 if template.field_specs.get(p) and
                 template.field_specs[p].type == FieldType.MEMO),
                None,
            )
            _gen_chain_pairs(
                linked, template, spec, name, memo_partner, quotation_field, pairs, seen
            )

        elif spec.type == FieldType.MEMO and name not in memo_in_chain_bundle:
            # MEMO nao bundled com CHAIN: gera pares autonomos
            _gen_memo_pairs(
                linked, template, spec, name, quotation_field, pairs, seen
            )

        elif spec.type == FieldType.CODE:
            _gen_code_pairs(
                linked, template, spec, name, quotation_field, pairs, seen
            )

    # --- ONTOLOGY scope ---
    for name, spec in template.field_specs.items():
        if spec.scope != Scope.ONTOLOGY:
            continue

        if spec.type == FieldType.TEXT:
            _gen_ontology_text_pairs(linked, spec, name, pairs, seen)
        elif spec.type in (FieldType.ENUMERATED, FieldType.ORDERED):
            _gen_ontology_classification_pairs(linked, spec, name, pairs, seen)
        elif spec.type == FieldType.SCALE:
            _gen_ontology_scale_pairs(linked, spec, name, pairs, seen)
        elif spec.type == FieldType.TOPIC:
            _gen_ontology_topic_pairs(linked, spec, name, pairs, seen)

    # --- SOURCE scope ---
    for name, spec in template.field_specs.items():
        if spec.scope == Scope.SOURCE and spec.type in (
            FieldType.TEXT, FieldType.MEMO, FieldType.QUOTATION
        ):
            _gen_source_text_pairs(linked, spec, name, pairs, seen, bibliography)

    # --- Pares agregados de indices ---
    _gen_aggregate_triple_pairs(linked, template, pairs, seen)
    _gen_topic_index_pairs(linked, template, pairs, seen)

    return pairs


def export_alpaca(
    linked: LinkedProject,
    output_path: Path,
    template: Optional[TemplateNode] = None,
    bibliography: Optional[Dict[str, BibEntry]] = None,
) -> None:
    """
    Exporta pares Alpaca para arquivo JSONL.

    Args:
        linked: Projeto vinculado com indices construidos
        output_path: Caminho do arquivo .jsonl de saida
        template: Template opcional
        bibliography: Entradas BibTeX opcionais
    """
    if not isinstance(output_path, Path):
        output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    pairs = build_alpaca_pairs(linked, template, bibliography)
    lines = [json.dumps(pair, ensure_ascii=False) for pair in pairs]
    output_path.write_text("\n".join(lines), encoding="utf-8")


# ===========================================================================
# Geradores por tipo de campo
# ===========================================================================

def _gen_quotation_memo_pairs(
    linked: LinkedProject,
    template: TemplateNode,
    spec: FieldSpec,
    field_name: str,
    memo_name: str,
    pairs: List[AlpacaPair],
    seen: Set[Tuple[str, str]],
) -> None:
    """QUOTATION + MEMO bundle: gera pares onde o memo explica o trecho."""
    memo_desc = _field_desc(template, memo_name) or "analytical memo"
    instruction = f"What is the analytical interpretation of the following passage? ({memo_desc})"

    for source in linked.sources.values():
        for item in source.items:
            quotes = _as_list(_get_item_field_value(item, field_name))
            memos = _as_list(_get_item_field_value(item, memo_name))
            for quote, memo in zip(quotes, memos):
                inp = _str(quote)
                out = _str(memo)
                if not inp or not out:
                    continue
                _add(pairs, seen, instruction, inp, out)


def _gen_chain_pairs(
    linked: LinkedProject,
    template: TemplateNode,
    spec: FieldSpec,
    field_name: str,
    memo_partner: Optional[str],
    quotation_field: Optional[str],
    pairs: List[AlpacaPair],
    seen: Set[Tuple[str, str]],
) -> None:
    """CHAIN field: gera pares de triplas causais com memo e contexto."""
    has_relations = bool(spec.relations)
    field_desc = spec.description or field_name

    # Instrucao varia se ha relacoes qualificadas ou simples
    if has_relations:
        instruction = (
            "Identify the causal mechanism or relationship illustrated in the "
            f"passage below. ({field_desc})"
        )
    else:
        instruction = (
            f"What relationship is illustrated in the passage below? ({field_desc})"
        )

    for source in linked.sources.values():
        for item in source.items:
            chains = _as_list(_get_item_field_value(item, field_name))
            memos = _as_list(_get_item_field_value(item, memo_partner)) if memo_partner else []
            quote = _get_quote(item, quotation_field)

            for idx, chain in enumerate(chains):
                if not isinstance(chain, ChainNode):
                    continue
                triples = chain.to_triples(has_relations)
                if not triples:
                    continue

                # Formata tripla principal
                from_c, rel, to_c = triples[0]
                triple_str = f"{from_c} -> {rel} -> {to_c}"

                # Memo emparelhado (se existir)
                memo_str = _str(memos[idx]) if idx < len(memos) else ""
                if memo_str:
                    output = f"{triple_str}. {memo_str}"
                else:
                    output = triple_str

                _add(pairs, seen, instruction, quote, output)


def _gen_memo_pairs(
    linked: LinkedProject,
    template: TemplateNode,
    spec: FieldSpec,
    field_name: str,
    quotation_field: Optional[str],
    pairs: List[AlpacaPair],
    seen: Set[Tuple[str, str]],
) -> None:
    """MEMO autonomo (sem bundle com CHAIN): gera pares de interpretacao."""
    field_desc = spec.description or field_name
    instruction = f"Provide an analytical interpretation of the passage below. ({field_desc})"

    for source in linked.sources.values():
        for item in source.items:
            memos = _as_list(_get_item_field_value(item, field_name))
            quote = _get_quote(item, quotation_field)
            for memo in memos:
                out = _str(memo)
                if not out:
                    continue
                _add(pairs, seen, instruction, quote, out)


def _gen_code_pairs(
    linked: LinkedProject,
    template: TemplateNode,
    spec: FieldSpec,
    field_name: str,
    quotation_field: Optional[str],
    pairs: List[AlpacaPair],
    seen: Set[Tuple[str, str]],
) -> None:
    """CODE field: gera pares de codificacao conceitual."""
    field_desc = spec.description or field_name
    instruction = (
        f"Which concepts are attributed to the following passage? ({field_desc})"
    )

    for source in linked.sources.values():
        for item in source.items:
            codes = _as_list(_get_item_field_value(item, field_name))
            if not codes:
                continue
            code_strs = [_str(c) for c in codes if _str(c)]
            if not code_strs:
                continue
            quote = _get_quote(item, quotation_field)
            output = ", ".join(code_strs)
            _add(pairs, seen, instruction, quote, output)


def _gen_ontology_text_pairs(
    linked: LinkedProject,
    spec: FieldSpec,
    field_name: str,
    pairs: List[AlpacaPair],
    seen: Set[Tuple[str, str]],
) -> None:
    """TEXT (ONTOLOGY): pares de definicao conceitual."""
    field_desc = spec.description or field_name
    instruction_template = (
        "In the context of this project, define the concept '{{concept}}'. ({desc})"
    ).format(desc=field_desc)

    for ontology in linked.ontology_index.values():
        val = _str(_get_ontology_field_value(ontology, field_name))
        if not val:
            continue
        instruction = instruction_template.replace("{concept}", ontology.concept)
        _add(pairs, seen, instruction, "", val)


_SENTINEL_LABELS = {"undefined", "none", "n/a", "not available", "na"}
_ORDERED_ABBREVIATED_THRESHOLD = 6


def _is_sentinel_value(v) -> bool:
    """Retorna True se o valor é um sentinela estrutural (ex: Undefined, N/A)."""
    if v.index == 0:
        return True
    label_lower = v.label.strip().lower()
    return label_lower in _SENTINEL_LABELS


def _gen_ontology_classification_pairs(
    linked: LinkedProject,
    spec: FieldSpec,
    field_name: str,
    pairs: List[AlpacaPair],
    seen: Set[Tuple[str, str]],
) -> None:
    """ENUMERATED / ORDERED: pares de classificacao com opcoes listadas."""
    field_desc = spec.description or field_name
    values_list = spec.values or []

    if not values_list:
        return

    # Filtra sentinelas (Undefined, N/A, index 0) — nao sao alvos validos de classificacao
    meaningful_values = [v for v in values_list if not _is_sentinel_value(v)]
    if not meaningful_values:
        return

    if spec.type == FieldType.ORDERED:
        # Para listas longas, usar forma abreviada com exemplos (evita instrucoes densas)
        if len(meaningful_values) > _ORDERED_ABBREVIATED_THRESHOLD:
            sample = [v.label for v in meaningful_values[:3]] + [meaningful_values[-1].label]
            examples_str = ", ".join(sample[:-1]) + f", ..., {sample[-1]}"
            instruction_tmpl = (
                "Classify the concept '{concept}' into the most appropriate level of "
                f"'{field_desc}' (e.g., {examples_str})."
            )
        else:
            options_str = "; ".join(
                f"{v.label}: {v.description}" if v.description else v.label
                for v in meaningful_values
            )
            instruction_tmpl = (
                "Rate '{{concept}}' on the scale '{desc}'. Levels: {opts}"
            ).format(desc=field_desc, opts=options_str)
    else:
        options_str = "; ".join(
            f"{v.label}: {v.description}" if v.description else v.label
            for v in meaningful_values
        )
        instruction_tmpl = (
            "Classify '{{concept}}' according to '{desc}'. Options: {opts}"
        ).format(desc=field_desc, opts=options_str)

    for ontology in linked.ontology_index.values():
        raw = _get_ontology_field_value(ontology, field_name)
        if raw is None or raw == "" or raw == []:
            continue

        # Resolve label from index value
        if isinstance(raw, int) and values_list:
            matched = next((v for v in values_list if v.index == raw), None)
            if matched:
                # Descarta se o valor anotado for o sentinela
                if _is_sentinel_value(matched):
                    continue
                output = f"{matched.label}: {matched.description}" if matched.description else matched.label
            else:
                output = str(raw)
        else:
            output = _str(raw)

        if not output:
            continue

        instruction = instruction_tmpl.replace("{concept}", ontology.concept)
        _add(pairs, seen, instruction, "", output)


def _gen_ontology_scale_pairs(
    linked: LinkedProject,
    spec: FieldSpec,
    field_name: str,
    pairs: List[AlpacaPair],
    seen: Set[Tuple[str, str]],
) -> None:
    """SCALE: pares numericos com intervalo."""
    field_desc = spec.description or field_name
    fmt = spec.format or ""
    m = re.search(r"\[(\d+)\.\.(\d+)\]", fmt)
    if m:
        min_v, max_v = m.group(1), m.group(2)
        range_str = f"from {min_v} to {max_v}"
    else:
        range_str = "numeric"

    instruction_tmpl = (
        "On a scale {range} for '{desc}', what is the value for '{{concept}}'?"
    ).format(range=range_str, desc=field_desc)

    for ontology in linked.ontology_index.values():
        raw = _get_ontology_field_value(ontology, field_name)
        if raw is None or raw == "":
            continue
        output = str(raw)
        if not output or output == "0":
            continue
        instruction = instruction_tmpl.replace("{concept}", ontology.concept)
        _add(pairs, seen, instruction, "", output)


def _gen_ontology_topic_pairs(
    linked: LinkedProject,
    spec: FieldSpec,
    field_name: str,
    pairs: List[AlpacaPair],
    seen: Set[Tuple[str, str]],
) -> None:
    """TOPIC: pares de categorizacao tematica."""
    field_desc = spec.description or field_name
    instruction_tmpl = (
        "What thematic category does the concept '{{concept}}' belong to? ({desc})"
    ).format(desc=field_desc)

    for ontology in linked.ontology_index.values():
        val = _str(_get_ontology_field_value(ontology, field_name))
        if not val:
            continue
        instruction = instruction_tmpl.replace("{concept}", ontology.concept)
        _add(pairs, seen, instruction, "", val)


def _gen_source_text_pairs(
    linked: LinkedProject,
    spec: FieldSpec,
    field_name: str,
    pairs: List[AlpacaPair],
    seen: Set[Tuple[str, str]],
    bibliography: Optional[Dict[str, "BibEntry"]] = None,
) -> None:
    """TEXT/MEMO/QUOTATION (SOURCE): pares de metadados bibliograficos."""
    field_desc = spec.description or field_name
    for bibref, source in linked.sources.items():
        val = _str(source.fields.get(field_name))
        if not val:
            continue
        citation = _format_citation(bibref, bibliography)
        instruction = f"Regarding {citation}, describe: {field_desc}"
        _add(pairs, seen, instruction, "", val)


def _format_citation(
    bibref: str,
    bibliography: Optional[Dict[str, "BibEntry"]],
) -> str:
    """
    Formata citacao bibliografica legivel para instrucoes de SOURCE.

    Retorna formato: "Author et al. (Year) – 'Title truncated...'"
    Fallback: chave normalizada se a entrada nao estiver na bibliografia.
    """
    key = bibref.lstrip("@")
    if not bibliography:
        return f"'{key}'"

    # Tenta correspondencia direta ou normalizada
    entry = bibliography.get(key) or bibliography.get(bibref)
    if entry is None:
        # Busca case-insensitive
        key_lower = key.lower()
        for k, v in bibliography.items():
            if k.lower().lstrip("@") == key_lower:
                entry = v
                break

    if entry is None:
        return f"'{key}'"

    # Extrai campos — BibEntry pode ser dict ou objeto com atributos
    def _get(field: str) -> str:
        if isinstance(entry, dict):
            return str(entry.get(field) or entry.get(field.upper()) or "").strip()
        return str(getattr(entry, field, "") or "").strip()

    authors_raw = _get("author")
    title_raw = _get("title")
    year_raw = _get("year")

    # Formata autores: "Last, F. and Last2, F." → "Last et al." ou "Last and Last2"
    authors_str = _format_authors(authors_raw) if authors_raw else key

    # Trunca titulo em 60 chars
    if title_raw and len(title_raw) > 60:
        title_str = title_raw[:57].rstrip() + "..."
    elif title_raw:
        title_str = title_raw
    else:
        title_str = ""

    parts = [authors_str]
    if year_raw:
        parts[0] = f"{authors_str} ({year_raw})"
    if title_str:
        parts.append(f"'{title_str}'")

    return " – ".join(parts) if len(parts) > 1 else parts[0]


def _format_authors(authors_raw: str) -> str:
    """
    Formata string de autores BibTeX para citacao curta.

    "Smith, John and Doe, Jane and Brown, Bob" → "Smith et al."
    "Smith, John and Doe, Jane" → "Smith and Doe"
    "Smith, John" → "Smith"
    """
    # Separa por " and " (BibTeX padrao)
    parts = [a.strip() for a in re.split(r"\s+and\s+", authors_raw, flags=re.IGNORECASE) if a.strip()]
    if not parts:
        return authors_raw

    def _last_name(author: str) -> str:
        # "Last, First" → "Last"  |  "First Last" → "Last"
        if "," in author:
            return author.split(",")[0].strip()
        tokens = author.split()
        return tokens[-1] if tokens else author

    last_names = [_last_name(a) for a in parts]

    if len(last_names) == 1:
        return last_names[0]
    if len(last_names) == 2:
        return f"{last_names[0]} and {last_names[1]}"
    return f"{last_names[0]} et al."


def _gen_aggregate_triple_pairs(
    linked: LinkedProject,
    template: Optional[TemplateNode],
    pairs: List[AlpacaPair],
    seen: Set[Tuple[str, str]],
) -> None:
    """Pares agregados a partir de all_triples, agrupados por conceito destino."""
    if not linked.all_triples:
        return

    # Agrupa triples por conceito alvo
    by_target: Dict[str, List[Tuple[str, str, str]]] = {}
    for from_c, rel, to_c in linked.all_triples:
        by_target.setdefault(to_c, []).append((from_c, rel, to_c))

    for concept, triples in by_target.items():
        # Deduplica triples pelo par (from, rel)
        seen_triples: set = set()
        unique = []
        for t in triples:
            key = (t[0], t[1])
            if key not in seen_triples:
                seen_triples.add(key)
                unique.append(t)

        if len(unique) < 2:
            continue

        instruction = (
            f"According to the corpus annotations, what factors and "
            f"relationships involve the concept '{concept}'?"
        )
        lines = [f"{f} -> {r} -> {t}" for f, r, t in unique]
        output = "\n".join(lines)
        _add(pairs, seen, instruction, "", output)


_TOPIC_INDEX_CHUNK_SIZE = 15


def _gen_topic_index_pairs(
    linked: LinkedProject,
    template: Optional[TemplateNode],
    pairs: List[AlpacaPair],
    seen: Set[Tuple[str, str]],
) -> None:
    """Pares agregados a partir de topic_index, com divisao para topicos grandes."""
    if not linked.topic_index:
        return

    for topic, concepts in linked.topic_index.items():
        if len(concepts) < 2:
            continue

        sorted_concepts = sorted(concepts)

        if len(sorted_concepts) <= _TOPIC_INDEX_CHUNK_SIZE:
            instruction = (
                f"Which concepts in this project belong to the thematic "
                f"category '{topic}'?"
            )
            output = ", ".join(sorted_concepts)
            _add(pairs, seen, instruction, "", output)
        else:
            # Divide em partes de _TOPIC_INDEX_CHUNK_SIZE para facilitar o aprendizado
            chunks = [
                sorted_concepts[i:i + _TOPIC_INDEX_CHUNK_SIZE]
                for i in range(0, len(sorted_concepts), _TOPIC_INDEX_CHUNK_SIZE)
            ]
            total = len(chunks)
            for idx, chunk in enumerate(chunks, start=1):
                instruction = (
                    f"Which concepts in this project belong to the thematic "
                    f"category '{topic}'? (part {idx} of {total})"
                )
                output = ", ".join(chunk)
                _add(pairs, seen, instruction, "", output)


# ===========================================================================
# Utilitarios internos
# ===========================================================================

def _add(
    pairs: List[AlpacaPair],
    seen: Set[Tuple[str, str]],
    instruction: str,
    input_text: str,
    output: str,
) -> None:
    """Adiciona par se output valido e nao duplicado."""
    output = output.strip()
    if not output or len(output) < _MIN_OUTPUT_LEN:
        return
    key = (instruction.strip(), output)
    if key in seen:
        return
    seen.add(key)
    pairs.append({
        "instruction": instruction.strip(),
        "input": (input_text or "").strip(),
        "output": output,
    })


def _build_bundle_map(template: TemplateNode, scope: Scope) -> Dict[str, List[str]]:
    """Mapeia campo -> lista de parceiros de bundle no mesmo scope."""
    result: Dict[str, List[str]] = {}
    for bundle in template.bundled_fields.get(scope, []):
        for name in bundle:
            result[name] = [other for other in bundle if other != name]
    return result


def _find_field_by_type(
    template: TemplateNode,
    scope: Scope,
    field_type: FieldType,
) -> Optional[str]:
    """Retorna o nome do primeiro campo do tipo e scope dados."""
    for name, spec in template.field_specs.items():
        if spec.scope == scope and spec.type == field_type:
            return name
    return None


def _find_chain_memo_bundles(
    template: TemplateNode,
    bundle_map: Dict[str, List[str]],
) -> List[Tuple[str, str]]:
    """Retorna lista de (chain_field, memo_field) onde os dois sao bundled."""
    result = []
    for name, spec in template.field_specs.items():
        if spec.scope == Scope.ITEM and spec.type == FieldType.CHAIN:
            for partner in bundle_map.get(name, []):
                partner_spec = template.field_specs.get(partner)
                if partner_spec and partner_spec.type == FieldType.MEMO:
                    result.append((name, partner))
    return result


def _get_quote(item: ItemNode, quotation_field: Optional[str]) -> str:
    """Retorna o texto da QUOTATION do item, ou string vazia."""
    if not quotation_field:
        return ""
    val = _get_item_field_value(item, quotation_field)
    return _str(val) or ""


def _field_desc(template: TemplateNode, field_name: str) -> Optional[str]:
    """Retorna a description de um campo do template."""
    spec = template.field_specs.get(field_name)
    return spec.description if spec else None


def _as_list(value: Any) -> List[Any]:
    """Normaliza valor para lista."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _str(value: Any) -> str:
    """Converte valor para string, retorna '' se vazio/None."""
    if value is None:
        return ""
    if isinstance(value, ChainNode):
        # Fallback para chain como texto (nao deveria ser usado diretamente)
        return " -> ".join(value.nodes)
    if isinstance(value, list):
        parts = [_str(v) for v in value]
        return "; ".join(p for p in parts if p)
    s = str(value).strip()
    return s
