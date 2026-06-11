# Estudo: Por que o campo CHAIN precisa se chamar literalmente `chain`

**Compilador:** Synesis v0.5.3.3
**Data:** 2026-06-10
**Escopo:** Investigação da causa raiz + plano de implementação seguro. **Nenhum código foi alterado.**

---

## 1. Sintoma

Declarar um campo CHAIN com nome descritivo:

```synesis
FIELD aplicacao TYPE CHAIN
    SCOPE ITEM
END FIELD
```

E usá-lo numa anotação sintaticamente correta:

```synesis
ITEM @x
  aplicacao: otimizacao -> aplicada_a -> escalonamento_medico
END ITEM
```

produz, para **todo** ITEM que usa o campo:

```
InvalidFieldType: field=aplicacao, expected=chain, actual=str
```

O mesmo vale para `trajetoria`, `argumento`, `causal_chain` — qualquer nome ≠ `chain`/`chains`.
A única forma de funcionar hoje é nomear o campo literalmente `chain` (como faz
`Social_Acceptance/social_acceptance.synt:110`). O mesmo acoplamento existe para
campos `CODE` (precisam se chamar `code`/`codes`).

---

## 2. Causa raiz — cadeia de execução em `api.py:load()`

A ordem dos passos é o cerne do problema:

| Passo | Código | O que acontece com `aplicacao: A -> rel -> B` |
|-------|--------|-----------------------------------------------|
| 5. Parse | `transformer.py:field_entry` | O ramo que converte para `ChainNode` só dispara se `_is_chain_field_name(name)`. Como `aplicacao ∉ {"chain","chains"}`, o valor é gravado em `extra_fields` como **`str`**. |
| 6. Validação | `validator.py:_validate_value` (linha 602) | `if expected==CHAIN and not isinstance(value, ChainNode)` → emite `InvalidFieldType(actual="str")`. Lê o `extra_fields` que tem **string**. |
| 7. Linker | `linker.py:_augment_item_field_locations` (367-394) | Este SIM percorre todos os campos `spec.type==CHAIN` e reparseia para `ChainNode`. Mas roda **depois** da validação — tarde demais. |

### 2.1 O acoplamento no parser

`transformer.py:235-236`:

```python
def _is_chain_field_name(name: str) -> bool:
    return name.lower() in {"chain", "chains"}
```

Usado em `field_entry` (linhas 929/932/946/949/969). Quando o nome não está no
conjunto, o `else` (linha 981) trata o valor como texto comum.

### 2.2 A gramática NÃO é o gargalo

`grammar/synesis.lark:185-197`:

```lark
value: STRING | NUMBER TEXT_LINE | NUMBER | chain_expr | code_list | TEXT_LINE
chain_expr: CHAIN_ELEMENT ("->" CHAIN_ELEMENT)+
```

A regra `value` reconhece `chain_expr` **por sintaxe** (presença de `->`), sem olhar o
nome do campo. O método `transformer.py:chain_expr` (linha 1024) já constrói um
`ChainNode` correto. O problema é exclusivamente o `field_entry` **reclassificar por nome**
e a **ordem validação-antes-de-linker**.

### 2.3 Prova empírica

Parsing puro (`compile_string`, sem template):

```
chain: C -> D            → item.chains = [ChainNode(nodes=['C','D'])]   ✓
causal_chain: A -> B     → extra_fields['causal_chain'] = 'A -> B' (str) ✗
```

O teste `tests/test_alpaca_export.py:83` usa `causal_chain TYPE CHAIN` e **passa** —
porque o alpaca_export lê por `spec.type==CHAIN`, não pelo nome. Mas rodar
`synesis.load()` com esse mesmo template+anotação **falha** na validação semântica.
Isto evidencia uma inconsistência interna já presente no próprio test-suite.

---

## 3. Por que existe esse acoplamento (interpretação)

O design assumiu campos canônicos `chain`/`chains` e `code`/`codes`, materializados em
atributos dedicados do `ItemNode` (`item.chains`, `item.codes`). O parser despeja nesses
atributos só pelos nomes canônicos; campos extras vão para `extra_fields` como texto.
O linker (mais recente) introduziu suporte genérico por `spec.type`, mas a validação
não foi realinhada à nova ordem.

---

## 4. Objetivo da correção

Permitir que **qualquer** campo `TYPE CHAIN` (e, por simetria, `TYPE CODE`) seja
parseado e validado corretamente, independentemente do nome — preservando 100% do
comportamento atual para campos chamados `chain`/`code`.

---

## 5. Plano de implementação (3 opções, com recomendação)

### Opção A (RECOMENDADA) — Parser passa a converter por sintaxe, validador lê ChainNode

**Princípio:** o `field_entry` já recebe, da gramática, candidatos a `chain_expr`. Em vez
de depender do nome, converter para `ChainNode` sempre que o valor for um `chain_expr`
(tem `->`) **ou** simplesmente preservar o `ChainNode` que a gramática produz.

**Mudança 5.A.1 — `transformer.py`**
Nos ramos de `field_entry` que hoje chamam `_is_chain_field_name(name)` (linhas 929-934,
946-951, 969-980), trocar a condição "nome é chain" por "valor tem estrutura de chain"
(`"->" in value_str`, ou o item já é `ChainNode`). Manter o caminho de CODE análogo
(detecção por `,` já existe parcialmente).

Resultado: `extra_fields['aplicacao']` passa a conter um `ChainNode`.

**Mudança 5.A.2 — `transformer.py:item_block` (linha 659)**
Hoje `if lname in {"chain","chains"}` decide o que vai para `item.chains`. Ampliar para:
"vai para `item.chains` se o valor for `ChainNode`" — assim qualquer campo chain popula
`item.chains` consistentemente. (Alternativa conservadora: deixar `item.chains` só para
`chain`/`chains` e fazer a validação ler de `extra_fields`; ver 5.A.3.)

**Mudança 5.A.3 — `validator.py` (sem mudança, se 5.A.1 feita)**
Com `extra_fields['aplicacao']` já sendo `ChainNode`, `_validate_value` (linha 602) e
`_is_valid_value_type` (linha 902) passam sem alteração. As funções `_validate_chains`
e `_validate_codes_defined` que fazem `field_specs.get("chain")` (linhas 747, 809)
precisam iterar por **todos** os campos `spec.type==CHAIN` em vez do nome fixo `"chain"`.

**Mudança 5.A.4 — `linker.py`**
`_has_chain_relations` (330) e `_get_item_field_value` (422-427) devem resolver o spec
do campo chain por tipo, não pelo literal `"chain"`. O `_augment_item_field_locations`
(367) já é genérico — pode virar redundante após 5.A.1, mas mantê-lo é inofensivo.

**Esforço:** médio. **Risco:** médio (toca o caminho central de parsing).

---

### Opção B (MAIS SEGURA, MENOR) — Só reordenar: validar CHAIN depois do augment

**Princípio:** não mexer no parser. Apenas garantir que, no momento da validação de tipo,
o campo chain já esteja convertido para `ChainNode`.

**Mudança 5.B.1 — `api.py:load()`**
Mover o `_augment_item_field_locations` (ou um pré-passo equivalente que reparseia campos
`spec.type==CHAIN`/`CODE` em `extra_fields`) para **antes** do laço de
`validator.validate_item(item)` (linha 343).

**Mudança 5.B.2 — `validator.py`**
`_validate_chains`/`_validate_codes_defined` iteram por todos os campos do tipo, não só
`get("chain")`.

**Esforço:** baixo. **Risco:** baixo — não altera parser nem gramática; só a ordem e
duas funções de validação. **Limitação:** depende de `_augment_item_field_locations`
cobrir todos os casos (single-line e multi-line) — verificar antes.

---

### Opção C (DOCUMENTAR, NÃO CORRIGIR) — Manter convenção e documentar

Aceitar que o nome canônico é `chain`/`code` e documentar isso no manual da DSL e no
linter de template. Acrescentar um **aviso de template** em `template_loader.py`: se um
campo `TYPE CHAIN` tiver nome ≠ `chain`/`chains`, emitir warning claro
("campos CHAIN devem se chamar 'chain'"). Zero risco funcional; resolve a confusão sem
mudar semântica.

**Esforço:** mínimo. **Risco:** nulo. **Ganho:** só ergonômico.

---

## 6. Verificação de não-quebra do ecossistema

### 6.1 Mapa de dependências por nome (`grep "chain"|"code"` em `synesis/`, sem testes)

| Módulo | Linhas | Já usa `spec.type`? | Afetado pela correção |
|--------|--------|---------------------|------------------------|
| `transformer.py` | 235-236, 643, 659, 929-980 | Não (usa nome) | **Sim** (Opção A) |
| `validator.py` | 98, 517-519, 602, 747, 809, 902 | Parcial | **Sim** (5.x.2) |
| `linker.py` | 330, 370, 422-427 | Sim (370) | **Sim** (5.x.4) |
| `exporters/_helpers.py` | 45-50 | Não | Verificar |
| `exporters/json_export.py` | 183, 467, 540, 573, 632 | Sim (maioria) | Baixo |
| `exporters/csv_export.py`, `xls_export.py` | vários | Sim (`spec.type`) | Baixo |
| `exporters/alpaca_export.py` | 109, 711 | Sim | Nenhum |
| `template_loader.py` | 371-483 | Sim (`spec.type`) | Nenhum |
| `error_handler.py` | 222 | dinâmico (`known_field_names`) | Nenhum |

A maior parte dos **exporters** já opera por `spec.type` — o que confirma que mover o
parser/validador para a mesma lógica é coerente com o design já em curso.

### 6.2 Garantias de compatibilidade retroativa

- **Campos chamados `chain`/`code` continuam idênticos.** Toda condição nova é da forma
  "nome é chain **ou** tipo é CHAIN" — superconjunto do comportamento atual.
- **`item.chains` / `item.codes`** permanecem populados para os nomes canônicos. Projetos
  e exporters que leem esses atributos não percebem diferença.
- **`to_dict`/`to_json_dict`** (`nodes.py:231-233`) usam `self.codes`/`self.chains` —
  inalterados se 5.A.2 mantiver os canônicos lá.

### 6.3 Impacto no ecossistema externo (fora do compilador)

- **synesis-coder**: gera ITEMs e valida via `synesis.load()`. Hoje contorna o bug exigindo
  campo `chain`. Após a correção, templates com nomes descritivos passam a compilar —
  ganho puro, sem regressão (os templates atuais com `chain` continuam válidos).
- **synesis-lsp / synesis-explorer**: consomem o AST (`item.chains`, `field_specs`) e o
  `lsp_adapter`. Como os atributos canônicos são preservados, não há mudança de contrato.
- **synesis2graph**: lê chains via exporters/`spec.type` — já agnóstico ao nome.

### 6.4 Suíte de testes a rodar (antes e depois)

```bash
cd d:\GitHub\synesis && python -m pytest tests/ -v
```

Atenção especial:
- `tests/test_parser.py:319` (`FIELD chain`) — não pode regredir.
- `tests/test_validator.py` (`_make_chain_template`, arity, relations) — comportamento de
  `chain` canônico intacto.
- `tests/test_alpaca_export.py:83` (`causal_chain`) — **adicionar** um teste novo que faça
  `synesis.load()` desse template+anotação e exija `success=True` (hoje falharia → é o
  teste de regressão da correção).
- `tests/test_integration.py` (`test_simple_chain_with_relations_required`,
  `test_invalid_chain_relation`) — relations continuam validando.

### 6.5 Testes novos a adicionar

1. `causal_chain TYPE CHAIN` + anotação `A -> REL -> B` → `success=True`, `ChainNode` no campo.
2. Campo CHAIN com nome custom + `RELATIONS` → validação de relação e arity funcionam.
3. Dois campos CHAIN no mesmo ITEM (`chain` + `causal_chain`) → ambos viram `ChainNode`.
4. Campo CODE com nome custom (`tema TYPE CODE`) → `UndefinedCode` dispara corretamente.
5. Regressão: template legado com `chain`/`code` → bytes de saída idênticos ao baseline.

---

## 7. Recomendação final

- **Curto prazo / risco mínimo:** Opção **C** (warning no template_loader) imediatamente,
  para parar de gerar confusão silenciosa, + manter o workaround atual (campo `chain`).
- **Correção real:** Opção **B** (reordenar augment antes da validação + iterar por
  `spec.type` nas duas funções de validação). É a menor mudança que conserta de verdade,
  não toca a gramática nem o parser, e a infraestrutura (`_augment_item_field_locations`)
  já existe. **Pré-condição:** confirmar que o augment cobre single-line e multi-line.
- **Opção A** só se quiser eliminar a dependência de nome de forma definitiva no parser —
  maior alcance, maior risco; justificável numa versão minor (0.6.x) com a bateria de
  testes da seção 6.5 verde.

Nenhuma das opções quebra projetos existentes que usam o nome canônico `chain`/`code`,
porque todas as condições novas são **superconjuntos** das atuais.
