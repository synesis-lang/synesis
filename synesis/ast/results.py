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
            f"A referencia `@{self.bibref}` nao foi encontrada no arquivo de referencias (`.bib`).\n"
            f"  Verifique se o identificador esta escrito corretamente — ele deve corresponder\n"
            f"  exatamente ao campo `ID` da entrada BibTeX.\n"
        )
        if self.suggestions:
            formatted = ", ".join(f"`@{s}`" for s in self.suggestions)
            msg += f"  Chaves similares encontradas no `.bib`: {formatted}.\n"
        msg += f"  Consulte o arquivo `.bib` para ver as referencias disponiveis."
        return msg

    def to_cli_line(self) -> str:
        if self.suggestions:
            formatted = ", ".join(f"`@{s}`" for s in self.suggestions)
            suffix = f". Sugestoes: {formatted}"
        else:
            suffix = ""
        return f"Referencia `@{self.bibref}` nao encontrada no .bib{suffix}"


@dataclass(frozen=True)
class OrphanItem(ValidationError):
    """ITEM sem SOURCE correspondente."""

    bibref: str
    CODE: ClassVar[str] = "SYNESIS_E002"

    def to_diagnostic(self) -> str:
        return (
            f"Este ITEM referencia `@{self.bibref}`, mas nao ha nenhum bloco SOURCE com\n"
            f"  essa referencia neste arquivo. Todo ITEM precisa de um SOURCE correspondente\n"
            f"  no mesmo arquivo.\n"
            f"  Crie um bloco `SOURCE @{self.bibref}` antes deste ITEM, ou verifique\n"
            f"  se a referencia esta correta."
        )

    def to_cli_line(self) -> str:
        return f"ITEM `@{self.bibref}` sem SOURCE correspondente neste arquivo"


@dataclass(frozen=True)
class SourceWithoutItems(ValidationError):
    """SOURCE sem ITEMs associados."""

    bibref: str
    CODE: ClassVar[str] = "SYNESIS_E003"
    DEFAULT_SEVERITY: ClassVar[ErrorSeverity] = ErrorSeverity.WARNING

    def to_diagnostic(self) -> str:
        return (
            f"O bloco `SOURCE @{self.bibref}` nao possui nenhum ITEM associado. Um SOURCE\n"
            f"  existe para contextualizar unidades de analise — sem ITEMs, a fonte foi\n"
            f"  registrada mas nunca analisada.\n"
            f"  Verifique se ha ITEMs com essa referencia em outro arquivo do projeto,\n"
            f"  ou adicione pelo menos um ITEM a este SOURCE."
        )

    def to_cli_line(self) -> str:
        return f"SOURCE `@{self.bibref}` sem nenhum ITEM associado"


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
            f"O codigo `{self.code}` nao esta definido na ontologia do projeto. Todos os\n"
            f"  codigos usados nas anotacoes precisam ter um conceito correspondente\n"
            f"  declarado em um bloco ONTOLOGY.\n"
        )
        if self.suggestions:
            msg += f"  Voce quis dizer `{self.suggestions[0]}`?\n"
        msg += (
            f"  Para criar o conceito, adicione em um arquivo `.syno`:\n"
            f"      ONTOLOGY {self.code}\n"
            f"          description: ...\n"
            f"      END ONTOLOGY"
        )
        return msg

    def to_cli_line(self) -> str:
        suggestion = f". Sugestao de correcao -> `{self.suggestions[0]}`" if self.suggestions else ""
        return f"Codigo `{self.code}` nao definido na ontologia{suggestion}"


@dataclass(frozen=True)
class MissingProjectFile(ValidationError):
    """Nenhum arquivo .synp encontrado na raiz do workspace."""

    workspace_root: str
    CODE: ClassVar[str] = "SYNESIS_E064"
    DEFAULT_SEVERITY: ClassVar[ErrorSeverity] = ErrorSeverity.WARNING

    def to_diagnostic(self) -> str:
        return (
            f"Nenhum arquivo .synp encontrado na raiz do workspace: {self.workspace_root}\n"
            f"  Validacao semantica desativada.\n"
            f"  Para ativar validacao completa, crie um arquivo PROJECT na raiz do workspace.\n"
            f"  Exemplo: projeto.synp"
        )

    def to_cli_line(self) -> str:
        return f"Nenhum .synp encontrado em `{self.workspace_root}` — crie um arquivo PROJECT"


@dataclass(frozen=True)
class MissingTemplateFile(ValidationError):
    """Template especificado no .synp nao existe no filesystem."""

    template_path: str
    project_file: str
    CODE: ClassVar[str] = "SYNESIS_E064"

    def to_diagnostic(self) -> str:
        return (
            f"Template '{self.template_path}' especificado em '{self.project_file}' nao encontrado.\n"
            f"  Verifique se o caminho esta correto e relativo ao diretorio do projeto.\n"
            f"  Ou crie o arquivo de template no local especificado."
        )

    def to_cli_line(self) -> str:
        return f"Template `{self.template_path}` nao encontrado"


@dataclass(frozen=True)
class InvalidProjectFile(ValidationError):
    """Arquivo .synp contem erros de sintaxe e nao pode ser parseado."""

    project_file: str
    parse_error: str
    CODE: ClassVar[str] = "SYNESIS_E064"
    DEFAULT_SEVERITY: ClassVar[ErrorSeverity] = ErrorSeverity.WARNING

    def to_diagnostic(self) -> str:
        return (
            f"Arquivo de projeto '{self.project_file}' contem erros de sintaxe:\n"
            f"  {self.parse_error}\n"
            f"  Validacao semantica desativada ate que o arquivo seja corrigido."
        )

    def to_cli_line(self) -> str:
        return f"`{self.project_file}` tem erro de sintaxe: {self.parse_error}"


@dataclass(frozen=True)
class MissingRequiredField(ValidationError):
    """Campo REQUIRED ausente."""

    field_name: str
    block_type: str
    CODE: ClassVar[str] = "SYNESIS_E020"

    def to_diagnostic(self) -> str:
        return (
            f"O campo `{self.field_name}` e obrigatorio neste bloco {self.block_type},\n"
            f"  mas nao foi encontrado.\n"
            f"  Adicione a linha `{self.field_name}: <valor>` ao bloco antes de\n"
            f"  `END {self.block_type}`."
        )

    def to_cli_line(self) -> str:
        return f"Campo obrigatorio `{self.field_name}` ausente no bloco {self.block_type}"


@dataclass(frozen=True)
class ForbiddenFieldPresent(ValidationError):
    """Campo FORBIDDEN presente."""

    field_name: str
    block_type: str
    CODE: ClassVar[str] = "SYNESIS_E021"

    def to_diagnostic(self) -> str:
        return (
            f"Campo '{self.field_name}' e proibido no bloco {self.block_type}.\n"
            f"  Remova esta linha do arquivo."
        )

    def to_cli_line(self) -> str:
        return f"Campo proibido `{self.field_name}` no bloco {self.block_type} — remova esta linha"


@dataclass(frozen=True)
class UnknownFieldName(ValidationError):
    """Campo usado no arquivo nao esta definido no template."""

    field_name: str
    block_type: str
    CODE: ClassVar[str] = "SYNESIS_E022"

    def to_diagnostic(self) -> str:
        return (
            f"Campo '{self.field_name}' nao definido no template para bloco {self.block_type}.\n"
            f"  Defina um FIELD '{self.field_name}' no template ou ajuste o nome do campo."
        )

    def to_cli_line(self) -> str:
        return f"Campo desconhecido `{self.field_name}` no bloco {self.block_type}"


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
            f"Os campos `{bundle_str}` formam um pacote indivisivel (bundle) neste bloco\n"
            f"  — eles representam informacao composta e devem sempre aparecer juntos.\n"
            f"  Um ou mais campos do pacote estao ausentes: `{missing_str}`.\n"
            f"  Adicione os campos faltantes ou remova todos os campos do pacote.\n"
            f"  Um bundle parcial nao e valido."
        )

    def to_cli_line(self) -> str:
        missing = set(self.bundle_fields) - self.present_fields
        missing_str = ", ".join(f"`{f}`" for f in sorted(missing))
        bundle_str = ", ".join(self.bundle_fields)
        return f"Bundle ({bundle_str}): campos ausentes {missing_str}"


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
            f"BUNDLE ({bundle_str}) tem contagens diferentes: {count_str}\n"
            f"  Todos os campos do bundle devem aparecer o mesmo numero de vezes.\n"
            f"  Adicione ou remova entradas para igualar as contagens."
        )

    def to_cli_line(self) -> str:
        bundle_str = ", ".join(self.bundle_fields)
        count_str = ", ".join(f"{k}={v}" for k, v in self.counts.items())
        return f"Bundle ({bundle_str}) com contagens desiguais: {count_str}"


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
            f"O valor `{self.value}` nao e reconhecido para o campo `{self.field_name}`.\n"
            f"  Este campo aceita apenas valores de uma lista fechada.\n"
        )
        suggestions = get_close_matches(self.value, self.valid_values, n=1, cutoff=0.6)
        if suggestions:
            msg += f"  Voce quis dizer `{suggestions[0]}`?\n"
        MAX_SHOWN = 8
        if len(self.valid_values) <= MAX_SHOWN:
            valid_str = ", ".join(f"`{v}`" for v in self.valid_values)
            msg += f"  Valores disponiveis: {valid_str}."
        else:
            shown = ", ".join(f"`{v}`" for v in self.valid_values[:MAX_SHOWN])
            msg += f"  Valores disponiveis: {shown} — e outros {len(self.valid_values) - MAX_SHOWN}. Consulte o template para a lista completa."
        return msg

    def to_cli_line(self) -> str:
        from difflib import get_close_matches
        suggestion = get_close_matches(self.value, self.valid_values, n=1, cutoff=0.6)
        suffix = f". Sugestao de correcao -> `{suggestion[0]}`" if suggestion else ""
        return f"Valor `{self.value}` invalido para `{self.field_name}`{suffix}"


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
                f"A data informada no campo `{self.field_name}` nao esta em um formato\n"
                f"  reconhecido. O formato aceito e `AAAA-MM-DD`.\n"
                f"  Por exemplo: `2024-03-15` para 15 de marco de 2024."
            )
        # Erro 30: número em campo de texto
        if self.expected in {"string", "text"} and self.actual in {"int", "float"}:
            return (
                f"O campo `{self.field_name}` espera texto, mas recebeu um valor que\n"
                f"  parece ser apenas um numero. Campos de texto e citacao precisam\n"
                f"  de conteudo textual.\n"
                f"  Se o numero faz parte de uma citacao ou nota, escreva-o como parte\n"
                f"  de uma frase. Se for um dado numerico, verifique se o campo correto\n"
                f"  nao seria do tipo SCALE ou ORDERED."
            )
        # Caso genérico (chain, outros)
        return (
            f"Tipo invalido para o campo `{self.field_name}`.\n"
            f"  Esperado: {self.expected}\n"
            f"  Encontrado: {self.actual}"
        )

    def to_cli_line(self) -> str:
        if self.expected == "date":
            return f"Data invalida em `{self.field_name}` — use formato AAAA-MM-DD"
        if self.expected in {"string", "text"} and self.actual in {"int", "float"}:
            return f"Campo `{self.field_name}` espera texto, recebeu numero"
        return f"Tipo invalido em `{self.field_name}`: esperado {self.expected}, encontrado {self.actual}"


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
            f"O valor `{self.value}` nao e valido para o campo `{self.field_name}`.\n"
            f"  Este campo usa uma escala ordenada com opcoes especificas.\n"
        )
        if isinstance(self.value, str):
            suggestions = get_close_matches(self.value, self.valid_options, n=1, cutoff=0.6)
            if suggestions:
                msg += f"  Voce quis dizer `{suggestions[0]}`?\n"
        MAX_SHOWN = 8
        if len(self.valid_options) <= MAX_SHOWN:
            opts_str = ", ".join(f"`{v}`" for v in self.valid_options)
            msg += f"  Opcoes disponiveis: {opts_str}.\n"
        else:
            shown = ", ".join(f"`{v}`" for v in self.valid_options[:MAX_SHOWN])
            msg += f"  Opcoes disponiveis: {shown} — e outras {len(self.valid_options) - MAX_SHOWN}. Consulte o template.\n"
        msg += f"  Voce pode usar o rotulo textual ou o numero de posicao na escala."
        return msg

    def to_cli_line(self) -> str:
        from difflib import get_close_matches
        if isinstance(self.value, str):
            suggestion = get_close_matches(self.value, self.valid_options, n=1, cutoff=0.6)
            suffix = f". Sugestao de correcao -> `{suggestion[0]}`" if suggestion else ""
        else:
            suffix = ""
        return f"Valor `{self.value}` invalido para `{self.field_name}` (ordered){suffix}"


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
            f"O valor `{self.value}` esta fora do intervalo permitido para o campo\n"
            f"  `{self.field_name}`. Este campo aceita apenas valores entre\n"
            f"  `{self.min_value}` e `{self.max_value}`.\n"
            f"  Corrija o valor para que fique dentro desse intervalo."
        )

    def to_cli_line(self) -> str:
        return f"Valor `{self.value}` fora do intervalo [{self.min_value}..{self.max_value}] no campo `{self.field_name}`"


@dataclass(frozen=True)
class ChainArityViolation(ValidationError):
    """Violacao de ARITY em cadeia causal."""

    expected: str
    found: int
    CODE: ClassVar[str] = "SYNESIS_E007"

    def to_diagnostic(self) -> str:
        return (
            f"Esta cadeia tem poucos elementos. O template exige `{self.expected}` conceitos,\n"
            f"  mas foram encontrados apenas `{self.found}`.\n"
            f"  Uma cadeia precisa conectar pelo menos dois conceitos com `->`.\n"
            f"  Acrescente os elementos faltantes ate satisfazer o requisito minimo."
        )

    def to_cli_line(self) -> str:
        return f"Cadeia com {self.found} elemento(s), template exige {self.expected}"


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

        msg = f"A relacao `{self.relation}` usada nesta cadeia nao esta declarada no\n"
        msg += f"  template para este campo.\n"

        if suggestion:
            msg += f"  Voce quis dizer `{suggestion}`?\n"

        if self.relation_descriptions:
            msg += "  Relacoes disponiveis:\n"
            for rel, desc in sorted(self.relation_descriptions.items()):
                msg += f"    {rel} - {desc}\n"
        else:
            valid_str = ", ".join(f"`{r}`" for r in sorted(self.valid_relations))
            msg += f"  Relacoes disponiveis: {valid_str}.\n"

        msg += "  Use uma das relacoes listadas ou peca ao coordenador do projeto\n"
        msg += "  que inclua a nova relacao no template."
        return msg

    def to_cli_line(self) -> str:
        suggestion = self._find_similar_relation()
        suffix = f". Sugestao de correcao -> `{suggestion}`" if suggestion else ""
        return f"Relacao `{self.relation}` nao declarada no template{suffix}"

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
            f"A estrutura desta cadeia esta incorreta: {par_problematico}\n"
            f"  Encontrado: {cadeia}\n"
            f"  Esperado:   [Conceito] -> [RELACAO] -> [Conceito]\n"
            f"  Em cadeias qualificadas, posicoes pares sao sempre tipos de relacao,\n"
            f"  nao conceitos. Revise a ordem dos elementos."
        )

    def to_cli_line(self) -> str:
        cadeia = " -> ".join(self.elements)
        return f"Cadeia qualificada com estrutura incorreta: {cadeia}"


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
            f"O campo '{self.field_name}' esta definido mais de uma vez no template.\n"
            f"  Nomes de campos devem ser unicos. Remova a definicao duplicada ou renomeie\n"
            f"  um dos campos se eles representam informacoes diferentes."
        )

    def to_cli_line(self) -> str:
        return f"Campo `{self.field_name}` definido mais de uma vez no template"


@dataclass(frozen=True)
class UndefinedFieldInScopeFields(ValidationError):
    """Campo listado em SCOPE FIELDS sem FIELD correspondente. (erros 39-41)"""

    field_name: str
    scope: str  # "SOURCE", "ITEM" ou "ONTOLOGY"
    CODE: ClassVar[str] = "SYNESIS_E039"

    def to_diagnostic(self) -> str:
        return (
            f"O campo '{self.field_name}' esta listado em `{self.scope} FIELDS`,\n"
            f"  mas nao ha uma definicao `FIELD` correspondente no template.\n"
            f"  Adicione ao template:\n"
            f"      FIELD {self.field_name} TYPE TEXT\n"
            f"          SCOPE {self.scope}\n"
            f"      END FIELD\n"
            f"  Este problema esta na definicao do template. Se voce nao e o autor\n"
            f"  do template, avise o coordenador do projeto."
        )

    def to_cli_line(self) -> str:
        return f"Campo `{self.field_name}` listado em `{self.scope} FIELDS` sem definicao FIELD"


@dataclass(frozen=True)
class OrphanFieldDefinition(ValidationError):
    """FIELD definido mas nao listado em nenhum SCOPE FIELDS. (erro 42)"""

    field_name: str
    scope: str
    CODE: ClassVar[str] = "SYNESIS_E042"
    DEFAULT_SEVERITY: ClassVar[ErrorSeverity] = ErrorSeverity.WARNING

    def to_diagnostic(self) -> str:
        return (
            f"O campo '{self.field_name}' esta definido no template, mas nao aparece\n"
            f"  em nenhum bloco `SOURCE FIELDS`, `ITEM FIELDS` ou `ONTOLOGY FIELDS`.\n"
            f"  Um campo definido mas nao listado nunca sera reconhecido nas anotacoes.\n"
            f"  Inclua `{self.field_name}` no bloco `{self.scope} FIELDS` correspondente\n"
            f"  ao seu escopo, ou remova a definicao se ela nao for necessaria."
        )

    def to_cli_line(self) -> str:
        return f"Campo `{self.field_name}` definido mas ausente em `{self.scope} FIELDS`"


@dataclass(frozen=True)
class SingleFieldBundle(ValidationError):
    """BUNDLE declarado com apenas um campo. (erro 18)"""

    bundle_fields: tuple
    CODE: ClassVar[str] = "SYNESIS_E018"

    def to_diagnostic(self) -> str:
        bundle_name = ", ".join(self.bundle_fields) if self.bundle_fields else "?"
        return (
            f"O bundle `{bundle_name}` no template foi declarado com apenas um campo.\n"
            f"  Um bundle precisa de pelo menos dois campos — ele existe para garantir\n"
            f"  que informacoes relacionadas aparecam sempre juntas.\n"
            f"  Este problema esta na definicao do template. Se voce nao e o autor\n"
            f"  do template, avise o coordenador do projeto.\n"
            f"  Adicione os demais campos ao bundle ou remova a declaracao BUNDLE,\n"
            f"  tornando o campo simplesmente REQUIRED ou OPTIONAL."
        )

    def to_cli_line(self) -> str:
        bundle_name = ", ".join(self.bundle_fields) if self.bundle_fields else "?"
        return f"Bundle `{bundle_name}` declarado com apenas um campo no template"


@dataclass(frozen=True)
class FieldScopeListMismatch(ValidationError):
    """Campo listado em SCOPE FIELDS cujo FIELD tem SCOPE diferente. (erro 6)"""

    field_name: str
    listed_scope: str
    actual_scope: str
    CODE: ClassVar[str] = "SYNESIS_E006"

    def to_diagnostic(self) -> str:
        return (
            f"O campo '{self.field_name}' esta listado em `{self.listed_scope} FIELDS`,\n"
            f"  mas sua definicao FIELD declara `SCOPE {self.actual_scope}`.\n"
            f"  Cada campo listado precisa ter sua propria definicao com o mesmo escopo.\n"
            f"  Corrija o escopo na definicao FIELD ou mova o campo para o bloco correto.\n"
            f"  Este problema esta na definicao do template. Se voce nao e o autor\n"
            f"  do template, avise o coordenador do projeto."
        )

    def to_cli_line(self) -> str:
        return f"Campo `{self.field_name}` listado em `{self.listed_scope} FIELDS` mas SCOPE declarado e {self.actual_scope}"


@dataclass(frozen=True)
class ChainWithoutArity(ValidationError):
    """TYPE CHAIN sem declaracao ARITY. (erro 47)"""

    field_name: str
    CODE: ClassVar[str] = "SYNESIS_E047"

    def to_diagnostic(self) -> str:
        return (
            f"O campo '{self.field_name}' e do tipo CHAIN, mas nao declara `ARITY`.\n"
            f"  Sem ARITY, o compilador nao pode verificar se as cadeias escritas pelos\n"
            f"  pesquisadores tem o numero minimo de conceitos exigidos.\n"
            f"  Adicione uma declaracao como `ARITY >= 2` para garantir que toda cadeia\n"
            f"  tenha ao menos dois conceitos conectados."
        )

    def to_cli_line(self) -> str:
        return f"Campo `{self.field_name}` (CHAIN) sem declaracao ARITY no template"


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
            f"O campo '{self.field_name}' declara `ARITY >= {self.arity}`, o que exige\n"
            f"  pelo menos {self.arity} conceitos por cadeia — mas apenas {self.n_relations}\n"
            f"  relacao(oes) esta(ao) definida(s) em `RELATIONS`. Para conectar {self.arity}\n"
            f"  conceitos em sequencia, sao necessarias pelo menos {arity_minus_1} relacoes.\n"
            f"  Adicione as relacoes faltantes ao bloco `RELATIONS` ou reduza o valor de `ARITY`."
        )

    def to_cli_line(self) -> str:
        return f"Campo `{self.field_name}`: ARITY >= {self.arity} exige mais relacoes que as {self.n_relations} declaradas"


@dataclass(frozen=True)
class OrderedWithoutValues(ValidationError):
    """TYPE ORDERED sem bloco VALUES. (erro 49)"""

    field_name: str
    CODE: ClassVar[str] = "SYNESIS_E049"

    def to_diagnostic(self) -> str:
        return (
            f"O campo '{self.field_name}' e do tipo ORDERED, mas nao define um bloco\n"
            f"  `VALUES` com as opcoes validas e sua ordem. Sem isso, nao ha como\n"
            f"  validar os valores inseridos nem apresentar a escala aos pesquisadores.\n"
            f"  Adicione um bloco `VALUES` listando as opcoes em ordem crescente."
        )

    def to_cli_line(self) -> str:
        return f"Campo `{self.field_name}` (ORDERED) sem bloco VALUES no template"


@dataclass(frozen=True)
class EnumeratedWithoutValues(ValidationError):
    """TYPE ENUMERATED sem bloco VALUES. (erro 50)"""

    field_name: str
    CODE: ClassVar[str] = "SYNESIS_E050"

    def to_diagnostic(self) -> str:
        return (
            f"O campo '{self.field_name}' e do tipo ENUMERATED, mas nao define um bloco\n"
            f"  `VALUES` com as opcoes validas. Sem isso, qualquer valor seria aceito,\n"
            f"  perdendo o controle sobre o vocabulario.\n"
            f"  Adicione um bloco `VALUES` listando todas as opcoes aceitas para este campo."
        )

    def to_cli_line(self) -> str:
        return f"Campo `{self.field_name}` (ENUMERATED) sem bloco VALUES no template"


@dataclass(frozen=True)
class ScaleWithoutFormat(ValidationError):
    """TYPE SCALE sem declaracao FORMAT. (erro 51)"""

    field_name: str
    CODE: ClassVar[str] = "SYNESIS_E051"

    def to_diagnostic(self) -> str:
        return (
            f"O campo '{self.field_name}' e do tipo SCALE, mas nao declara o intervalo\n"
            f"  numerico permitido. Sem o intervalo, o compilador nao pode verificar se\n"
            f"  os valores estao dentro da faixa esperada.\n"
            f"  Adicione uma declaracao como `FORMAT [0..10]` para definir o valor\n"
            f"  minimo e maximo aceitos."
        )

    def to_cli_line(self) -> str:
        return f"Campo `{self.field_name}` (SCALE) sem declaracao FORMAT no template"


@dataclass(frozen=True)
class InvalidFormatSyntax(ValidationError):
    """Sintaxe invalida na declaracao FORMAT de campo SCALE. (erro 52)"""

    field_name: str
    format_str: str
    CODE: ClassVar[str] = "SYNESIS_E052"

    def to_diagnostic(self) -> str:
        return (
            f"O intervalo declarado em `FORMAT` para o campo '{self.field_name}' nao\n"
            f"  esta no formato esperado: `{self.format_str}`\n"
            f"  O formato correto usa colchetes e dois pontos como separador: `[minimo..maximo]`.\n"
            f"  Exemplos validos: `[1..5]`, `[0..100]`, `[0.0..1.0]`."
        )

    def to_cli_line(self) -> str:
        return f"FORMAT invalido em `{self.field_name}`: `{self.format_str}` — use `[min..max]`"


@dataclass(frozen=True)
class InvalidArityOperator(ValidationError):
    """Operador invalido na declaracao ARITY. (erro 53)"""

    field_name: str
    operator: str
    CODE: ClassVar[str] = "SYNESIS_E053"

    def to_diagnostic(self) -> str:
        return (
            f"A declaracao `ARITY` do campo '{self.field_name}' usa um operador\n"
            f"  nao reconhecido: `{self.operator}`.\n"
            f"  Os operadores validos sao: `>=`, `>`, `<=`, `<`, `=`.\n"
            f"  Por exemplo: `ARITY >= 2` significa 'ao menos dois conceitos por cadeia'."
        )

    def to_cli_line(self) -> str:
        return f"Operador `{self.operator}` invalido em ARITY do campo `{self.field_name}` — use >=, >, <=, <, ="


@dataclass(frozen=True)
class FormatOnNonScale(ValidationError):
    """FORMAT declarado em campo que nao e TYPE SCALE. (erro 54)"""

    field_name: str
    field_type: str
    CODE: ClassVar[str] = "SYNESIS_E054"

    def to_diagnostic(self) -> str:
        return (
            f"O campo '{self.field_name}' declara `FORMAT`, mas seu tipo e `{self.field_type}`.\n"
            f"  A declaracao `FORMAT [min..max]` e exclusiva de campos do tipo SCALE.\n"
            f"  Este problema esta na definicao do template.\n"
            f"  Remova a declaracao `FORMAT` ou altere o tipo do campo para `SCALE`."
        )

    def to_cli_line(self) -> str:
        return f"FORMAT declarado em `{self.field_name}` (tipo {self.field_type}) — FORMAT e exclusivo de SCALE"


@dataclass(frozen=True)
class ArityOnNonChain(ValidationError):
    """ARITY declarado em campo que nao e TYPE CHAIN. (erro 55)"""

    field_name: str
    field_type: str
    CODE: ClassVar[str] = "SYNESIS_E055"

    def to_diagnostic(self) -> str:
        return (
            f"O campo '{self.field_name}' declara `ARITY`, mas seu tipo e `{self.field_type}`.\n"
            f"  A declaracao `ARITY` e exclusiva de campos do tipo CHAIN.\n"
            f"  Este problema esta na definicao do template.\n"
            f"  Remova a declaracao `ARITY` ou altere o tipo do campo para `CHAIN`."
        )

    def to_cli_line(self) -> str:
        return f"ARITY declarado em `{self.field_name}` (tipo {self.field_type}) — ARITY e exclusivo de CHAIN"


@dataclass(frozen=True)
class RelationsOnNonChain(ValidationError):
    """RELATIONS definido em campo que nao e TYPE CHAIN. (erro 56)"""

    field_name: str
    field_type: str
    CODE: ClassVar[str] = "SYNESIS_E056"

    def to_diagnostic(self) -> str:
        return (
            f"O campo '{self.field_name}' define um bloco `RELATIONS`, mas seu tipo e\n"
            f"  `{self.field_type}`, nao `CHAIN`. Blocos `RELATIONS` descrevem os tipos\n"
            f"  de vinculo possiveis entre conceitos — eles so fazem sentido em campos\n"
            f"  do tipo CHAIN. Remova o bloco `RELATIONS` ou altere o tipo para `CHAIN`."
        )

    def to_cli_line(self) -> str:
        return f"RELATIONS declarado em `{self.field_name}` (tipo {self.field_type}) — RELATIONS e exclusivo de CHAIN"


@dataclass(frozen=True)
class DuplicateScopeBlock(ValidationError):
    """Dois ou mais blocos SCOPE FIELDS no mesmo template. (erro 57)"""

    scope: str
    CODE: ClassVar[str] = "SYNESIS_E057"

    def to_diagnostic(self) -> str:
        return (
            f"O template contem mais de um bloco `{self.scope} FIELDS`. Apenas um bloco\n"
            f"  desse tipo e permitido por template — ter dois causaria ambiguidade sobre\n"
            f"  quais campos sao validos nos conceitos.\n"
            f"  Unifique todas as declaracoes em um unico bloco `{self.scope} FIELDS`."
        )

    def to_cli_line(self) -> str:
        return f"Bloco `{self.scope} FIELDS` declarado mais de uma vez no template"


@dataclass(frozen=True)
class ValueWithWhitespace(ValidationError):
    """Valor em bloco VALUES com espaco no inicio ou fim. (erro 58)"""

    field_name: str
    value: str
    CODE: ClassVar[str] = "SYNESIS_E058"

    def to_diagnostic(self) -> str:
        return (
            f"O valor `\"{self.value}\"` declarado no campo '{self.field_name}' contem\n"
            f"  espaco em branco no inicio ou no final. Esses espacos invisiveis fariam\n"
            f"  com que o valor nao fosse reconhecido quando usado nas anotacoes.\n"
            f"  Remova os espacos extras ao redor do valor na declaracao do template."
        )

    def to_cli_line(self) -> str:
        return f"Valor `\"{self.value}\"` em `{self.field_name}` tem espaco no inicio ou fim"


@dataclass(frozen=True)
class DuplicateValue(ValidationError):
    """Valores duplicados dentro de um mesmo bloco VALUES. (erro 59)"""

    field_name: str
    value: str
    CODE: ClassVar[str] = "SYNESIS_E059"

    def to_diagnostic(self) -> str:
        return (
            f"O campo '{self.field_name}' tem o valor `{self.value}` declarado mais de\n"
            f"  uma vez no bloco `VALUES`. Valores duplicados causam ambiguidade e podem\n"
            f"  gerar resultados inconsistentes na exportacao.\n"
            f"  Remova a entrada duplicada."
        )

    def to_cli_line(self) -> str:
        return f"Valor `{self.value}` duplicado no bloco VALUES de `{self.field_name}`"


# ---------------------------------------------------------------------------
# Erros de Validação Semântica de Anotações (Fase 2 — erros 5, 8, 9, 23, 26, 31-33)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OntologyWithoutTemplateFields(ValidationError):
    """ONTOLOGY presente mas template nao declara ONTOLOGY FIELDS. (erro 5)"""

    CODE: ClassVar[str] = "SYNESIS_E005"

    def to_diagnostic(self) -> str:
        return (
            f"O projeto contem blocos ONTOLOGY, mas o template nao declara nenhum\n"
            f"  campo em `ONTOLOGY FIELDS`. Sem essa configuracao, os campos dos\n"
            f"  conceitos nao podem ser validados.\n"
            f"  Este problema esta na definicao do template. Se voce nao e o autor\n"
            f"  do template, avise o coordenador do projeto.\n"
            f"  Para corrigir, adicione ao template:\n"
            f"      ONTOLOGY FIELDS\n"
            f"          REQUIRED nome_do_campo\n"
            f"      END ONTOLOGY FIELDS"
        )

    def to_cli_line(self) -> str:
        return "Projeto tem blocos ONTOLOGY mas template nao declara ONTOLOGY FIELDS"


@dataclass(frozen=True)
class QualifiedChainWithoutRelations(ValidationError):
    """Chain qualificada usada mas template nao define RELATIONS. (erro 8)"""

    field_name: str
    CODE: ClassVar[str] = "SYNESIS_E008"

    def to_diagnostic(self) -> str:
        return (
            f"Esta cadeia usa relacoes nomeadas (ex: `Conceito -> RELACAO -> Conceito`),\n"
            f"  mas o template nao define nenhum bloco `RELATIONS` para o campo\n"
            f"  `{self.field_name}`.\n"
            f"  Se o template usa cadeias simples, reescreva a cadeia sem relacoes:\n"
            f"  `Conceito -> Conceito`. Se deseja usar relacoes nomeadas, peca ao\n"
            f"  coordenador do projeto que adicione um bloco `RELATIONS` ao template."
        )

    def to_cli_line(self) -> str:
        return f"Cadeia com relacoes nomeadas em `{self.field_name}`, mas template nao define RELATIONS"


@dataclass(frozen=True)
class SimpleChainWithRelationsRequired(ValidationError):
    """Chain simples usada mas template exige RELATIONS. (erro 9)"""

    field_name: str
    valid_relations: list[str]
    CODE: ClassVar[str] = "SYNESIS_E009"

    def to_diagnostic(self) -> str:
        rels = ", ".join(f"`{r}`" for r in self.valid_relations)
        return (
            f"O template exige que as cadeias usem relacoes nomeadas, mas esta cadeia\n"
            f"  foi escrita sem relacoes para o campo `{self.field_name}`.\n"
            f"  Relacoes disponiveis: {rels}.\n"
            f"  Reescreva a cadeia no formato: `Conceito -> RELACAO -> Conceito`."
        )

    def to_cli_line(self) -> str:
        return f"Cadeia simples em `{self.field_name}` mas template exige relacoes nomeadas"


@dataclass(frozen=True)
class EmptyItemBlock(ValidationError):
    """Bloco ITEM sem nenhum campo. (erro 23)"""

    CODE: ClassVar[str] = "SYNESIS_E023"

    def to_diagnostic(self) -> str:
        return (
            f"Este bloco ITEM esta vazio — nao contem nenhum campo com conteudo.\n"
            f"  Um ITEM sem campos nao representa nenhuma unidade de analise.\n"
            f"  Adicione os campos exigidos pelo template ou remova o bloco se ele\n"
            f"  foi criado por engano."
        )

    def to_cli_line(self) -> str:
        return "Bloco ITEM vazio — sem nenhum campo"


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
            f"O valor `{self.value}` tem casas decimais, mas o campo `{self.field_name}`\n"
            f"  foi declarado com um intervalo de inteiros (`FORMAT [{int(self.min_val)}..{int(self.max_val)}]`).\n"
            f"  Este campo aceita apenas numeros inteiros.\n"
            f"  Use um valor inteiro dentro do intervalo, ou peca ao coordenador do\n"
            f"  projeto que ajuste o FORMAT para aceitar decimais (ex: `FORMAT [{self.min_val}..{self.max_val}]`)."
        )

    def to_cli_line(self) -> str:
        return f"Valor decimal `{self.value}` em `{self.field_name}` — campo aceita apenas inteiros [{int(self.min_val)}..{int(self.max_val)}]"


@dataclass(frozen=True)
class DuplicateCodeInField(ValidationError):
    """Mesmo codigo repetido na mesma ocorrencia de campo CODE. (erro 31)"""

    field_name: str
    code: str
    CODE: ClassVar[str] = "SYNESIS_W031"
    DEFAULT_SEVERITY: ClassVar[ErrorSeverity] = ErrorSeverity.WARNING

    def to_diagnostic(self) -> str:
        return (
            f"O codigo `{self.code}` aparece mais de uma vez no campo `{self.field_name}`\n"
            f"  neste bloco. Codigos repetidos nao acrescentam informacao e podem\n"
            f"  distorcer a contagem nas exportacoes.\n"
            f"  Remova a ocorrencia duplicada e mantenha o codigo apenas uma vez."
        )

    def to_cli_line(self) -> str:
        return f"Codigo `{self.code}` duplicado no campo `{self.field_name}`"


@dataclass(frozen=True)
class TopicWithSpaces(ValidationError):
    """Campo TOPIC recebendo valor com espacos. (erro 32)"""

    field_name: str
    value: str
    CODE: ClassVar[str] = "SYNESIS_E032"

    def to_diagnostic(self) -> str:
        suggestion = self.value.replace(" ", "_")
        return (
            f"O valor `{self.value}` do campo `{self.field_name}` contem espacos, o que\n"
            f"  nao e permitido para campos do tipo TOPIC. Espacos sao interpretados como\n"
            f"  separadores e causariam ambiguidade na hierarquia ontologica.\n"
            f"  Use underscore no lugar de espacos. Por exemplo: `{suggestion}`."
        )

    def to_cli_line(self) -> str:
        suggestion = self.value.replace(" ", "_")
        return f"Valor `{self.value}` em `{self.field_name}` contem espacos. Sugestao de correcao -> `{suggestion}`"


@dataclass(frozen=True)
class InvalidIdentifierCharacter(ValidationError):
    """Nome de codigo ou conceito com caracteres invalidos. (erro 33)"""

    name: str
    invalid_char: str
    CODE: ClassVar[str] = "SYNESIS_E033"

    def to_diagnostic(self) -> str:
        suggestion = self.name.replace(self.invalid_char, "_")
        return (
            f"O nome `{self.name}` contem o caractere invalido `{self.invalid_char}`,\n"
            f"  que nao e permitido em identificadores Synesis. Identificadores aceitam\n"
            f"  apenas letras, numeros, underscore e hifen, e devem comecar com uma letra.\n"
            f"  Por exemplo: use `{suggestion}` em vez de `{self.name}`."
        )

    def to_cli_line(self) -> str:
        return f"Identificador `{self.name}` contem caractere invalido `{self.invalid_char}`"


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
            f"Os elementos desta cadeia nao estao separados pelo operador `->`.\n"
            f"  Sem a seta, o compilador nao consegue identificar onde um elemento\n"
            f"  termina e o proximo comeca.\n"
            f"  Valor encontrado: `{self.raw_value}`\n"
            f"  Reescreva conectando os elementos com `->`, por exemplo:\n"
            f"  `ConceitoA -> ConceitoB` ou `ConceitoA -> RELACAO -> ConceitoB`"
        )

    def to_cli_line(self) -> str:
        return f"Cadeia sem operador `->`: `{self.raw_value}`"


@dataclass(frozen=True)
class ConceptNameMatchesRelation(ValidationError):
    """Conceito em posicao de codigo com nome identico a uma relacao. (erro 14)"""

    name: str
    field_name: str
    CODE: ClassVar[str] = "SYNESIS_E014"

    def to_diagnostic(self) -> str:
        return (
            f"O elemento `{self.name}` aparece nesta cadeia em posicao de conceito,\n"
            f"  mas tambem esta declarado como relacao no template para o campo\n"
            f"  `{self.field_name}`. Essa ambiguidade impede o compilador de\n"
            f"  determinar o papel do elemento na cadeia.\n"
            f"  Renomeie o conceito na ontologia para que seja distinto dos nomes\n"
            f"  de relacao, ou renomeie a relacao no template."
        )

    def to_cli_line(self) -> str:
        return f"`{self.name}` e ambiguo: conceito e relacao ao mesmo tempo em `{self.field_name}`"


@dataclass(frozen=True)
class ConceptWithSpaces(ValidationError):
    """Conceito em chain contendo espacos. (erro 15)"""

    concept: str
    CODE: ClassVar[str] = "SYNESIS_E015"

    def to_diagnostic(self) -> str:
        suggestion = self.concept.replace(" ", "_")
        return (
            f"O elemento `{self.concept}` contem espacos, o que nao e permitido\n"
            f"  em nomes de conceitos. O compilador interpreta cada espaco como\n"
            f"  separador entre elementos distintos da cadeia.\n"
            f"  Substitua os espacos por underscore: `{suggestion}`."
        )

    def to_cli_line(self) -> str:
        suggestion = self.concept.replace(" ", "_")
        return f"Conceito `{self.concept}` contem espacos. Sugestao de correcao -> `{suggestion}`"


@dataclass(frozen=True)
class DuplicateOntologyConcept(ValidationError):
    """Dois blocos ONTOLOGY com o mesmo nome de conceito. (erro 68)"""

    concept_name: str
    file_a: str
    file_b: str
    CODE: ClassVar[str] = "SYNESIS_E068"

    def to_diagnostic(self) -> str:
        return (
            f"O conceito `{self.concept_name}` esta definido mais de uma vez na\n"
            f"  ontologia do projeto:\n"
            f"  - {self.file_a}\n"
            f"  - {self.file_b}\n"
            f"  Cada conceito deve ter um nome unico em todo o projeto. Verifique\n"
            f"  se os dois blocos representam o mesmo conceito — se sim, unifique-os.\n"
            f"  Se nao, renomeie um deles para que os nomes sejam distintos."
        )

    def to_cli_line(self) -> str:
        return f"Conceito `{self.concept_name}` duplicado em {self.file_a} e {self.file_b}"


@dataclass(frozen=True)
class DuplicateSourceBibref(ValidationError):
    """Mesmo @bibref declarado em dois blocos SOURCE no mesmo arquivo. (erro 70)"""

    bibref: str
    filename: str
    CODE: ClassVar[str] = "SYNESIS_E070"

    def to_diagnostic(self) -> str:
        return (
            f"A referencia `@{self.bibref}` aparece em dois blocos SOURCE diferentes\n"
            f"  no arquivo `{self.filename}`. Cada referencia bibliografica pode ter\n"
            f"  apenas um bloco SOURCE por arquivo.\n"
            f"  Unifique os dois blocos SOURCE em um unico, ou distribua as anotacoes\n"
            f"  em arquivos `.syn` separados."
        )

    def to_cli_line(self) -> str:
        return f"SOURCE `@{self.bibref}` duplicado neste arquivo"


@dataclass(frozen=True)
class DuplicateOntologyDescription(ValidationError):
    """Dois blocos ONTOLOGY com description identica. (erro 71)"""

    concept_a: str
    concept_b: str
    CODE: ClassVar[str] = "SYNESIS_W071"
    DEFAULT_SEVERITY: ClassVar[ErrorSeverity] = ErrorSeverity.WARNING

    def to_diagnostic(self) -> str:
        return (
            f"Os conceitos `{self.concept_a}` e `{self.concept_b}` tem exatamente\n"
            f"  a mesma descricao. Isso geralmente indica um erro de copia — dois\n"
            f"  conceitos distintos nao devem ter definicoes identicas.\n"
            f"  Revise as definicoes e diferencie as descricoes, ou verifique se os\n"
            f"  dois conceitos deveriam ser um unico."
        )

    def to_cli_line(self) -> str:
        return f"Conceitos `{self.concept_a}` e `{self.concept_b}` tem descricoes identicas"


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
            f"O arquivo `{self.filename}` (extensao `.syn`) existe no diretorio do projeto\n"
            f"  mas nao esta referenciado em nenhum bloco INCLUDE ANNOTATIONS no `.synp`.\n"
            f"  Sem essa declaracao, o compilador ignora o arquivo e as anotacoes nele\n"
            f"  contidas nao serao carregadas nem validadas.\n"
            f"  Adicione ao arquivo de projeto:\n"
            f"    INCLUDE ANNOTATIONS \"{self.filename}\""
        )

    def to_cli_line(self) -> str:
        return f"Arquivo `{self.filename}` nao incluido em INCLUDE ANNOTATIONS no .synp"


@dataclass(frozen=True)
class MissingOntologyInclude(ValidationError):
    """Arquivo .syno no diretorio do projeto nao referenciado em INCLUDE ONTOLOGY. (erro 62)"""

    filename: str
    CODE: ClassVar[str] = "SYNESIS_E062"

    def to_diagnostic(self) -> str:
        return (
            f"O arquivo `{self.filename}` (extensao `.syno`) existe no diretorio do projeto\n"
            f"  mas nao esta referenciado em nenhum bloco INCLUDE ONTOLOGY no `.synp`.\n"
            f"  Sem essa declaracao, a ontologia nao sera carregada e os codigos definidos\n"
            f"  nela nao poderao ser validados.\n"
            f"  Adicione ao arquivo de projeto:\n"
            f"    INCLUDE ONTOLOGY \"{self.filename}\""
        )

    def to_cli_line(self) -> str:
        return f"Arquivo `{self.filename}` nao incluido em INCLUDE ONTOLOGY no .synp"


@dataclass(frozen=True)
class MissingBibliographyFile(ValidationError):
    """Arquivo .bib declarado no projeto nao encontrado no caminho indicado. (erro 63)"""

    filename: str
    CODE: ClassVar[str] = "SYNESIS_E063"

    def to_diagnostic(self) -> str:
        return (
            f"O arquivo de referencias bibliograficas `{self.filename}` declarado no\n"
            f"  projeto nao foi encontrado. Sem ele, nenhuma referencia `@bibref` pode\n"
            f"  ser validada.\n"
            f"  Verifique se o arquivo existe e se o caminho esta correto. O caminho\n"
            f"  deve ser relativo a pasta onde esta o arquivo de projeto (`.synp`)."
        )

    def to_cli_line(self) -> str:
        return f"Arquivo de referencias `{self.filename}` declarado no projeto nao encontrado"


@dataclass(frozen=True)
class MalformedBibliographyEntry(ValidationError):
    """Entrada em arquivo .bib nao esta em formato BibTeX valido. (erro 72)"""

    filename: str
    entry_key: str
    CODE: ClassVar[str] = "SYNESIS_E072"

    def to_diagnostic(self) -> str:
        return (
            f"A entrada `@{self.entry_key}` no arquivo de referencias `{self.filename}`\n"
            f"  nao esta em formato BibTeX valido e foi ignorada pelo compilador. Por\n"
            f"  isso, qualquer `@bibref` que aponte para ela sera reportada como nao\n"
            f"  encontrada.\n"
            f"  Uma entrada BibTeX valida tem tres partes: um tipo, a chave de citacao\n"
            f"  entre chaves, e campos separados por virgula usando `=`:\n"
            f"    @book{{{self.entry_key},\n"
            f"        title = {{Titulo da obra}},\n"
            f"        year = {{2024}}\n"
            f"    }}\n"
            f"  Verifique se a entrada comeca com um tipo (@book, @article, @misc...),\n"
            f"  se a chave vem entre chaves `{{ }}`, e se cada campo usa `=` (e nao `:`)."
        )

    def to_cli_line(self) -> str:
        return (
            f"Entrada `@{self.entry_key}` em `{self.filename}` nao esta em "
            f"formato BibTeX valido"
        )


@dataclass(frozen=True)
class MissingTemplateDeclaration(ValidationError):
    """Bloco PROJECT sem declaracao TEMPLATE. (erro 65)"""

    CODE: ClassVar[str] = "SYNESIS_E065"

    def to_diagnostic(self) -> str:
        return (
            f"O arquivo de projeto nao declara nenhum template. O template e obrigatorio\n"
            f"  — ele define as regras de validacao para todas as anotacoes do projeto.\n"
            f"  Sem ele, o compilador nao pode verificar se as anotacoes estao corretas.\n"
            f"  Adicione ao bloco PROJECT:\n"
            f"    TEMPLATE \"nome_do_arquivo.synt\""
        )

    def to_cli_line(self) -> str:
        return "Bloco PROJECT sem declaracao TEMPLATE"


@dataclass(frozen=True)
class DuplicateProjectBlock(ValidationError):
    """Dois blocos PROJECT no mesmo arquivo .synp. (erro 66)"""

    CODE: ClassVar[str] = "SYNESIS_E066"

    def to_diagnostic(self) -> str:
        return (
            f"Este arquivo de projeto contem dois blocos PROJECT. Apenas um bloco\n"
            f"  PROJECT e permitido por arquivo — o compilador nao saberia qual dos\n"
            f"  dois usar como ponto de entrada.\n"
            f"  Remova o bloco duplicado ou separe os projetos em arquivos `.synp` distintos."
        )

    def to_cli_line(self) -> str:
        return "Dois blocos PROJECT no mesmo .synp — remova o duplicado"


@dataclass(frozen=True)
class ModifiedBeforeCreated(ValidationError):
    """Data MODIFIED anterior a data CREATED no bloco METADATA. (erro 67)"""

    modified: str
    created: str
    CODE: ClassVar[str] = "SYNESIS_W067"
    DEFAULT_SEVERITY: ClassVar[ErrorSeverity] = ErrorSeverity.WARNING

    def to_diagnostic(self) -> str:
        return (
            f"A data de modificacao `{self.modified}` e anterior a data de criacao\n"
            f"  `{self.created}` declarada no bloco METADATA do projeto. Um projeto nao\n"
            f"  pode ter sido modificado antes de existir.\n"
            f"  Verifique as datas e corrija a que estiver incorreta. O formato esperado\n"
            f"  e `AAAA-MM-DD`."
        )

    def to_cli_line(self) -> str:
        return f"MODIFIED `{self.modified}` e anterior a CREATED `{self.created}` no METADATA"


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

    def _to_diagnostics_compact(self) -> str:
        """Versão enxuta: uma linha por erro; UndefinedCode agrupados por código."""
        from collections import defaultdict

        lines: list[str] = []

        # --- ERROS (todos compactos, uma linha cada) ---
        if self.errors:
            lines.append("=== ERROS ===")
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
            lines.append("=== AVISOS ===")

            # Outros warnings (compactos, uma linha cada)
            for warn in other_warnings:
                lines.append(f"[!] {warn.to_cli_line()}")

            # UndefinedCode agrupados por código, ordenados por frequência desc
            if undefined_code_counts:
                n_codes = len(undefined_code_counts)
                total_occ = sum(undefined_code_counts.values())
                header = (
                    f"[!] {n_codes} codigo(s) usados nas anotacoes sem definicao na ontologia"
                    f" ({total_occ} ocorrencia(s) no total):"
                )
                lines.append(header)
                max_name_len = max(len(c) for c in undefined_code_counts)
                for code, count in sorted(
                    undefined_code_counts.items(), key=lambda x: -x[1]
                ):
                    suffix = ""
                    if code in undefined_code_suggestions:
                        suffix = f"  (voce quis dizer `{undefined_code_suggestions[code][0]}`?)"
                    occ_label = "ocorrencia" if count == 1 else "ocorrencias"
                    lines.append(
                        f"    - {code.ljust(max_name_len)}  ({count} {occ_label}){suffix}"
                    )
                lines.append("")
                lines.append(
                    "Dica: execute `synesis-coder ontology` para gerar as definicoes automaticamente."
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
