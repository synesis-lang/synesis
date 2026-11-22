"""
_helpers.py - Funcoes compartilhadas pelos exportadores Synesis.

Extraidas de json_export.py, csv_export.py e xls_export.py para evitar duplicacao.
As quatro funcoes abaixo eram identicas nos tres exportadores.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from synesis.ast.nodes import FieldType, ItemNode, OntologyNode, Scope, SourceNode, TemplateNode
from synesis.semantic.occurrences import item_field_value, ontology_field_value


def _get_field_names_for_scope(template: TemplateNode, scope: Scope) -> List[str]:
    """Retorna nomes de campos do template preservando a ordem de definicao."""
    return [
        name
        for name, spec in template.field_specs.items()
        if spec.scope == scope
    ]


def _get_field_names_for_scope_and_types(
    template: TemplateNode,
    scope: Scope,
    field_types: set[FieldType],
) -> List[str]:
    """Retorna nomes de campos do template por escopo e tipos, mantendo ordem."""
    return [
        name
        for name, spec in template.field_specs.items()
        if spec.scope == scope and spec.type in field_types
    ]


def _get_item_field_value(item: ItemNode, name: str) -> Any:
    """Valor de um campo do ITEM pelo nome declarado (ver occurrences.item_field_value).

    `note` e `memo` escritos no mesmo ITEM devolvem cada um as próprias
    ocorrências; um nome roteado escrito mais de uma vez devolve todas.
    """
    return item_field_value(item, name, default="")


def _chain_to_text(chain: Any) -> str:
    """Forma legivel de um ChainNode: "a -> REL -> b" (ou "a -> b" sem relacao).

    Sem isto, um ChainNode cai no `str()` padrao do dataclass e a planilha
    recebe o `repr()` inteiro — nodes, relations, SourceLocation e WindowsPath —
    ilegivel para quem abre o arquivo. O JSON ja serializa como triplas; aqui a
    cadeia vira uma linha de texto porque a celula e escalar.
    """
    nodes = getattr(chain, "nodes", None)
    if not nodes:
        return ""
    return " -> ".join(str(n) for n in nodes)


def _get_source_field_value(
    source: SourceNode,
    name: str,
    template: Optional[TemplateNode] = None,
    bibliography: Optional[Dict[str, Any]] = None,
    dataset: Optional[Dict[str, Any]] = None,
) -> Any:
    """Valor de um campo SCOPE SOURCE respeitando a origem-de-valor do template.

    Um campo pode ter valor fora do bloco SOURCE: `ON BIBLIOGRAPHY` le da
    entrada .bib do proprio bibref, `ON DATASET` le do registro TOML via
    resolve_path(spec.dataset_path). Ler `source.fields` direto — como os
    exportadores tabulares faziam — devolve vazio para esses campos, embora o
    compilador, o validador e o link step os resolvam corretamente.

    Espelha `_resolve_field_values` de semantic/link_step.py. Em ambos, o valor
    ja presente no bloco SOURCE prevalece (a compilacao ja checou conflito).
    Sem template/fonte externa, degrada para o comportamento anterior.
    """
    in_source = source.fields.get(name)
    if in_source is not None:
        return in_source

    spec = template.field_specs.get(name) if template else None
    origin = getattr(spec, "value_origin", "document") if spec is not None else "document"

    if origin == "bibliography" and bibliography:
        from synesis.parser.bib_loader import find_bibref

        entry = find_bibref(bibliography, source.bibref.lstrip("@"))
        if entry:
            value = entry.get(name)
            if value is not None:
                return value
    elif origin == "dataset" and dataset:
        from synesis.parser.dataset_loader import find_record, resolve_path

        record = find_record(dataset, source.bibref.lstrip("@"))
        path = getattr(spec, "dataset_path", None)
        if record is not None and path:
            value = resolve_path(record, path)
            if value is not None:
                return value

    return ""


def _get_ontology_field_value(ontology: OntologyNode, name: str) -> Any:
    """Valor de um campo da ONTOLOGY pelo nome declarado (ver occurrences.ontology_field_value).

    Um CHAIN chamado `is_a`/`parent` volta pelo nome, como qualquer outro campo;
    o acessor não lhe atribui sentido de hierarquia.
    """
    return ontology_field_value(ontology, name, default="")


def project_base_dir(linked: Any) -> Optional[Path]:
    """Pasta do .synp: a base dos caminhos em todas as saídas (C-3).

    Caminhos relativos a ela não expõem a estrutura de pastas de quem exporta e
    fazem duas cópias do mesmo projeto gerarem a mesma saída. Um JSON gravado
    dentro da pasta do projeto encontra as anotações juntando a pasta do projeto
    (não a do JSON) com o caminho.
    """
    project = getattr(linked, "project", None)
    location = getattr(project, "location", None)
    file = getattr(location, "file", None)
    if not file:
        return None
    return Path(str(file)).resolve().parent


def relative_to_project(file: Any, base: Optional[Path]) -> str:
    """Caminho relativo à pasta do projeto, com barras normais.

    Arquivo fora da pasta (INCLUDE SHARED) fica com `../`. Sem base, ou em outro
    disco do Windows (não existe caminho relativo entre discos), o caminho segue
    como veio, com barras normais.
    """
    if file is None or str(file) == "":
        return ""
    path = Path(str(file))
    if base is None:
        return path.as_posix()
    try:
        return Path(os.path.relpath(path.resolve(), base)).as_posix()
    except ValueError:
        return path.as_posix()


def relativize_location_files(obj: Any, base: Optional[Path]) -> Any:
    """Torna relativos à pasta do projeto todos os valores de chave `file` (C-3).

    No JSON as chaves `file` são as de localização (`location`, `traceability`):
    projeto, includes, template e campos, ontologia e corpus.
    """
    if base is None:
        return obj
    if isinstance(obj, dict):
        return {
            key: (relative_to_project(value, base)
                  if key == "file" and isinstance(value, str) and value
                  else relativize_location_files(value, base))
            for key, value in obj.items()
        }
    if isinstance(obj, list):
        return [relativize_location_files(value, base) for value in obj]
    return obj

