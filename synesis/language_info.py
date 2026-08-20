"""
language_info.py - Descricao executavel da linguagem Synesis (Etapa 1)

Proposito:
    Responder "o que posso escrever num template?" a partir do PROPRIO
    compilador, sem tabela paralela. Todo o tooling existente (autocomplete,
    hover, validate-template) opera sobre um template que ja existe; este
    modulo cobre a lacuna de quem esta ESCREVENDO um.

Como funciona (sondagem):
    Para cada combinacao (tipo de campo, propriedade), monta um template
    minimo em memoria, compila e le o codigo de erro emitido:
      - erro sem a propriedade  -> propriedade OBRIGATORIA para o tipo
      - erro com a propriedade  -> propriedade PROIBIDA no tipo
      - nenhum erro             -> propriedade PERMITIDA

    A matriz e portanto CONSEQUENCIA OBSERVADA do validador, nunca uma copia
    dele. Se uma regra mudar em template_loader.py, a resposta muda junto.

Fronteira fixo/derivado (respeitar em revisao de codigo):
    FIXO     - o andaime dos templates de sondagem (_SKELETON) e os trechos
               sintaticos de cada propriedade (_PROPERTY_SNIPPETS): sao o
               minimo para o compilador aceitar um template.
    DERIVADO - a lista de tipos (enum FieldType), a lista de escopos (enum
               Scope), a classificacao obrigatoria/permitida/proibida
               (codigos de erro) e o texto explicativo (to_diagnostic()).
               NADA disso pode ser escrito a mao.

Custo medido: ~36 ms para um tipo, ~57 ms para a matriz completa. Barato o
bastante para rodar sob demanda — sem cache, sem arquivo gerado, sem I/O.

Escopo desta etapa:
    Somente conteudo DERIVADO. Exemplos minimos, orientacoes de uso e titulos
    pedagogicos sao conteudo autoral e ficam para a Etapa 2. Ver
    synesis-planning/synesis/estudo_help_e_snippets.md, secao 6.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

from synesis.ast.nodes import FieldType, Scope

# --------------------------------------------------------------------------
# Andaime de sondagem (FIXO — ver docstring do modulo)
# --------------------------------------------------------------------------

# Menor template que o compilador aceita: um campo declarado no bloco de
# escopo e definido logo abaixo.
#
# O nome do campo aparece INTERPOLADO no texto de to_diagnostic() ("O campo
# 'nome_do_campo' e do tipo CHAIN..."), que este modulo repassa como conteudo
# didatico. Por isso e um placeholder legivel, e nao um identificador tecnico
# como "f" — reescrever a prosa depois seria fragil.
_PROBE_FIELD_NAME = "nome_do_campo"

_SKELETON = (
    "TEMPLATE probe\n"
    "{scope} FIELDS\n"
    f"    REQUIRED {_PROBE_FIELD_NAME}\n"
    "END {scope} FIELDS\n"
    f"FIELD {_PROBE_FIELD_NAME} TYPE {{field_type}}\n"
    "    SCOPE {scope}\n"
    "{extra}"
    "END FIELD\n"
)

# Um exemplo sintaticamente valido de cada propriedade. O conteudo e
# irrelevante — importa apenas que o parser aceite a construcao, para que o
# validador possa opinar sobre ela.
_PROPERTY_SNIPPETS: Dict[str, str] = {
    "ARITY": "    ARITY >= 2\n",
    "FORMAT": "    FORMAT [0..3]\n",
    "RELATIONS": (
        "    RELATIONS\n"
        "        RELACAO_A: descricao\n"
        "        RELACAO_B: descricao\n"
        "    END RELATIONS\n"
    ),
    # Sem prefixo `[N]`: e a forma valida em ENUMERATED e a unica que serve de
    # sonda neutra. ORDERED exige o indice e usa a variante em
    # _PROPERTY_SNIPPETS_BY_TYPE (ver _snippet_for).
    "VALUES": (
        "    VALUES\n"
        "        rotulo_um: descricao\n"
        "        rotulo_dois: descricao\n"
        "    END VALUES\n"
    ),
    "DESCRIPTION": "    DESCRIPTION texto explicativo do campo\n",
    "GUIDELINES": (
        "    GUIDELINES\n"
        "        orientacao de preenchimento\n"
        "    END GUIDELINES\n"
    ),
    "CONTEXT FROM DATASET": '    CONTEXT FROM DATASET "secao"\n',
}

# Modificadores de ligacao multiprojeto. Sondados a parte porque sua validade
# depende do ESCOPO (SOURCE), nao do tipo do campo.
_LINKAGE_SNIPPETS: Dict[str, str] = {
    "IDENTIFIES": "    IDENTIFIES entidade\n",
    "REFERS TO": "    REFERS TO entidade\n",
}


class Requirement(Enum):
    """Como uma propriedade se relaciona com um tipo de campo."""

    REQUIRED = "required"
    ALLOWED = "allowed"
    FORBIDDEN = "forbidden"


@dataclass(frozen=True)
class PropertyInfo:
    """Situacao de uma propriedade para um tipo de campo (ou escopo)."""

    name: str
    requirement: Requirement
    #: Codigo do erro que o compilador emite quando a regra e violada
    #: (ausencia, se REQUIRED; presenca, se FORBIDDEN). None se ALLOWED.
    error_code: Optional[str] = None
    #: Texto didatico do proprio compilador (to_diagnostic()), quando ha erro
    #: associado. Mesma prosa que o pesquisador vera se errar.
    explanation: Optional[str] = None


@dataclass(frozen=True)
class FieldTypeInfo:
    """Descricao completa de um tipo de campo."""

    name: str
    properties: List[PropertyInfo]

    def _by(self, requirement: Requirement) -> List[PropertyInfo]:
        return [p for p in self.properties if p.requirement is requirement]

    @property
    def required(self) -> List[PropertyInfo]:
        return self._by(Requirement.REQUIRED)

    @property
    def allowed(self) -> List[PropertyInfo]:
        return self._by(Requirement.ALLOWED)

    @property
    def forbidden(self) -> List[PropertyInfo]:
        return self._by(Requirement.FORBIDDEN)


@dataclass(frozen=True)
class LanguageInfo:
    """Descricao derivada da linguagem: tipos, escopos e regras de ligacao."""

    field_types: List[FieldTypeInfo]
    scopes: List[str]
    #: escopo -> situacao de IDENTIFIES / REFERS TO naquele escopo
    linkage_by_scope: Dict[str, List[PropertyInfo]]

    def field_type(self, name: str) -> Optional[FieldTypeInfo]:
        wanted = name.strip().upper()
        return next((f for f in self.field_types if f.name == wanted), None)


# --------------------------------------------------------------------------
# Sondagem
# --------------------------------------------------------------------------

# Propriedades cuja FORMA depende do tipo do campo. `VALUES` e o unico caso:
# o prefixo `[N]` estabelece ordem, sendo obrigatorio em ORDERED (o indice e o
# dado gravado) e proibido em ENUMERATED (E087). Sondar ambos com a mesma forma
# faria a sonda reportar VALUES como proibido em um dos dois tipos.
_PROPERTY_SNIPPETS_BY_TYPE: Dict[str, Dict[str, str]] = {
    "ORDERED": {
        "VALUES": (
            "    VALUES\n"
            "        [1] rotulo_um: descricao\n"
            "        [2] rotulo_dois: descricao\n"
            "    END VALUES\n"
        ),
    },
}


def _snippet_for(field_type: str, prop_name: str, default: str) -> str:
    """Trecho de sondagem da propriedade, na forma valida para o tipo."""
    return _PROPERTY_SNIPPETS_BY_TYPE.get(field_type, {}).get(prop_name, default)


def _probe(field_type: str, scope: str = "ITEM", extra: str = "") -> List:
    """Compila um template minimo e devolve os erros de validacao.

    Import local: template_loader importa de varios pontos do compilador, e
    manter o import no topo criaria ciclo com quem venha a consumir este
    modulo (ex.: cli).
    """
    from synesis.parser.template_loader import (
        load_template_from_string,
        validate_template,
    )

    src = _SKELETON.format(field_type=field_type, scope=scope, extra=extra)
    try:
        template = load_template_from_string(src, "<language_info>")
    except Exception:
        # Construcao rejeitada ja no parse. Nao deveria ocorrer com os
        # trechos de _PROPERTY_SNIPPETS (todos sintaticamente validos), mas
        # falhar aqui nao deve derrubar a consulta de ajuda.
        return []
    return list(validate_template(template).errors)


def _diagnostic_of(error) -> Optional[str]:
    """Texto didatico do erro, quando disponivel."""
    to_diagnostic = getattr(error, "to_diagnostic", None)
    if to_diagnostic is None:
        return None
    try:
        text: str = to_diagnostic()
    except Exception:
        return None
    return text


def _classify(
    field_type: str, prop_name: str, snippet: str, baseline: List
) -> PropertyInfo:
    """Classifica uma propriedade para um tipo, comparando com a linha-base.

    `baseline` sao os erros do tipo SEM nenhuma propriedade extra — servem
    para isolar o efeito da propriedade sondada dos erros que o tipo ja
    apresenta por conta propria (ex.: CHAIN sem ARITY).
    """
    baseline_codes = {e.CODE for e in baseline}
    with_prop = [e for e in _probe(field_type, extra=snippet)
                 if e.CODE not in baseline_codes]

    if with_prop:
        return PropertyInfo(
            name=prop_name,
            requirement=Requirement.FORBIDDEN,
            error_code=with_prop[0].CODE,
            explanation=_diagnostic_of(with_prop[0]),
        )

    # A propriedade e aceita. Ela e obrigatoria se a sua ausencia (a
    # linha-base) produz um erro que ela resolve.
    resolved = [
        e for e in baseline
        if e.CODE not in {x.CODE for x in _probe(field_type, extra=snippet)}
    ]
    if resolved:
        return PropertyInfo(
            name=prop_name,
            requirement=Requirement.REQUIRED,
            error_code=resolved[0].CODE,
            explanation=_diagnostic_of(resolved[0]),
        )

    return PropertyInfo(name=prop_name, requirement=Requirement.ALLOWED)


def get_field_type_info(field_type: str) -> Optional[FieldTypeInfo]:
    """Descreve um tipo de campo. `None` se o tipo nao existir.

    Sonda apenas o tipo pedido (~36 ms), nao a matriz inteira.
    """
    wanted = field_type.strip().upper()
    if wanted not in {t.value for t in FieldType}:
        return None

    baseline = _probe(wanted)
    properties = [
        _classify(wanted, name, _snippet_for(wanted, name, snippet), baseline)
        for name, snippet in _PROPERTY_SNIPPETS.items()
    ]
    return FieldTypeInfo(name=wanted, properties=properties)


def get_linkage_info() -> Dict[str, List[PropertyInfo]]:
    """Situacao de IDENTIFIES / REFERS TO em cada escopo.

    Sondado por escopo (nao por tipo) porque a regra E078 depende do SCOPE.
    Usa TEXT como tipo neutro: nao tem propriedade obrigatoria propria, entao
    a linha-base fica limpa.
    """
    result: Dict[str, List[PropertyInfo]] = {}
    for scope in (s.value for s in Scope):
        baseline_codes = {e.CODE for e in _probe("TEXT", scope=scope)}
        entries: List[PropertyInfo] = []
        for name, snippet in _LINKAGE_SNIPPETS.items():
            new = [e for e in _probe("TEXT", scope=scope, extra=snippet)
                   if e.CODE not in baseline_codes]
            if new:
                entries.append(PropertyInfo(
                    name=name,
                    requirement=Requirement.FORBIDDEN,
                    error_code=new[0].CODE,
                    explanation=_diagnostic_of(new[0]),
                ))
            else:
                entries.append(PropertyInfo(name=name, requirement=Requirement.ALLOWED))
        result[scope] = entries
    return result


def get_language_info() -> LanguageInfo:
    """Descricao completa da linguagem (~57 ms). Todos os tipos e escopos."""
    return LanguageInfo(
        field_types=[
            info for t in FieldType
            if (info := get_field_type_info(t.value)) is not None
        ],
        scopes=[s.value for s in Scope],
        linkage_by_scope=get_linkage_info(),
    )


def field_type_names() -> List[str]:
    """Nomes dos tipos de campo, direto do enum (sem sondagem)."""
    return [t.value for t in FieldType]


# --------------------------------------------------------------------------
# Snippets para editores (VS Code)
# --------------------------------------------------------------------------

# Corpo sintatico de cada propriedade obrigatoria, com tab-stops no formato
# do VS Code. CURADORIA DE ERGONOMIA — nao e conhecimento de linguagem: QUAIS
# propriedades entram vem de get_field_type_info() (derivado). Isto so diz
# como cada uma se escreve e onde o cursor para.
#
# Mesma divisao adotada por rust-analyzer/TypeScript/Roslyn: corpo curado,
# aplicabilidade derivada.
_SNIPPET_BODIES: Dict[str, List[str]] = {
    "ARITY": ["    ARITY >= ${N:2}"],
    "FORMAT": ["    FORMAT [${N:0}..${M:3}]"],
    # Sem `[N]`: forma valida em ENUMERATED. ORDERED usa a variante indexada em
    # _SNIPPET_BODIES_BY_TYPE — o indice ali e obrigatorio (e o dado gravado).
    "VALUES": [
        "    VALUES",
        "        ${N:primeiro_rotulo}: ${M:descricao}",
        "        ${O:segundo_rotulo}: ${P:descricao}",
        "    END VALUES",
    ],
    "RELATIONS": [
        "    RELATIONS",
        "        ${N:NOME_DA_RELACAO}: ${M:quando usar}",
        "    END RELATIONS",
    ],
}

#: Corpos que mudam conforme o tipo. `VALUES` em ORDERED leva o prefixo `[N]`,
#: que estabelece a ordem e e o valor gravado nas anotacoes.
_SNIPPET_BODIES_BY_TYPE: Dict[str, Dict[str, List[str]]] = {
    "ORDERED": {
        "VALUES": [
            "    VALUES",
            "        [1] ${N:primeiro_rotulo}: ${M:descricao}",
            "        [2] ${O:segundo_rotulo}: ${P:descricao}",
            "    END VALUES",
        ],
    },
}

#: Propriedades opcionais que valem a pena sugerir no snippet quando o tipo as
#: aceita. Deliberadamente curto: um snippet com tudo vira ruido.
_SUGGESTED_OPTIONAL = ("RELATIONS",)


def _snippet_body(info: FieldTypeInfo) -> List[str]:
    """Monta o corpo do snippet de um tipo, numerando os tab-stops."""
    lines = [f"FIELD $" + "{1:nome_do_campo}" + f" TYPE {info.name}",
             "    SCOPE ${2|SOURCE,ITEM,ONTOLOGY|}"]

    counter = 3
    included = list(info.required)
    included += [p for p in info.allowed if p.name in _SUGGESTED_OPTIONAL]

    for prop in included:
        by_type = _SNIPPET_BODIES_BY_TYPE.get(info.name, {})
        template = by_type.get(prop.name) or _SNIPPET_BODIES.get(prop.name)
        if template is None:
            continue
        for line in template:
            # Substitui os marcadores N/M/O/P por indices sequenciais reais.
            for placeholder in ("N", "M", "O", "P"):
                if "${" + placeholder + ":" in line:
                    line = line.replace("${" + placeholder + ":",
                                        "${" + str(counter) + ":")
                    counter += 1
            lines.append(line)

    lines.append("    DESCRIPTION ${%d:o que este campo registra}" % counter)
    lines.append("END FIELD")
    lines.append("$0")
    return lines


def build_editor_snippets() -> Dict[str, Dict[str, object]]:
    """Snippets de bloco FIELD, um por tipo, no formato do VS Code.

    O CONTEUDO e derivado: quais propriedades entram no corpo sai de
    `get_field_type_info()`, portanto do proprio validador. Se uma regra mudar
    (como ocorreu quando `VALUES` deixou de valer em CHAIN), o snippet muda
    junto sem edicao manual.

    A ERGONOMIA e curada: prefixo, tab-stops e nomes de exemplo estao em
    `_SNIPPET_BODIES` — texto nao e derivavel de uma gramatica.
    """
    snippets: Dict[str, Dict[str, object]] = {}
    for type_name in field_type_names():
        info = get_field_type_info(type_name)
        if info is None:  # pragma: no cover - defensivo
            continue
        required = ", ".join(p.name for p in info.required)
        description = (
            f"Campo TYPE {info.name}"
            + (f" (exige {required})" if required else "")
        )
        snippets[f"FIELD {info.name}"] = {
            "prefix": f"field-{info.name.lower()}",
            "body": _snippet_body(info),
            "description": description,
        }
    return snippets
