"""
occurrences.py - Valor de campo por ocorrência e acessor por nome declarado

Propósito:
    Ler o valor de um campo de SOURCE/ITEM/ONTOLOGY pela ocorrência escrita no
    arquivo, e não por um atributo que funde ocorrências. Cada nó guarda em
    `entries` a lista ordenada das ocorrências (FieldEntry) tal como o
    transformer as produziu; daqui saem os valores por campo e por ocorrência.

Componentes principais:
    - field_occurrences: valores de um campo, um por ocorrência, pelo TIPO
    - item_field_value: acessor do ITEM pelo nome declarado no template
    - item_chains: cadeias de todo campo CHAIN do ITEM, com o modo do campo
    - ontology_field_value: acessor da ONTOLOGY pelo nome declarado
    - raw_item_fields: valores do ITEM no estado do transformer (validador)
    - _parse_code_lines / _parse_chain_lines: leitura de linhas TEXT_LINE

Dependências críticas:
    - synesis.ast.nodes: FieldEntry, nós da AST e ChainNode

Exemplo de uso:
    from synesis.semantic.occurrences import field_occurrences
    for codes in field_occurrences(item, "rotulos", template):
        ...  # lista de códigos de UMA ocorrência do campo

Notas de implementação:
    - O transformer não conhece o template: um CODE de nome livre chega como
      texto ("X, Y") com as linhas brutas em FieldEntry.lines. O tipo resolve.
    - Os nomes quote/code/note/memo/chain (e plurais) têm atributos próprios no
      ItemNode que FUNDEM ocorrências (note e memo vão juntos para `notes`).
      O acessor lê primeiro as ocorrências do nome exato; o atributo fundido só
      responde quando o nome não foi escrito (compatibilidade).
    - Nada aqui modifica os nós: o parse_cache devolve os mesmos objetos a cada
      compilação, e ler não pode mudar o que a próxima leitura vê.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from lark import Token

from synesis.ast.nodes import (
    ChainNode,
    FieldEntry,
    FieldType,
    ItemNode,
    OntologyNode,
    Scope,
    SourceLocation,
    SourceNode,
    TemplateNode,
)

# Nome do campo -> atributo do ItemNode que o transformer preenche por NOME.
ITEM_ROUTED_ATTRS: Dict[str, str] = {
    "quote": "quote",
    "quotation": "quote",
    "code": "codes",
    "codes": "codes",
    "note": "notes",
    "notes": "notes",
    "memo": "notes",
    "memos": "notes",
    "chain": "chains",
    "chains": "chains",
}


def _token_location(file_path: Path, token: Token, offset: int = 0) -> SourceLocation:
    return SourceLocation(
        file=file_path,
        line=getattr(token, "line", 1),
        column=max(1, getattr(token, "column", 1) + offset),
    )


def _split_codes_from_line(file_path: Path, token: Token) -> Tuple[List[str], List[SourceLocation]]:
    text = str(token)
    values: List[str] = []
    locations: List[SourceLocation] = []
    start = 0
    while start <= len(text):
        comma_idx = text.find(",", start)
        if comma_idx == -1:
            segment = text[start:]
        else:
            segment = text[start:comma_idx]
        trimmed = segment.strip()
        if trimmed:
            leading_ws = len(segment) - len(segment.lstrip())
            offset = start + leading_ws
            values.append(trimmed)
            locations.append(_token_location(file_path, token, offset))
        if comma_idx == -1:
            break
        start = comma_idx + 1
    return values, locations


def _split_chain_from_line(file_path: Path, token: Token) -> Tuple[List[str], List[SourceLocation]]:
    text = str(token)
    nodes: List[str] = []
    locations: List[SourceLocation] = []
    start = 0
    while start <= len(text):
        arrow_idx = text.find("->", start)
        if arrow_idx == -1:
            segment = text[start:]
        else:
            segment = text[start:arrow_idx]
        trimmed = segment.strip()
        if trimmed:
            leading_ws = len(segment) - len(segment.lstrip())
            offset = start + leading_ws
            nodes.append(trimmed)
            locations.append(_token_location(file_path, token, offset))
        if arrow_idx == -1:
            break
        start = arrow_idx + 2
    return nodes, locations


def _parse_code_lines(file_path: Path, lines: List[Any]) -> Tuple[List[str], List[SourceLocation]]:
    values: List[str] = []
    locations: List[SourceLocation] = []
    for line in lines:
        if isinstance(line, Token):
            parsed_values, parsed_locations = _split_codes_from_line(file_path, line)
            values.extend(parsed_values)
            locations.extend(parsed_locations)
        else:
            for part in str(line).split(","):
                part = part.strip()
                if part:
                    values.append(part)
    return values, locations


def _parse_chain_lines(file_path: Path, lines: List[Any], location: SourceLocation) -> ChainNode:
    nodes: List[str] = []
    locations: List[SourceLocation] = []
    for line in lines:
        if isinstance(line, Token):
            parsed_nodes, parsed_locations = _split_chain_from_line(file_path, line)
            nodes.extend(parsed_nodes)
            locations.extend(parsed_locations)
        else:
            for part in str(line).split("->"):
                part = part.strip()
                if part:
                    nodes.append(part)
    return ChainNode(
        nodes=nodes,
        relations=[],
        location=location,
        node_locations=locations if locations else None,
    )


Node = SourceNode | ItemNode | OntologyNode


def entries_named(node: Node, name: str) -> List[FieldEntry]:
    """Ocorrências escritas do campo `name` (nome exato), na ordem do arquivo."""
    return [entry for entry in getattr(node, "entries", None) or [] if entry.name == name]


def resolve_occurrence(entry: FieldEntry, field_type: Optional[FieldType]) -> Any:
    """Valor de UMA ocorrência interpretado pelo tipo do campo.

    CODE vira a lista de códigos daquela ocorrência (em qualquer escopo); CHAIN
    vira ChainNode quando o texto é uma cadeia. Os demais tipos voltam como o
    transformer os produziu.
    """
    value = entry.value
    file_path = entry.file or Path("<unknown>")
    if field_type == FieldType.CODE:
        if entry.lines:
            codes, _locations = _parse_code_lines(file_path, entry.lines)
            return codes
        if isinstance(value, list):
            return [str(code) for code in value]
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return [str(value)]
    if field_type == FieldType.CHAIN:
        if isinstance(value, ChainNode):
            return value
        if entry.lines:
            chain = _parse_chain_lines(file_path, entry.lines, entry.location)
            if chain.nodes:
                return chain
        return value
    return value


def field_occurrences(node: Node, name: str, template: Optional[TemplateNode] = None) -> List[Any]:
    """Valores do campo `name` no nó, UM POR OCORRÊNCIA escrita, pelo tipo.

    É a leitura que preserva multiplicidade e fronteira de ocorrência: dois
    `rotulos:` no mesmo ITEM dão duas listas de códigos, e o k-ésimo elemento
    de cada membro de um BUNDLE forma o k-ésimo par. Campos com valor fora do
    bloco (ON BIBLIOGRAPHY, ON DATASET) não têm ocorrência escrita.
    """
    spec = template.field_specs.get(name) if template else None
    field_type = spec.type if spec else None
    return [resolve_occurrence(entry, field_type) for entry in entries_named(node, name)]


def _routed_item_value(item: ItemNode, name: str) -> Any:
    """Valor de um nome roteado pelas ocorrências do NOME EXATO, na forma legada.

    Devolve None quando o nome não foi escrito no ITEM (o chamador usa então o
    atributo fundido, como antes). quote: texto, ou lista se escrito mais de
    uma vez; code: lista plana de códigos; note/memo: lista de textos; chain:
    lista de ChainNode.
    """
    attr = ITEM_ROUTED_ATTRS.get(name.lower())
    occurrences = entries_named(item, name)
    if attr is None or not occurrences:
        return None
    if attr == "quote":
        texts = [str(entry.value) for entry in occurrences]
        return texts[0] if len(texts) == 1 else texts
    if attr == "codes":
        codes: List[str] = []
        for entry in occurrences:
            if isinstance(entry.value, list):
                codes.extend(str(code) for code in entry.value)
            else:
                codes.append(str(entry.value))
        return codes
    if attr == "notes":
        notes: List[str] = []
        for entry in occurrences:
            if isinstance(entry.value, list):
                notes.extend(str(note) for note in entry.value)
            else:
                notes.append(str(entry.value))
        return notes
    # Sem nenhuma cadeia válida (ex.: texto sem seta), o nome conta como não
    # escrito, como no transformer, que não põe nada em `item.chains`.
    chains = [entry.value for entry in occurrences if isinstance(entry.value, ChainNode)]
    return chains or None


def item_field_value(item: ItemNode, name: str, default: Any = None) -> Any:
    """Valor de um campo do ITEM pelo nome DECLARADO no template.

    Ordem: `extra_fields` (nomes livres); ocorrências do nome exato (nomes
    roteados: `note` não devolve o que foi escrito em `memo`); atributo fundido
    do ItemNode quando o nome não foi escrito; `default`.
    """
    value = item.extra_fields.get(name)
    if value is not None:
        return value
    routed = _routed_item_value(item, name)
    if routed is not None:
        return routed
    attr = ITEM_ROUTED_ATTRS.get(name.lower())
    if attr is not None:
        return getattr(item, attr)
    return default


def ontology_field_value(ontology: OntologyNode, name: str, default: Any = None) -> Any:
    """Valor de um campo da ONTOLOGY pelo nome DECLARADO, sem atribuir sentido.

    O transformer desvia por NOME: `description` vai para `ontology.description`
    e `parent`/`parents`/`is_a`/`isa` para `ontology.parent_chains`, fora de
    `fields`. Lidos pelo nome, esses campos sumiam do acessor. Aqui eles voltam
    pelas ocorrências do nome exato — uma CHAIN de qualquer nome é só o seu
    valor; dizer que ela é hierarquia (IS_A) é decisão de linguagem, não deste
    acessor. Ocorrência única devolve o valor; repetida, a lista.
    """
    value = ontology.fields.get(name)
    if value is not None:
        return value
    occurrences = entries_named(ontology, name)
    if occurrences:
        values = [entry.value for entry in occurrences]
        return values[0] if len(values) == 1 else values
    lname = name.lower()
    if lname == "description":
        return ontology.description
    if lname == "concept":
        return ontology.concept
    return default


def item_chains(
    item: ItemNode, template: Optional[TemplateNode], default_qualified: bool
) -> List[Tuple[ChainNode, bool]]:
    """Cadeias do ITEM, de TODOS os campos CHAIN do template, pelo TIPO.

    Cada cadeia sai com o modo do SEU campo (qualificada se o campo declara
    RELATIONS): com dois CHAIN de configurações diferentes, um flag global
    leria a cadeia simples como qualificada. Sem template, ou sem campo CHAIN
    declarado, vale `item.chains` com `default_qualified`, como antes.

    Returns:
        Lista de (cadeia, qualificada), sem repetir a mesma cadeia.
    """
    chain_fields = []
    if template:
        chain_fields = [
            (name, spec)
            for name, spec in template.field_specs.items()
            if spec.scope == Scope.ITEM and spec.type == FieldType.CHAIN
        ]
    if not chain_fields:
        return [(chain, default_qualified) for chain in item.chains]

    out: List[Tuple[ChainNode, bool]] = []
    seen: set = set()
    for name, spec in chain_fields:
        raw = item_field_value(item, name)
        values = raw if isinstance(raw, list) else [raw]
        for chain in values:
            if isinstance(chain, ChainNode) and id(chain) not in seen:
                seen.add(id(chain))
                out.append((chain, bool(spec.relations)))
    # Cadeia em item.chains que nenhum campo declarado cobriu: modo anterior.
    for chain in item.chains:
        if id(chain) not in seen:
            seen.add(id(chain))
            out.append((chain, default_qualified))
    return out


def _accumulate(fields: Dict[str, Any], name: str, value: Any) -> None:
    """Acumula como o transformer (`_add_field`), sem compartilhar listas."""
    if isinstance(value, list):
        value = list(value)
    if name in fields:
        existing = fields[name]
        if isinstance(existing, list):
            existing.append(value)
        else:
            fields[name] = [existing, value]
    else:
        fields[name] = value


def raw_item_fields(item: ItemNode) -> Optional[Dict[str, Any]]:
    """Campos do ITEM no estado do transformer, lidos das ocorrências.

    Para nomes livres, é o que o transformer pôs em `extra_fields` (antes de o
    linker reinterpretar CODE/CHAIN pelo tipo). Para nomes roteados, o valor do
    nome exato. Devolve None quando o nó não tem `entries` (construído à mão).
    """
    if not getattr(item, "entries", None):
        return None
    fields: Dict[str, Any] = {}
    for entry in item.entries:
        if entry.name.lower() in ITEM_ROUTED_ATTRS:
            continue
        _accumulate(fields, entry.name, entry.value)
    for entry in item.entries:
        if entry.name.lower() in ITEM_ROUTED_ATTRS and entry.name not in fields:
            fields[entry.name] = _routed_item_value(item, entry.name)
    return fields
