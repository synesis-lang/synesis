"""
lsp_adapter.py - Adaptador entre o compilador Synesis e Language Server Protocol

Propósito:
    Expor interface de validação de arquivo único para LSP sem persistência.
    Permite validação em memória com contexto opcional (template/bibliografia).
    Descobre automaticamente contexto via arquivo .synp (projeto).

Componentes principais:
    - ValidationContext: contexto opcional para validação enriquecida
    - validate_single_file: função principal de validação in-memory
    - _discover_context: descoberta automática via arquivo .synp
    - _find_workspace_root: detecção de raiz do workspace
    - _find_project_in_workspace: busca e parsing de .synp
    - _load_context_from_project: carregamento de template/bibliografia
    - _parse_with_error_handling: wrapper para captura de erros sintáticos

NOVIDADE (v2.0):
    Descoberta de contexto agora baseada em arquivo .synp ao invés de busca heurística.
    - Busca .synp na raiz do workspace (detectado por .git, .vscode, ou próprio .synp)
    - Retorna warnings quando .synp não encontrado ou template ausente
    - Cache de contexto por workspace com invalidação baseada em mtime

Dependências críticas:
    - synesis.parser: parsing com Lark
    - synesis.semantic: validação semântica
    - synesis.ast: tipos de nós e ValidationResult

Exemplo de uso:
    from synesis.lsp_adapter import validate_single_file, ValidationContext

    result = validate_single_file(source_code, "file:///path/to/file.syn")
    for error in result.errors:
        print(error.to_diagnostic())

Notas de implementação:
    - Validação sempre inclui parsing sintático
    - Validação semântica ocorre apenas se context.template fornecido
    - Warnings de descoberta são incluídos no ValidationResult
    - Cache melhora performance em validações repetidas
    - Bibrefs geram WARNING se bibliografia não disponível

Gerado conforme: Especificação Synesis v1.1 + ADR-002 LSP + ADR-003 Project Discovery
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Dict, List, Optional

from synesis.ast.nodes import (
    ItemNode,
    OntologyNode,
    ProjectNode,
    SourceLocation,
    SourceNode,
    TemplateNode,
)
from synesis.ast.results import ValidationResult
from synesis.parser.bib_loader import BibEntry, load_bibliography
from synesis.parser.lexer import SynesisSyntaxError, parse_string
from synesis.parser.template_loader import load_template
from synesis.parser.transformer import SynesisTransformer
from synesis.semantic.validator import SemanticValidator


@dataclass
class ValidationContext:
    """
    Contexto opcional para validação enriquecida.

    Attributes:
        template: Template Synesis carregado (.synt)
        bibliography: Dicionário de entradas BibTeX indexadas por ID
        ontology_index: Dicionário de conceitos da ontologia
    """

    template: Optional[TemplateNode] = None
    bibliography: Optional[Dict[str, BibEntry]] = None
    ontology_index: Optional[Dict[str, OntologyNode]] = None


# ============================================
# CACHE DE CONTEXTO POR WORKSPACE
# ============================================

# Cache: workspace_root -> ValidationContext
_context_cache: Dict[Path, ValidationContext] = {}

# Cache de timestamps: workspace_root -> {file: mtime}
_cache_mtimes: Dict[Path, Dict[str, float]] = {}

logger = logging.getLogger(__name__)


def _get_cached_context(workspace_root: Path) -> Optional[ValidationContext]:
    """
    Retorna contexto cacheado se ainda válido.

    Validade: Verifica se arquivos .synp e .synt não foram modificados.

    Args:
        workspace_root: Raiz do workspace

    Returns:
        ValidationContext cacheado ou None se inválido/ausente
    """
    if workspace_root not in _context_cache:
        return None

    # Verificar se arquivos foram modificados
    cached_mtimes = _cache_mtimes.get(workspace_root, {})

    for file_path_str, cached_mtime in cached_mtimes.items():
        file_path = Path(file_path_str)
        if not file_path.exists():
            # Arquivo deletado - invalidar cache
            return None

        current_mtime = file_path.stat().st_mtime
        if current_mtime != cached_mtime:
            # Arquivo modificado - invalidar cache
            return None

    # Cache válido
    return _context_cache[workspace_root]


def _set_cached_context(
    workspace_root: Path, context: ValidationContext, monitored_files: List[Path]
) -> None:
    """
    Armazena contexto no cache com timestamps dos arquivos monitorados.

    Args:
        workspace_root: Raiz do workspace
        context: ValidationContext a cachear
        monitored_files: Lista de arquivos para monitorar modificações
    """
    _context_cache[workspace_root] = context

    # Armazenar mtimes
    mtimes: Dict[str, float] = {}
    for file_path in monitored_files:
        if file_path.exists():
            mtimes[str(file_path)] = file_path.stat().st_mtime

    _cache_mtimes[workspace_root] = mtimes


def _invalidate_cache(workspace_root: Path) -> None:
    """
    Invalida cache para workspace específico.

    Args:
        workspace_root: Raiz do workspace
    """
    _context_cache.pop(workspace_root, None)
    _cache_mtimes.pop(workspace_root, None)


def validate_single_file(
    source: str,
    file_uri: str,
    context: Optional[ValidationContext] = None,
) -> ValidationResult:
    """
    Valida texto Synesis em memória sem persistência.

    Args:
        source: Conteúdo do arquivo como string
        file_uri: URI do arquivo (para rastreabilidade de erros)
        context: Contexto opcional com template/bibliografia/ontologia
                 Se None, tenta descobrir automaticamente

    Returns:
        ValidationResult com erros, warnings (incluindo descoberta) e info

    Comportamento:
        - Sempre valida sintaxe (parser Lark)
        - Valida semântica se context.template fornecido
        - Bibrefs validados se context.bibliography fornecido (WARNING se ausente)
        - Códigos sempre geram WARNING se não em ontology_index
        - Warnings de descoberta (.synp ausente, template ausente) incluídos no resultado
    """
    result = ValidationResult()

    # Descoberta automática de contexto se não fornecido
    discovery_warnings: List["ValidationError"] = []
    if context is None:
        context, discovery_warnings = _discover_context(file_uri)

    # Adicionar warnings de descoberta ao resultado
    for warning in discovery_warnings:
        result.add(warning)

    # Etapa 1: Parsing sintático
    nodes, parse_errors = _parse_with_error_handling(source, file_uri)
    for error in parse_errors:
        result.add(error)

    # Se parsing falhou, retorna apenas erros sintáticos
    if parse_errors:
        return result

    # Etapa 2: Validação semântica (se contexto disponível)
    if context.template:
        semantic_result = _validate_semantics(nodes, context)
        result.errors.extend(semantic_result.errors)
        result.warnings.extend(semantic_result.warnings)
        result.info.extend(semantic_result.info)

    return result


def _parse_with_error_handling(
    source: str, file_uri: str
) -> tuple[List, List]:
    """
    Parseia source e converte exceções Lark em ValidationError.

    Returns:
        Tupla (nodes, errors) onde:
        - nodes: lista de nós da AST (vazia se erro)
        - errors: lista de SyntaxError ValidationErrors
    """
    from synesis.ast.results import ValidationError

    errors = []

    try:
        tree = parse_string(source, file_uri)
        # Converte URI para Path (remove file:// se presente)
        file_path = Path(file_uri.replace("file://", ""))
        transformer = SynesisTransformer(file_path)
        nodes = transformer.transform(tree)
        return nodes, errors

    except SynesisSyntaxError as exc:
        # Converte SynesisSyntaxError em ValidationError personalizado
        syntax_error = SyntaxError(
            location=exc.location,
            message=exc.message,
            expected=exc.expected,
        )
        errors.append(syntax_error)
        return [], errors


def _validate_semantics(
    nodes: List, context: ValidationContext
) -> ValidationResult:
    """
    Executa validação semântica nos nós parseados.

    Args:
        nodes: Lista de nós da AST
        context: Contexto com template e bibliografia

    Returns:
        ValidationResult agregado de todas as validações
    """
    result = ValidationResult()

    # Separa nós por tipo
    sources: List[SourceNode] = []
    items: List[ItemNode] = []
    ontologies: List[OntologyNode] = []

    for node in nodes:
        if isinstance(node, SourceNode):
            sources.append(node)
        elif isinstance(node, ItemNode):
            items.append(node)
        elif isinstance(node, OntologyNode):
            ontologies.append(node)

    # Constrói índice de ontologia
    ontology_index = context.ontology_index or {}
    for ont in ontologies:
        ontology_index[ont.concept] = ont

    # Configura validador semântico
    # Se bibliografia ausente, passa None para gerar WARNINGs
    bibliography = context.bibliography if context.bibliography else None

    validator = SemanticValidator(
        template=context.template,
        bibliography=bibliography,
        ontology_index=ontology_index,
    )

    # Valida cada tipo de nó
    for source in sources:
        semantic_result = validator.validate_source(source)
        result.errors.extend(semantic_result.errors)
        result.warnings.extend(semantic_result.warnings)
        result.info.extend(semantic_result.info)

    for item in items:
        semantic_result = validator.validate_item(item)
        result.errors.extend(semantic_result.errors)
        result.warnings.extend(semantic_result.warnings)
        result.info.extend(semantic_result.info)

    for ontology in ontologies:
        semantic_result = validator.validate_ontology(ontology)
        result.errors.extend(semantic_result.errors)
        result.warnings.extend(semantic_result.warnings)
        result.info.extend(semantic_result.info)

    return result


def _discover_context(file_uri: str) -> tuple[ValidationContext, List["ValidationError"]]:
    """
    Descobre automaticamente contexto via arquivo .synp no workspace.

    Nova estratégia (v2.0):
        1. Detecta raiz do workspace (busca .synp, .git, .vscode)
        2. Busca arquivo .synp na raiz do workspace
        3. Parseia projeto e carrega template/bibliografia
        4. Retorna warnings se .synp não encontrado ou inválido

    Args:
        file_uri: URI do arquivo sendo validado

    Returns:
        Tupla (ValidationContext, lista de warnings de descoberta)
    """
    from synesis.ast.results import MissingProjectFile, ValidationError

    warnings: List[ValidationError] = []

    # 1. ENCONTRAR RAIZ DO WORKSPACE
    workspace_root = _find_workspace_root(file_uri)

    if workspace_root is None:
        # Sem workspace detectado - retornar contexto vazio SEM warning
        # (pode ser arquivo isolado, não necessariamente erro)
        return ValidationContext(), warnings

    # 2. VERIFICAR CACHE
    cached_context = _get_cached_context(workspace_root)
    if cached_context is not None:
        return cached_context, warnings

    # 3. BUSCAR PROJETO NO WORKSPACE
    project_result = _find_project_in_workspace(workspace_root)

    if project_result is None:
        # Nenhum .synp encontrado - gerar WARNING
        file_path = Path(file_uri.replace("file://", ""))
        warning = MissingProjectFile(
            location=SourceLocation(file_path, 1, 1), workspace_root=str(workspace_root)
        )
        warnings.append(warning)
        logger.warning("Nenhum .synp encontrado no workspace: %s", workspace_root)
        return ValidationContext(), warnings

    # 4. CARREGAR CONTEXTO DO PROJETO
    project_path, project_node = project_result
    project_dir = project_path.parent
    logger.info("Projeto Synesis carregado: %s", project_path)
    context, load_errors = _load_context_from_project(project_dir, project_node)

    # Erros de carregamento (template ausente, etc.) vão para warnings
    warnings.extend(load_errors)

    # 5. CACHEAR CONTEXTO SE VÁLIDO
    if context.template is not None:
        # Determinar arquivos a monitorar
        monitored_files: List[Path] = []

        # .synp
        synp_files = list(workspace_root.glob("*.synp"))
        monitored_files.extend(synp_files)

        # .synt (template)
        template_path = project_dir / project_node.template_path
        if template_path.exists():
            monitored_files.append(template_path)

        # .bib (se presente)
        for include in project_node.includes:
            if include.include_type.upper() == "BIBLIOGRAPHY":
                bib_path = project_dir / include.path
                if bib_path.exists():
                    monitored_files.append(bib_path)
                break

        _set_cached_context(workspace_root, context, monitored_files)

    return context, warnings


def _find_template(directory: Path) -> Optional[TemplateNode]:
    """
    DEPRECATED: Substituído por descoberta via .synp (_load_context_from_project).
    Mantido para referência histórica.

    Busca arquivo .synt no diretório ou diretórios pais.

    Ordem de busca:
        1. template.synt no diretório atual
        2. Primeiro .synt encontrado no diretório atual
        3. Recursivamente nos diretórios pais (até 3 níveis)
    """
    # Busca no diretório atual
    template_path = directory / "template.synt"
    if template_path.exists():
        try:
            return load_template(template_path)
        except Exception:
            return None

    # Busca qualquer .synt no diretório
    synt_files = list(directory.glob("*.synt"))
    if synt_files:
        try:
            return load_template(synt_files[0])
        except Exception:
            return None

    # Busca em diretórios pais (até 3 níveis)
    current = directory
    for _ in range(3):
        parent = current.parent
        if parent == current:  # Chegou na raiz
            break

        template_path = parent / "template.synt"
        if template_path.exists():
            try:
                return load_template(template_path)
            except Exception:
                return None

        current = parent

    return None


def _find_bibliography(directory: Path) -> Optional[Dict[str, BibEntry]]:
    """
    Busca arquivo .bib no diretório.

    Estratégia:
        1. Busca primeiro .bib encontrado no diretório
        2. Se não encontrar, retorna None (gera WARNINGs para bibrefs)
    """
    bib_files = list(directory.glob("*.bib"))
    if bib_files:
        try:
            return load_bibliography(bib_files[0])
        except Exception:
            return None

    return None


# ============================================
# DESCOBERTA DE WORKSPACE E PROJETO (.synp)
# ============================================

def _find_workspace_root(file_uri: str) -> Optional[Path]:
    """
    Detecta raiz do workspace VSCode a partir de um arquivo.

    Estratégia:
        1. Busca arquivo .synp subindo hierarquia de diretórios
        2. Busca marcadores .git ou .vscode como fallback
        3. Limita busca a 10 níveis acima

    Args:
        file_uri: URI do arquivo sendo validado (pode ter prefixo file://)

    Returns:
        Path da raiz do workspace ou None se não encontrado
    """
    # Remove prefixo file:// se presente
    file_path = Path(file_uri.replace("file://", ""))

    # Garante que é arquivo válido
    if not file_path.exists():
        return None

    # Começa do diretório do arquivo
    current = file_path.parent if file_path.is_file() else file_path
    max_levels = 10

    for _ in range(max_levels):
        # Critério 1: Diretório contém .synp?
        if list(current.glob("*.synp")):
            return current

        # Critério 2: Diretório contém .git ou .vscode?
        if (current / ".git").exists() or (current / ".vscode").exists():
            return current

        # Subir um nível
        parent = current.parent
        if parent == current:  # Chegou na raiz do sistema
            break
        current = parent

    return None


def _find_project_in_workspace(workspace_root: Path) -> Optional[tuple[Path, "ProjectNode"]]:
    """
    Busca arquivo .synp na raiz do workspace e parseia projeto.

    Comportamento:
        - Busca APENAS na raiz (não em subdiretórios)
        - Se múltiplos .synp: escolhe alfabeticamente o primeiro
        - Trata erros de parsing retornando None

    Args:
        workspace_root: Diretório raiz do workspace

    Returns:
        Tupla (synp_path, ProjectNode) ou None se não encontrado/inválido
    """
    from synesis.ast.nodes import ProjectNode
    from synesis.parser.lexer import parse_file

    # Busca arquivos .synp APENAS na raiz
    synp_files = sorted(workspace_root.glob("*.synp"))

    if not synp_files:
        return None

    # Se múltiplos, usa o primeiro alfabeticamente
    synp_path = synp_files[0]

    # Log warning se múltiplos encontrados
    if len(synp_files) > 1:
        logger.warning(
            f"Múltiplos arquivos .synp encontrados em {workspace_root}. "
            f"Usando '{synp_path.name}' (primeiro alfabeticamente)."
        )

    # Tenta parsear o projeto
    try:
        tree = parse_file(synp_path)
        transformer = SynesisTransformer(synp_path)
        nodes = transformer.transform(tree)

        # Busca ProjectNode
        for node in nodes:
            if isinstance(node, ProjectNode):
                return (synp_path, node)

        # .synp válido mas sem bloco PROJECT
        return None

    except Exception as e:
        # Parsing falhou - logar e retornar None
        logger.error("Erro ao parsear %s: %s", synp_path, e)
        return None


def _load_context_from_project(
    project_dir: Path, project: "ProjectNode"
) -> tuple[ValidationContext, List["ValidationError"]]:
    """
    Carrega template e bibliografia a partir do ProjectNode.

    Comportamento:
        - Template: OBRIGATÓRIO - se ausente, gera ERRO
        - Bibliografia: OPCIONAL - se ausente, retorna None
        - Erros de carregamento são capturados e retornados

    Args:
        project_dir: Diretório do arquivo .synp
        project: ProjectNode parseado

    Returns:
        Tupla (ValidationContext, lista de ValidationErrors)
    """
    from synesis.ast.nodes import ProjectNode
    from synesis.ast.results import MissingTemplateFile, InvalidProjectFile, ValidationError

    errors: List[ValidationError] = []
    template = None
    bibliography = None

    # 1. CARREGAR TEMPLATE (obrigatório)
    template_path = project_dir / project.template_path

    if not template_path.exists():
        # Template especificado mas não existe
        error = MissingTemplateFile(
            location=project.location,
            template_path=str(template_path),
            project_file=f"{project_dir}/*.synp",
        )
        errors.append(error)
        logger.warning("Template nao encontrado: %s", template_path)
    else:
        try:
            template = load_template(template_path)
            logger.info("Template carregado: %s", template_path)
        except Exception as e:
            # Template existe mas não pode ser carregado
            error = InvalidProjectFile(
                location=project.location,
                project_file=str(template_path),
                parse_error=str(e),
            )
            errors.append(error)
            logger.warning("Falha ao carregar template %s: %s", template_path, e)

    # 2. CARREGAR BIBLIOGRAFIA (opcional)
    for include in project.includes:
        if include.include_type.upper() == "BIBLIOGRAPHY":
            bib_path = project_dir / include.path

            if bib_path.exists():
                try:
                    bibliography = load_bibliography(bib_path)
                    logger.info("Bibliografia carregada: %s", bib_path)
                except Exception as e:
                    # Bibliografia existe mas não pode ser carregada
                    # Não é erro fatal - apenas logar
                    logger.warning("Erro ao carregar bibliografia %s: %s", bib_path, e)
            else:
                logger.warning("Bibliografia nao encontrada: %s", bib_path)
            break  # Usar apenas primeiro INCLUDE BIBLIOGRAPHY

    # 3. RETORNAR CONTEXTO
    context = ValidationContext(
        template=template, bibliography=bibliography, ontology_index={}
    )

    return context, errors


# ============================================
# DEFINIÇÃO DE ERRO SINTÁTICO
# ============================================

# Define novo tipo de erro sintático para integração com ValidationResult
from synesis.ast.results import ErrorSeverity, ValidationError as BaseValidationError


@dataclass(frozen=True)
class SyntaxError(BaseValidationError):
    """Erro de sintaxe capturado do parser Lark."""

    message: str
    expected: Optional[List[str]] = None

    def to_diagnostic(self) -> str:
        msg = f"Erro de sintaxe: {self.message}"
        if self.expected:
            expected_str = ", ".join(self.expected[:5])  # Limita a 5 tokens
            msg += f"\n  Esperado: {expected_str}"
        return msg
