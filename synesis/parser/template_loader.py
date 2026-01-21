"""
template_loader.py - Carregamento e validacao de templates Synesis

Proposito:
    Ler arquivos .synt, parsear com Lark e construir TemplateNode.
    Valida listas REQUIRED/OPTIONAL/FORBIDDEN e processa bundles.

Componentes principais:
    - load_template: funcao principal de carga e validacao
    - TemplateLoadError: erro com localizacao quando disponivel

Dependencias criticas:
    - synesis.parser.lexer: parser Lark
    - synesis.parser.transformer: conversao para AST parcial
    - synesis.ast.nodes: FieldSpec, TemplateNode, Scope, FieldType

Exemplo de uso:
    from synesis.parser.template_loader import load_template
    template = load_template("modelo.synt")

Notas de implementacao:
    - Campos em bundles nao entram em required_fields.
    - Campos listados devem existir em FIELD.

Gerado conforme: Especificacao Synesis v1.1
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from synesis.ast.nodes import FieldSpec, FieldType, Scope, SourceLocation, TemplateNode
from synesis.parser.lexer import parse_file, parse_string
from synesis.parser.transformer import SynesisTransformer


@dataclass
class TemplateLoadError(Exception):
    message: str
    location: SourceLocation

    def __str__(self) -> str:
        return f"{self.location}: {self.message}"


def load_template(path: Path | str) -> TemplateNode:
    """
    Carrega e valida arquivo .synt do disco.

    - Parseia usando a gramatica Lark
    - Construi dicionario de FieldSpec
    - Processa REQUIRED/OPTIONAL/FORBIDDEN e BUNDLE
    - Valida referencias a campos inexistentes

    Args:
        path: Caminho para o arquivo .synt

    Returns:
        TemplateNode validado e pronto para uso

    Raises:
        TemplateLoadError: Se houver erro de validacao no template
        SynesisSyntaxError: Se houver erro de sintaxe no arquivo
    """
    file_path = Path(path)
    content = file_path.read_text(encoding="utf-8")
    return _load_template_impl(content, str(file_path))


def load_template_from_string(content: str, filename: str = "<template>") -> TemplateNode:
    """
    Carrega e valida template a partir de string em memoria.

    Reutiliza a logica de load_template() sem dependencia de I/O em disco.
    Ideal para uso em Jupyter Notebooks, LSP e testes.

    Args:
        content: Conteudo do arquivo .synt como string
        filename: Nome virtual para mensagens de erro (default: "<template>")

    Returns:
        TemplateNode validado e pronto para uso

    Raises:
        TemplateLoadError: Se houver erro de validacao no template
        SynesisSyntaxError: Se houver erro de sintaxe no conteudo

    Example:
        >>> template = load_template_from_string('''
        ...     TEMPLATE Demo
        ...     SOURCE FIELDS
        ...         REQUIRED date
        ...     END SOURCE FIELDS
        ...     FIELD date TYPE DATE SCOPE SOURCE END FIELD
        ... ''')
    """
    return _load_template_impl(content, filename)


def _load_template_impl(content: str, filename: str) -> TemplateNode:
    """Implementacao compartilhada para load_template e load_template_from_string."""
    file_path = Path(filename)
    tree = parse_string(content, filename)
    transformer = SynesisTransformer(file_path)
    nodes = transformer.transform(tree)

    header = None
    field_specs: Dict[str, FieldSpec] = {}
    field_specs_order: List[FieldSpec] = []
    spec_blocks: List[Dict[str, object]] = []

    for node in nodes:
        if isinstance(node, dict) and "name" in node and "metadata" in node:
            header = node
        elif isinstance(node, dict) and "scope" in node:
            spec_blocks.append(node)
        elif isinstance(node, FieldSpec):
            field_specs_order.append(node)

    for spec in field_specs_order:
        if spec.name in field_specs:
            location = spec.location or SourceLocation(file_path, 1, 1)
            raise TemplateLoadError(
                message=f"Campo FIELD duplicado: '{spec.name}'",
                location=location,
            )
        if spec.type == FieldType.ORDERED and spec.values:
            for value in spec.values:
                if value.index < 0:
                    raise TemplateLoadError(
                        message=f"ORDERED exige indice em VALUES: '{spec.name}'",
                        location=value.location,
                    )
        field_specs[spec.name] = spec

    required_fields: Dict[Scope, List[str]] = {
        Scope.SOURCE: [],
        Scope.ITEM: [],
        Scope.ONTOLOGY: [],
    }
    optional_fields: Dict[Scope, List[str]] = {
        Scope.SOURCE: [],
        Scope.ITEM: [],
        Scope.ONTOLOGY: [],
    }
    forbidden_fields: Dict[Scope, List[str]] = {
        Scope.SOURCE: [],
        Scope.ITEM: [],
        Scope.ONTOLOGY: [],
    }
    bundled_fields: Dict[Scope, List[Tuple[str, ...]]] = {
        Scope.SOURCE: [],
        Scope.ITEM: [],
        Scope.ONTOLOGY: [],
    }

    for block in spec_blocks:
        scope = block["scope"]
        required = block.get("required", [])
        optional = block.get("optional", [])
        forbidden = block.get("forbidden", [])
        bundles = block.get("bundles", [])

        for bundle in bundles:
            bundled_fields[scope].append(tuple(bundle))

        for name in required:
            required_fields[scope].append(name)

        for name in optional:
            optional_fields[scope].append(name)

        for name in forbidden:
            forbidden_fields[scope].append(name)

    for scope, names in (
        (Scope.SOURCE, required_fields[Scope.SOURCE]),
        (Scope.ITEM, required_fields[Scope.ITEM]),
        (Scope.ONTOLOGY, required_fields[Scope.ONTOLOGY]),
    ):
        _validate_field_names(file_path, scope, names, field_specs)

    for scope, names in (
        (Scope.SOURCE, optional_fields[Scope.SOURCE]),
        (Scope.ITEM, optional_fields[Scope.ITEM]),
        (Scope.ONTOLOGY, optional_fields[Scope.ONTOLOGY]),
    ):
        _validate_field_names(file_path, scope, names, field_specs)

    for scope, names in (
        (Scope.SOURCE, forbidden_fields[Scope.SOURCE]),
        (Scope.ITEM, forbidden_fields[Scope.ITEM]),
        (Scope.ONTOLOGY, forbidden_fields[Scope.ONTOLOGY]),
    ):
        _validate_field_names(file_path, scope, names, field_specs)

    for scope, bundles in bundled_fields.items():
        for bundle in bundles:
            _validate_field_names(file_path, scope, list(bundle), field_specs)

    if header is None:
        header = {"name": "", "metadata": {}, "location": SourceLocation(file_path, 1, 1)}

    return TemplateNode(
        name=header["name"],
        metadata=header["metadata"],
        field_specs=field_specs,
        required_fields=required_fields,
        optional_fields=optional_fields,
        forbidden_fields=forbidden_fields,
        bundled_fields=bundled_fields,
        location=header["location"],
    )


def _validate_field_names(
    file_path: Path,
    scope: Scope,
    names: List[str],
    field_specs: Dict[str, FieldSpec],
) -> None:
    for name in names:
        if name not in field_specs:
            location = SourceLocation(file_path, 1, 1)
            raise TemplateLoadError(
                message=f"Campo '{name}' listado em {scope.value} FIELDS nao definido em FIELD",
                location=location,
            )
