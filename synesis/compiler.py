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

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from synesis.ast.nodes import ItemNode, OntologyNode, ProjectNode, SourceNode, TemplateNode
from synesis.parser.bib_loader import BibEntry
from synesis.ast.results import (
    DuplicateProjectBlock,
    MissingAnnotationsInclude,
    MissingBibliographyFile,
    MissingOntologyInclude,
    MissingTemplateDeclaration,
    MissingTemplateFile,
    ModifiedBeforeCreated,
    ValidationResult,
)
from synesis.exporters.csv_export import export_csv
from synesis.exporters.json_export import export_json
from synesis.exporters.xls_export import export_xls
from synesis.parser.bib_loader import load_bibliography
from synesis.parser.lexer import parse_file
from synesis.parser.parse_cache import get_cached_nodes, put_cached_nodes
from synesis.parser.template_loader import load_template, validate_template
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
        project, project_validation = self.parse_project()

        # Validacao de estrutura do projeto (erros 61, 62, 63, 65, 66, 67)
        project_validation_structure = self.validate_project_structure(project)

        # Erro 63: arquivo .bib declarado mas nao encontrado (antes de load_bibliography)
        bib_validation = self._check_bibliography_file(project)

        # Se template ausente ou invalido, retornar cedo com os erros de estrutura
        template, template_load_result = self._safe_load_template(project)
        if template is None:
            result = ValidationResult()
            self._merge(result, project_validation)
            self._merge(result, project_validation_structure)
            self._merge(result, template_load_result)
            self._merge(result, bib_validation)
            return CompilationResult(
                success=False,
                linked_project=None,
                validation_result=result,
                stats=CompilationStats(),
            )

        # Validacao estrutural do template (erros 6, 18, 39-60, 69)
        template_validation = validate_template(template)

        bibliography = self.load_bibliography(project)

        ontologies = self.parse_ontologies(project)
        sources, items = self.parse_annotations(project)

        norm_cache: dict = {}

        validation_result = self.validate_all(
            project=project,
            template=template,
            bibliography=bibliography,
            sources=sources,
            items=items,
            ontologies=ontologies,
            norm_cache=norm_cache,
        )

        self._merge(validation_result, project_validation)
        self._merge(validation_result, project_validation_structure)
        self._merge(validation_result, template_validation)
        self._merge(validation_result, bib_validation)

        linked_project = self.link_all(
            project=project,
            template=template,
            sources=sources,
            items=items,
            ontologies=ontologies,
            validation_result=validation_result,
            norm_cache=norm_cache,
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

    def parse_project(self) -> tuple[ProjectNode, ValidationResult]:
        tree = parse_file(self.project_path)
        nodes = SynesisTransformer(self.project_path).transform(tree)
        result = ValidationResult()
        project_nodes = [n for n in nodes if isinstance(n, ProjectNode)]

        if not project_nodes:
            raise ValueError("Nenhum bloco PROJECT encontrado no .synp")

        # Erro 66: dois ou mais blocos PROJECT no mesmo .synp
        if len(project_nodes) > 1:
            for duplicate in project_nodes[1:]:
                loc = duplicate.location
                result.add(DuplicateProjectBlock(location=loc))

        return project_nodes[0], result

    def load_template(self, project: ProjectNode):
        template_path = self.project_dir / project.template_path
        return load_template(template_path)

    def load_bibliography(self, project: ProjectNode):
        for include in project.includes:
            if include.include_type.upper() == "BIBLIOGRAPHY":
                path = self.project_dir / include.path
                if not path.exists():
                    return {}
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

        if len(paths) <= 2:
            return self._parse_annotations_sequential(paths)

        # Garantir que o parser esta cacheado ANTES de spawnar threads
        from synesis.parser.lexer import create_parser
        create_parser()

        with ThreadPoolExecutor(max_workers=min(4, len(paths))) as executor:
            results = list(executor.map(_parse_single_annotation, paths))

        sources: List[SourceNode] = []
        items: List[ItemNode] = []
        for file_sources, file_items in results:
            sources.extend(file_sources)
            items.extend(file_items)
        return sources, items

    def _parse_annotations_sequential(self, paths: List[Path]) -> tuple[List[SourceNode], List[ItemNode]]:
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
        norm_cache: dict | None = None,
    ) -> ValidationResult:
        ontology_index = {o.concept: o for o in ontologies}
        validator = SemanticValidator(template, bibliography, ontology_index, norm_cache=norm_cache)
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
        norm_cache: dict | None = None,
    ) -> Optional[LinkedProject]:
        linker = Linker(sources, items, ontologies, project=project, template=template, norm_cache=norm_cache)
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

    def validate_project_structure(self, project: ProjectNode) -> ValidationResult:
        """Valida estrutura do projeto: arquivos nao incluidos, template ausente, datas. (erros 61, 62, 65, 67)"""
        result = ValidationResult()
        loc = project.location

        # Erro 65: PROJECT sem TEMPLATE declarado
        if not project.template_path or str(project.template_path).strip() == "":
            result.add(MissingTemplateDeclaration(location=loc))

        # Erros 61-62: arquivos .syn/.syno no diretorio nao referenciados no .synp
        included_annotations = set()
        included_ontologies = set()
        for include in project.includes:
            inc_type = include.include_type.upper()
            raw = include.path
            if inc_type == "ANNOTATIONS":
                if self._has_glob(raw):
                    for p in self.project_dir.glob(raw):
                        included_annotations.add(p.resolve())
                else:
                    included_annotations.add((self.project_dir / raw).resolve())
            elif inc_type == "ONTOLOGY":
                included_ontologies.add((self.project_dir / raw).resolve())

        for syn_file in self.project_dir.glob("*.syn"):
            if syn_file.resolve() not in included_annotations:
                result.add(MissingAnnotationsInclude(location=loc, filename=syn_file.name))

        for syno_file in self.project_dir.glob("*.syno"):
            if syno_file.resolve() not in included_ontologies:
                result.add(MissingOntologyInclude(location=loc, filename=syno_file.name))

        # Erro 67: MODIFIED < CREATED no bloco METADATA
        metadata = project.metadata or {}
        created = metadata.get("created") or metadata.get("CREATED")
        modified = metadata.get("modified") or metadata.get("MODIFIED")
        if created and modified:
            try:
                if modified < created:
                    result.add(ModifiedBeforeCreated(location=loc, modified=modified, created=created))
            except TypeError:
                pass  # Datas nao comparaveis — nao e erro de estrutura

        return result

    def _safe_load_template(self, project: ProjectNode) -> tuple[Optional[TemplateNode], ValidationResult]:
        """Carrega o template capturando erros de arquivo ausente. (erros 64, 65)"""
        result = ValidationResult()
        template_path_str = str(project.template_path).strip() if project.template_path else ""
        if not template_path_str:
            # Erro 65 já emitido em validate_project_structure; retornar None para abortar cedo
            return None, result
        template_path = self.project_dir / project.template_path
        if not template_path.exists():
            result.add(MissingTemplateFile(
                location=project.location,
                template_path=str(project.template_path),
                project_file=self.project_path.name,
            ))
            return None, result
        try:
            return load_template(template_path), result
        except Exception as exc:
            result.add(MissingTemplateFile(
                location=project.location,
                template_path=str(project.template_path),
                project_file=self.project_path.name,
            ))
            return None, result

    def _check_bibliography_file(self, project: ProjectNode) -> ValidationResult:
        """Erro 63: arquivo .bib declarado no projeto nao encontrado."""
        result = ValidationResult()
        for include in project.includes:
            if include.include_type.upper() == "BIBLIOGRAPHY":
                path = self.project_dir / include.path
                if not path.exists():
                    result.add(MissingBibliographyFile(
                        location=include.location,
                        filename=include.path,
                    ))
                break
        return result

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
        cached = get_cached_nodes(path)
        if cached is None:
            tree = parse_file(path)
            cached = SynesisTransformer(path).transform(tree)
            put_cached_nodes(path, cached)
        if only_type:
            return [n for n in cached if isinstance(n, only_type)]
        return cached

    def _merge(self, base: ValidationResult, other: ValidationResult) -> None:
        base.errors.extend(other.errors)
        base.warnings.extend(other.warnings)
        base.info.extend(other.info)


def _parse_single_annotation(path: Path) -> tuple[List[SourceNode], List[ItemNode]]:
    """Parseia uma anotacao. Thread-safe: parser cacheado, transformer per-file."""
    from synesis.parser.lexer import parse_file
    from synesis.parser.transformer import SynesisTransformer

    tree = parse_file(path)
    nodes = SynesisTransformer(path).transform(tree)
    sources = [n for n in nodes if isinstance(n, SourceNode)]
    items = [n for n in nodes if isinstance(n, ItemNode)]
    return sources, items
