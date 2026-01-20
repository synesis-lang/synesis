"""
results.py - Tipos de resultado e erros de validacao do Synesis

Proposito:
    Definir Result/Ok/Err inspirados em Elm para fluxo de erros tipado.
    Centralizar erros semanticos com diagnosticos estruturados.

Componentes principais:
    - Result, Ok, Err: tipos genericos para sucesso/erro
    - ValidationError e subclasses: erros semanticos tipados
    - ValidationResult: agregador de diagnosticos

Dependencias criticas:
    - synesis.ast.nodes: SourceLocation para localizacao precisa
    - dataclasses/typing/enum: estrutura e tipagem

Exemplo de uso:
    from synesis.ast.results import Ok, Err, ValidationResult
    result = Ok(123)

Notas de implementacao:
    - Erros retornam mensagens prontas para exibicao ao usuario.
    - ValidationResult agrega erros, avisos e informacoes.

Gerado conforme: Especificacao Synesis v1.1
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, ClassVar, Dict, Generic, Optional, Tuple, TypeVar, Union

from synesis.ast.nodes import SourceLocation

T = TypeVar("T")
E = TypeVar("E")
U = TypeVar("U")


@dataclass(frozen=True)
class Ok(Generic[T]):
    """Representa sucesso com valor."""

    value: T

    def is_ok(self) -> bool:
        return True

    def is_err(self) -> bool:
        return False

    def unwrap(self) -> T:
        return self.value

    def unwrap_or(self, default: T) -> T:
        return self.value

    def map(self, fn: Callable[[T], U]) -> "Result[U, E]":
        return Ok(fn(self.value))

    def and_then(self, fn: Callable[[T], "Result[U, E]"]) -> "Result[U, E]":
        return fn(self.value)


@dataclass(frozen=True)
class Err(Generic[E]):
    """Representa falha com erro tipado."""

    error: E

    def is_ok(self) -> bool:
        return False

    def is_err(self) -> bool:
        return True

    def unwrap(self):
        raise ValueError(f"Tentou unwrap() em Err: {self.error}")

    def unwrap_or(self, default: T) -> T:
        return default

    def map(self, fn: Callable[[T], U]) -> "Result[U, E]":
        return self

    def and_then(self, fn: Callable[[T], "Result[U, E]"]) -> "Result[U, E]":
        return self


Result = Union[Ok[T], Err[E]]


class ErrorSeverity(Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class ValidationError:
    """Classe base para todos os erros de validacao."""

    location: SourceLocation
    severity: ErrorSeverity = field(init=False, default=ErrorSeverity.ERROR)
    DEFAULT_SEVERITY: ClassVar[ErrorSeverity] = ErrorSeverity.ERROR

    def __post_init__(self) -> None:
        object.__setattr__(self, "severity", self.DEFAULT_SEVERITY)

    def to_diagnostic(self) -> str:
        raise NotImplementedError


@dataclass(frozen=True)
class UnregisteredSource(ValidationError):
    """Referencia @bibref nao encontrada no arquivo .bib."""

    bibref: str
    suggestions: list[str] = field(default_factory=list)

    def to_diagnostic(self) -> str:
        msg = f"Fonte @{self.bibref} nao encontrada no arquivo .bib\n"
        if self.suggestions:
            # Calcula diferença visual
            diff_count = self._count_differences(self.bibref, self.suggestions[0])
            msg += f"\nVoce quis dizer @{self.suggestions[0]}? (diferenca: {diff_count} {'letra' if diff_count == 1 else 'letras'})\n"

            if len(self.suggestions) > 1:
                msg += f"\nOutras opcoes similares:\n"
                for sug in self.suggestions[1:3]:
                    msg += f"  @{sug}\n"
        else:
            msg += "\nNenhuma entrada similar encontrada.\n"
            msg += "Dica: Verifique o campo 'ID' da entrada BibTeX\n"
        return msg.rstrip()

    def _count_differences(self, s1: str, s2: str) -> int:
        """Conta número de caracteres diferentes entre duas strings."""
        return sum(c1 != c2 for c1, c2 in zip(s1, s2)) + abs(len(s1) - len(s2))


@dataclass(frozen=True)
class OrphanItem(ValidationError):
    """ITEM sem SOURCE correspondente."""

    bibref: str

    def to_diagnostic(self) -> str:
        return (
            f"ITEM referencia @{self.bibref}, mas nao ha SOURCE com essa referencia.\n"
            f"  Crie um bloco SOURCE @{self.bibref} antes de usar em ITEMs."
        )


@dataclass(frozen=True)
class SourceWithoutItems(ValidationError):
    """SOURCE sem ITEMs associados."""

    bibref: str
    DEFAULT_SEVERITY: ClassVar[ErrorSeverity] = ErrorSeverity.WARNING

    def to_diagnostic(self) -> str:
        return (
            f"SOURCE @{self.bibref} nao possui ITEMs associados.\n"
            f"  Verifique se ha ITEMs com essa referencia."
        )


@dataclass(frozen=True)
class UndefinedCode(ValidationError):
    """Codigo usado em ITEM/CHAIN sem definicao em ONTOLOGY."""

    code: str
    context: str
    DEFAULT_SEVERITY: ClassVar[ErrorSeverity] = ErrorSeverity.WARNING

    def to_diagnostic(self) -> str:
        return (
            f"O codigo '{self.code}' usado em {self.context} nao esta definido na ontologia.\n"
            f"  Considere criar: ONTOLOGY {self.code}\n"
            f"      description: ...\n"
            f"  END ONTOLOGY"
        )


@dataclass(frozen=True)
class MissingProjectFile(ValidationError):
    """Nenhum arquivo .synp encontrado na raiz do workspace."""

    workspace_root: str
    DEFAULT_SEVERITY: ClassVar[ErrorSeverity] = ErrorSeverity.WARNING

    def to_diagnostic(self) -> str:
        return (
            f"Nenhum arquivo .synp encontrado na raiz do workspace: {self.workspace_root}\n"
            f"  Validacao semantica desativada.\n"
            f"  Para ativar validacao completa, crie um arquivo PROJECT na raiz do workspace.\n"
            f"  Exemplo: projeto.synp"
        )


@dataclass(frozen=True)
class MissingTemplateFile(ValidationError):
    """Template especificado no .synp nao existe no filesystem."""

    template_path: str
    project_file: str

    def to_diagnostic(self) -> str:
        return (
            f"Template '{self.template_path}' especificado em '{self.project_file}' nao encontrado.\n"
            f"  Verifique se o caminho esta correto e relativo ao diretorio do projeto.\n"
            f"  Ou crie o arquivo de template no local especificado."
        )


@dataclass(frozen=True)
class InvalidProjectFile(ValidationError):
    """Arquivo .synp contem erros de sintaxe e nao pode ser parseado."""

    project_file: str
    parse_error: str
    DEFAULT_SEVERITY: ClassVar[ErrorSeverity] = ErrorSeverity.WARNING

    def to_diagnostic(self) -> str:
        return (
            f"Arquivo de projeto '{self.project_file}' contem erros de sintaxe:\n"
            f"  {self.parse_error}\n"
            f"  Validacao semantica desativada ate que o arquivo seja corrigido."
        )


@dataclass(frozen=True)
class MissingRequiredField(ValidationError):
    """Campo REQUIRED ausente."""

    field_name: str
    block_type: str

    def to_diagnostic(self) -> str:
        return (
            f"Campo obrigatorio '{self.field_name}' ausente no bloco {self.block_type}.\n"
            f"  Adicione: {self.field_name}: <valor>"
        )


@dataclass(frozen=True)
class ForbiddenFieldPresent(ValidationError):
    """Campo FORBIDDEN presente."""

    field_name: str
    block_type: str

    def to_diagnostic(self) -> str:
        return (
            f"Campo '{self.field_name}' e proibido no bloco {self.block_type}.\n"
            f"  Remova esta linha do arquivo."
        )


@dataclass(frozen=True)
class UnknownFieldName(ValidationError):
    """Campo usado no arquivo nao esta definido no template."""

    field_name: str
    block_type: str

    def to_diagnostic(self) -> str:
        return (
            f"Campo '{self.field_name}' nao definido no template para bloco {self.block_type}.\n"
            f"  Defina um FIELD '{self.field_name}' no template ou ajuste o nome do campo."
        )


@dataclass(frozen=True)
class MissingBundleField(ValidationError):
    """Campo de BUNDLE ausente (violacao de pareamento)."""

    bundle_fields: Tuple[str, ...]
    present_fields: set[str]

    def to_diagnostic(self) -> str:
        bundle_str = ", ".join(self.bundle_fields)
        missing = set(self.bundle_fields) - self.present_fields
        missing_str = ", ".join(missing)
        return (
            f"Campos do BUNDLE ({bundle_str}) devem aparecer juntos.\n"
            f"  Faltam: {missing_str}\n"
            f"  Adicione os campos faltantes ou remova os presentes."
        )


@dataclass(frozen=True)
class BundleCountMismatch(ValidationError):
    """Campos de BUNDLE com quantidades diferentes."""

    bundle_fields: Tuple[str, ...]
    counts: Dict[str, int]

    def to_diagnostic(self) -> str:
        bundle_str = ", ".join(self.bundle_fields)
        count_str = ", ".join(f"{k}={v}" for k, v in self.counts.items())
        return (
            f"BUNDLE ({bundle_str}) tem contagens diferentes: {count_str}\n"
            f"  Todos os campos do bundle devem aparecer o mesmo numero de vezes.\n"
            f"  Adicione ou remova entradas para igualar as contagens."
        )


@dataclass(frozen=True)
class InvalidEnumeratedValue(ValidationError):
    """Valor fora da lista ENUMERATED."""

    field_name: str
    value: str
    valid_values: list[str]

    def to_diagnostic(self) -> str:
        valid_str = ", ".join(self.valid_values)
        return (
            f"Valor '{self.value}' invalido para campo '{self.field_name}'.\n"
            f"  Valores permitidos: {valid_str}"
        )


@dataclass(frozen=True)
class InvalidFieldType(ValidationError):
    """Tipo de valor incompativel com FieldSpec."""

    field_name: str
    expected: str
    actual: str

    def to_diagnostic(self) -> str:
        return (
            f"Tipo invalido para campo '{self.field_name}'.\n"
            f"  Esperado: {self.expected}\n"
            f"  Encontrado: {self.actual}"
        )


@dataclass(frozen=True)
class InvalidOrderedValue(ValidationError):
    """Valor fora do range ORDERED."""

    field_name: str
    value: Union[int, str]
    valid_options: list[str]

    def to_diagnostic(self) -> str:
        if isinstance(self.value, int):
            indices = ", ".join(f"[{i}]" for i in range(1, len(self.valid_options) + 1))
            return (
                f"Indice {self.value} invalido para campo '{self.field_name}'.\n"
                f"  Indices validos: {indices}"
            )
        return (
            f"Label '{self.value}' invalido para campo '{self.field_name}'.\n"
            f"  Valores validos: {', '.join(self.valid_options)}"
        )


@dataclass(frozen=True)
class ScaleOutOfRange(ValidationError):
    """Valor SCALE fora do intervalo [min..max]."""

    field_name: str
    value: float
    min_value: float
    max_value: float

    def to_diagnostic(self) -> str:
        return (
            f"Valor {self.value} fora do intervalo para '{self.field_name}'.\n"
            f"  Intervalo permitido: [{self.min_value}..{self.max_value}]"
        )


@dataclass(frozen=True)
class ChainArityViolation(ValidationError):
    """Violacao de ARITY em cadeia causal."""

    expected: str
    found: int

    def to_diagnostic(self) -> str:
        return (
            f"Cadeia causal viola ARITY {self.expected} "
            f"(encontrados {self.found} codigos).\n"
            f"  Ajuste o numero de elementos na cadeia."
        )


@dataclass(frozen=True)
class InvalidChainRelation(ValidationError):
    """Relacao nao definida no template."""

    relation: str
    valid_relations: list[str]
    relation_descriptions: Optional[Dict[str, str]] = None

    def to_diagnostic(self) -> str:
        # Tenta encontrar sugestão por similaridade
        suggestion = self._find_similar_relation()

        msg = f"Relacao '{self.relation}' nao existe no template."

        if suggestion:
            msg += f" Voce quis dizer '{suggestion}'?\n"
        else:
            msg += "\n"

        if self.relation_descriptions:
            msg += "\nRelacoes validas:\n"
            for rel, desc in sorted(self.relation_descriptions.items()):
                msg += f"  {rel} - {desc}\n"
        else:
            valid_str = ", ".join(sorted(self.valid_relations))
            msg += f"\nRelacoes validas: {valid_str}\n"

        return msg.rstrip()

    def _find_similar_relation(self) -> Optional[str]:
        """Encontra relação similar usando distância de edição."""
        from difflib import get_close_matches
        matches = get_close_matches(
            self.relation.upper(),
            [r.upper() for r in self.valid_relations],
            n=1,
            cutoff=0.6
        )
        return matches[0] if matches else None


@dataclass(frozen=True)
class MalformedQualifiedChain(ValidationError):
    """Chain qualificada com estrutura incorreta."""

    elements: list[str]

    def to_diagnostic(self) -> str:
        return (
            f"Cadeia qualificada mal formada.\n"
            f"  Padrao esperado: Codigo -> RELACAO -> Codigo -> RELACAO -> Codigo\n"
            f"  Encontrado: {' -> '.join(self.elements)}"
        )


@dataclass
class ValidationResult:
    """Resultado agregado de validacao com diagnosticos estruturados."""

    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)
    info: list[ValidationError] = field(default_factory=list)

    def has_errors(self) -> bool:
        return len(self.errors) > 0

    def has_warnings(self) -> bool:
        return len(self.warnings) > 0

    def is_valid(self) -> bool:
        return not self.has_errors()

    def add(self, error: ValidationError) -> None:
        match error.severity:
            case ErrorSeverity.ERROR:
                self.errors.append(error)
            case ErrorSeverity.WARNING:
                self.warnings.append(error)
            case ErrorSeverity.INFO:
                self.info.append(error)

    def merge(self, other: "ValidationResult") -> "ValidationResult":
        return ValidationResult(
            errors=self.errors + other.errors,
            warnings=self.warnings + other.warnings,
            info=self.info + other.info,
        )

    def to_diagnostics(self) -> str:
        lines: list[str] = []
        if self.errors:
            lines.append("=== ERROS ===")
            for err in self.errors:
                lines.append(err.to_diagnostic())
                lines.append("")
        if self.warnings:
            lines.append("=== AVISOS ===")
            for warn in self.warnings:
                lines.append(warn.to_diagnostic())
                lines.append("")
        if self.info:
            lines.append("=== INFORMACOES ===")
            for inf in self.info:
                lines.append(inf.to_diagnostic())
                lines.append("")
        return "\n".join(lines)


def handle_result(
    result: Result[T, ValidationError],
    on_ok: Callable[[T], None],
    on_err: Callable[[ValidationError], None],
) -> None:
    """Helper para pattern matching em Result."""
    match result:
        case Ok(value):
            on_ok(value)
        case Err(error):
            on_err(error)
