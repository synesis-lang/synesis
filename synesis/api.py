"""
api.py - API publica para compilacao em memoria

Proposito:
    Expoe funcoes para compilar projetos Synesis a partir de strings,
    sem dependencia de I/O em disco. Ideal para Jupyter Notebooks,
    servidores LSP e integracao com APIs.

Componentes principais:
    - load(): Compila projeto completo a partir de strings
    - compile_string(): Parseia arquivo unico retornando nos AST
    - MemoryCompilationResult: Resultado com metodos de exportacao em memoria

Dependencias criticas:
    - synesis.parser: parse_string, load_*_from_string
    - synesis.semantic: SemanticValidator, Linker
    - synesis.exporters: build_*_payload

Exemplo de uso:
    import synesis
    result = synesis.load(
        project_content='PROJECT Demo TEMPLATE "t.synt" END PROJECT',
        template_content='TEMPLATE Demo ... END TEMPLATE',
    )
    if result.success:
        data = result.to_json_dict()

Gerado conforme: Especificacao Synesis v1.1
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from synesis.ast.nodes import (
    ItemNode,
    OntologyNode,
    ProjectNode,
    SourceNode,
    TemplateNode,
)
from synesis.ast.results import ValidationResult
from synesis.parser.bib_loader import BibEntry, load_bibliography_from_string
from synesis.parser.lexer import parse_string
from synesis.parser.template_loader import load_template_from_string
from synesis.parser.transformer import SynesisTransformer
from synesis.semantic.linker import Linker, LinkedProject
from synesis.semantic.validator import SemanticValidator


@dataclass
class CompilationStats:
    """Estatisticas de compilacao."""

    source_count: int = 0
    item_count: int = 0
    ontology_count: int = 0
    code_count: int = 0
    chain_count: int = 0
    triple_count: int = 0


@dataclass
class MemoryCompilationResult:
    """
    Resultado da compilacao em memoria.

    Contem o projeto compilado, resultado de validacao e metodos
    para exportar dados sem escrever em disco.

    Attributes:
        success: True se compilacao sem erros
        linked_project: Projeto vinculado (None se erros)
        validation_result: Erros, warnings e info
        template: Template carregado
        bibliography: Bibliografia carregada
        stats: Estatisticas de compilacao

    Example:
        >>> result = synesis.load(project_str, template_str)
        >>> if result.success:
        ...     df = result.to_dataframe("items")
        ...     data = result.to_json_dict()
    """

    success: bool
    linked_project: Optional[LinkedProject]
    validation_result: ValidationResult
    template: Optional[TemplateNode] = None
    bibliography: Optional[Dict[str, BibEntry]] = None
    stats: CompilationStats = field(default_factory=CompilationStats)

    def has_errors(self) -> bool:
        """Retorna True se houver erros de validacao."""
        return self.validation_result.has_errors()

    def has_warnings(self) -> bool:
        """Retorna True se houver warnings de validacao."""
        return self.validation_result.has_warnings()

    def get_diagnostics(self) -> str:
        """Retorna mensagens de erro/warning formatadas."""
        return self.validation_result.to_diagnostics()

    def to_json_dict(self) -> Dict[str, Any]:
        """
        Retorna estrutura JSON v2.0 como dict Python.

        Util para serializacao, APIs ou manipulacao programatica.

        Returns:
            Dict com estrutura JSON completa ou {} se erros

        Example:
            >>> data = result.to_json_dict()
            >>> print(json.dumps(data, indent=2))
        """
        if not self.linked_project:
            return {}
        from synesis.exporters.json_export import build_json_payload

        return build_json_payload(self.linked_project, self.template, self.bibliography)

    def to_csv_tables(self) -> Dict[str, tuple]:
        """
        Retorna tabelas CSV como dicts.

        Cada tabela e (headers, rows) onde rows e lista de dicts.

        Returns:
            Dict mapeando nome -> (headers, rows)

        Example:
            >>> tables = result.to_csv_tables()
            >>> headers, rows = tables["items"]
            >>> for row in rows:
            ...     print(row["bibref"])
        """
        if not self.linked_project:
            return {}
        from synesis.exporters.csv_export import build_csv_tables

        return build_csv_tables(self.linked_project, self.template)

    def to_dataframe(self, table_name: str) -> Any:
        """
        Retorna tabela como pandas DataFrame.

        Requer pandas instalado.

        Args:
            table_name: Nome da tabela (sources, items, ontologies, chains, codes)

        Returns:
            pandas.DataFrame com dados da tabela

        Raises:
            ImportError: Se pandas nao estiver instalado
            KeyError: Se tabela nao existir

        Example:
            >>> df = result.to_dataframe("items")
            >>> df.head()
        """
        try:
            import pandas as pd
        except ImportError:
            raise ImportError("pandas nao encontrado. Instale com: pip install pandas")

        tables = self.to_csv_tables()
        if table_name not in tables:
            available = ", ".join(tables.keys())
            raise KeyError(f"Tabela '{table_name}' nao encontrada. Disponiveis: {available}")

        headers, rows = tables[table_name]
        return pd.DataFrame(rows, columns=headers)

    def to_dataframes(self) -> Dict[str, Any]:
        """
        Retorna todas as tabelas como DataFrames.

        Requer pandas instalado.

        Returns:
            Dict mapeando nome da tabela -> DataFrame

        Example:
            >>> dfs = result.to_dataframes()
            >>> dfs["items"].head()
        """
        try:
            import pandas as pd
        except ImportError:
            raise ImportError("pandas nao encontrado. Instale com: pip install pandas")

        tables = self.to_csv_tables()
        return {
            name: pd.DataFrame(rows, columns=headers)
            for name, (headers, rows) in tables.items()
        }


def load(
    project_content: str,
    template_content: str,
    annotation_contents: Optional[Dict[str, str]] = None,
    ontology_contents: Optional[Dict[str, str]] = None,
    bibliography_content: Optional[str] = None,
    project_filename: str = "<project>",
    template_filename: str = "<template>",
) -> MemoryCompilationResult:
    """
    Compila projeto Synesis a partir de strings em memoria.

    Esta funcao executa o pipeline completo de compilacao sem
    acessar o sistema de arquivos. Ideal para Jupyter Notebooks,
    servidores LSP e testes.

    Args:
        project_content: Conteudo do arquivo .synp
        template_content: Conteudo do arquivo .synt
        annotation_contents: Dict[filename, content] para arquivos .syn
        ontology_contents: Dict[filename, content] para arquivos .syno
        bibliography_content: Conteudo do arquivo .bib (opcional)
        project_filename: Nome virtual para mensagens de erro
        template_filename: Nome virtual para mensagens de erro

    Returns:
        MemoryCompilationResult com projeto compilado e metodos de exportacao

    Raises:
        SynesisSyntaxError: Se houver erro de sintaxe nos conteudos

    Example:
        >>> import synesis
        >>> result = synesis.load(
        ...     project_content='''
        ...         PROJECT Demo
        ...             TEMPLATE "template.synt"
        ...         END PROJECT
        ...     ''',
        ...     template_content='''
        ...         TEMPLATE Demo
        ...         SOURCE FIELDS
        ...             REQUIRED date
        ...         END SOURCE FIELDS
        ...         ITEM FIELDS
        ...             REQUIRED quote
        ...         END ITEM FIELDS
        ...         FIELD date TYPE DATE SCOPE SOURCE END FIELD
        ...         FIELD quote TYPE QUOTATION SCOPE ITEM END FIELD
        ...     ''',
        ...     annotation_contents={
        ...         "sample.syn": '''
        ...             SOURCE @ref2020
        ...                 date: 2020-01-15
        ...             END SOURCE
        ...             ITEM @ref2020
        ...                 quote: Texto de exemplo
        ...             END ITEM
        ...         '''
        ...     },
        ... )
        >>> if result.success:
        ...     print(f"Compilado: {result.stats.item_count} items")
    """
    # 1. Parse project
    project = _parse_project(project_content, project_filename)

    # 2. Load template
    template = load_template_from_string(template_content, template_filename)

    # 3. Load bibliography (se fornecido)
    bibliography: Dict[str, BibEntry] = {}
    if bibliography_content:
        bibliography = load_bibliography_from_string(bibliography_content)

    # 4. Parse ontologies (se fornecido)
    ontologies: List[OntologyNode] = []
    if ontology_contents:
        for filename, content in ontology_contents.items():
            nodes = compile_string(content, filename)
            ontologies.extend([n for n in nodes if isinstance(n, OntologyNode)])

    # 5. Parse annotations (se fornecido)
    sources: List[SourceNode] = []
    items: List[ItemNode] = []
    if annotation_contents:
        for filename, content in annotation_contents.items():
            nodes = compile_string(content, filename)
            for node in nodes:
                if isinstance(node, SourceNode):
                    sources.append(node)
                elif isinstance(node, ItemNode):
                    items.append(node)

    # 6. Validacao semantica
    ontology_index = {o.concept: o for o in ontologies}
    validator = SemanticValidator(template, bibliography, ontology_index)
    validation_result = ValidationResult()

    _merge_validation(validation_result, validator.validate_project(project))
    for source in sources:
        _merge_validation(validation_result, validator.validate_source(source))
    for item in items:
        _merge_validation(validation_result, validator.validate_item(item))
    for ontology in ontologies:
        _merge_validation(validation_result, validator.validate_ontology(ontology))

    # 7. Vinculacao
    linker = Linker(sources, items, ontologies, project=project, template=template)
    linked_project = linker.link()
    _merge_validation(validation_result, linker.validation_result)

    # 8. Estatisticas
    stats = _compute_stats(linked_project, sources, items, ontologies)
    success = not validation_result.has_errors()

    return MemoryCompilationResult(
        success=success,
        linked_project=linked_project if success else linked_project,
        validation_result=validation_result,
        template=template,
        bibliography=bibliography,
        stats=stats,
    )


def compile_string(content: str, filename: str = "<string>") -> List[Any]:
    """
    Parseia arquivo Synesis unico, retornando nos AST.

    Util para LSP, validacao incremental ou parsing de fragmentos.

    Args:
        content: Conteudo do arquivo .syn, .syno, etc.
        filename: Nome virtual para mensagens de erro

    Returns:
        Lista de nos AST (SourceNode, ItemNode, OntologyNode, etc.)

    Raises:
        SynesisSyntaxError: Se houver erro de sintaxe

    Example:
        >>> nodes = synesis.compile_string('''
        ...     SOURCE @ref2020
        ...         date: 2020-01-15
        ...     END SOURCE
        ... ''')
        >>> source = nodes[0]
        >>> print(source.bibref)
        ref2020
    """
    tree = parse_string(content, filename)
    transformer = SynesisTransformer(Path(filename))
    return transformer.transform(tree)


def _parse_project(content: str, filename: str) -> ProjectNode:
    """Parseia conteudo de projeto e extrai ProjectNode."""
    nodes = compile_string(content, filename)
    for node in nodes:
        if isinstance(node, ProjectNode):
            return node
    raise ValueError(f"Nenhum bloco PROJECT encontrado em {filename}")


def _merge_validation(base: ValidationResult, other: ValidationResult) -> None:
    """Mescla resultados de validacao."""
    base.errors.extend(other.errors)
    base.warnings.extend(other.warnings)
    base.info.extend(other.info)


def _compute_stats(
    linked: Optional[LinkedProject],
    sources: List[SourceNode],
    items: List[ItemNode],
    ontologies: List[OntologyNode],
) -> CompilationStats:
    """Calcula estatisticas de compilacao."""
    stats = CompilationStats()
    stats.source_count = len(sources)
    stats.item_count = len(items)
    stats.ontology_count = len(ontologies)
    if linked:
        stats.code_count = len(linked.ontology_index)
        stats.chain_count = sum(len(item.chains) for item in items)
        stats.triple_count = len(linked.all_triples)
    return stats
