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
        raise ValueError(f"Tried unwrap() on Err: {self.error}")

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

    def to_cli_line(self) -> str:
        """Mensagem compacta de uma linha para saida CLI.

        Padrao: extrai primeira linha de to_diagnostic().
        Subclasses devem sobrescrever para mensagens mais informativas.
        """
        return self.to_diagnostic().split("\n")[0].strip()


@dataclass(frozen=True)
class UnregisteredSource(ValidationError):
    """Referencia @bibref nao encontrada no arquivo .bib."""

    bibref: str
    suggestions: list[str] = field(default_factory=list)
    CODE: ClassVar[str] = "SYNESIS_E001"

    def to_diagnostic(self) -> str:
        msg = (
            f"The reference `@{self.bibref}` was not found in the references file (`.bib`).\n"
            f"  Check that the identifier is spelled correctly — it must match\n"
            f"  the `ID` field of the BibTeX entry exactly.\n"
        )
        if self.suggestions:
            formatted = ", ".join(f"`@{s}`" for s in self.suggestions)
            msg += f"  Similar keys found in the `.bib`: {formatted}.\n"
        msg += f"  See the `.bib` file for the available references."
        return msg

    def to_cli_line(self) -> str:
        if self.suggestions:
            formatted = ", ".join(f"`@{s}`" for s in self.suggestions)
            suffix = f". Suggestions: {formatted}"
        else:
            suffix = ""
        return f"Reference `@{self.bibref}` not found in the .bib{suffix}"


@dataclass(frozen=True)
class OrphanItem(ValidationError):
    """ITEM sem SOURCE correspondente."""

    bibref: str
    CODE: ClassVar[str] = "SYNESIS_E002"

    def to_diagnostic(self) -> str:
        return (
            f"This ITEM references `@{self.bibref}`, but there is no SOURCE block with\n"
            f"  that reference in this file. Every ITEM needs a matching SOURCE\n"
            f"  in the same file.\n"
            f"  Create a `SOURCE @{self.bibref}` block before this ITEM, or check\n"
            f"  that the reference is correct."
        )

    def to_cli_line(self) -> str:
        return f"ITEM `@{self.bibref}` has no matching SOURCE in this file"


@dataclass(frozen=True)
class SourceWithoutItems(ValidationError):
    """SOURCE sem ITEMs associados."""

    bibref: str
    CODE: ClassVar[str] = "SYNESIS_E003"
    DEFAULT_SEVERITY: ClassVar[ErrorSeverity] = ErrorSeverity.WARNING

    def to_diagnostic(self) -> str:
        return (
            f"The `SOURCE @{self.bibref}` block has no associated ITEM. A SOURCE\n"
            f"  exists to give context to units of analysis — without ITEMs, the source was\n"
            f"  registered but never analyzed.\n"
            f"  Check whether ITEMs with this reference exist in another project file,\n"
            f"  or add at least one ITEM to this SOURCE."
        )

    def to_cli_line(self) -> str:
        return f"SOURCE `@{self.bibref}` has no associated ITEM"


@dataclass(frozen=True)
class UndefinedCode(ValidationError):
    """Codigo usado em ITEM/CHAIN sem definicao em ONTOLOGY."""

    code: str
    context: str
    suggestions: list[str] = field(default_factory=list)
    CODE: ClassVar[str] = "SYNESIS_E004"
    DEFAULT_SEVERITY: ClassVar[ErrorSeverity] = ErrorSeverity.WARNING

    def to_diagnostic(self) -> str:
        msg = (
            f"The code `{self.code}` is not defined in the project's organizing model. Every\n"
            f"  code used in the annotations needs a matching concept\n"
            f"  declared in an ONTOLOGY block.\n"
        )
        if self.suggestions:
            msg += f"  Did you mean `{self.suggestions[0]}`?\n"
        msg += (
            f"  To create the concept, add to a `.syno` file:\n"
            f"      ONTOLOGY {self.code}\n"
            f"          description: ...\n"
            f"      END ONTOLOGY"
        )
        return msg

    def to_cli_line(self) -> str:
        suggestion = f". Suggested fix -> `{self.suggestions[0]}`" if self.suggestions else ""
        return f"Code `{self.code}` is not defined in the organizing model{suggestion}"


@dataclass(frozen=True)
class UndefinedCodesSummary(ValidationError):
    """Resumo dos codigos sem conceito na ontologia, quando a checagem esta desligada.

    A checagem de codigo por ocorrencia (E004) e opcional: antes de a ontologia
    existir, todo codigo in vivo a dispara (66 mil avisos no face85). Desligada,
    os codigos continuam sendo contados e o projeto recebe esta unica linha.
    """

    code_count: int
    occurrence_count: int
    CODE: ClassVar[str] = "SYNESIS_E090"
    DEFAULT_SEVERITY: ClassVar[ErrorSeverity] = ErrorSeverity.WARNING

    def to_diagnostic(self) -> str:
        return (
            f"{self.code_count} code(s) used in the annotations have no concept in the\n"
            f"  organizing model ({self.occurrence_count} occurrence(s)). The per-occurrence list,\n"
            f"  with suggestions, is off: use `synesis compile --check-codes` or the\n"
            f"  extension setting `synesisExplorer.diagnostics.checkCodes`."
        )

    def to_cli_line(self) -> str:
        return (
            f"{self.code_count} code(s) without a concept in the organizing model "
            f"({self.occurrence_count} occurrence(s)); use --check-codes to list them"
        )


@dataclass(frozen=True)
class MissingProjectFile(ValidationError):
    """Nenhum arquivo .synp encontrado na raiz do workspace."""

    workspace_root: str
    CODE: ClassVar[str] = "SYNESIS_E064"
    DEFAULT_SEVERITY: ClassVar[ErrorSeverity] = ErrorSeverity.WARNING

    def to_diagnostic(self) -> str:
        return (
            f"No .synp file found at the workspace root: {self.workspace_root}\n"
            f"  Semantic validation disabled.\n"
            f"  To enable full validation, create a PROJECT file at the workspace root.\n"
            f"  Example: project.synp"
        )

    def to_cli_line(self) -> str:
        return f"No .synp found in `{self.workspace_root}` — create a PROJECT file"


@dataclass(frozen=True)
class MissingTemplateFile(ValidationError):
    """Template especificado no .synp nao existe no filesystem."""

    template_path: str
    project_file: str
    CODE: ClassVar[str] = "SYNESIS_E064"

    def to_diagnostic(self) -> str:
        return (
            f"Template '{self.template_path}' given in '{self.project_file}' was not found.\n"
            f"  Check that the path is correct and relative to the project folder.\n"
            f"  Or create the template file at the given location."
        )

    def to_cli_line(self) -> str:
        return f"Template `{self.template_path}` not found"


@dataclass(frozen=True)
class InvalidProjectFile(ValidationError):
    """Arquivo .synp contem erros de sintaxe e nao pode ser parseado."""

    project_file: str
    parse_error: str
    CODE: ClassVar[str] = "SYNESIS_E064"
    DEFAULT_SEVERITY: ClassVar[ErrorSeverity] = ErrorSeverity.WARNING

    def to_diagnostic(self) -> str:
        return (
            f"Project file '{self.project_file}' has syntax errors:\n"
            f"  {self.parse_error}\n"
            f"  Semantic validation is disabled until the file is fixed."
        )

    def to_cli_line(self) -> str:
        return f"`{self.project_file}` has a syntax error: {self.parse_error}"


@dataclass(frozen=True)
class MissingRequiredField(ValidationError):
    """Campo REQUIRED ausente."""

    field_name: str
    block_type: str
    CODE: ClassVar[str] = "SYNESIS_E020"

    def to_diagnostic(self) -> str:
        return (
            f"The field `{self.field_name}` is required in this {self.block_type} block,\n"
            f"  but it was not found.\n"
            f"  Add the line `{self.field_name}: <value>` to the block before\n"
            f"  `END {self.block_type}`."
        )

    def to_cli_line(self) -> str:
        return f"Required field `{self.field_name}` missing in {self.block_type} block"


@dataclass(frozen=True)
class ForbiddenFieldPresent(ValidationError):
    """Campo FORBIDDEN presente."""

    field_name: str
    block_type: str
    CODE: ClassVar[str] = "SYNESIS_E021"

    def to_diagnostic(self) -> str:
        return (
            f"Field '{self.field_name}' is forbidden in the {self.block_type} block.\n"
            f"  Remove this line from the file."
        )

    def to_cli_line(self) -> str:
        return f"Forbidden field `{self.field_name}` in {self.block_type} block — remove this line"


@dataclass(frozen=True)
class UnknownFieldName(ValidationError):
    """Campo usado no arquivo nao esta definido no template."""

    field_name: str
    block_type: str
    CODE: ClassVar[str] = "SYNESIS_E022"

    def to_diagnostic(self) -> str:
        return (
            f"Field '{self.field_name}' is not defined in the template for the {self.block_type} block.\n"
            f"  Define a FIELD '{self.field_name}' in the template or fix the field name."
        )

    def to_cli_line(self) -> str:
        return f"Unknown field `{self.field_name}` in {self.block_type} block"


@dataclass(frozen=True)
class MissingBundleField(ValidationError):
    """Campo de BUNDLE ausente (violacao de pareamento)."""

    bundle_fields: Tuple[str, ...]
    present_fields: set[str]
    CODE: ClassVar[str] = "SYNESIS_E016"

    def to_diagnostic(self) -> str:
        bundle_str = ", ".join(self.bundle_fields)
        missing = set(self.bundle_fields) - self.present_fields
        missing_str = ", ".join(sorted(missing))
        return (
            f"The fields `{bundle_str}` form an indivisible bundle in this block\n"
            f"  — they represent compound information and must always appear together.\n"
            f"  One or more bundle fields are missing: `{missing_str}`.\n"
            f"  Add the missing fields or remove all fields of the bundle.\n"
            f"  A partial bundle is not valid."
        )

    def to_cli_line(self) -> str:
        missing = set(self.bundle_fields) - self.present_fields
        missing_str = ", ".join(f"`{f}`" for f in sorted(missing))
        bundle_str = ", ".join(self.bundle_fields)
        return f"Bundle ({bundle_str}): missing fields {missing_str}"


@dataclass(frozen=True)
class BundleCountMismatch(ValidationError):
    """Campos de BUNDLE com quantidades diferentes."""

    bundle_fields: Tuple[str, ...]
    counts: Dict[str, int]
    CODE: ClassVar[str] = "SYNESIS_E017"

    def to_diagnostic(self) -> str:
        bundle_str = ", ".join(self.bundle_fields)
        count_str = ", ".join(f"{k}={v}" for k, v in self.counts.items())
        return (
            f"BUNDLE ({bundle_str}) has different counts: {count_str}\n"
            f"  Every bundle field must appear the same number of times.\n"
            f"  Add or remove entries to make the counts equal."
        )

    def to_cli_line(self) -> str:
        bundle_str = ", ".join(self.bundle_fields)
        count_str = ", ".join(f"{k}={v}" for k, v in self.counts.items())
        return f"Bundle ({bundle_str}) with unequal counts: {count_str}"


@dataclass(frozen=True)
class InvalidEnumeratedValue(ValidationError):
    """Valor fora da lista ENUMERATED."""

    field_name: str
    value: str
    valid_values: list[str]
    CODE: ClassVar[str] = "SYNESIS_E027"

    def to_diagnostic(self) -> str:
        from difflib import get_close_matches
        msg = (
            f"The value `{self.value}` is not recognized for the field `{self.field_name}`.\n"
            f"  This field only accepts values from a closed list.\n"
        )
        suggestions = get_close_matches(self.value, self.valid_values, n=1, cutoff=0.6)
        if suggestions:
            msg += f"  Did you mean `{suggestions[0]}`?\n"
        MAX_SHOWN = 8
        if len(self.valid_values) <= MAX_SHOWN:
            valid_str = ", ".join(f"`{v}`" for v in self.valid_values)
            msg += f"  Available values: {valid_str}."
        else:
            shown = ", ".join(f"`{v}`" for v in self.valid_values[:MAX_SHOWN])
            msg += f"  Available values: {shown} — and {len(self.valid_values) - MAX_SHOWN} more. See the template for the full list."
        return msg

    def to_cli_line(self) -> str:
        from difflib import get_close_matches
        suggestion = get_close_matches(self.value, self.valid_values, n=1, cutoff=0.6)
        suffix = f". Suggested fix -> `{suggestion[0]}`" if suggestion else ""
        return f"Invalid value `{self.value}` for `{self.field_name}`{suffix}"


@dataclass(frozen=True)
class InvalidFieldType(ValidationError):
    """Tipo de valor incompativel com FieldSpec."""

    field_name: str
    expected: str
    actual: str
    CODE: ClassVar[str] = "SYNESIS_E028"

    def to_diagnostic(self) -> str:
        # Erro 29: data em formato inválido
        if self.expected == "date":
            return (
                f"The date given in the field `{self.field_name}` is not in a\n"
                f"  recognized format. The accepted format is `YYYY-MM-DD`.\n"
                f"  For example: `2024-03-15` for March 15, 2024."
            )
        # Erro 30: número em campo de texto
        if self.expected in {"string", "text"} and self.actual in {"int", "float"}:
            return (
                f"The field `{self.field_name}` expects text, but received a value that\n"
                f"  looks like a number only. Text and quotation fields need\n"
                f"  textual content.\n"
                f"  If the number is part of a quotation or note, write it as part\n"
                f"  of a sentence. If it is numeric data, check whether the right field\n"
                f"  would be of type SCALE or ORDERED."
            )
        # Caso genérico (chain, outros)
        return (
            f"Invalid type for the field `{self.field_name}`.\n"
            f"  Expected: {self.expected}\n"
            f"  Found: {self.actual}"
        )

    def to_cli_line(self) -> str:
        if self.expected == "date":
            return f"Invalid date in `{self.field_name}` — use the YYYY-MM-DD format"
        if self.expected in {"string", "text"} and self.actual in {"int", "float"}:
            return f"Field `{self.field_name}` expects text, received a number"
        return f"Invalid type in `{self.field_name}`: expected {self.expected}, found {self.actual}"


@dataclass(frozen=True)
class InvalidOrderedValue(ValidationError):
    """Valor fora do range ORDERED."""

    field_name: str
    value: Union[int, str]
    valid_options: list[str]
    CODE: ClassVar[str] = "SYNESIS_E029"

    def to_diagnostic(self) -> str:
        from difflib import get_close_matches
        msg = (
            f"The value `{self.value}` is not valid for the field `{self.field_name}`.\n"
            f"  This field uses an ordered scale with specific options.\n"
        )
        if isinstance(self.value, str):
            suggestions = get_close_matches(self.value, self.valid_options, n=1, cutoff=0.6)
            if suggestions:
                msg += f"  Did you mean `{suggestions[0]}`?\n"
        MAX_SHOWN = 8
        if len(self.valid_options) <= MAX_SHOWN:
            opts_str = ", ".join(f"`{v}`" for v in self.valid_options)
            msg += f"  Opcoes disponiveis: {opts_str}.\n"
        else:
            shown = ", ".join(f"`{v}`" for v in self.valid_options[:MAX_SHOWN])
            msg += f"  Opcoes disponiveis: {shown} — e outras {len(self.valid_options) - MAX_SHOWN}. Consulte o template.\n"
        msg += f"  You can use the text label or the position number on the scale."
        return msg

    def to_cli_line(self) -> str:
        from difflib import get_close_matches
        if isinstance(self.value, str):
            suggestion = get_close_matches(self.value, self.valid_options, n=1, cutoff=0.6)
            suffix = f". Suggested fix -> `{suggestion[0]}`" if suggestion else ""
        else:
            suffix = ""
        return f"Invalid value `{self.value}` for `{self.field_name}` (ordered){suffix}"


@dataclass(frozen=True)
class ScaleOutOfRange(ValidationError):
    """Valor SCALE fora do intervalo [min..max]."""

    field_name: str
    value: float
    min_value: float
    max_value: float
    CODE: ClassVar[str] = "SYNESIS_E030"

    def to_diagnostic(self) -> str:
        return (
            f"The value `{self.value}` is outside the allowed range for the field\n"
            f"  `{self.field_name}`. This field only accepts values between\n"
            f"  `{self.min_value}` and `{self.max_value}`.\n"
            f"  Fix the value so it falls within this range."
        )

    def to_cli_line(self) -> str:
        return f"Value `{self.value}` outside the range [{self.min_value}..{self.max_value}] in the field `{self.field_name}`"


@dataclass(frozen=True)
class ChainArityViolation(ValidationError):
    """Violacao de ARITY em cadeia causal."""

    expected: str
    found: int
    CODE: ClassVar[str] = "SYNESIS_E007"

    def to_diagnostic(self) -> str:
        return (
            f"This chain has too few elements. The template requires `{self.expected}` concepts,\n"
            f"  but only `{self.found}` were found.\n"
            f"  A chain must connect at least two concepts with `->`.\n"
            f"  Add the missing elements until the minimum requirement is met."
        )

    def to_cli_line(self) -> str:
        return f"Chain with {self.found} element(s), the template requires {self.expected}"


@dataclass(frozen=True)
class InvalidChainRelation(ValidationError):
    """Relacao nao definida no template."""

    relation: str
    valid_relations: list[str]
    relation_descriptions: Optional[Dict[str, str]] = None
    CODE: ClassVar[str] = "SYNESIS_E010"

    def to_diagnostic(self) -> str:
        # Tenta encontrar sugestão por similaridade
        suggestion = self._find_similar_relation()

        msg = f"The relation `{self.relation}` used in this chain is not declared in the\n"
        msg += f"  template for this field.\n"

        if suggestion:
            msg += f"  Did you mean `{suggestion}`?\n"

        if self.relation_descriptions:
            msg += "  Available relations:\n"
            for rel, desc in sorted(self.relation_descriptions.items()):
                msg += f"    {rel} - {desc}\n"
        else:
            valid_str = ", ".join(f"`{r}`" for r in sorted(self.valid_relations))
            msg += f"  Available relations: {valid_str}.\n"

        msg += "  Use one of the listed relations or ask the project coordinator\n"
        msg += "  to add the new relation to the template."
        return msg

    def to_cli_line(self) -> str:
        suggestion = self._find_similar_relation()
        suffix = f". Suggested fix -> `{suggestion}`" if suggestion else ""
        return f"Relation `{self.relation}` not declared in the template{suffix}"

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
    CODE: ClassVar[str] = "SYNESIS_E011"

    def to_diagnostic(self) -> str:
        cadeia = " -> ".join(self.elements)
        # Identifica o primeiro par problemático para contextualizar o erro
        par_problematico = ""
        if len(self.elements) >= 2:
            for i in range(len(self.elements) - 1):
                par_problematico = f"`{self.elements[i]} -> {self.elements[i+1]}`"
                break
        return (
            f"The structure of this chain is incorrect: {par_problematico}\n"
            f"  Found:    {cadeia}\n"
            f"  Expected: [Concept] -> [RELATION] -> [Concept]\n"
            f"  In qualified chains, even positions are always relation types,\n"
            f"  not concepts. Review the order of the elements."
        )

    def to_cli_line(self) -> str:
        cadeia = " -> ".join(self.elements)
        return f"Qualified chain with incorrect structure: {cadeia}"


# ---------------------------------------------------------------------------
# Erros de Declaração de Template (Fase 1 — erros 18, 39-60, 69)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DuplicateFieldName(ValidationError):
    """Dois FIELD com o mesmo nome no template. (erro 69)"""

    field_name: str
    CODE: ClassVar[str] = "SYNESIS_E069"

    def to_diagnostic(self) -> str:
        return (
            f"The field '{self.field_name}' is defined more than once in the template.\n"
            f"  Field names must be unique. Remove the duplicate definition or rename\n"
            f"  one of the fields if they represent different information."
        )

    def to_cli_line(self) -> str:
        return f"Field `{self.field_name}` defined more than once in the template"


@dataclass(frozen=True)
class UndefinedFieldInScopeFields(ValidationError):
    """Campo listado em SCOPE FIELDS sem FIELD correspondente. (erros 39-41)"""

    field_name: str
    scope: str  # "SOURCE", "ITEM" ou "ONTOLOGY"
    CODE: ClassVar[str] = "SYNESIS_E039"

    def to_diagnostic(self) -> str:
        return (
            f"The field '{self.field_name}' is listed in `{self.scope} FIELDS`,\n"
            f"  but there is no matching `FIELD` definition in the template.\n"
            f"  Add to the template:\n"
            f"      FIELD {self.field_name} TYPE TEXT\n"
            f"          SCOPE {self.scope}\n"
            f"      END FIELD\n"
            f"  This problem is in the template definition. If you are not the author\n"
            f"  of the template, tell the project coordinator."
        )

    def to_cli_line(self) -> str:
        return f"Field `{self.field_name}` listed in `{self.scope} FIELDS` without a FIELD definition"


@dataclass(frozen=True)
class OrphanFieldDefinition(ValidationError):
    """FIELD definido mas nao listado em nenhum SCOPE FIELDS. (erro 42)"""

    field_name: str
    scope: str
    CODE: ClassVar[str] = "SYNESIS_E042"
    DEFAULT_SEVERITY: ClassVar[ErrorSeverity] = ErrorSeverity.WARNING

    def to_diagnostic(self) -> str:
        return (
            f"The field '{self.field_name}' is defined in the template, but does not appear\n"
            f"  in any `SOURCE FIELDS`, `ITEM FIELDS` or `ONTOLOGY FIELDS` block.\n"
            f"  A field that is defined but not listed is never recognized in the annotations.\n"
            f"  Include `{self.field_name}` in the `{self.scope} FIELDS` block matching\n"
            f"  its scope, or remove the definition if it is not needed."
        )

    def to_cli_line(self) -> str:
        return f"Field `{self.field_name}` defined but missing from `{self.scope} FIELDS`"


@dataclass(frozen=True)
class SingleFieldBundle(ValidationError):
    """BUNDLE declarado com apenas um campo. (erro 18)"""

    bundle_fields: tuple
    CODE: ClassVar[str] = "SYNESIS_E018"

    def to_diagnostic(self) -> str:
        bundle_name = ", ".join(self.bundle_fields) if self.bundle_fields else "?"
        return (
            f"The bundle `{bundle_name}` in the template was declared with only one field.\n"
            f"  A bundle needs at least two fields — it exists to ensure that\n"
            f"  related information always appears together.\n"
            f"  This problem is in the template definition. If you are not the author\n"
            f"  of the template, tell the project coordinator.\n"
            f"  Add the other fields to the bundle or remove the BUNDLE declaration,\n"
            f"  making the field simply REQUIRED or OPTIONAL."
        )

    def to_cli_line(self) -> str:
        bundle_name = ", ".join(self.bundle_fields) if self.bundle_fields else "?"
        return f"Bundle `{bundle_name}` declared with only one field in the template"


@dataclass(frozen=True)
class FieldScopeListMismatch(ValidationError):
    """Campo listado em SCOPE FIELDS cujo FIELD tem SCOPE diferente. (erro 6)"""

    field_name: str
    listed_scope: str
    actual_scope: str
    CODE: ClassVar[str] = "SYNESIS_E006"

    def to_diagnostic(self) -> str:
        return (
            f"The field '{self.field_name}' is listed in `{self.listed_scope} FIELDS`,\n"
            f"  but its FIELD definition declares `SCOPE {self.actual_scope}`.\n"
            f"  Each listed field needs its own definition with the same scope.\n"
            f"  Fix the scope in the FIELD definition or move the field to the right block.\n"
            f"  This problem is in the template definition. If you are not the author\n"
            f"  of the template, tell the project coordinator."
        )

    def to_cli_line(self) -> str:
        return f"Field `{self.field_name}` listed in `{self.listed_scope} FIELDS` but its declared SCOPE is {self.actual_scope}"


@dataclass(frozen=True)
class ChainWithoutArity(ValidationError):
    """TYPE CHAIN sem declaracao ARITY. (erro 47)"""

    field_name: str
    CODE: ClassVar[str] = "SYNESIS_E047"

    def to_diagnostic(self) -> str:
        return (
            f"The field '{self.field_name}' is of type CHAIN, but does not declare `ARITY`.\n"
            f"  Without ARITY, the compiler cannot check whether the chains written by\n"
            f"  researchers have the minimum number of concepts required.\n"
            f"  Add a declaration such as `ARITY >= 2` to ensure that every chain\n"
            f"  connects at least two concepts."
        )

    def to_cli_line(self) -> str:
        return f"Field `{self.field_name}` (CHAIN) without an ARITY declaration in the template"


@dataclass(frozen=True)
class ArityRelationsMismatch(ValidationError):
    """ARITY incompativel com numero de RELATIONS declaradas. (erro 48)"""

    field_name: str
    arity: int
    n_relations: int
    CODE: ClassVar[str] = "SYNESIS_E048"

    def to_diagnostic(self) -> str:
        arity_minus_1 = self.arity - 1
        return (
            f"The field '{self.field_name}' declares `ARITY >= {self.arity}`, which requires\n"
            f"  at least {self.arity} concepts per chain — but only {self.n_relations}\n"
            f"  relation(s) are defined in `RELATIONS`. To connect {self.arity}\n"
            f"  concepts in sequence, at least {arity_minus_1} relations are needed.\n"
            f"  Add the missing relations to the `RELATIONS` block or lower the `ARITY` value."
        )

    def to_cli_line(self) -> str:
        return f"Field `{self.field_name}`: ARITY >= {self.arity} requires more relations than the {self.n_relations} declared"


@dataclass(frozen=True)
class OrderedWithoutValues(ValidationError):
    """TYPE ORDERED sem bloco VALUES. (erro 49)"""

    field_name: str
    CODE: ClassVar[str] = "SYNESIS_E049"

    def to_diagnostic(self) -> str:
        return (
            f"The field '{self.field_name}' is of type ORDERED, but does not define a\n"
            f"  `VALUES` block with the valid options and their order. Without it, there is no\n"
            f"  way to validate the values entered or show the scale to researchers.\n"
            f"  Add a `VALUES` block listing the options in ascending order."
        )

    def to_cli_line(self) -> str:
        return f"Field `{self.field_name}` (ORDERED) without a VALUES block in the template"


@dataclass(frozen=True)
class EnumeratedWithoutValues(ValidationError):
    """TYPE ENUMERATED sem bloco VALUES. (erro 50)"""

    field_name: str
    CODE: ClassVar[str] = "SYNESIS_E050"

    def to_diagnostic(self) -> str:
        return (
            f"The field '{self.field_name}' is of type ENUMERATED, but does not define a\n"
            f"  `VALUES` block with the valid options. Without it, any value would be accepted,\n"
            f"  losing control over the vocabulary.\n"
            f"  Add a `VALUES` block listing every option accepted for this field."
        )

    def to_cli_line(self) -> str:
        return f"Field `{self.field_name}` (ENUMERATED) without a VALUES block in the template"


@dataclass(frozen=True)
class ScaleWithoutFormat(ValidationError):
    """TYPE SCALE sem declaracao FORMAT. (erro 51)"""

    field_name: str
    CODE: ClassVar[str] = "SYNESIS_E051"

    def to_diagnostic(self) -> str:
        return (
            f"The field '{self.field_name}' is of type SCALE, but does not declare the allowed\n"
            f"  numeric range. Without the range, the compiler cannot check whether\n"
            f"  the values fall within the expected interval.\n"
            f"  Add a declaration such as `FORMAT [0..10]` to set the minimum\n"
            f"  and maximum accepted values."
        )

    def to_cli_line(self) -> str:
        return f"Field `{self.field_name}` (SCALE) without a FORMAT declaration in the template"


@dataclass(frozen=True)
class InvalidFormatSyntax(ValidationError):
    """Sintaxe invalida na declaracao FORMAT de campo SCALE. (erro 52)"""

    field_name: str
    format_str: str
    CODE: ClassVar[str] = "SYNESIS_E052"

    def to_diagnostic(self) -> str:
        return (
            f"The range declared in `FORMAT` for the field '{self.field_name}' is not\n"
            f"  in the expected format: `{self.format_str}`\n"
            f"  The correct format uses brackets and two dots as separator: `[minimum..maximum]`.\n"
            f"  Valid examples: `[1..5]`, `[0..100]`, `[0.0..1.0]`."
        )

    def to_cli_line(self) -> str:
        return f"Invalid FORMAT in `{self.field_name}`: `{self.format_str}` — use `[min..max]`"


@dataclass(frozen=True)
class InvalidArityOperator(ValidationError):
    """Operador invalido na declaracao ARITY. (erro 53)"""

    field_name: str
    operator: str
    CODE: ClassVar[str] = "SYNESIS_E053"

    def to_diagnostic(self) -> str:
        return (
            f"The `ARITY` declaration of the field '{self.field_name}' uses an\n"
            f"  unrecognized operator: `{self.operator}`.\n"
            f"  The valid operators are: `>=`, `>`, `<=`, `<`, `=`.\n"
            f"  For example: `ARITY >= 2` means 'at least two concepts per chain'."
        )

    def to_cli_line(self) -> str:
        return f"Invalid operator `{self.operator}` in ARITY of field `{self.field_name}` — use >=, >, <=, <, ="


@dataclass(frozen=True)
class NonIntegerArityValue(ValidationError):
    """Valor de ARITY nao e um inteiro (ex: 2.0). (erro 60)"""

    field_name: str
    value: str
    CODE: ClassVar[str] = "SYNESIS_E060"

    def to_diagnostic(self) -> str:
        return (
            f"The `ARITY` declaration of the field '{self.field_name}' uses the value\n"
            f"  `{self.value}`, which is not an integer.\n"
            f"  ARITY counts concepts per chain and must be an integer.\n"
            f"  For example: `ARITY >= 2`, not `ARITY >= 2.0`."
        )

    def to_cli_line(self) -> str:
        return f"ARITY of field `{self.field_name}` uses non-integer value `{self.value}` — use an integer (e.g. 2)"


@dataclass(frozen=True)
class FormatOnNonScale(ValidationError):
    """FORMAT declarado em campo que nao e TYPE SCALE. (erro 54)"""

    field_name: str
    field_type: str
    CODE: ClassVar[str] = "SYNESIS_E054"

    def to_diagnostic(self) -> str:
        return (
            f"The field '{self.field_name}' declares `FORMAT`, but its type is `{self.field_type}`.\n"
            f"  The `FORMAT [min..max]` declaration is exclusive to SCALE fields.\n"
            f"  This problem is in the template definition.\n"
            f"  Remove the `FORMAT` declaration or change the field type to `SCALE`."
        )

    def to_cli_line(self) -> str:
        return f"FORMAT declared in `{self.field_name}` (type {self.field_type}) — FORMAT is exclusive to SCALE"


@dataclass(frozen=True)
class ArityOnNonChain(ValidationError):
    """ARITY declarado em campo que nao e TYPE CHAIN. (erro 55)"""

    field_name: str
    field_type: str
    CODE: ClassVar[str] = "SYNESIS_E055"

    def to_diagnostic(self) -> str:
        return (
            f"The field '{self.field_name}' declares `ARITY`, but its type is `{self.field_type}`.\n"
            f"  The `ARITY` declaration is exclusive to CHAIN fields.\n"
            f"  This problem is in the template definition.\n"
            f"  Remove the `ARITY` declaration or change the field type to `CHAIN`."
        )

    def to_cli_line(self) -> str:
        return f"ARITY declared in `{self.field_name}` (type {self.field_type}) — ARITY is exclusive to CHAIN"


@dataclass(frozen=True)
class RelationsOnNonChain(ValidationError):
    """RELATIONS definido em campo que nao e TYPE CHAIN. (erro 56)"""

    field_name: str
    field_type: str
    CODE: ClassVar[str] = "SYNESIS_E056"

    def to_diagnostic(self) -> str:
        return (
            f"The field '{self.field_name}' defines a `RELATIONS` block, but its type is\n"
            f"  `{self.field_type}`, not `CHAIN`. `RELATIONS` blocks describe the possible\n"
            f"  kinds of link between concepts — they only make sense in fields\n"
            f"  of type CHAIN. Remove the `RELATIONS` block or change the type to `CHAIN`."
        )

    def to_cli_line(self) -> str:
        return f"RELATIONS declared in `{self.field_name}` (type {self.field_type}) — RELATIONS is exclusive to CHAIN"


@dataclass(frozen=True)
class ValuesOnNonEnumerable(ValidationError):
    """VALUES definido em campo que nao e ORDERED nem ENUMERATED. (erro 86)

    Simetrico a FormatOnNonScale (E054), ArityOnNonChain (E055) e
    RelationsOnNonChain (E056): fecha a lacuna em que um bloco `VALUES` era
    aceito em qualquer tipo, populado em `spec.values` e silenciosamente
    ignorado — o pesquisador escrevia uma lista de valores que nao restringia
    nada.
    """

    field_name: str
    field_type: str
    CODE: ClassVar[str] = "SYNESIS_E086"

    def to_diagnostic(self) -> str:
        return (
            f"The field '{self.field_name}' defines a `VALUES` block, but its type is\n"
            f"  `{self.field_type}`. `VALUES` blocks list the valid options of a\n"
            f"  closed vocabulary — they only take effect in `ORDERED` fields (options with\n"
            f"  an order, e.g. Low, Medium, High) or `ENUMERATED` fields (options without order).\n"
            f"  In `{self.field_type}` the list would be ignored during validation.\n"
            f"  Remove the `VALUES` block or change the type to `ORDERED`/`ENUMERATED`."
        )

    def to_cli_line(self) -> str:
        return (
            f"VALUES declared in `{self.field_name}` (type {self.field_type}) "
            f"— VALUES is exclusive to ORDERED/ENUMERATED"
        )


@dataclass(frozen=True)
class IndexOnEnumeratedValue(ValidationError):
    """Prefixo de indice `[N]` em VALUES de campo ENUMERATED. (erro 87)

    Simetrico a `ORDERED exige indice em VALUES`: em ORDERED o indice E o dado
    materializado e define a ordem, portanto e obrigatorio; em ENUMERATED nao ha
    ordem, o dado e o proprio rotulo e o indice nunca e usado.

    Fecha a lacuna em que `[1] Aim: ...` era aceito num ENUMERATED, populado em
    `spec.values[].index` e silenciosamente ignorado — o pesquisador declarava
    uma ordem que o sistema nao honra em lugar nenhum.
    """

    field_name: str
    CODE: ClassVar[str] = "SYNESIS_E087"

    def to_diagnostic(self) -> str:
        return (
            f"The field '{self.field_name}' is of type `ENUMERATED`, but its values use\n"
            f"  an index prefix (`[0]`, `[1]`, ...). The index exists to establish an\n"
            f"  ORDER among the values and only takes effect in `ORDERED` fields, where it is\n"
            f"  the data written in the annotations. In `ENUMERATED` there is no order: the data is\n"
            f"  the label itself, and the index would be ignored.\n"
            f"  Remove the `[N]` prefixes or change the field type to `ORDERED`."
        )

    def to_cli_line(self) -> str:
        return (
            f"`[N]` prefix in the VALUES of `{self.field_name}` (ENUMERATED type) "
            f"— the index is exclusive to ORDERED"
        )


@dataclass(frozen=True)
class OrderedValueAsLabel(ValidationError):
    """Campo ORDERED escrito com o rotulo em vez do indice. (erro 88)

    Em ORDERED o dado E o indice: ele define a ordem e nao admite variantes de
    grafia. O rotulo pertence a DECLARACAO do template e e reconstituido na
    apresentacao (inlay hint do LSP) — o pesquisador le `11 ← Economico` e
    escreve `11`.

    Rejeitar, em vez de normalizar em silencio, e o que faz o arquivo convergir
    para a forma canonica: normalizacao silenciosa mantem o disco divergente do
    que o compilador entrega e deixa a grafia livre se acumular no corpus.

    Simetrico a IndexOnEnumeratedValue (E087): ali o indice sobra, aqui falta.
    """

    field_name: str
    label: str
    index: int
    CODE: ClassVar[str] = "SYNESIS_E088"

    def to_diagnostic(self) -> str:
        return (
            f"The field '{self.field_name}' was written with the label `{self.label}`,\n"
            f"  but in `ORDERED` fields the data written is the INDEX. The index defines the\n"
            f"  order of the values and admits no spelling variants; the label is\n"
            f"  declared in the template and shown by the editor next to the index.\n"
            f"  Write `{self.field_name}: {self.index}`."
        )

    def to_cli_line(self) -> str:
        return (
            f"`{self.field_name}: {self.label}` — in ORDERED write the index "
            f"({self.index}); the label is display only"
        )


@dataclass(frozen=True)
class DuplicateKeyAcrossFiles(ValidationError):
    """Mesma chave em dois arquivos da bibliografia ou do dataset. (erro 89)

    Com varios `.bib` (ou `.toml`) declarados — por pasta, curinga ou varias
    linhas INCLUDE —, uma chave repetida faria um registro sombrear o outro em
    silencio. A primeira ocorrencia, na ordem deterministica dos arquivos, e a
    que vale; a repeticao vira erro, porque decidir qual e o registro certo cabe
    ao pesquisador.
    """

    kind: str  # "BIBLIOGRAPHY" ou "DATASET"
    key: str
    first_file: str
    first_line: int
    duplicate_file: str
    CODE: ClassVar[str] = "SYNESIS_E089"

    def _what(self) -> str:
        return "reference" if self.kind == "BIBLIOGRAPHY" else "dataset record"

    def _first(self) -> str:
        return f"{self.first_file}:{self.first_line}" if self.first_line else self.first_file

    def to_diagnostic(self) -> str:
        return (
            f"The key `{self.key}` appears in two project files: `{self._first()}`\n"
            f"  and `{self.duplicate_file}`. Each {self._what()} needs a unique key\n"
            f"  across the whole project; the compiler used the first occurrence and ignored this one.\n"
            f"  If it is the same item, delete one of the two entries. If they are different\n"
            f"  items, give one of them another key and update the annotations that cite it."
        )

    def to_cli_line(self) -> str:
        return f"Duplicate key `{self.key}`: already defined in `{self._first()}`"


@dataclass(frozen=True)
class DuplicateScopeBlock(ValidationError):
    """Dois ou mais blocos SCOPE FIELDS no mesmo template. (erro 57)"""

    scope: str
    CODE: ClassVar[str] = "SYNESIS_E057"

    def to_diagnostic(self) -> str:
        return (
            f"The template has more than one `{self.scope} FIELDS` block. Only one block\n"
            f"  of this kind is allowed per template — two would make it ambiguous\n"
            f"  which fields are valid in the blocks.\n"
            f"  Merge all declarations into a single `{self.scope} FIELDS` block."
        )

    def to_cli_line(self) -> str:
        return f"`{self.scope} FIELDS` block declared more than once in the template"


@dataclass(frozen=True)
class ValueWithWhitespace(ValidationError):
    """Valor em bloco VALUES com espaco no inicio ou fim. (erro 58)"""

    field_name: str
    value: str
    CODE: ClassVar[str] = "SYNESIS_E058"

    def to_diagnostic(self) -> str:
        return (
            f"The value `\"{self.value}\"` declared in the field '{self.field_name}' has\n"
            f"  whitespace at the start or end. These invisible spaces would\n"
            f"  keep the value from being recognized when used in the annotations.\n"
            f"  Remove the extra spaces around the value in the template declaration."
        )

    def to_cli_line(self) -> str:
        return f"Value `\"{self.value}\"` in `{self.field_name}` has whitespace at the start or end"


@dataclass(frozen=True)
class DuplicateValue(ValidationError):
    """Valores duplicados dentro de um mesmo bloco VALUES. (erro 59)"""

    field_name: str
    value: str
    CODE: ClassVar[str] = "SYNESIS_E059"

    def to_diagnostic(self) -> str:
        return (
            f"The field '{self.field_name}' has the value `{self.value}` declared more than\n"
            f"  once in the `VALUES` block. Duplicate values are ambiguous and may\n"
            f"  produce inconsistent results in exports.\n"
            f"  Remove the duplicate entry."
        )

    def to_cli_line(self) -> str:
        return f"Duplicate value `{self.value}` in the VALUES block of `{self.field_name}`"


# ---------------------------------------------------------------------------
# Erros de Validação Semântica de Anotações (Fase 2 — erros 5, 8, 9, 23, 26, 31-33)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OntologyWithoutTemplateFields(ValidationError):
    """ONTOLOGY presente mas template nao declara ONTOLOGY FIELDS. (erro 5)"""

    CODE: ClassVar[str] = "SYNESIS_E005"

    def to_diagnostic(self) -> str:
        return (
            f"The project has ONTOLOGY blocks, but the template does not declare any\n"
            f"  field in `ONTOLOGY FIELDS`. Without this, the fields of the\n"
            f"  concepts cannot be validated.\n"
            f"  This problem is in the template definition. If you are not the author\n"
            f"  of the template, tell the project coordinator.\n"
            f"  To fix it, add to the template:\n"
            f"      ONTOLOGY FIELDS\n"
            f"          REQUIRED field_name\n"
            f"      END ONTOLOGY FIELDS"
        )

    def to_cli_line(self) -> str:
        return "Project has ONTOLOGY blocks but the template does not declare ONTOLOGY FIELDS"


@dataclass(frozen=True)
class QualifiedChainWithoutRelations(ValidationError):
    """Chain qualificada usada mas template nao define RELATIONS. (erro 8)"""

    field_name: str
    CODE: ClassVar[str] = "SYNESIS_E008"

    def to_diagnostic(self) -> str:
        return (
            f"This chain uses named relations (e.g. `Concept -> RELATION -> Concept`),\n"
            f"  but the template does not define a `RELATIONS` block for the field\n"
            f"  `{self.field_name}`.\n"
            f"  If the template uses simple chains, rewrite the chain without relations:\n"
            f"  `Concept -> Concept`. If you want named relations, ask the\n"
            f"  project coordinator to add a `RELATIONS` block to the template."
        )

    def to_cli_line(self) -> str:
        return f"Chain with named relations in `{self.field_name}`, but the template defines no RELATIONS"


@dataclass(frozen=True)
class SimpleChainWithRelationsRequired(ValidationError):
    """Chain simples usada mas template exige RELATIONS. (erro 9)"""

    field_name: str
    valid_relations: list[str]
    CODE: ClassVar[str] = "SYNESIS_E009"

    def to_diagnostic(self) -> str:
        rels = ", ".join(f"`{r}`" for r in self.valid_relations)
        return (
            f"The template requires chains to use named relations, but this chain\n"
            f"  was written without relations for the field `{self.field_name}`.\n"
            f"  Available relations: {rels}.\n"
            f"  Rewrite the chain as: `Concept -> RELATION -> Concept`."
        )

    def to_cli_line(self) -> str:
        return f"Simple chain in `{self.field_name}` but the template requires named relations"


@dataclass(frozen=True)
class EmptyItemBlock(ValidationError):
    """Bloco ITEM sem nenhum campo. (erro 23)"""

    CODE: ClassVar[str] = "SYNESIS_E023"

    def to_diagnostic(self) -> str:
        return (
            f"This ITEM block is empty — it has no field with content.\n"
            f"  An ITEM without fields represents no unit of analysis.\n"
            f"  Add the fields required by the template or remove the block if it\n"
            f"  was created by mistake."
        )

    def to_cli_line(self) -> str:
        return "Empty ITEM block — no fields"


@dataclass(frozen=True)
class DecimalInIntegerScale(ValidationError):
    """Valor decimal em campo SCALE com intervalo inteiro. (erro 26)"""

    field_name: str
    value: str
    min_val: float
    max_val: float
    CODE: ClassVar[str] = "SYNESIS_E026"

    def to_diagnostic(self) -> str:
        return (
            f"The value `{self.value}` has decimals, but the field `{self.field_name}`\n"
            f"  was declared with an integer range (`FORMAT [{int(self.min_val)}..{int(self.max_val)}]`).\n"
            f"  This field only accepts integers.\n"
            f"  Use an integer within the range, or ask the project coordinator\n"
            f"  to adjust FORMAT to accept decimals (e.g. `FORMAT [{self.min_val}..{self.max_val}]`)."
        )

    def to_cli_line(self) -> str:
        return f"Decimal value `{self.value}` in `{self.field_name}` — the field only accepts integers [{int(self.min_val)}..{int(self.max_val)}]"


@dataclass(frozen=True)
class DuplicateCodeInField(ValidationError):
    """Mesmo codigo repetido na mesma ocorrencia de campo CODE. (erro 31)"""

    field_name: str
    code: str
    CODE: ClassVar[str] = "SYNESIS_W031"
    DEFAULT_SEVERITY: ClassVar[ErrorSeverity] = ErrorSeverity.WARNING

    def to_diagnostic(self) -> str:
        return (
            f"The code `{self.code}` appears more than once in the field `{self.field_name}`\n"
            f"  in this block. Repeated codes add no information and may\n"
            f"  distort the counts in exports.\n"
            f"  Remove the duplicate occurrence and keep the code only once."
        )

    def to_cli_line(self) -> str:
        return f"Code `{self.code}` duplicated in the field `{self.field_name}`"


@dataclass(frozen=True)
class TopicWithSpaces(ValidationError):
    """Campo TOPIC recebendo valor com espacos. (erro 32)"""

    field_name: str
    value: str
    CODE: ClassVar[str] = "SYNESIS_E032"

    def to_diagnostic(self) -> str:
        suggestion = self.value.replace(" ", "_")
        return (
            f"The value `{self.value}` of the field `{self.field_name}` contains spaces, which\n"
            f"  is not allowed in TOPIC fields. Spaces are read as\n"
            f"  separators and would make the grouping ambiguous.\n"
            f"  Use underscores instead of spaces. For example: `{suggestion}`."
        )

    def to_cli_line(self) -> str:
        suggestion = self.value.replace(" ", "_")
        return f"Value `{self.value}` in `{self.field_name}` contains spaces. Suggested fix -> `{suggestion}`"


@dataclass(frozen=True)
class InvalidIdentifierCharacter(ValidationError):
    """Nome de codigo ou conceito com caracteres invalidos. (erro 33)"""

    name: str
    invalid_char: str
    CODE: ClassVar[str] = "SYNESIS_E033"

    def to_diagnostic(self) -> str:
        suggestion = self.name.replace(self.invalid_char, "_")
        return (
            f"The name `{self.name}` contains the invalid character `{self.invalid_char}`,\n"
            f"  which is not allowed in Synesis identifiers. Identifiers accept\n"
            f"  only letters, digits, underscore and hyphen, and must start with a letter.\n"
            f"  For example: use `{suggestion}` instead of `{self.name}`."
        )

    def to_cli_line(self) -> str:
        return f"Identifier `{self.name}` contains the invalid character `{self.invalid_char}`"


# ---------------------------------------------------------------------------
# Erros de Validação Cross-Entity (Fase 3 — erros 13, 14, 15, 68, 70, 71)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ChainWithoutArrowOperator(ValidationError):
    """Chain sem operador -> entre elementos. (erro 13)"""

    raw_value: str
    CODE: ClassVar[str] = "SYNESIS_E013"

    def to_diagnostic(self) -> str:
        return (
            f"The elements of this chain are not separated by the `->` operator.\n"
            f"  Without the arrow, the compiler cannot tell where one element\n"
            f"  ends and the next one begins.\n"
            f"  Value found: `{self.raw_value}`\n"
            f"  Rewrite it connecting the elements with `->`, for example:\n"
            f"  `ConceptA -> ConceptB` or `ConceptA -> RELATION -> ConceptB`"
        )

    def to_cli_line(self) -> str:
        return f"Chain without the `->` operator: `{self.raw_value}`"


@dataclass(frozen=True)
class ConceptNameMatchesRelation(ValidationError):
    """Conceito em posicao de codigo com nome identico a uma relacao. (erro 14)"""

    name: str
    field_name: str
    CODE: ClassVar[str] = "SYNESIS_E014"

    def to_diagnostic(self) -> str:
        return (
            f"The element `{self.name}` appears in this chain in a concept position,\n"
            f"  but it is also declared as a relation in the template for the field\n"
            f"  `{self.field_name}`. This ambiguity keeps the compiler from\n"
            f"  determining the element's role in the chain.\n"
            f"  Rename the concept in the organizing model so it differs from the\n"
            f"  relation names, or rename the relation in the template."
        )

    def to_cli_line(self) -> str:
        return f"`{self.name}` is ambiguous: both concept and relation in `{self.field_name}`"


@dataclass(frozen=True)
class ConceptWithSpaces(ValidationError):
    """Conceito em chain contendo espacos. (erro 15)"""

    concept: str
    CODE: ClassVar[str] = "SYNESIS_E015"

    def to_diagnostic(self) -> str:
        suggestion = self.concept.replace(" ", "_")
        return (
            f"The element `{self.concept}` contains spaces, which are not allowed\n"
            f"  in concept names. The compiler reads each space as a\n"
            f"  separator between distinct elements of the chain.\n"
            f"  Replace the spaces with underscores: `{suggestion}`."
        )

    def to_cli_line(self) -> str:
        suggestion = self.concept.replace(" ", "_")
        return f"Concept `{self.concept}` contains spaces. Suggested fix -> `{suggestion}`"


@dataclass(frozen=True)
class DuplicateOntologyConcept(ValidationError):
    """Dois blocos ONTOLOGY com o mesmo nome de conceito. (erro 68)"""

    concept_name: str
    file_a: str
    file_b: str
    CODE: ClassVar[str] = "SYNESIS_E068"

    def to_diagnostic(self) -> str:
        return (
            f"The concept `{self.concept_name}` is defined more than once in the\n"
            f"  project's organizing model:\n"
            f"  - {self.file_a}\n"
            f"  - {self.file_b}\n"
            f"  Each concept must have a unique name across the project. Check\n"
            f"  whether the two blocks represent the same concept — if so, merge them.\n"
            f"  If not, rename one of them so the names differ."
        )

    def to_cli_line(self) -> str:
        return f"Concept `{self.concept_name}` duplicated in {self.file_a} and {self.file_b}"


@dataclass(frozen=True)
class DuplicateSourceBibref(ValidationError):
    """Mesmo @bibref declarado em dois blocos SOURCE no mesmo arquivo. (erro 70)"""

    bibref: str
    filename: str
    CODE: ClassVar[str] = "SYNESIS_E070"

    def to_diagnostic(self) -> str:
        return (
            f"The reference `@{self.bibref}` appears in two different SOURCE blocks\n"
            f"  in the file `{self.filename}`. Each bibliographic reference can have\n"
            f"  only one SOURCE block per file.\n"
            f"  Merge the two SOURCE blocks into one, or split the annotations\n"
            f"  into separate `.syn` files."
        )

    def to_cli_line(self) -> str:
        return f"SOURCE `@{self.bibref}` duplicated in this file"


@dataclass(frozen=True)
class DuplicateOntologyDescription(ValidationError):
    """Dois blocos ONTOLOGY com description identica. (erro 71)"""

    concept_a: str
    concept_b: str
    CODE: ClassVar[str] = "SYNESIS_W071"
    DEFAULT_SEVERITY: ClassVar[ErrorSeverity] = ErrorSeverity.WARNING

    def to_diagnostic(self) -> str:
        return (
            f"The concepts `{self.concept_a}` and `{self.concept_b}` have exactly\n"
            f"  the same description. This usually indicates a copy error — two\n"
            f"  distinct concepts should not have identical definitions.\n"
            f"  Review the definitions and make the descriptions differ, or check whether\n"
            f"  the two concepts should be a single one."
        )

    def to_cli_line(self) -> str:
        return f"Concepts `{self.concept_a}` and `{self.concept_b}` have identical descriptions"


# ---------------------------------------------------------------------------
# Erros de Estrutura de Projeto (Fase 4 — erros 61, 62, 63, 65, 66, 67)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MissingAnnotationsInclude(ValidationError):
    """Arquivo .syn no diretorio do projeto nao referenciado em INCLUDE ANNOTATIONS. (erro 61)"""

    filename: str
    CODE: ClassVar[str] = "SYNESIS_E061"

    def to_diagnostic(self) -> str:
        return (
            f"The file `{self.filename}` (`.syn` extension) exists in the project folder\n"
            f"  but is not referenced by any INCLUDE ANNOTATIONS in the `.synp`.\n"
            f"  Without that declaration, the compiler ignores the file and the annotations\n"
            f"  in it are neither loaded nor validated.\n"
            f"  Add to the project file:\n"
            f"    INCLUDE ANNOTATIONS \"{self.filename}\""
        )

    def to_cli_line(self) -> str:
        return f"File `{self.filename}` not included by INCLUDE ANNOTATIONS in the .synp"


@dataclass(frozen=True)
class MissingOntologyInclude(ValidationError):
    """Arquivo .syno no diretorio do projeto nao referenciado em INCLUDE ONTOLOGY. (erro 62)"""

    filename: str
    CODE: ClassVar[str] = "SYNESIS_E062"

    def to_diagnostic(self) -> str:
        return (
            f"The file `{self.filename}` (`.syno` extension) exists in the project folder\n"
            f"  but is not referenced by any INCLUDE ONTOLOGY in the `.synp`.\n"
            f"  Without that declaration, the organizing model is not loaded and the codes\n"
            f"  defined in it cannot be validated.\n"
            f"  Add to the project file:\n"
            f"    INCLUDE ONTOLOGY \"{self.filename}\""
        )

    def to_cli_line(self) -> str:
        return f"File `{self.filename}` not included by INCLUDE ONTOLOGY in the .synp"


@dataclass(frozen=True)
class MissingBibliographyFile(ValidationError):
    """Arquivo .bib declarado no projeto nao encontrado no caminho indicado. (erro 63)

    Tambem cobre curinga ou pasta que nao casou nenhum `.bib` (`no_matches`).
    """

    filename: str
    no_matches: bool = False
    CODE: ClassVar[str] = "SYNESIS_E063"

    def to_diagnostic(self) -> str:
        if self.no_matches:
            return (
                f"The pattern `{self.filename}` declared in `INCLUDE BIBLIOGRAPHY` did not\n"
                f"  match any `.bib` file. Without a bibliography, no `@bibref`\n"
                f"  reference can be validated.\n"
                f"  Check that the files were copied to the folder and that the pattern\n"
                f"  is correct. A folder is searched entirely (subfolders included)\n"
                f"  for `.bib` files; a wildcard such as `sources/*.bib` matches only what it\n"
                f"  describes. The path is relative to the folder of the project file (`.synp`)."
            )
        return (
            f"The bibliographic references file `{self.filename}` declared in the\n"
            f"  project was not found. Without it, no `@bibref` reference can\n"
            f"  be validated.\n"
            f"  Check that the file exists and that the path is correct. The path\n"
            f"  must be relative to the folder of the project file (`.synp`)."
        )

    def to_cli_line(self) -> str:
        if self.no_matches:
            return f"`{self.filename}` did not match any .bib file"
        return f"References file `{self.filename}` declared in the project was not found"


@dataclass(frozen=True)
class MissingAnnotationsFile(ValidationError):
    """Arquivo .syn declarado em INCLUDE ANNOTATIONS nao encontrado. (erro 73)"""

    filename: str
    CODE: ClassVar[str] = "SYNESIS_E073"

    def to_diagnostic(self) -> str:
        return (
            f"The annotations file `{self.filename}` is declared in INCLUDE ANNOTATIONS\n"
            f"  but was not found. The annotations it should contain are neither\n"
            f"  loaded nor validated.\n"
            f"  Check that the name is correct and that the file exists. The path must be\n"
            f"  relative to the folder of the project file (`.synp`)."
        )

    def to_cli_line(self) -> str:
        return f"Annotations file `{self.filename}` declared in the project was not found"


@dataclass(frozen=True)
class MissingOntologyFile(ValidationError):
    """Arquivo .syno declarado em INCLUDE ONTOLOGY nao encontrado. (erro 74)"""

    filename: str
    CODE: ClassVar[str] = "SYNESIS_E074"

    def to_diagnostic(self) -> str:
        return (
            f"The organizing model file `{self.filename}` is declared in INCLUDE ONTOLOGY\n"
            f"  but was not found. Without it, the codes used in the annotations cannot\n"
            f"  be validated against the organizing model.\n"
            f"  Check that the name is correct and that the file exists. The path must be\n"
            f"  relative to the folder of the project file (`.synp`)."
        )

    def to_cli_line(self) -> str:
        return f"Organizing model file `{self.filename}` declared in the project was not found"


@dataclass(frozen=True)
class IncludePathEscapesProject(ValidationError):
    """Caminho declarado no .synp aponta para fora do diretorio do projeto. (erro 75)"""

    filename: str
    CODE: ClassVar[str] = "SYNESIS_E075"

    def to_diagnostic(self) -> str:
        return (
            f"The path `{self.filename}` declared in the project points outside the\n"
            f"  project folder. For safety, the compiler only loads files inside the\n"
            f"  folder of the `.synp` (or its subfolders).\n"
            f"  Move the file into the project folder and fix the path."
        )

    def to_cli_line(self) -> str:
        return f"Path `{self.filename}` points outside the project folder"


@dataclass(frozen=True)
class UnreadableIncludedFile(ValidationError):
    """Arquivo declarado no .synp existe mas nao pode ser lido/parseado. (erro 76)"""

    filename: str
    reason: str
    CODE: ClassVar[str] = "SYNESIS_E076"

    def to_diagnostic(self) -> str:
        return (
            f"The file `{self.filename}` was found but could not be read by the\n"
            f"  compiler:\n"
            f"    {self.reason}\n"
            f"  Check that the file is saved as UTF-8 and is not\n"
            f"  corrupted or locked by another program."
        )

    def to_cli_line(self) -> str:
        return f"File `{self.filename}` could not be read: {self.reason}"


@dataclass(frozen=True)
class MalformedBibliographyEntry(ValidationError):
    """Entrada em arquivo .bib nao esta em formato BibTeX valido. (erro 72)"""

    filename: str
    entry_key: str
    CODE: ClassVar[str] = "SYNESIS_E072"

    def to_diagnostic(self) -> str:
        return (
            f"The entry `@{self.entry_key}` in the references file `{self.filename}`\n"
            f"  is not valid BibTeX and was ignored by the compiler. Because of\n"
            f"  that, any `@bibref` pointing to it will be reported as not\n"
            f"  found.\n"
            f"  A valid BibTeX entry has three parts: a type, the citation key\n"
            f"  in braces, and comma-separated fields using `=`:\n"
            f"    @book{{{self.entry_key},\n"
            f"        title = {{Title of the work}},\n"
            f"        year = {{2024}}\n"
            f"    }}\n"
            f"  Check that the entry starts with a type (@book, @article, @misc...),\n"
            f"  that the key is in braces `{{ }}`, and that each field uses `=` (not `:`)."
        )

    def to_cli_line(self) -> str:
        return (
            f"Entry `@{self.entry_key}` in `{self.filename}` is not "
            f"valid BibTeX"
        )


@dataclass(frozen=True)
class MissingTemplateDeclaration(ValidationError):
    """Bloco PROJECT sem declaracao TEMPLATE. (erro 65)"""

    CODE: ClassVar[str] = "SYNESIS_E065"

    def to_diagnostic(self) -> str:
        return (
            f"The project file declares no template. The template is required\n"
            f"  — it defines the validation rules for every annotation in the project.\n"
            f"  Without it, the compiler cannot check whether the annotations are correct.\n"
            f"  Add to the PROJECT block:\n"
            f"    TEMPLATE \"file_name.synt\""
        )

    def to_cli_line(self) -> str:
        return "PROJECT block without a TEMPLATE declaration"


@dataclass(frozen=True)
class DuplicateProjectBlock(ValidationError):
    """Dois blocos PROJECT no mesmo arquivo .synp. (erro 66)"""

    CODE: ClassVar[str] = "SYNESIS_E066"

    def to_diagnostic(self) -> str:
        return (
            f"This project file has two PROJECT blocks. Only one PROJECT\n"
            f"  block is allowed per file — the compiler would not know which of\n"
            f"  the two to use as the entry point.\n"
            f"  Remove the duplicate block or split the projects into separate `.synp` files."
        )

    def to_cli_line(self) -> str:
        return "Two PROJECT blocks in the same .synp — remove the duplicate"


@dataclass(frozen=True)
class ModifiedBeforeCreated(ValidationError):
    """Data MODIFIED anterior a data CREATED no bloco METADATA. (erro 67)"""

    modified: str
    created: str
    CODE: ClassVar[str] = "SYNESIS_W067"
    DEFAULT_SEVERITY: ClassVar[ErrorSeverity] = ErrorSeverity.WARNING

    def to_diagnostic(self) -> str:
        return (
            f"The modification date `{self.modified}` is earlier than the creation date\n"
            f"  `{self.created}` declared in the project's METADATA block. A project cannot\n"
            f"  have been modified before it existed.\n"
            f"  Check the dates and fix the wrong one. The expected format\n"
            f"  is `YYYY-MM-DD`."
        )

    def to_cli_line(self) -> str:
        return f"MODIFIED `{self.modified}` e anterior a CREATED `{self.created}` no METADATA"


@dataclass(frozen=True)
class DuplicateIdentityValue(ValidationError):
    """Dois SOURCEs com o mesmo valor num campo IDENTIFIES. (erro 77)

    O campo IDENTIFIES declara uma chave primaria de entidade: cada valor deve
    identificar UM unico SOURCE. Dois SOURCEs com o mesmo valor violam a unicidade.
    """

    field_name: str
    entity: str
    value: str
    first_bibref: str
    duplicate_bibref: str
    CODE: ClassVar[str] = "SYNESIS_E077"

    def to_diagnostic(self) -> str:
        return (
            f"The field `{self.field_name}` identifies the entity `{self.entity}` (IDENTIFIES),\n"
            f"  so each value must match a single SOURCE — like a primary\n"
            f"  key. But the value `{self.value}` appears in two SOURCEs:\n"
            f"    `{self.first_bibref}` and `{self.duplicate_bibref}`.\n"
            f"  If they are the same entity, merge the two SOURCEs. If they are distinct\n"
            f"  entities, fix the value of `{self.field_name}` in one of them."
        )

    def to_cli_line(self) -> str:
        return (
            f"Value `{self.value}` of `{self.field_name}` (IDENTIFIES {self.entity}) "
            f"duplicated in `{self.first_bibref}` and `{self.duplicate_bibref}`"
        )


@dataclass(frozen=True)
class LinkageModifierOutsideSource(ValidationError):
    """IDENTIFIES/REFERS TO em campo que nao e SCOPE SOURCE. (erro 78)

    A ligacao multiprojeto opera sobre SOURCEs (unidades de coleta). Aplicar o
    modificador a um campo ITEM ou ONTOLOGY nao tem semantica definida.
    """

    field_name: str
    modifier: str  # "IDENTIFIES" | "REFERS TO"
    scope: str
    CODE: ClassVar[str] = "SYNESIS_E078"

    def to_diagnostic(self) -> str:
        return (
            f"The field `{self.field_name}` uses `{self.modifier}`, but it is declared with\n"
            f"  `SCOPE {self.scope}`. The linkage modifiers (`IDENTIFIES` / `REFERS TO`)\n"
            f"  only make sense in `SCOPE SOURCE` fields — linkage between projects\n"
            f"  works on SOURCEs (collection units), not on ITEMs or concepts.\n"
            f"  Move the modifier to a SOURCE field, or remove it from this field."
        )

    def to_cli_line(self) -> str:
        return (
            f"`{self.modifier}` in `{self.field_name}` (SCOPE {self.scope}) — "
            f"only valid in SCOPE SOURCE"
        )


@dataclass(frozen=True)
class MissingBibliographyValue(ValidationError):
    """Campo REQUIRED ... ON BIBLIOGRAPHY sem valor no .bib do SOURCE. (erro 79)"""

    field_name: str
    bibref: str
    CODE: ClassVar[str] = "SYNESIS_E079"

    def to_diagnostic(self) -> str:
        return (
            f"The field `{self.field_name}` was declared `REQUIRED ... ON BIBLIOGRAPHY`,\n"
            f"  so its value must come from the SOURCE's `.bib` entry — not from the text.\n"
            f"  But the entry `{self.bibref}` has no `{self.field_name}` field.\n"
            f"  Add `{self.field_name} = {{...}}` to the entry `{self.bibref}` in the\n"
            f"  `.bib` file, or remove the `ON BIBLIOGRAPHY` requirement from the template."
        )

    def to_cli_line(self) -> str:
        return (
            f"Field `{self.field_name}` (ON BIBLIOGRAPHY) missing in the .bib entry of `{self.bibref}`"
        )


@dataclass(frozen=True)
class MissingDatasetValue(ValidationError):
    """Campo REQUIRED ... ON DATASET sem valor no registro do dataset TOML. (erro 85)"""

    field_name: str
    bibref: str
    dataset_path: str
    CODE: ClassVar[str] = "SYNESIS_E085"

    def to_diagnostic(self) -> str:
        return (
            f"The field `{self.field_name}` was declared `REQUIRED ... ON DATASET`,\n"
            f"  so its value must come from the SOURCE's TOML record — not from the text.\n"
            f"  But the record `{self.bibref}` has no value at the path\n"
            f"  `{self.dataset_path}`.\n"
            f"  Check the TOML section/field, or remove the `ON DATASET` requirement\n"
            f"  from the template."
        )

    def to_cli_line(self) -> str:
        return (
            f"Field `{self.field_name}` (ON DATASET \"{self.dataset_path}\") "
            f"missing in the record `{self.bibref}`"
        )


@dataclass(frozen=True)
class ExternalReferenceDeclared(ValidationError):
    """INFO: projeto declara REFERS TO — referencia externa nao resolvida isolada. (info 80)

    Nao e erro nem warning: um REFERS TO so se resolve num link step (varios .synp).
    Isolado, a referencia externa e esperada — o INFO documenta que ha ligacoes a
    materializar, sem poluir o painel com warning recorrente.
    """

    entity: str
    field_name: str
    CODE: ClassVar[str] = "SYNESIS_I080"
    DEFAULT_SEVERITY: ClassVar[ErrorSeverity] = ErrorSeverity.INFO

    def to_diagnostic(self) -> str:
        return (
            f"This project references the external entity `{self.entity}` "
            f"(`REFERS TO` in `{self.field_name}`).\n"
            f"  The links are not materialized in this artifact. To resolve them,\n"
            f"  compile this project together with the project that declares `IDENTIFIES {self.entity}`."
        )

    def to_cli_line(self) -> str:
        return (
            f"External reference `{self.entity}` (REFERS TO in {self.field_name}) "
            f"— not materialized in isolation"
        )


@dataclass(frozen=True)
class DuplicateEntityOwner(ValidationError):
    """Dois membros declaram IDENTIFIES do mesmo rotulo no link step. (erro 81)

    Um rotulo de entidade tem um corpus proprietario. Identidade entre esquemas
    de ID distintos (Lattes vs ORCID) resolve-se com o hub referenciando a
    periferia (REFERS TO), nunca com dois IDENTIFIES do mesmo rotulo.
    """

    entity: str
    first_member: str
    duplicate_member: str
    CODE: ClassVar[str] = "SYNESIS_E081"

    def to_diagnostic(self) -> str:
        return (
            f"The entity `{self.entity}` is declared with `IDENTIFIES` by two projects:\n"
            f"  `{self.first_member}` and `{self.duplicate_member}`.\n"
            f"  An entity label has a single owning corpus (the primary key).\n"
            f"  If they are distinct ID schemes of the same person (Lattes vs ORCID), the hub\n"
            f"  should `REFERS TO` the periphery — not declare two `IDENTIFIES` of the same label."
        )

    def to_cli_line(self) -> str:
        return (
            f"Entity `{self.entity}` with a duplicate owner: "
            f"`{self.first_member}` and `{self.duplicate_member}`"
        )


@dataclass(frozen=True)
class TypeMismatchInLinkage(ValidationError):
    """TYPE divergente entre campos da mesma entidade no link step. (erro 82)

    Todos os campos que participam da mesma entidade (o IDENTIFIES e todos os
    REFERS TO) devem ter TYPE identico. Divergencia e sintoma de erro de
    modelagem: os dois lados nao modelam a mesma entidade.
    """

    entity: str
    member_a: str
    type_a: str
    member_b: str
    type_b: str
    CODE: ClassVar[str] = "SYNESIS_E082"

    def to_diagnostic(self) -> str:
        return (
            f"The fields taking part in the entity `{self.entity}` have diverging `TYPE`:\n"
            f"  `{self.member_a}` declares `TYPE {self.type_a}`; "
            f"`{self.member_b}` declares `TYPE {self.type_b}`.\n"
            f"  Fields of the same entity (the `IDENTIFIES` and every `REFERS TO`) must have\n"
            f"  the same `TYPE` — the divergence means the two sides do not model the\n"
            f"  same thing. Align the types in the template."
        )

    def to_cli_line(self) -> str:
        return (
            f"Tipos divergentes na entidade `{self.entity}`: "
            f"`{self.member_a}` TYPE {self.type_a} vs `{self.member_b}` TYPE {self.type_b}"
        )


@dataclass(frozen=True)
class OrphanReference(ValidationError):
    """REFERS TO cujo valor nao casa com nenhum IDENTIFIES no link step. (warning 83)

    Nao e erro: um autor externo sem curriculo no corpus e um orfao legitimo.
    Se `near_match` estiver preenchido, o valor casaria sob normalizacao de caixa
    (quase-casamento) — o link step detecta e sugere, mas NUNCA funde.
    """

    entity: str
    value: str
    member: str
    near_match: Optional[str] = None
    DEFAULT_SEVERITY: ClassVar[ErrorSeverity] = ErrorSeverity.WARNING
    CODE: ClassVar[str] = "SYNESIS_W083"

    def to_diagnostic(self) -> str:
        base = (
            f"The value `{self.value}` (`REFERS TO {self.entity}` in `{self.member}`) has no\n"
            f"  matching `IDENTIFIES {self.entity}` — it is an orphan reference."
        )
        if self.near_match is not None:
            return (
                f"{base}\n"
                f"  Near match: `{self.near_match}` differs only in case/invisible characters.\n"
                f"  If they are the same entity, canonicalize the value at the origin (.bib/SOURCE) — the\n"
                f"  compiler does not normalize automatically (that would merge distinct entities)."
            )
        return (
            f"{base}\n"
            f"  This may be expected (e.g. an external author with no record in the corpus). No node is created."
        )

    def to_cli_line(self) -> str:
        if self.near_match is not None:
            return (
                f"Orphan REFERS TO `{self.value}` ({self.entity}) — "
                f"near match `{self.near_match}` (differs only in case)"
            )
        return f"Orphan REFERS TO `{self.value}` ({self.entity}) in {self.member}"


@dataclass(frozen=True)
class SharedOnlyForOntology(ValidationError):
    """INCLUDE SHARED usado com tipo diferente de ONTOLOGY. (erro 84)

    O escape de path autorizado existe para compartilhar VOCABULARIO CONCEITUAL
    entre projetos (a ontologia). Deixa-lo vazar para TEMPLATE/BIBLIOGRAPHY/
    ANNOTATIONS abriria a contencao para tipos que a motivacao nao pediu.
    """

    include_type: str
    path: str
    CODE: ClassVar[str] = "SYNESIS_E084"

    def to_diagnostic(self) -> str:
        return (
            f"`INCLUDE SHARED` is only valid for `ONTOLOGY`, but it was used with\n"
            f"  `{self.include_type}` (`{self.path}`).\n"
            f"  The word `SHARED` allows a target OUTSIDE the project folder — it exists\n"
            f"  to share the conceptual vocabulary (the organizing model) between projects\n"
            f"  of the same study. The other includes must stay inside the project.\n"
            f"  Remove `SHARED`, or move the file into the project folder."
        )

    def to_cli_line(self) -> str:
        return f"`INCLUDE SHARED` invalid for {self.include_type} — only ONTOLOGY accepts SHARED"


# ---------------------------------------------------------------------------
# ROLE: papeis no template e coerencia da hierarquia e dos rotulos (etapa A2c,
# Spec ROLE/EXPORT v7 §5-§6). Catalogo em synesis/semantic/roles.py.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UnknownRole(ValidationError):
    """Papel fora do catalogo."""

    field_name: str
    role: str
    removed: bool = False
    CODE: ClassVar[str] = "SYNESIS_E104"

    def to_diagnostic(self) -> str:
        if self.removed:
            return (
                f"The role `{self.role}` of the field `{self.field_name}` does not exist.\n"
                f"  Horizontal relations between concepts belong in the CHAIN; to take them to SKOS,\n"
                f"  use `MAP RELATIONS ... TO RELATED` in an EXPORT block."
            )
        return (
            f"The role `{self.role}` of the field `{self.field_name}` does not exist.\n"
            f"  Available roles: LABEL PREFERRED/ALTERNATIVE/HIDDEN, NOTE DEFINITION/USAGE/\n"
            f"  EXAMPLE/COUNTEREXAMPLE, HIERARCHY KIND/PART/INSTANCE and USE."
        )

    def to_cli_line(self) -> str:
        return f"Unknown role `{self.role}` in the field `{self.field_name}`"


@dataclass(frozen=True)
class RoleNotAvailable(ValidationError):
    """Papel previsto e ainda indisponivel (DIVISION)."""

    field_name: str
    role: str
    reason: str
    CODE: ClassVar[str] = "SYNESIS_E105"

    def to_diagnostic(self) -> str:
        return (
            f"The role `{self.role}` (field `{self.field_name}`) is planned, but not yet\n"
            f"  available: {self.reason}."
        )

    def to_cli_line(self) -> str:
        return f"Role `{self.role}` not yet available (field `{self.field_name}`)"


@dataclass(frozen=True)
class RoleRequiresSpecies(ValidationError):
    """LABEL, NOTE, HIERARCHY ou DIVISION sem especie."""

    field_name: str
    role: str
    CODE: ClassVar[str] = "SYNESIS_E106"

    def to_diagnostic(self) -> str:
        examples = {
            "LABEL": "PREFERRED, ALTERNATIVE or HIDDEN",
            "NOTE": "DEFINITION, USAGE, EXAMPLE or COUNTEREXAMPLE",
            "HIERARCHY": "KIND, PART or INSTANCE",
            "DIVISION": "EXCLUSIVE or COMPLETE",
        }.get(self.role, "")
        return (
            f"The role `{self.role}` of the field `{self.field_name}` needs a species:\n"
            f"  `ROLE {self.role} <species>`, with species {examples}."
        )

    def to_cli_line(self) -> str:
        return f"Role `{self.role}` without a species in the field `{self.field_name}`"


@dataclass(frozen=True)
class RoleTypeMismatch(ValidationError):
    """Papel com tipo de campo incompativel."""

    field_name: str
    role: str
    expected: str
    actual: str
    CODE: ClassVar[str] = "SYNESIS_E107"

    def to_diagnostic(self) -> str:
        return (
            f"The role `{self.role}` requires a `TYPE {self.expected}` field, but `{self.field_name}`\n"
            f"  is `TYPE {self.actual}`. HIERARCHY and USE cite concepts (CODE); LABEL and NOTE are text (TEXT)."
        )

    def to_cli_line(self) -> str:
        return f"`{self.field_name}`: `{self.role}` exige TYPE {self.expected} (e {self.actual})"


@dataclass(frozen=True)
class RoleOutsideOntology(ValidationError):
    """ROLE num campo fora de SCOPE ONTOLOGY."""

    field_name: str
    role: str
    scope: str
    CODE: ClassVar[str] = "SYNESIS_E108"

    def to_diagnostic(self) -> str:
        return (
            f"ROLE {self.role} in the field `{self.field_name}` (SCOPE {self.scope}): roles only apply\n"
            f"  to SCOPE ONTOLOGY fields.\n"
            f"  Hierarchy adopted by the project: move the field to SCOPE ONTOLOGY.\n"
            f"  Hierarchy stated by the source: use a relation in the CHAIN (e.g. TIPO_DE)."
        )

    def to_cli_line(self) -> str:
        return f"ROLE {self.role} in `{self.field_name}` (SCOPE {self.scope}): only valid in SCOPE ONTOLOGY"


@dataclass(frozen=True)
class DuplicateRole(ValidationError):
    """ROLE repetido no mesmo FIELD."""

    field_name: str
    role: str
    CODE: ClassVar[str] = "SYNESIS_E109"

    def to_diagnostic(self) -> str:
        return (
            f"The field `{self.field_name}` declares ROLE more than once (`{self.role}`).\n"
            f"  A field has a single role; keep one ROLE line."
        )

    def to_cli_line(self) -> str:
        return f"Repeated ROLE in the field `{self.field_name}`"


@dataclass(frozen=True)
class DuplicateUniqueRole(ValidationError):
    """Dois campos com NOTE DEFINITION, ou dois com LABEL PREFERRED."""

    field_name: str
    role: str
    first_field: str
    CODE: ClassVar[str] = "SYNESIS_E110"

    def to_diagnostic(self) -> str:
        return (
            f"The role `{self.role}` is already on the field `{self.first_field}`; `{self.field_name}`\n"
            f"  cannot have it too. The template has at most one field with this role."
        )

    def to_cli_line(self) -> str:
        return f"`{self.role}` in two fields: `{self.first_field}` and `{self.field_name}`"


@dataclass(frozen=True)
class RequiredHierarchy(ValidationError):
    """Campo HIERARCHY declarado REQUIRED."""

    field_name: str
    role: str
    CODE: ClassVar[str] = "SYNESIS_E111"

    def to_diagnostic(self) -> str:
        return (
            f"The field `{self.field_name}` ({self.role}) is REQUIRED. That would demand a parent\n"
            f"  for every concept, and no finite hierarchy without cycles satisfies the rule:\n"
            f"  some concept has to be at the top. Declare the field as OPTIONAL."
        )

    def to_cli_line(self) -> str:
        return f"`{self.field_name}` ({self.role}) cannot be REQUIRED: the top concepts would be invalid"


@dataclass(frozen=True)
class ReservedOntologyFieldName(ValidationError):
    """Campo do ONTOLOGY com nome de chave canonica do JSON."""

    field_name: str
    CODE: ClassVar[str] = "SYNESIS_E112"

    def to_diagnostic(self) -> str:
        return (
            f"The ONTOLOGY field `{self.field_name}` has the name of a key the compiler\n"
            f"  reserves for the concept in the JSON (concept, location, frequency, source_count,\n"
            f"  parent_chains; or description, when another field has ROLE NOTE DEFINITION).\n"
            f"  The field value would overwrite the key. Rename the field."
        )

    def to_cli_line(self) -> str:
        return f"ONTOLOGY field `{self.field_name}` uses a name reserved in the JSON"


@dataclass(frozen=True)
class MultiplePreferredLabels(ValidationError):
    """Mais de um termo em LABEL PREFERRED num conceito."""

    concept: str
    terms: list
    CODE: ClassVar[str] = "SYNESIS_E113"

    def to_diagnostic(self) -> str:
        return (
            f"The concept `{self.concept}` has {len(self.terms)} preferred labels "
            f"({', '.join(self.terms)}).\n"
            f"  LABEL PREFERRED takes a single term; the others go in LABEL ALTERNATIVE."
        )

    def to_cli_line(self) -> str:
        return f"`{self.concept}`: more than one preferred label"


@dataclass(frozen=True)
class LabelSpeciesOverlap(ValidationError):
    """O mesmo termo em duas especies de LABEL no mesmo conceito."""

    concept: str
    term: str
    first_role: str
    second_role: str
    CODE: ClassVar[str] = "SYNESIS_E114"

    def to_diagnostic(self) -> str:
        return (
            f"The term `{self.term}` appears in `{self.first_role}` and in `{self.second_role}` in\n"
            f"  the concept `{self.concept}`. A label has a single species (SKOS S13)."
        )

    def to_cli_line(self) -> str:
        return f"`{self.concept}`: `{self.term}` in two LABEL species"


@dataclass(frozen=True)
class AmbiguousLabel(ValidationError):
    """O mesmo termo de LABEL em dois conceitos."""

    term: str
    concept: str
    other: str
    CODE: ClassVar[str] = "SYNESIS_E115"

    def to_diagnostic(self) -> str:
        return (
            f"The label `{self.term}` is on `{self.concept}` and on `{self.other}`. A label\n"
            f"  refers to a single concept; remove it from one of the two."
        )

    def to_cli_line(self) -> str:
        return f"Label `{self.term}` on two concepts: `{self.other}` and `{self.concept}`"


@dataclass(frozen=True)
class LabelConflictsWithConcept(ValidationError):
    """Termo de LABEL igual ao nome de outro conceito."""

    concept: str
    term: str
    other: str
    CODE: ClassVar[str] = "SYNESIS_E116"

    def to_diagnostic(self) -> str:
        return (
            f"The label `{self.term}` of `{self.concept}` is the name of the concept `{self.other}`.\n"
            f"  A label cannot be another concept with a block. If both name the same\n"
            f"  thing, consolidate them with USE (synesis-coder consolidate)."
        )

    def to_cli_line(self) -> str:
        return f"`{self.concept}`: label `{self.term}` is the name of the concept `{self.other}`"


@dataclass(frozen=True)
class SelfReference(ValidationError):
    """Conceito que aponta para si mesmo num campo HIERARCHY."""

    concept: str
    field_name: str
    CODE: ClassVar[str] = "SYNESIS_E117"

    def to_diagnostic(self) -> str:
        return f"The concept `{self.concept}` points to itself in `{self.field_name}`."

    def to_cli_line(self) -> str:
        return f"`{self.concept}` points to itself in `{self.field_name}`"


@dataclass(frozen=True)
class CyclicHierarchy(ValidationError):
    """Ciclo na hierarquia (uniao das especies)."""

    path: list
    CODE: ClassVar[str] = "SYNESIS_E118"

    def to_diagnostic(self) -> str:
        return (
            f"The hierarchy has a cycle: {' -> '.join(self.path)}.\n"
            f"  A concept cannot be, directly or indirectly, broader than itself."
        )

    def to_cli_line(self) -> str:
        return f"Hierarchy cycle: {' -> '.join(self.path)}"


@dataclass(frozen=True)
class DuplicateHierarchySpecies(ValidationError):
    """O mesmo par filho-pai em duas especies de HIERARCHY."""

    child: str
    parent: str
    first_species: str
    second_species: str
    CODE: ClassVar[str] = "SYNESIS_E119"

    def to_diagnostic(self) -> str:
        return (
            f"`{self.child}` -> `{self.parent}` appears as {self.first_species} and as "
            f"{self.second_species}.\n"
            f"  Hierarchical situations are exclusive (Z39.19 §8.3): choose one species."
        )

    def to_cli_line(self) -> str:
        return f"`{self.child}` -> `{self.parent}` in two species ({self.first_species}, {self.second_species})"


@dataclass(frozen=True)
class UngroundedConcept(ValidationError):
    """Bloco sem mencao em ITEM (CODE ou CHAIN) e sem descendente mencionado."""

    concept: str
    CODE: ClassVar[str] = "SYNESIS_E120"
    DEFAULT_SEVERITY: ClassVar[ErrorSeverity] = ErrorSeverity.WARNING

    def to_diagnostic(self) -> str:
        return (
            f"The concept `{self.concept}` is not mentioned in any ITEM (CODE or CHAIN) and has\n"
            f"  no mentioned descendant. A broad term without direct use is legitimate when\n"
            f"  it completes the hierarchy (Z39.19 §11.1.8); without descendants, nothing supports it."
        )

    def to_cli_line(self) -> str:
        return f"`{self.concept}` has no mention and no mentioned descendant"


@dataclass(frozen=True)
class DeprecatedNameBasedHierarchy(ValidationError):
    """Hierarquia pela rota de nome (`parent`/`is_a`)."""

    concept: str
    field_name: str
    CODE: ClassVar[str] = "SYNESIS_E121"
    DEFAULT_SEVERITY: ClassVar[ErrorSeverity] = ErrorSeverity.WARNING

    def to_diagnostic(self) -> str:
        return (
            f"The field `{self.field_name}` of `{self.concept}` becomes hierarchy only by its NAME.\n"
            f"  This route will be removed: declare the field as CODE with `ROLE HIERARCHY KIND`."
        )

    def to_cli_line(self) -> str:
        return f"`{self.concept}`: hierarchy by the name `{self.field_name}` (deprecated route)"


# ---------------------------------------------------------------------------
# Valor pelo tipo no ONTOLOGY (Spec ROLE/EXPORT §3) — etapa A2a.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UndeclaredConcept(ValidationError):
    """Conceito citado num campo CODE do ONTOLOGY sem bloco ONTOLOGY.

    Erro, e nao aviso como o E004: e uma declaracao da propria ontologia. Uma
    hierarquia ou referencia apontando para o nada quebra o grafo e o SKOS.
    """

    field_name: str
    concept: str
    suggestions: list[str] = field(default_factory=list)
    CODE: ClassVar[str] = "SYNESIS_E101"

    def to_diagnostic(self) -> str:
        msg = (
            f"The field `{self.field_name}` cites the concept `{self.concept}`, which has no\n"
            f"  ONTOLOGY block. In a CODE field of the organizing model, each item must be a\n"
            f"  declared concept: create the block `ONTOLOGY {self.concept}` or fix the name."
        )
        if self.suggestions:
            msg += f"\n  Similar concept: `{self.suggestions[0]}`."
        return msg

    def to_cli_line(self) -> str:
        suffix = f" (parecido: `{self.suggestions[0]}`)" if self.suggestions else ""
        return f"`{self.field_name}`: concept `{self.concept}` without an ONTOLOGY block{suffix}"


@dataclass(frozen=True)
class IdentityCollision(ValidationError):
    """Dois blocos com nomes que so coincidem pela forma Unicode (NFC)."""

    first_name: str
    second_name: str
    first_file: str
    CODE: ClassVar[str] = "SYNESIS_E103"

    def to_diagnostic(self) -> str:
        return (
            f"The concept `{self.second_name}` has the same identity as `{self.first_name}`\n"
            f"  (in `{self.first_file}`): the names look equal, but one of them uses accented\n"
            f"  letters in decomposed form (letter + combining accent). Synesis treats\n"
            f"  them as the same concept. Rewrite one of the names, or merge the two blocks."
        )

    def to_cli_line(self) -> str:
        return (
            f"Concepts `{self.first_name}` and `{self.second_name}` collide "
            f"(same identity after Unicode normalization)"
        )


@dataclass(frozen=True)
class InvalidValueForm(ValidationError):
    """Item vazio numa lista (`a, , b`) de um campo CODE do ONTOLOGY."""

    field_name: str
    CODE: ClassVar[str] = "SYNESIS_E102"

    def to_diagnostic(self) -> str:
        return (
            f"The list in the field `{self.field_name}` has an empty item (two commas\n"
            f"  in a row, or a comma at the start or end). Remove the extra comma."
        )

    def to_cli_line(self) -> str:
        return f"`{self.field_name}`: empty item in the list"


# ---------------------------------------------------------------------------
# QUESTIONS (questoes de competencia) — erros do nucleo do projeto.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QuestionWithoutId(ValidationError):
    """Linha de QUESTIONS fora da forma `<id>: <texto>`."""

    line: str
    CODE: ClassVar[str] = "SYNESIS_E091"

    def to_diagnostic(self) -> str:
        return (
            f"The line `{self.line}` in the QUESTIONS block has no identifier.\n"
            f"  Each competency question is a line `<id>: <text>`, for example\n"
            f"  `Q1: Which tactics appear in each channel?`. The identifier starts with\n"
            f"  a letter or `_` and lets manifests, tests and the graph cite the question.\n"
            f"  Add an identifier before `:`."
        )

    def to_cli_line(self) -> str:
        return f"Question without identifier in QUESTIONS: `{self.line}` (use `Q1: text`)"


@dataclass(frozen=True)
class QuestionWithoutText(ValidationError):
    """Questao com identificador e sem texto (`Q1:`)."""

    question_id: str
    CODE: ClassVar[str] = "SYNESIS_E092"

    def to_diagnostic(self) -> str:
        return (
            f"The question `{self.question_id}` in the QUESTIONS block has no text.\n"
            f"  Write the question after `{self.question_id}:`, or remove the line."
        )

    def to_cli_line(self) -> str:
        return f"Question `{self.question_id}` without text in QUESTIONS"


@dataclass(frozen=True)
class DuplicateQuestionId(ValidationError):
    """Identificador de questao repetido no projeto."""

    question_id: str
    first_line: int
    CODE: ClassVar[str] = "SYNESIS_E093"

    def to_diagnostic(self) -> str:
        return (
            f"The question identifier `{self.question_id}` was already used on line "
            f"{self.first_line}.\n"
            f"  Each question needs a unique identifier in the project (case does not\n"
            f"  matter: `Q1` and `q1` are the same). Rename one of the two."
        )

    def to_cli_line(self) -> str:
        return f"Repeated question `{self.question_id}` (first on line {self.first_line})"


# ---------------------------------------------------------------------------
# EXPORT — erros locais ao bloco. Na compilacao sao avisos (o corpus continua
# compilavel); em `synesis export`, impedem so o bloco em que aparecem.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExportBlockError(ValidationError):
    """Base dos erros de um bloco EXPORT: `block` e como o bloco e citado."""

    block: str
    DEFAULT_SEVERITY: ClassVar[ErrorSeverity] = ErrorSeverity.WARNING

    def cli_group(self) -> tuple[str, str]:
        """(titulo do grupo, item) para o relatorio agrupado do `synesis export`.

        O bloco ja esta no cabecalho da secao, entao sai da linha. Item vazio:
        a linha inteira e o titulo (diagnostico sem agrupamento proprio).
        """
        line = self.to_cli_line()
        prefix = f"{self.block}: "
        return (line[len(prefix):] if line.startswith(prefix) else line), ""


@dataclass(frozen=True)
class UnknownExportFormat(ExportBlockError):
    """Formato de EXPORT desconhecido ou ainda nao disponivel."""

    export_format: str
    known: tuple[str, ...] = ()
    planned: bool = False
    CODE: ClassVar[str] = "SYNESIS_E094"

    def to_diagnostic(self) -> str:
        known = ", ".join(self.known)
        if self.planned:
            return (
                f"`{self.block}`: the format `{self.export_format}` is planned, but not yet\n"
                f"  available in this compiler version. Available formats: {known}."
            )
        return (
            f"`{self.block}`: unknown export format `{self.export_format}`.\n"
            f"  Available formats: {known}."
        )

    def to_cli_line(self) -> str:
        suffix = " (planned, not yet available)" if self.planned else ""
        return f"{self.block}: unknown format `{self.export_format}`{suffix}"


@dataclass(frozen=True)
class UnknownExportProperty(ExportBlockError):
    """Propriedade fora das aceitas pelo formato."""

    prop: str
    allowed: tuple[str, ...] = ()
    CODE: ClassVar[str] = "SYNESIS_E095"

    def to_diagnostic(self) -> str:
        return (
            f"`{self.block}`: unknown property `{self.prop}` for this format.\n"
            f"  Accepted properties: {', '.join(self.allowed)}."
        )

    def to_cli_line(self) -> str:
        return f"{self.block}: unknown property `{self.prop}` (accepted: {', '.join(self.allowed)})"


@dataclass(frozen=True)
class MissingExportProperty(ExportBlockError):
    """Falta uma propriedade obrigatoria do formato."""

    prop: str
    CODE: ClassVar[str] = "SYNESIS_E096"

    def to_diagnostic(self) -> str:
        example = ' "output/file"' if self.prop == "OUTPUT" else " <value>"
        return (
            f"`{self.block}`: the required property `{self.prop}` is missing.\n"
            f"  Add a line `{self.prop}{example}` inside the block."
        )

    def to_cli_line(self) -> str:
        return f"{self.block}: required property `{self.prop}` is missing"


@dataclass(frozen=True)
class DuplicateExportProperty(ExportBlockError):
    """Propriedade repetida no mesmo bloco."""

    prop: str
    CODE: ClassVar[str] = "SYNESIS_E097"

    def to_diagnostic(self) -> str:
        return (
            f"`{self.block}`: the property `{self.prop}` appears more than once.\n"
            f"  Keep only one; the compiler does not choose between values."
        )

    def to_cli_line(self) -> str:
        return f"{self.block}: repeated property `{self.prop}`"


@dataclass(frozen=True)
class AmbiguousExportName(ExportBlockError):
    """Dois blocos do mesmo formato sem nome, ou nome repetido."""

    reason: str
    CODE: ClassVar[str] = "SYNESIS_E098"

    def to_diagnostic(self) -> str:
        return (
            f"`{self.block}`: {self.reason}.\n"
            f"  With more than one block of the same format, each one needs a unique\n"
            f"  name in the project (`EXPORT JSON panel`), so `synesis export` can choose."
        )

    def to_cli_line(self) -> str:
        return f"{self.block}: {self.reason}"


@dataclass(frozen=True)
class MapNotSupported(ExportBlockError):
    """MAP (ou MAP RELATIONS) num formato que nao o usa."""

    CODE: ClassVar[str] = "SYNESIS_E099"

    def to_diagnostic(self) -> str:
        return (
            f"`{self.block}`: this format does not use `MAP` lines.\n"
            f"  `MAP RELATIONS` is accepted in SKOS and `MAP <fields> TO` in ALPACA (and in CNA,\n"
            f"  when that format is available). Remove the line."
        )

    def to_cli_line(self) -> str:
        return f"{self.block}: `MAP` is not accepted in this format"


@dataclass(frozen=True)
class InvalidGeneratedAt(ExportBlockError):
    """GENERATED_AT que nao e data ISO 8601 com fuso."""

    value: str
    CODE: ClassVar[str] = "SYNESIS_E100"

    def to_diagnostic(self) -> str:
        return (
            f"`{self.block}`: `GENERATED_AT {self.value}` is not an ISO 8601 date with a time zone.\n"
            f"  Example: `GENERATED_AT 2026-11-16T12:00:00Z` or `...T12:00:00-03:00`."
        )

    def to_cli_line(self) -> str:
        return f"{self.block}: invalid GENERATED_AT `{self.value}` (ISO 8601 with time zone)"


@dataclass(frozen=True)
class UnknownRelation(ExportBlockError):
    """Relacao de MAP RELATIONS ausente das RELATIONS dos campos CHAIN."""

    relation: str
    from_field: str = ""
    CODE: ClassVar[str] = "SYNESIS_E122"

    def to_diagnostic(self) -> str:
        where = f"of the field `{self.from_field}`" if self.from_field else "of any CHAIN field in the template"
        return (
            f"`{self.block}`: the relation `{self.relation}` is not in the RELATIONS {where}.\n"
            f"  Use the name exactly as declared in the template (case matters)."
        )

    def to_cli_line(self) -> str:
        return f"{self.block}: unknown relation `{self.relation}`"


@dataclass(frozen=True)
class AmbiguousRelation(ExportBlockError):
    """Relacao presente em mais de um campo CHAIN, sem FROM."""

    relation: str
    fields: tuple = ()
    CODE: ClassVar[str] = "SYNESIS_E123"

    def to_diagnostic(self) -> str:
        return (
            f"`{self.block}`: the relation `{self.relation}` exists in more than one CHAIN field "
            f"({', '.join(self.fields)}).\n"
            f"  Say which with `MAP RELATIONS {self.relation} FROM <field> TO ...`."
        )

    def to_cli_line(self) -> str:
        return f"{self.block}: `{self.relation}` in several CHAIN fields; use FROM"


@dataclass(frozen=True)
class MapTargetNotAllowed(ExportBlockError):
    """Alvo de MAP RELATIONS fora de HIERARCHY KIND/PART/INSTANCE e RELATED."""

    target: str
    CODE: ClassVar[str] = "SYNESIS_E124"

    def to_diagnostic(self) -> str:
        return (
            f"`{self.block}`: `{self.target}` is not a MAP RELATIONS target. Accepted targets:\n"
            f"  HIERARCHY KIND, HIERARCHY PART, HIERARCHY INSTANCE and RELATED."
        )

    def to_cli_line(self) -> str:
        return f"{self.block}: target `{self.target}` not accepted in MAP RELATIONS"


@dataclass(frozen=True)
class RelationMappedTwice(ExportBlockError):
    """A mesma relacao em dois MAP RELATIONS do bloco."""

    relation: str
    CODE: ClassVar[str] = "SYNESIS_E125"

    def to_diagnostic(self) -> str:
        return (
            f"`{self.block}`: the relation `{self.relation}` appears in two `MAP RELATIONS`.\n"
            f"  Each relation has a single reading per artifact."
        )

    def to_cli_line(self) -> str:
        return f"{self.block}: relation `{self.relation}` mapped twice"


@dataclass(frozen=True)
class InvalidMinSources(ExportBlockError):
    """MIN_SOURCES que nao e inteiro >= 1."""

    value: str
    CODE: ClassVar[str] = "SYNESIS_E126"

    def to_diagnostic(self) -> str:
        return f"`{self.block}`: `MIN_SOURCES {self.value}` must be an integer greater than or equal to 1."

    def to_cli_line(self) -> str:
        return f"{self.block}: invalid MIN_SOURCES `{self.value}`"


@dataclass(frozen=True)
class InvalidNamespace(ExportBlockError):
    """NAMESPACE que nao e IRI absoluto terminado em / ou #."""

    value: str
    CODE: ClassVar[str] = "SYNESIS_E127"

    def to_diagnostic(self) -> str:
        return (
            f"`{self.block}`: `NAMESPACE {self.value}` must be an absolute IRI ending\n"
            f"  in `/` or `#`, for example `https://example.org/id/project/`."
        )

    def to_cli_line(self) -> str:
        return f"{self.block}: invalid NAMESPACE `{self.value}`"


@dataclass(frozen=True)
class InvalidLanguageTag(ExportBlockError):
    """LANGUAGE que nao e etiqueta BCP 47 bem formada."""

    value: str
    CODE: ClassVar[str] = "SYNESIS_E128"

    def to_diagnostic(self) -> str:
        return f"`{self.block}`: `LANGUAGE {self.value}` is not a language tag (e.g. pt-BR, en)."

    def to_cli_line(self) -> str:
        return f"{self.block}: invalid LANGUAGE `{self.value}`"


@dataclass(frozen=True)
class DerivedLabelConflict(ExportBlockError):
    """prefLabel derivado do nome coincide com um rotulo de outro conceito."""

    concept: str
    label: str
    other: str
    CODE: ClassVar[str] = "SYNESIS_E129"

    def to_diagnostic(self) -> str:
        return (
            f"`{self.block}`: the preferred label of `{self.concept}`, derived from the name\n"
            f"  (\"{self.label}\"), matches a label of `{self.other}`. Declare a\n"
            f"  LABEL PREFERRED for one of the two."
        )

    def to_cli_line(self) -> str:
        return f"{self.block}: derived label \"{self.label}\" of `{self.concept}` matches `{self.other}`"


@dataclass(frozen=True)
class DerivedLabelOverlap(ExportBlockError):
    """prefLabel derivado coincide com altLabel/hiddenLabel do mesmo conceito (S13)."""

    concept: str
    label: str
    CODE: ClassVar[str] = "SYNESIS_E130"

    def to_diagnostic(self) -> str:
        return (
            f"`{self.block}`: the preferred label derived from `{self.concept}` (\"{self.label}\")\n"
            f"  is also an alternative or hidden label of the same concept (SKOS S13).\n"
            f"  Remove the term from LABEL ALTERNATIVE/HIDDEN or declare a LABEL PREFERRED."
        )

    def to_cli_line(self) -> str:
        return f"{self.block}: \"{self.label}\" is both preferred and alternative in `{self.concept}`"


@dataclass(frozen=True)
class IriCollision(ExportBlockError):
    """Dois recursos com o mesmo IRI (defesa)."""

    iri: str
    CODE: ClassVar[str] = "SYNESIS_E131"

    def to_diagnostic(self) -> str:
        return f"`{self.block}`: dois recursos recebem o mesmo IRI `{self.iri}`."

    def to_cli_line(self) -> str:
        return f"{self.block}: repeated IRI `{self.iri}`"


@dataclass(frozen=True)
class TopicCaseVariant(ExportBlockError):
    """Valores de TOPIC com a mesma identidade e grafias diferentes, unidos."""

    field_name: str
    spellings: tuple = ()
    chosen: str = ""
    CODE: ClassVar[str] = "SYNESIS_E132"

    def to_diagnostic(self) -> str:
        return (
            f"`{self.block}`: the TOPIC `{self.field_name}` has spellings of the same value\n"
            f"  ({', '.join(self.spellings)}), merged into one collection labeled \"{self.chosen}\"."
        )

    def to_cli_line(self) -> str:
        return f"{self.block}: TOPIC spellings merged ({', '.join(self.spellings)}) -> \"{self.chosen}\""

    def cli_group(self) -> tuple[str, str]:
        return "TOPIC spellings merged", f"({', '.join(self.spellings)}) -> \"{self.chosen}\""


# ---------------------------------------------------------------------------
# PHASE: plano de producao dos campos pelo synesis-coder (etapa B1). O
# compilador so valida o plano; nunca executa uma fase.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PhaseError(ValidationError):
    """Base dos diagnosticos de PHASE: `phase` e como o bloco e citado."""

    phase: str


@dataclass(frozen=True)
class UnknownPhaseProperty(PhaseError):
    """Propriedade fora de FIELDS, INPUT, RULES e OUTPUT (OUTPUT so em ONTOLOGY)."""

    prop: str
    CODE: ClassVar[str] = "SYNESIS_E133"

    def to_diagnostic(self) -> str:
        return (
            f"`{self.phase}`: unknown property `{self.prop}`. A PHASE accepts FIELDS,\n"
            f"  INPUT, RULES and, only in PHASE ONTOLOGY, OUTPUT."
        )

    def to_cli_line(self) -> str:
        return f"{self.phase}: unknown property `{self.prop}`"


@dataclass(frozen=True)
class DuplicatePhaseProperty(PhaseError):
    """Propriedade repetida no bloco PHASE."""

    prop: str
    CODE: ClassVar[str] = "SYNESIS_E134"

    def to_diagnostic(self) -> str:
        return (
            f"`{self.phase}`: the property `{self.prop}` appears more than once.\n"
            f"  Put the fields on a single line (`{self.prop} a, b, c`)."
        )

    def to_cli_line(self) -> str:
        return f"{self.phase}: repeated property `{self.prop}`"


@dataclass(frozen=True)
class EmptyPhaseList(PhaseError):
    """FIELDS, INPUT ou RULES sem campo; PHASE sem FIELDS."""

    prop: str
    CODE: ClassVar[str] = "SYNESIS_E135"

    def to_diagnostic(self) -> str:
        if self.prop == "FIELDS":
            return f"`{self.phase}`: the phase needs `FIELDS` with at least one field to produce."
        return f"`{self.phase}`: `{self.prop}` is empty; remove the line or list the fields."

    def to_cli_line(self) -> str:
        return f"{self.phase}: `{self.prop}` without fields"


@dataclass(frozen=True)
class UnknownPhaseField(PhaseError):
    """Campo de FIELDS, INPUT ou RULES ausente do template."""

    prop: str
    field_name: str
    CODE: ClassVar[str] = "SYNESIS_E136"

    def to_diagnostic(self) -> str:
        return (
            f"`{self.phase}`: the field `{self.field_name}` in `{self.prop}` does not exist in the template.\n"
            f"  A phase only produces and reads fields that the template declares."
        )

    def to_cli_line(self) -> str:
        return f"{self.phase}: field `{self.field_name}` ({self.prop}) outside the template"


@dataclass(frozen=True)
class FieldInTwoPhases(PhaseError):
    """O mesmo campo em FIELDS de duas fases."""

    field_name: str
    first_phase: str
    CODE: ClassVar[str] = "SYNESIS_E137"

    def to_diagnostic(self) -> str:
        return (
            f"`{self.phase}`: the field `{self.field_name}` is already produced by `{self.first_phase}`.\n"
            f"  Each field is produced by a single phase."
        )

    def to_cli_line(self) -> str:
        return f"{self.phase}: `{self.field_name}` is already produced by `{self.first_phase}`"


@dataclass(frozen=True)
class PhaseScopeMismatch(PhaseError):
    """Campo de ONTOLOGY numa PHASE ANNOTATIONS, ou de SOURCE/ITEM numa PHASE ONTOLOGY."""

    field_name: str
    field_scope: str
    CODE: ClassVar[str] = "SYNESIS_E138"

    def to_diagnostic(self) -> str:
        return (
            f"`{self.phase}`: the field `{self.field_name}` belongs to scope {self.field_scope}.\n"
            f"  PHASE ANNOTATIONS produces SOURCE and ITEM fields; PHASE ONTOLOGY, ONTOLOGY fields."
        )

    def to_cli_line(self) -> str:
        return f"{self.phase}: `{self.field_name}` ({self.field_scope}) outside the phase scope"


@dataclass(frozen=True)
class InputNotAvailable(PhaseError):
    """INPUT produzido só por uma fase POSTERIOR (ordem das fases)."""

    field_name: str
    CODE: ClassVar[str] = "SYNESIS_E139"
    DEFAULT_SEVERITY: ClassVar[ErrorSeverity] = ErrorSeverity.WARNING

    def to_diagnostic(self) -> str:
        return (
            f"`{self.phase}`: `{self.field_name}` (INPUT) is only produced by a later phase.\n"
            f"  In this order, the phase reads whatever value exists before it; move it later."
        )

    def to_cli_line(self) -> str:
        return f"{self.phase}: INPUT `{self.field_name}` only produced by a later phase"


@dataclass(frozen=True)
class BundleSplitAcrossPhases(PhaseError):
    """Campos de um BUNDLE em fases diferentes."""

    bundle: tuple
    CODE: ClassVar[str] = "SYNESIS_E140"

    def to_diagnostic(self) -> str:
        return (
            f"`{self.phase}`: the fields of the BUNDLE ({', '.join(self.bundle)}) are in different\n"
            f"  phases. Fields of a BUNDLE are produced together (the cross rule between\n"
            f"  them is lost when they are split)."
        )

    def to_cli_line(self) -> str:
        return f"BUNDLE ({', '.join(self.bundle)}) split across phases"


@dataclass(frozen=True)
class FieldWithoutPhase(ValidationError):
    """Com blocos PHASE, campo REQUIRED que nenhuma fase produz."""

    field_name: str
    CODE: ClassVar[str] = "SYNESIS_E141"
    DEFAULT_SEVERITY: ClassVar[ErrorSeverity] = ErrorSeverity.WARNING

    def to_diagnostic(self) -> str:
        return (
            f"The required field `{self.field_name}` is not produced by any PHASE.\n"
            f"  It will have to be filled by hand, or added to the FIELDS of a phase."
        )

    def to_cli_line(self) -> str:
        return f"REQUIRED field `{self.field_name}` without a phase"


@dataclass(frozen=True)
class AmbiguousPhaseOutput(PhaseError):
    """PHASE ONTOLOGY sem OUTPUT num projeto sem exatamente um .syno elegivel."""

    eligible: int
    CODE: ClassVar[str] = "SYNESIS_E142"

    def to_diagnostic(self) -> str:
        return (
            f"`{self.phase}`: the project has {self.eligible} .syno file(s) eligible for writing\n"
            f"  (local, cited as a file). Set the destination with `OUTPUT \"file.syno\"`."
        )

    def to_cli_line(self) -> str:
        return f"{self.phase}: ambiguous destination ({self.eligible} eligible .syno files); use OUTPUT"


@dataclass(frozen=True)
class PhaseOutputNotLocal(PhaseError):
    """OUTPUT fora dos .syno locais citados como arquivo."""

    output: str
    CODE: ClassVar[str] = "SYNESIS_E143"

    def to_diagnostic(self) -> str:
        return (
            f"`{self.phase}`: `OUTPUT {self.output}` is not a local .syno of the project. The destination\n"
            f"  must be an INCLUDE ONTOLOGY cited as a file (not a folder or pattern) and\n"
            f"  outside INCLUDE SHARED."
        )

    def to_cli_line(self) -> str:
        return f"{self.phase}: OUTPUT `{self.output}` is not a local .syno of the project"


@dataclass(frozen=True)
class PhaseNameCollision(PhaseError):
    """Fases com o mesmo nome, ou nomes que viram a mesma variavel de ambiente."""

    other: str
    CODE: ClassVar[str] = "SYNESIS_E144"

    def to_diagnostic(self) -> str:
        return (
            f"`{self.phase}` collides with `{self.other}`: both names become the same\n"
            f"  coder environment variable (SYNESIS_CODER_PHASE_<NAME>_*). Rename one of the phases."
        )

    def to_cli_line(self) -> str:
        return f"{self.phase} collides with {self.other} (same environment variable)"


# ---------------------------------------------------------------------------
# USE: consolidacao de conceitos (etapa U; Spec_USE_Etapa_U.md). O bloco com
# o campo USE e o preterido; o alvo e o conceito que vale.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class UseSelf(ValidationError):
    """Bloco cujo USE aponta para ele mesmo."""

    concept: str
    field_name: str
    CODE: ClassVar[str] = "SYNESIS_E145"

    def to_diagnostic(self) -> str:
        return f"`{self.concept}` points to itself in `{self.field_name}` (USE)."

    def to_cli_line(self) -> str:
        return f"`{self.concept}` uses itself in `{self.field_name}`"


@dataclass(frozen=True)
class UseChain(ValidationError):
    """USE que aponta para um conceito que tambem e preterido."""

    concept: str
    target: str
    final: str
    CODE: ClassVar[str] = "SYNESIS_E146"

    def to_diagnostic(self) -> str:
        return (
            f"`{self.concept}` uses `{self.target}`, which is also an alias (uses `{self.final}`).\n"
            f"  Point directly to `{self.final}`: an alias always points to the concept that remains."
        )

    def to_cli_line(self) -> str:
        return f"`{self.concept}` uses `{self.target}`, which uses `{self.final}`"


@dataclass(frozen=True)
class UseMultipleTargets(ValidationError):
    """Campo USE com mais de um conceito."""

    concept: str
    field_name: str
    targets: tuple = ()
    CODE: ClassVar[str] = "SYNESIS_E147"

    def to_diagnostic(self) -> str:
        return (
            f"`{self.concept}`: `{self.field_name}` (USE) has {len(self.targets)} concepts "
            f"({', '.join(self.targets)}).\n  An alias points to a single concept."
        )

    def to_cli_line(self) -> str:
        return f"`{self.concept}`: USE with several targets ({', '.join(self.targets)})"


@dataclass(frozen=True)
class AliasWithContent(ValidationError):
    """Bloco preterido com outros campos alem do USE."""

    concept: str
    fields: tuple = ()
    CODE: ClassVar[str] = "SYNESIS_E148"

    def to_diagnostic(self) -> str:
        return (
            f"`{self.concept}` is an alias (USE) and still has {', '.join(self.fields)}.\n"
            f"  Move the content to the target first (synesis-coder consolidate transfers it\n"
            f"  and archives what does not fit): an alias has only the USE field."
        )

    def to_cli_line(self) -> str:
        return f"`{self.concept}` is an alias and has other fields ({', '.join(self.fields)})"


@dataclass(frozen=True)
class HierarchyCollapsedByUse(ValidationError):
    """Depois de resolver USE, um conceito seria pai de si mesmo."""

    concept: str
    field_name: str
    parent: str
    CODE: ClassVar[str] = "SYNESIS_E149"

    def to_diagnostic(self) -> str:
        return (
            f"`{self.concept}` has `{self.parent}` in `{self.field_name}`, but `{self.parent}` uses\n"
            f"  `{self.concept}`: after consolidation, the concept would be its own parent."
        )

    def to_cli_line(self) -> str:
        return f"`{self.concept}` -> `{self.parent}` collapses after USE (parent of itself)"


@dataclass(frozen=True)
class UnknownAliasLabel(ExportBlockError):
    """ALIAS_LABEL fora de HIDDEN e ALTERNATIVE."""

    value: str
    CODE: ClassVar[str] = "SYNESIS_E150"

    def to_diagnostic(self) -> str:
        return f"`{self.block}`: `ALIAS_LABEL {self.value}` unknown; use HIDDEN or ALTERNATIVE."

    def to_cli_line(self) -> str:
        return f"{self.block}: unknown ALIAS_LABEL `{self.value}`"


@dataclass(frozen=True)
class AliasLabelCollision(ExportBlockError):
    """Nome preterido igual a um rotulo que o alvo ja tem."""

    alias: str
    target: str
    CODE: ClassVar[str] = "SYNESIS_E151"

    def to_diagnostic(self) -> str:
        return (
            f"`{self.block}`: the alias name `{self.alias}` is already a label of `{self.target}`;\n"
            f"  it was not repeated (the labels of a concept are disjoint, SKOS S13)."
        )

    def to_cli_line(self) -> str:
        return f"{self.block}: `{self.alias}` is already a label of `{self.target}`"


@dataclass(frozen=True)
class RegistryNotFound(ExportBlockError):
    """REGISTRY que nao e um arquivo de texto utilizavel."""

    path: str
    CODE: ClassVar[str] = "SYNESIS_E152"

    def to_diagnostic(self) -> str:
        return (
            f"`{self.block}`: `REGISTRY {self.path}` is not a usable file (folder or invalid\n"
            f"  path). Without a registry, no IRI counts as published."
        )

    def to_cli_line(self) -> str:
        return f"{self.block}: REGISTRY `{self.path}` unusable"

    def cli_group(self) -> tuple[str, str]:
        return "REGISTRY unusable", f"`{self.path}`"


@dataclass(frozen=True)
class PublishedIriWithoutBlock(ExportBlockError):
    """IRI registrado como publicado sem bloco nem USE que o substitua."""

    iri: str
    CODE: ClassVar[str] = "SYNESIS_E153"

    def to_diagnostic(self) -> str:
        return (
            f"`{self.block}`: the published IRI `{self.iri}` no longer has a block in the project.\n"
            f"  A published concept does not vanish: consolidate it with USE (it is exported as\n"
            f"  deprecated, with isReplacedBy) instead of deleting or renaming the block."
        )

    def to_cli_line(self) -> str:
        return f"{self.block}: published IRI without a block `{self.iri}`"

    def cli_group(self) -> tuple[str, str]:
        return "Published IRI without a block", f"`{self.iri}`"


@dataclass(frozen=True)
class RegistryOutsideNamespace(ExportBlockError):
    """REGISTRY com IRIs de outro NAMESPACE: nao sao conferidos (aviso; o namespace e do pesquisador)."""

    namespace: str
    count: int
    examples: tuple[str, ...] = ()
    CODE: ClassVar[str] = "SYNESIS_E156"

    def to_diagnostic(self) -> str:
        shown = "\n".join(f"    {e}" for e in self.examples)
        return (
            f"`{self.block}`: the REGISTRY has {self.count} published IRI(s) outside the current\n"
            f"  NAMESPACE `{self.namespace}`; they are not checked and are absent from this file.\n{shown}\n"
            f"  The NAMESPACE is the researcher's decision. If the change is intended, links to the\n"
            f"  old IRIs will break: keep a redirect at the old address, or a separate REGISTRY."
        )

    def to_cli_line(self) -> str:
        return f"{self.block}: {self.count} registered IRI(s) outside NAMESPACE `{self.namespace}`"

    def cli_group(self) -> tuple[str, str]:
        return "REGISTRY IRIs outside the NAMESPACE (not checked)", f"{self.count} — e.g. {self.examples[0]}" \
            if self.examples else f"{self.count}"


@dataclass(frozen=True)
class RegistryIsOutput(ExportBlockError):
    """REGISTRY e OUTPUT apontam para o mesmo arquivo: um sobrescreveria o outro."""

    path: str
    CODE: ClassVar[str] = "SYNESIS_E157"
    DEFAULT_SEVERITY: ClassVar[ErrorSeverity] = ErrorSeverity.ERROR

    def to_diagnostic(self) -> str:
        return (
            f"`{self.block}`: OUTPUT and REGISTRY are the same file (`{self.path}`); nothing was written.\n"
            f"  The SKOS would overwrite the registry of published IRIs, or the registry the SKOS.\n"
            f"  Give REGISTRY its own file, for example \"saida/published-iris.txt\"."
        )

    def to_cli_line(self) -> str:
        return f"{self.block}: OUTPUT and REGISTRY are the same file `{self.path}`"


@dataclass(frozen=True)
class SkosIntegrityViolation(ExportBlockError):
    """SKOS gerado viola condicao de integridade (S9, S13, S14, S27, S37) ou a regra de hierarquia aciclica do Synesis."""

    condition: str
    count: int
    examples: tuple[str, ...] = ()
    CODE: ClassVar[str] = "SYNESIS_E154"
    DEFAULT_SEVERITY: ClassVar[ErrorSeverity] = ErrorSeverity.ERROR

    def to_diagnostic(self) -> str:
        shown = "\n".join(f"    {e}" for e in self.examples)
        if self.condition.startswith("Synesis rule"):
            # O SKOS admite ciclos hierarquicos (§8.6.8); a proibicao e do Synesis.
            return (
                f"`{self.block}`: the generated SKOS breaks the {self.condition} "
                f"({self.count} case(s)); the file was not written.\n{shown}\n"
                f"  SKOS itself allows hierarchical cycles (SKOS Reference §8.6.8); Synesis does not.\n"
                f"  The compiler rejects cycles in the .syno, so this points to MAP RELATIONS pairs."
            )
        return (
            f"`{self.block}`: the generated SKOS violates the integrity condition {self.condition} "
            f"({self.count} case(s)); the file was not written.\n{shown}\n"
            f"  This is an exporter or project inconsistency, not an editorial choice: "
            f"report it with the project files."
        )

    def to_cli_line(self) -> str:
        return f"{self.block}: SKOS integrity {self.condition} ({self.count})"


@dataclass(frozen=True)
class SkosQualityNotice(ExportBlockError):
    """Verificacao editorial do SKOS gerado (sem prefLabel, sem posicao, esquema sem topo...)."""

    condition: str
    count: int
    examples: tuple[str, ...] = ()
    CODE: ClassVar[str] = "SYNESIS_E155"

    def to_diagnostic(self) -> str:
        shown = "\n".join(f"    {e}" for e in self.examples)
        return (
            f"`{self.block}`: SKOS quality check \"{self.condition}\" — {self.count} case(s).\n{shown}\n"
            f"  Editorial, not a violation of SKOS: the file was written. Tools such as VocBench (ICV)\n"
            f"  and qSKOS report the same group."
        )

    def to_cli_line(self) -> str:
        return f"{self.block}: SKOS quality \"{self.condition}\" ({self.count})"

    def cli_group(self) -> tuple[str, str]:
        examples = f" — e.g. {self.examples[0]}" if self.examples else ""
        return "SKOS quality notices", f"{self.condition}: {self.count}{examples}"


# ---------------------------------------------------------------------------
# EXPORT ALPACA com composicao declarada (MAP <campos> TO INSTRUCTION/INPUT/OUTPUT)
# Estudo: synesis-planning/synesis/Estudo_Alpaca_Composicao_Declarada_MAP_TO.md
# ---------------------------------------------------------------------------

_ALPACA_DOC = "Each key of the Alpaca line comes from `MAP <fields> TO INSTRUCTION | INPUT | OUTPUT`."


@dataclass(frozen=True)
class AlpacaOutputMapMissing(ExportBlockError):
    """Modo declarado (MAP de campos ou INSTRUCTION) sem `MAP ... TO OUTPUT`."""

    CODE: ClassVar[str] = "SYNESIS_E158"

    def to_diagnostic(self) -> str:
        return (
            f"`{self.block}`: no `MAP <fields> TO OUTPUT`. The output is what the model learns\n"
            f"  to produce, so it must be declared. {_ALPACA_DOC}\n"
            f"  Without any MAP or INSTRUCTION the block keeps the built-in Alpaca pairs."
        )

    def to_cli_line(self) -> str:
        return f"{self.block}: missing `MAP <fields> TO OUTPUT`"


@dataclass(frozen=True)
class AlpacaInstructionSource(ExportBlockError):
    """Nenhuma origem de instrucao, ou propriedade INSTRUCTION e MAP TO INSTRUCTION juntas."""

    both: bool = False
    CODE: ClassVar[str] = "SYNESIS_E159"

    def to_diagnostic(self) -> str:
        if self.both:
            return (
                f"`{self.block}`: the instruction is declared twice — the `INSTRUCTION` property\n"
                f"  and `MAP ... TO INSTRUCTION`. Keep one: a fixed text or a field."
            )
        return (
            f"`{self.block}`: no instruction. Write `INSTRUCTION <text>` (same instruction on\n"
            f"  every line) or `MAP <field> TO INSTRUCTION` (instruction taken from a field)."
        )

    def to_cli_line(self) -> str:
        if self.both:
            return f"{self.block}: INSTRUCTION and MAP TO INSTRUCTION together; keep one"
        return f"{self.block}: no instruction (INSTRUCTION <text> or MAP <field> TO INSTRUCTION)"


@dataclass(frozen=True)
class AlpacaUnknownField(ExportBlockError):
    """Campo do MAP ausente do template."""

    field_name: str
    suggestion: str = ""
    CODE: ClassVar[str] = "SYNESIS_E160"

    def to_diagnostic(self) -> str:
        hint = f" Did you mean `{self.suggestion}`?" if self.suggestion else ""
        return (
            f"`{self.block}`: the field `{self.field_name}` is not declared in the template.{hint}\n"
            f"  Use the field name exactly as in the template."
        )

    def to_cli_line(self) -> str:
        hint = f" (did you mean `{self.suggestion}`?)" if self.suggestion else ""
        return f"{self.block}: unknown field `{self.field_name}`{hint}"


@dataclass(frozen=True)
class AlpacaDuplicateField(ExportBlockError):
    """O mesmo campo duas vezes no mesmo alvo."""

    field_name: str
    target: str
    CODE: ClassVar[str] = "SYNESIS_E161"

    def to_diagnostic(self) -> str:
        return (
            f"`{self.block}`: the field `{self.field_name}` is mapped twice to {self.target}.\n"
            f"  Each field enters a key once."
        )

    def to_cli_line(self) -> str:
        return f"{self.block}: `{self.field_name}` mapped twice to {self.target}"


@dataclass(frozen=True)
class AlpacaFieldLeak(ExportBlockError):
    """Campo do OUTPUT tambem em INPUT ou INSTRUCTION: a resposta vazaria no prompt."""

    field_name: str
    target: str
    CODE: ClassVar[str] = "SYNESIS_E162"

    def to_diagnostic(self) -> str:
        return (
            f"`{self.block}`: the field `{self.field_name}` is in OUTPUT and also in {self.target}.\n"
            f"  The answer would be in the prompt, and the model would learn to copy it.\n"
            f"  Instruction and input are joined into the prompt at training time."
        )

    def to_cli_line(self) -> str:
        return f"{self.block}: `{self.field_name}` in OUTPUT and in {self.target} (answer leaks into the prompt)"


@dataclass(frozen=True)
class AlpacaMultipleBundles(ExportBlockError):
    """Campos de dois bundles diferentes: nao ha uma unidade unica por linha."""

    bundles: tuple = ()
    CODE: ClassVar[str] = "SYNESIS_E163"

    def to_diagnostic(self) -> str:
        shown = "; ".join("(" + ", ".join(b) + ")" for b in self.bundles)
        return (
            f"`{self.block}`: the fields come from more than one BUNDLE: {shown}.\n"
            f"  One BUNDLE sets the lines (one line per occurrence); fields outside it are\n"
            f"  context. Fields of two bundles would pair occurrences that do not belong together."
        )

    def to_cli_line(self) -> str:
        return f"{self.block}: fields from {len(self.bundles)} bundles; use fields of one BUNDLE"


@dataclass(frozen=True)
class AlpacaFieldNotSupported(ExportBlockError):
    """Campo de ONTOLOGY, ou de SOURCE com valor fora do .syn (ON BIBLIOGRAPHY/ON DATASET)."""

    field_name: str
    reason: str
    CODE: ClassVar[str] = "SYNESIS_E164"

    def to_diagnostic(self) -> str:
        return (
            f"`{self.block}`: the field `{self.field_name}` cannot enter an Alpaca key yet\n"
            f"  ({self.reason}). Planned for a later version; use ITEM fields and SOURCE fields\n"
            f"  written in the annotation files."
        )

    def to_cli_line(self) -> str:
        return f"{self.block}: `{self.field_name}` not supported yet ({self.reason})"


@dataclass(frozen=True)
class AlpacaMapTarget(ExportBlockError):
    """Alvo de MAP fora de INSTRUCTION/INPUT/OUTPUT, ou FROM nesses alvos."""

    target: str
    with_from: bool = False
    CODE: ClassVar[str] = "SYNESIS_E165"

    def to_diagnostic(self) -> str:
        if self.with_from:
            return (
                f"`{self.block}`: `FROM` is not used with the target {self.target}.\n"
                f"  In EXPORT ALPACA, `MAP` names fields: `MAP <fields> TO {self.target}`."
            )
        return (
            f"`{self.block}`: `{self.target}` is not a target of EXPORT ALPACA.\n"
            f"  Accepted targets: INSTRUCTION, INPUT and OUTPUT."
        )

    def to_cli_line(self) -> str:
        if self.with_from:
            return f"{self.block}: FROM not accepted in MAP ... TO {self.target}"
        return f"{self.block}: target `{self.target}` not accepted (INSTRUCTION, INPUT, OUTPUT)"


@dataclass(frozen=True)
class ExportBlockNotice(ValidationError):
    """Base dos informativos de um bloco EXPORT.

    NAO herda de ExportBlockError de proposito: `synesis export` bloqueia o
    artefato com qualquer ExportBlockError. Um informativo e mostrado e o
    artefato e gerado.
    """

    block: str
    DEFAULT_SEVERITY: ClassVar[ErrorSeverity] = ErrorSeverity.INFO


@dataclass(frozen=True)
class AlpacaBundlePartnerOmitted(ExportBlockNotice):
    """Parceiro qualificador (ENUMERATED/ORDERED/SCALE) do bundle iterador fora do mapa."""

    field_name: str
    partner_of: str
    CODE: ClassVar[str] = "SYNESIS_I166"

    def to_diagnostic(self) -> str:
        return (
            f"`{self.block}`: `{self.field_name}` qualifies `{self.partner_of}` in the BUNDLE and does\n"
            f"  not enter the dataset. If that is intended (for instance, a dataset already\n"
            f"  filtered), ignore this note; otherwise add it to a MAP."
        )

    def to_cli_line(self) -> str:
        return f"{self.block}: `{self.field_name}` qualifies `{self.partner_of}` in the BUNDLE and is not in the dataset"


@dataclass(frozen=True)
class AlpacaLegacyDropsQualifier(ExportBlockNotice):
    """Modo Alpaca embutido com template cujo bundle de CHAIN tem qualificador."""

    field_name: str
    chain_field: str
    CODE: ClassVar[str] = "SYNESIS_I167"

    def to_diagnostic(self) -> str:
        return (
            f"`{self.block}`: the built-in Alpaca pairs do not carry `{self.field_name}`, which\n"
            f"  qualifies `{self.chain_field}` in a BUNDLE: every relation is exported as if asserted.\n"
            f"  Declare the composition with `EXPORT ALPACA` and `MAP {self.chain_field}, "
            f"{self.field_name} TO OUTPUT`."
        )

    def to_cli_line(self) -> str:
        return f"{self.block}: built-in pairs drop `{self.field_name}` (qualifies `{self.chain_field}`); declare MAP ... TO OUTPUT"


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

    def to_diagnostics(self, *, verbose: bool = True) -> str:
        """Retorna mensagens de erro/warning formatadas.

        Args:
            verbose: Se True (padrão), usa mensagens pedagógicas completas —
                adequado para o LLM de auto-correção e para o LSP.
                Se False, usa mensagens compactas de uma linha (to_cli_line()),
                agrupando UndefinedCode por código com contagem de ocorrências —
                adequado para exibição ao usuário pesquisador.
        """
        if verbose:
            return self._to_diagnostics_verbose()
        return self._to_diagnostics_compact()

    def _to_diagnostics_verbose(self) -> str:
        lines: list[str] = []
        if self.errors:
            lines.append("=== ERRORS ===")
            for err in self.errors:
                lines.append(err.to_diagnostic())
                lines.append("")
        if self.warnings:
            lines.append("=== WARNINGS ===")
            for warn in self.warnings:
                lines.append(warn.to_diagnostic())
                lines.append("")
        if self.info:
            lines.append("=== INFORMACOES ===")
            for inf in self.info:
                lines.append(inf.to_diagnostic())
                lines.append("")
        return "\n".join(lines)

    def _to_diagnostics_compact(self) -> str:
        """Versão enxuta: uma linha por erro; UndefinedCode agrupados por código."""
        from collections import defaultdict

        lines: list[str] = []

        # --- ERROS (todos compactos, uma linha cada) ---
        if self.errors:
            lines.append("=== ERRORS ===")
            for err in self.errors:
                lines.append(f"[!] {err.to_cli_line()}")

        # --- AVISOS: separar UndefinedCode dos demais ---
        undefined_code_counts: dict[str, int] = defaultdict(int)
        undefined_code_suggestions: dict[str, list[str]] = {}
        other_warnings: list[ValidationError] = []

        for warn in self.warnings:
            if isinstance(warn, UndefinedCode):
                undefined_code_counts[warn.code] += 1
                if warn.suggestions and warn.code not in undefined_code_suggestions:
                    undefined_code_suggestions[warn.code] = warn.suggestions
            else:
                other_warnings.append(warn)

        has_warnings = bool(undefined_code_counts or other_warnings)
        if has_warnings:
            if lines:
                lines.append("")
            lines.append("=== WARNINGS ===")

            # Outros warnings (compactos, uma linha cada)
            for warn in other_warnings:
                lines.append(f"[!] {warn.to_cli_line()}")

            # UndefinedCode agrupados por código, ordenados por frequência desc
            if undefined_code_counts:
                n_codes = len(undefined_code_counts)
                total_occ = sum(undefined_code_counts.values())
                header = (
                    f"[!] {n_codes} code(s) used in the annotations without a definition in the organizing model"
                    f" ({total_occ} occurrence(s) in total):"
                )
                lines.append(header)
                max_name_len = max(len(c) for c in undefined_code_counts)
                for code, count in sorted(
                    undefined_code_counts.items(), key=lambda x: -x[1]
                ):
                    suffix = ""
                    if code in undefined_code_suggestions:
                        suffix = f"  (did you mean `{undefined_code_suggestions[code][0]}`?)"
                    occ_label = "occurrence" if count == 1 else "occurrences"
                    lines.append(
                        f"    - {code.ljust(max_name_len)}  ({count} {occ_label}){suffix}"
                    )
                lines.append("")
                lines.append(
                    "Tip: run `synesis-coder ontology` to generate the definitions automatically."
                )

        # --- INFO (compactos, uma linha cada) ---
        if self.info:
            if lines:
                lines.append("")
            lines.append("=== INFORMACOES ===")
            for inf in self.info:
                lines.append(f"[i] {inf.to_cli_line()}")

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
