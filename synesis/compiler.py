"""
compiler.py - Orquestrador principal do compilador Synesis

Proposito:
    Executar o pipeline completo de compilacao Synesis a partir de um .synp.
    Coordena parsing, validacao, vinculacao e exportacao dos artefatos.

Componentes principais:
    - SynesisCompiler: executa pipeline em etapas ordenadas
    - CompilationResult/CompilationStats: resultados e estatisticas

Dependencias criticas:
    - synesis.parser: parsing com Lark
    - synesis.semantic: validacao e vinculacao
    - synesis.exporters: exportacao JSON/CSV

Exemplo de uso:
    compiler = SynesisCompiler(Path("projeto.synp"))
    result = compiler.compile()
    if result.has_errors():
        print(result.get_diagnostics())

Notas de implementacao:
    - Exportacao so ocorre quando nao ha erros.
    - Suporta glob patterns para INCLUDE ANNOTATIONS.

Gerado conforme: Especificacao Synesis v1.1
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from synesis.ast.nodes import ItemNode, OntologyNode, ProjectNode, SourceNode, TemplateNode
from synesis.parser.bib_loader import BibEntry
from synesis.ast.results import ValidationResult
from synesis.exporters.csv_export import export_csv
from synesis.exporters.json_export import export_json
from synesis.exporters.xls_export import export_xls
from synesis.parser.bib_loader import load_bibliography
from synesis.parser.lexer import parse_file
from synesis.parser.template_loader import load_template
from synesis.parser.transformer import SynesisTransformer
from synesis.semantic.linker import Linker, LinkedProject
from synesis.semantic.validator import SemanticValidator


@dataclass
class CompilationStats:
    source_count: int = 0
    item_count: int = 0
    ontology_count: int = 0
    code_count: int = 0
    chain_count: int = 0
    triple_count: int = 0


@dataclass
class CompilationResult:
    success: bool
    linked_project: Optional[LinkedProject]
    validation_result: ValidationResult
    stats: CompilationStats
    template: Optional[TemplateNode] = None
    bibliography: Optional[Dict[str, BibEntry]] = None

    def has_errors(self) -> bool:
        return self.validation_result.has_errors()

    def has_warnings(self) -> bool:
        return self.validation_result.has_warnings()

    def get_diagnostics(self) -> str:
        return self.validation_result.to_diagnostics()

    def to_json(self, path: Path) -> None:
        if self.has_errors() or not self.linked_project:
            return
        export_json(self.linked_project, path, self.template, self.bibliography)

    def to_csv(self, output_dir: Path) -> None:
        if self.has_errors() or not self.linked_project:
            return
        export_csv(self.linked_project, self.template, output_dir)

    def to_xls(self, path: Path) -> None:
        if self.has_errors() or not self.linked_project:
            return
        export_xls(self.linked_project, self.template, path)


class SynesisCompiler:
    def __init__(self, project_path: Path):
        self.project_path = Path(project_path)
        self.project_dir = self.project_path.parent

    def compile(self) -> CompilationResult:
        project = self.parse_project()
        template = self.load_template(project)
        bibliography = self.load_bibliography(project)
        ontologies = self.parse_ontologies(project)
        sources, items = self.parse_annotations(project)

        validation_result = self.validate_all(
            project=project,
            template=template,
            bibliography=bibliography,
            sources=sources,
            items=items,
            ontologies=ontologies,
        )

        linked_project = self.link_all(
            project=project,
            template=template,
            sources=sources,
            items=items,
            ontologies=ontologies,
            validation_result=validation_result,
        )

        stats = self._compute_stats(linked_project, sources, items, ontologies)
        success = not validation_result.has_errors()
        return CompilationResult(
            success=success,
            linked_project=linked_project if success or linked_project else linked_project,
            validation_result=validation_result,
            stats=stats,
            template=template,
            bibliography=bibliography,
        )

    def parse_project(self) -> ProjectNode:
        tree = parse_file(self.project_path)
        nodes = SynesisTransformer(self.project_path).transform(tree)
        for node in nodes:
            if isinstance(node, ProjectNode):
                return node
        raise ValueError("Nenhum bloco PROJECT encontrado no .synp")

    def load_template(self, project: ProjectNode):
        template_path = self.project_dir / project.template_path
        return load_template(template_path)

    def load_bibliography(self, project: ProjectNode):
        for include in project.includes:
            if include.include_type.upper() == "BIBLIOGRAPHY":
                path = self.project_dir / include.path
                return load_bibliography(path)
        return {}

    def parse_ontologies(self, project: ProjectNode) -> List[OntologyNode]:
        paths = self._collect_include_paths(project, "ONTOLOGY")
        ontologies: List[OntologyNode] = []
        for path in paths:
            ontologies.extend(self._parse_nodes(path, OntologyNode))
        return ontologies

    def parse_annotations(self, project: ProjectNode) -> tuple[List[SourceNode], List[ItemNode]]:
        paths = self._collect_include_paths(project, "ANNOTATIONS", allow_glob=True)
        sources: List[SourceNode] = []
        items: List[ItemNode] = []
        for path in paths:
            nodes = self._parse_nodes(path)
            for node in nodes:
                if isinstance(node, SourceNode):
                    sources.append(node)
                elif isinstance(node, ItemNode):
                    items.append(node)
        return sources, items

    def validate_all(
        self,
        project: ProjectNode,
        template,
        bibliography: Dict[str, dict],
        sources: List[SourceNode],
        items: List[ItemNode],
        ontologies: List[OntologyNode],
    ) -> ValidationResult:
        ontology_index = {o.concept: o for o in ontologies}
        validator = SemanticValidator(template, bibliography, ontology_index)
        result = ValidationResult()

        self._merge(result, validator.validate_project(project))
        for source in sources:
            self._merge(result, validator.validate_source(source))
        for item in items:
            self._merge(result, validator.validate_item(item))
        for ontology in ontologies:
            self._merge(result, validator.validate_ontology(ontology))
        return result

    def link_all(
        self,
        project: ProjectNode,
        template,
        sources: List[SourceNode],
        items: List[ItemNode],
        ontologies: List[OntologyNode],
        validation_result: ValidationResult,
    ) -> Optional[LinkedProject]:
        linker = Linker(sources, items, ontologies, project=project, template=template)
        linked = linker.link()
        self._merge(validation_result, linker.validation_result)
        return linked

    def _compute_stats(
        self,
        linked: Optional[LinkedProject],
        sources: List[SourceNode],
        items: List[ItemNode],
        ontologies: List[OntologyNode],
    ) -> CompilationStats:
        stats = CompilationStats()
        stats.source_count = len(sources)
        stats.item_count = len(items)
        stats.ontology_count = len(ontologies)
        if linked:
            stats.code_count = len(linked.ontology_index)
            stats.chain_count = sum(len(item.chains) for item in items)
            stats.triple_count = len(linked.all_triples)
        return stats

    def _collect_include_paths(
        self,
        project: ProjectNode,
        include_type: str,
        allow_glob: bool = False,
    ) -> List[Path]:
        paths: List[Path] = []
        for include in project.includes:
            if include.include_type.upper() != include_type:
                continue
            raw = include.path
            if allow_glob and self._has_glob(raw):
                paths.extend([self.project_dir / p for p in self.project_dir.glob(raw)])
            else:
                paths.append(self.project_dir / raw)
        return paths

    def _has_glob(self, value: str) -> bool:
        return any(ch in value for ch in ["*", "?", "["])

    def _parse_nodes(self, path: Path, only_type=None) -> List:
        tree = parse_file(path)
        nodes = SynesisTransformer(path).transform(tree)
        if only_type:
            return [n for n in nodes if isinstance(n, only_type)]
        return nodes

    def _merge(self, base: ValidationResult, other: ValidationResult) -> None:
        base.errors.extend(other.errors)
        base.warnings.extend(other.warnings)
        base.info.extend(other.info)
