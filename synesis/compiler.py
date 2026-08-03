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

from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from synesis.ast.nodes import (
    ItemNode,
    OntologyNode,
    ProjectNode,
    Scope,
    SourceLocation,
    SourceNode,
    TemplateNode,
)
from synesis.ast.results import (
    DuplicateProjectBlock,
    IncludePathEscapesProject,
    MalformedBibliographyEntry,
    MissingAnnotationsFile,
    MissingAnnotationsInclude,
    MissingBibliographyFile,
    MissingOntologyFile,
    MissingOntologyInclude,
    MissingTemplateDeclaration,
    MissingTemplateFile,
    ModifiedBeforeCreated,
    SharedOnlyForOntology,
    UnreadableIncludedFile,
    ValidationResult,
)
from synesis.exporters.alpaca_export import export_alpaca
from synesis.exporters.csv_export import export_csv
from synesis.exporters.json_export import export_json
from synesis.exporters.xls_export import export_xls
from synesis.parser.bib_loader import BibEntry, detect_malformed_entries, load_bibliography
from synesis.parser.dataset_loader import DatasetError, load_dataset
from synesis.parser.lexer import SynesisSyntaxError, parse_file, read_source_file
from synesis.parser.parse_cache import get_cached_nodes, put_cached_nodes
from synesis.parser.paths import (
    IncludeError,
    canonical_path,
    has_glob,
    normalize_include_path,
    resolve_glob,
    resolve_include,
)
from synesis.parser.template_loader import load_template, validate_template
from synesis.parser.transformer import SynesisTransformer
from synesis.semantic.linker import LinkedProject, Linker
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
    # Registros TOML de INCLUDE DATASET, indexados pela chave do template.
    # Espelha `bibliography` e usa o mesmo contrato de tres estados:
    #   None = projeto nao declara INCLUDE DATASET (ou chave indescobrivel);
    #   {}   = declarado mas nao carregou (o erro ja esta no validation_result);
    #   dict = carregado.
    dataset: Optional[Dict[str, Any]] = None

    def has_errors(self) -> bool:
        return self.validation_result.has_errors()

    def has_warnings(self) -> bool:
        return self.validation_result.has_warnings()

    def get_diagnostics(self, *, verbose: bool = True) -> str:
        return self.validation_result.to_diagnostics(verbose=verbose)

    def to_json(self, path: Path) -> None:
        if self.has_errors() or not self.linked_project:
            return
        export_json(self.linked_project, path, self.template, self.bibliography, self.dataset)

    def to_csv(self, output_dir: Path) -> None:
        if self.has_errors() or not self.linked_project:
            return
        export_csv(self.linked_project, self.template, output_dir, self.bibliography, self.dataset)

    def to_xls(self, path: Path) -> None:
        if self.has_errors() or not self.linked_project:
            return
        export_xls(self.linked_project, self.template, path, self.bibliography, self.dataset)

    def to_alpaca(self, path: Path) -> None:
        if self.has_errors() or not self.linked_project:
            return
        export_alpaca(self.linked_project, path, self.template, self.bibliography)


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

        # Erro 72: entradas BibTeX malformadas no arquivo .bib
        bib_format_validation = self._check_bibliography_format(project)

        # Se template ausente ou invalido, retornar cedo com os erros de estrutura
        template, template_load_result = self._safe_load_template(project)
        if template is None:
            result = ValidationResult()
            self._merge(result, project_validation)
            self._merge(result, project_validation_structure)
            self._merge(result, template_load_result)
            self._merge(result, bib_validation)
            self._merge(result, bib_format_validation)
            return CompilationResult(
                success=False,
                linked_project=None,
                validation_result=result,
                stats=CompilationStats(),
            )

        # Validacao estrutural do template (erros 6, 18, 39-60, 69)
        template_validation = validate_template(template)

        bibliography = self.load_bibliography(project)
        dataset, dataset_load_result = self.load_dataset_index(project, template)

        ontologies, ontology_load_result = self.parse_ontologies(project)
        sources, items, annotations_load_result = self.parse_annotations(project)

        norm_cache: dict = {}

        malformed_keys = {
            e.entry_key.lower() for e in bib_format_validation.errors
            if isinstance(e, MalformedBibliographyEntry)
        }
        validation_result = self.validate_all(
            project=project,
            template=template,
            bibliography=bibliography,
            sources=sources,
            items=items,
            ontologies=ontologies,
            norm_cache=norm_cache,
            malformed_bib_keys=malformed_keys,
            dataset=dataset,
        )

        self._merge(validation_result, project_validation)
        self._merge(validation_result, project_validation_structure)
        self._merge(validation_result, template_validation)
        self._merge(validation_result, bib_validation)
        self._merge(validation_result, bib_format_validation)
        self._merge(validation_result, dataset_load_result)
        self._merge(validation_result, ontology_load_result)
        self._merge(validation_result, annotations_load_result)

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
            dataset=dataset,
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
        resolution = resolve_include(self.project_dir, str(project.template_path))
        return load_template(resolution.path)

    def load_bibliography(self, project: ProjectNode):
        # Retorna None quando o projeto NAO declara INCLUDE BIBLIOGRAPHY: nesse caso
        # os identificadores de SOURCE sao chaves internas e a validacao de bibref
        # (E001) e desativada no SemanticValidator. Quando ha INCLUDE BIBLIOGRAPHY
        # mas o arquivo nao existe ou nao pode ser lido, retorna {} (a falta do
        # arquivo ja e reportada como E063/E076 e os bibrefs ainda sao validados).
        for include in project.includes:
            if include.include_type.upper() == "BIBLIOGRAPHY":
                resolution = resolve_include(self.project_dir, include.path)
                if not resolution.ok:
                    return {}
                try:
                    return load_bibliography(resolution.path)
                except (OSError, UnicodeDecodeError):
                    return {}
        return None

    @staticmethod
    def _dataset_key_path(template: Optional[TemplateNode]) -> Optional[str]:
        """Caminho da chave de indexacao do dataset, derivado do template.

        A chave e o `dataset_path` do campo SCOPE SOURCE que tambem e
        `IDENTIFIES` (D3/D8): e a identidade do registro. Sem campo IDENTIFIES
        ON DATASET, cai no primeiro campo SOURCE com ON DATASET. O loader e
        agnostico de dominio — quem sabe a chave e o template.
        """
        if template is None:
            return None
        fallback: Optional[str] = None
        for spec in template.field_specs.values():
            if getattr(spec, "value_origin", "document") != "dataset":
                continue
            if spec.scope != Scope.SOURCE:
                continue
            path = getattr(spec, "dataset_path", None)
            if path is None:
                continue
            if getattr(spec, "identifies", None):
                return path
            if fallback is None:
                fallback = path
        return fallback

    def load_dataset_index(
        self, project: ProjectNode, template: Optional[TemplateNode]
    ) -> tuple[Optional[Dict[str, Any]], ValidationResult]:
        """Carrega os registros TOML de INCLUDE DATASET (origem-de-valor ON DATASET).

        Espelha load_bibliography e usa o mesmo contrato de tres estados:
          None = projeto nao declara INCLUDE DATASET, ou o template nao tem
                 campo ON DATASET (chave indescobrivel) — no-op;
          {}   = declarado mas o caminho nao resolve / o TOML falha ao carregar
                 (o erro correspondente vai no ValidationResult);
          dict = carregado e indexado pela chave do template.
        """
        result = ValidationResult()
        for include in project.includes:
            if include.include_type.upper() != "DATASET":
                continue

            key_path = self._dataset_key_path(template)
            if key_path is None:
                # Sem campo ON DATASET no template nao ha como indexar os
                # registros. Nao e erro: o INCLUDE fica inerte, como um .bib
                # declarado num projeto que nao usa bibref.
                return None, result

            raw = normalize_include_path(include.path)
            if has_glob(raw):
                inside, outside = resolve_glob(self.project_dir, raw)
                for escaped in outside:
                    result.add(IncludePathEscapesProject(
                        location=include.location,
                        filename=str(escaped),
                    ))
                if not inside:
                    # Glob declarado sem nenhum match: o dataset foi pedido e
                    # nao existe. Distingue-se de "projeto sem dataset" ({} vs
                    # None) para que E085 continue exigindo os campos REQUIRED.
                    return {}, result
                paths: List[Path] = inside
            else:
                resolution = resolve_include(self.project_dir, raw)
                if resolution.error is IncludeError.ESCAPES_PROJECT:
                    result.add(IncludePathEscapesProject(
                        location=include.location,
                        filename=include.path,
                    ))
                    return {}, result
                if not resolution.ok:
                    result.add(UnreadableIncludedFile(
                        location=include.location,
                        filename=include.path,
                        reason="arquivo de dataset declarado nao encontrado",
                    ))
                    return {}, result
                paths = [resolution.path]

            index: Dict[str, Any] = {}
            for path in paths:
                try:
                    index.update(load_dataset(path, key_path=key_path, base_dir=self.project_dir))
                except DatasetError as exc:
                    result.add(UnreadableIncludedFile(
                        location=include.location,
                        filename=include.path,
                        reason=str(exc),
                    ))
                    return {}, result
            return index, result
        return None, result

    def parse_ontologies(
        self, project: ProjectNode
    ) -> tuple[List[OntologyNode], ValidationResult]:
        paths, result = self._collect_include_paths(project, "ONTOLOGY")
        ontologies: List[OntologyNode] = []
        for path in paths:
            nodes, parse_result = self._parse_nodes(path, OntologyNode)
            ontologies.extend(nodes)
            self._merge(result, parse_result)
        return ontologies, result

    def parse_annotations(
        self, project: ProjectNode
    ) -> tuple[List[SourceNode], List[ItemNode], ValidationResult]:
        paths, result = self._collect_include_paths(project, "ANNOTATIONS", allow_glob=True)

        if len(paths) <= 3:
            sources, items, parse_result = self._parse_annotations_sequential(paths)
            self._merge(result, parse_result)
            return sources, items, result

        with ProcessPoolExecutor(max_workers=min(4, len(paths))) as executor:
            results = list(executor.map(_parse_single_annotation, paths))

        sources = []
        items = []
        for path, (file_sources, file_items, failure) in zip(paths, results):
            if failure is not None:
                result.add(UnreadableIncludedFile(
                    location=SourceLocation(path, 1, 1),
                    filename=path.name,
                    reason=failure,
                ))
                continue
            sources.extend(file_sources)
            items.extend(file_items)
        return sources, items, result

    def _parse_annotations_sequential(
        self, paths: List[Path]
    ) -> tuple[List[SourceNode], List[ItemNode], ValidationResult]:
        result = ValidationResult()
        sources: List[SourceNode] = []
        items: List[ItemNode] = []
        for path in paths:
            nodes, parse_result = self._parse_nodes(path)
            self._merge(result, parse_result)
            for node in nodes:
                if isinstance(node, SourceNode):
                    sources.append(node)
                elif isinstance(node, ItemNode):
                    items.append(node)
        return sources, items, result

    def validate_all(
        self,
        project: ProjectNode,
        template,
        bibliography: Dict[str, dict],
        sources: List[SourceNode],
        items: List[ItemNode],
        ontologies: List[OntologyNode],
        norm_cache: dict | None = None,
        malformed_bib_keys: set | None = None,
        dataset: Optional[Dict[str, Any]] = None,
    ) -> ValidationResult:
        ontology_index = {o.concept: o for o in ontologies}
        validator = SemanticValidator(
            template, bibliography, ontology_index,
            norm_cache=norm_cache,
            malformed_bib_keys=malformed_bib_keys or set(),
            dataset=dataset or {},
        )
        result = ValidationResult()

        self._merge(result, validator.validate_project(project))
        self._merge(result, validator.validate_identity_uniqueness(sources))
        self._merge(result, validator.validate_bibliography_values(sources))
        self._merge(result, validator.validate_dataset_values(sources))
        self._merge(result, validator.validate_external_references())
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

        # Erros 61-62: arquivos .syn/.syno no diretorio nao referenciados no .synp.
        # Os paths sao comparados na caixa real do disco (resolve_include), senao um
        # .synp que escreve "NOTES.SYN" para o arquivo "notes.syn" produz E061
        # falso-positivo em sistemas de arquivos case-insensitive.
        included_annotations = set()
        included_ontologies = set()
        for include in project.includes:
            inc_type = include.include_type.upper()
            raw = normalize_include_path(include.path)

            # Erro 84: SHARED so autoriza escape para ONTOLOGY (D13)
            if include.shared and inc_type != "ONTOLOGY":
                result.add(SharedOnlyForOntology(
                    location=include.location,
                    include_type=inc_type,
                    path=include.path,
                ))

            if inc_type == "ANNOTATIONS":
                if has_glob(raw):
                    inside, _outside = resolve_glob(self.project_dir, raw)
                    for p in inside:
                        included_annotations.add(self._canonical(p))
                else:
                    included_annotations.add(self._canonical(self.project_dir / raw))
            elif inc_type == "ONTOLOGY":
                included_ontologies.add(self._canonical(self.project_dir / raw))

        for syn_file in self.project_dir.glob("*.syn"):
            if self._canonical(syn_file) not in included_annotations:
                result.add(MissingAnnotationsInclude(location=loc, filename=syn_file.name))

        for syno_file in self.project_dir.glob("*.syno"):
            if self._canonical(syno_file) not in included_ontologies:
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

    def _canonical(self, path: Path) -> Path:
        """Caminho canonico (caixa real do disco) para comparacao entre paths."""
        return canonical_path(path)

    def _safe_load_template(self, project: ProjectNode) -> tuple[Optional[TemplateNode], ValidationResult]:
        """Carrega o template capturando erros de arquivo ausente. (erros 64, 65, 75)"""
        result = ValidationResult()
        template_path_str = normalize_include_path(str(project.template_path)) if project.template_path else ""
        if not template_path_str:
            # Erro 65 já emitido em validate_project_structure; retornar None para abortar cedo
            return None, result

        resolution = resolve_include(self.project_dir, template_path_str)
        if resolution.error is IncludeError.ESCAPES_PROJECT:
            result.add(IncludePathEscapesProject(
                location=project.location,
                filename=str(project.template_path),
            ))
            return None, result
        if not resolution.ok:
            result.add(MissingTemplateFile(
                location=project.location,
                template_path=str(project.template_path),
                project_file=self.project_path.name,
            ))
            return None, result
        try:
            return load_template(resolution.path), result
        except Exception:
            result.add(MissingTemplateFile(
                location=project.location,
                template_path=str(project.template_path),
                project_file=self.project_path.name,
            ))
            return None, result

    def _check_bibliography_file(self, project: ProjectNode) -> ValidationResult:
        """Erros 63 e 75: arquivo .bib declarado nao encontrado ou fora do projeto."""
        result = ValidationResult()
        for include in project.includes:
            if include.include_type.upper() == "BIBLIOGRAPHY":
                resolution = resolve_include(self.project_dir, include.path)
                if resolution.error is IncludeError.ESCAPES_PROJECT:
                    result.add(IncludePathEscapesProject(
                        location=include.location,
                        filename=include.path,
                    ))
                elif not resolution.ok:
                    result.add(MissingBibliographyFile(
                        location=include.location,
                        filename=include.path,
                    ))
                break
        return result

    def _check_bibliography_format(self, project: ProjectNode) -> ValidationResult:
        """Erros 72 e 76: entradas BibTeX malformadas ou arquivo .bib ilegivel."""
        result = ValidationResult()
        for include in project.includes:
            if include.include_type.upper() == "BIBLIOGRAPHY":
                resolution = resolve_include(self.project_dir, include.path)
                if resolution.ok:
                    path = resolution.path
                    try:
                        content = read_source_file(path)
                    except (OSError, UnicodeDecodeError) as exc:
                        result.add(UnreadableIncludedFile(
                            location=include.location,
                            filename=include.path,
                            reason=str(exc),
                        ))
                        break
                    for entry_key, line_number in detect_malformed_entries(content):
                        result.add(MalformedBibliographyEntry(
                            location=SourceLocation(path, line_number or 1, 1),
                            filename=include.path,
                            entry_key=entry_key,
                        ))
                break
        return result

    def _collect_include_paths(
        self,
        project: ProjectNode,
        include_type: str,
        allow_glob: bool = False,
    ) -> tuple[List[Path], ValidationResult]:
        """Resolve os caminhos de um tipo de INCLUDE.

        Devolve apenas os caminhos legiveis; arquivos ausentes ou fora da pasta do
        projeto viram erros de validacao (E073/E074/E075) em vez de excecao.
        """
        result = ValidationResult()
        paths: List[Path] = []
        missing_cls = (
            MissingOntologyFile if include_type == "ONTOLOGY" else MissingAnnotationsFile
        )

        for include in project.includes:
            if include.include_type.upper() != include_type:
                continue

            raw = normalize_include_path(include.path)

            if allow_glob and has_glob(raw):
                # Glob sem match nao e erro aqui: a ausencia de arquivos .syn ja e
                # coberta por E061/E062 em validate_project_structure. Mas o glob
                # segue `..`, entao filtramos os matches que escapam do projeto.
                inside, outside = resolve_glob(self.project_dir, raw)
                paths.extend(inside)
                for escaped in outside:
                    result.add(IncludePathEscapesProject(
                        location=include.location,
                        filename=str(escaped),
                    ))
                continue

            # SHARED so autoriza escape para ONTOLOGY (D13); o uso indevido em
            # outros tipos e reportado como SharedOnlyForOntology na validacao
            # estrutural — aqui o escape simplesmente nao se aplica.
            shared = include.shared and include_type == "ONTOLOGY"

            resolution = resolve_include(self.project_dir, raw, shared=shared)
            if resolution.ok:
                paths.append(resolution.path)
            elif resolution.error is IncludeError.ESCAPES_PROJECT:
                result.add(IncludePathEscapesProject(
                    location=include.location,
                    filename=include.path,
                ))
            else:
                result.add(missing_cls(
                    location=include.location,
                    filename=include.path,
                ))

        return paths, result

    def _parse_nodes(self, path: Path, only_type=None) -> tuple[List, ValidationResult]:
        """Parseia um arquivo incluido, convertendo falhas de leitura em erros.

        Erros de sintaxe e de codificacao em arquivos incluidos viram diagnosticos
        (E076 / erro de sintaxe posicionado) em vez de derrubar a compilacao.
        """
        result = ValidationResult()

        cached = get_cached_nodes(path)
        if cached is not None:
            nodes = cached
        else:
            try:
                tree = parse_file(path)
                nodes = SynesisTransformer(path).transform(tree)
            except SynesisSyntaxError as exc:
                result.add(UnreadableIncludedFile(
                    location=exc.location or SourceLocation(path, 1, 1),
                    filename=path.name,
                    reason=exc.message,
                ))
                return [], result
            except (OSError, UnicodeDecodeError) as exc:
                result.add(UnreadableIncludedFile(
                    location=SourceLocation(path, 1, 1),
                    filename=path.name,
                    reason=str(exc),
                ))
                return [], result
            put_cached_nodes(path, nodes)

        if only_type:
            return [n for n in nodes if isinstance(n, only_type)], result
        return nodes, result

    def _merge(self, base: ValidationResult, other: ValidationResult) -> None:
        base.errors.extend(other.errors)
        base.warnings.extend(other.warnings)
        base.info.extend(other.info)


def _parse_single_annotation(
    path: Path,
) -> tuple[List[SourceNode], List[ItemNode], Optional[str]]:
    """Parseia uma anotacao. Thread-safe: parser cacheado, transformer per-file.

    Roda em outro processo: devolve a falha como string (o chamador a converte em
    UnreadableIncludedFile) para nao depender de excecoes picklable.
    """
    from synesis.parser.lexer import SynesisSyntaxError, parse_file
    from synesis.parser.transformer import SynesisTransformer

    try:
        tree = parse_file(path)
        nodes = SynesisTransformer(path).transform(tree)
    except SynesisSyntaxError as exc:
        return [], [], exc.message
    except (OSError, UnicodeDecodeError) as exc:
        return [], [], str(exc)

    sources = [n for n in nodes if isinstance(n, SourceNode)]
    items = [n for n in nodes if isinstance(n, ItemNode)]
    return sources, items, None
