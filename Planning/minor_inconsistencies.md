# Inconsistências no Compilador Synesis

Data do estudo: 2026-06-21 | Versão analisada: 0.5.7

---

## 1. Campos CHAIN/CODE ainda resolvidos por nome literal em `json_export.py`

### Contexto

A v0.5.4 corrigiu o acoplamento entre tipo de campo e nome literal em `transformer.py`, `validator.py` e `linker.py`. A correção foi aplicada corretamente nesses três módulos. Porém, um quarto ponto permaneceu sem correção.

### Bug remanescente

**Arquivo:** `synesis/exporters/json_export.py`  
**Função:** `_has_chain_relations(template)` (linha ~183)

```python
chain_spec = template.field_specs.get("chain")  # nome literal hardcoded
if not chain_spec:
    return False
return bool(chain_spec.relations)
```

A função busca pelo nome literal `"chain"` em vez de iterar por tipo. A implementação correta já existe em `semantic/linker.py:321–333`, que usa:

```python
for spec in self.template.field_specs.values():
    if spec.type == FieldType.CHAIN and spec.relations:
        return True
```

### Impacto

`_has_chain_relations()` é consultada em três lugares dentro de `json_export.py`: `_build_chain_usage()`, `_build_triples_index()` e `_build_item_data()`. Quando o projeto usa um campo CHAIN com nome customizado (ex.: `causal_chain`, `relacao`) e nenhum campo se chama literalmente `"chain"`, a função retorna `False` mesmo havendo RELATIONS definidas — o que faz `chain.to_triples(has_relations=False)` tratar cadeias qualificadas como simples, corrompendo a exportação JSON de triples.

### Severidade: **ALTA**

Projetos com campos CHAIN de nome customizado e RELATIONS declaradas geram JSON incorreto. O bug é silencioso (sem erro ou aviso) e só se manifesta quando o nome do campo difere de `"chain"`.

### Correção

Substituir `template.field_specs.get("chain")` + verificação da spec pelo padrão já adotado no linker: iterar `field_specs.values()`, filtrar por `spec.type == FieldType.CHAIN`, retornar `True` se qualquer spec tiver `relations`.

---

## 2. Colisão de campo com keyword de tipo de dado (`TEXT`, `CODE`, `CHAIN`, `DATE`, etc.)

### Contexto

O lexer usa prioridade de terminais. Palavras-chave têm prioridade 5; `FIELD_NAME` tem prioridade 1. Quando o Lark encontra um identificador que começa com (ou coincide exatamente com) uma palavra-chave, o terminal de maior prioridade vence na fase de tokenização — antes que o parser possa usar contexto gramatical para desambiguar.

### O que está protegido

A gramática já protege contra colisão com `END` via lookahead negativo em `FIELD_NAME`:

```lark
FIELD_NAME.1: /(?![eE][nN][dD]\b)[\p{L}_][\p{L}\p{N}_\-]*/u
```

Isso significa que `Endurecimento`, `ending`, `endurance` são tokenizados corretamente como `FIELD_NAME`. A reportagem original de que "Endurecimento seria confundido com KW_END" é **incorreta** — o lookahead com word boundary (`\b`) protege todos os casos em que o identificador continua após "end".

### O que não está protegido

As palavras-chave que aparecem em `field_key` como alternativas válidas de nome de campo (`KW_TEXT`, `KW_CODE`, `KW_CHAIN`, `KW_DATE`, `KW_MEMO`, `KW_QUOTATION`, `KW_SCALE`, `KW_ENUMERATED`, `KW_ORDERED`, `KW_TOPIC`, `KW_DESCRIPTION`) **não têm lookahead equivalente**. Essas keywords têm padrão `/palavra/i` sem word boundary.

No Lark com lexer contextual, um token é escolhido pelo comprimento do match mais longo (regra de Lark) e, em empate, pela prioridade. O padrão `/text/i` matcheia exatamente 4 caracteres de "Texto" — e como a keyword tem prioridade 5 vs. 1 de `FIELD_NAME`, o Lark pode tokenizar "Texto" como `KW_TEXT` (4 chars) + `TEXT_LINE` ("o: valor") em vez de `FIELD_NAME` ("Texto").

### Casos problemáticos confirmados

| Nome de campo | Keyword que colide | Motivo |
|---|---|---|
| `texto`, `Texto`, `textual` | `KW_TEXT` | "text" (4 chars) matcheia prefixo |
| `chain_length` | `KW_CHAIN` | "chain" (5 chars) matcheia prefixo |
| `code_quality` | `KW_CODE` | "code" (4 chars) matcheia prefixo |
| `date_created` | `KW_DATE` | "date" (4 chars) matcheia prefixo |
| `memo_text` | `KW_MEMO` | "memo" (4 chars) matcheia prefixo |
| `scale_value` | `KW_SCALE` | "scale" (5 chars) matcheia prefixo |
| `topic_area` | `KW_TOPIC` | "topic" (5 chars) matcheia prefixo |
| `description_text` | `KW_DESCRIPTION` | "description" (11 chars) matcheia prefixo |
| `quotation_mark` | `KW_QUOTATION` | "quotation" (9 chars) matcheia prefixo |
| `enumerated_type` | `KW_ENUMERATED` | "enumerated" (10 chars) matcheia prefixo |
| `ordered_list` | `KW_ORDERED` | "ordered" (7 chars) matcheia prefixo |

> **Nota:** O Lark usa longest-match, então `KW_TEXT` só matcheia se o padrão `/text/i` produzir um match **mais longo ou igual** ao de `FIELD_NAME`. Na prática, `/text/i` casa 4 chars de "Texto", enquanto `FIELD_NAME` casaria "Texto" inteiro (5 chars). Por longest-match, `FIELD_NAME` deveria vencer. Mas com prioridade 5 vs. 1 e o lexer contextual, o comportamento pode variar conforme o estado do parser. **Recomenda-se teste empírico** com cada caso antes de concluir que todos falham — o agente de exploração deduziu colisões por análise estática, não por execução.

### Casos seguros confirmados

- Campos iniciados com `END` + caractere não-boundary: `Endurecimento`, `ending`, `endurance` — **seguros** (lookahead protege).
- Campos iniciados com `SOURCE`, `ITEM`, `TEMPLATE`, `FIELD`, `INCLUDE`, `PROJECT`, `BUNDLE`, `REQUIRED`, `OPTIONAL`, `FORBIDDEN`, `SCOPE`, `FORMAT`, `ARITY`, `VALUES`, `RELATIONS`, `METADATA`, `GUIDELINES` — **seguros** (nenhuma dessas keywords aparece como alternativa em `field_key`; só são válidas em contextos específicos do parser).

### Severidade: **MÉDIA** (necessita verificação empírica)

A colisão, se confirmada, produz erro de parse (`UnexpectedToken`) silencioso para o usuário. No template, isso impede que o campo seja definido. Nas anotações, impede que o campo seja reconhecido. A correção estrutural requer estender o lookahead negativo em `FIELD_NAME` para cobrir todas as keywords presentes em `field_key` — o que torna a gramática mais verbosa mas resolve definitivamente.

---

## 3. `ARITY = 2` — validação correta, semântica pode surpreender

### Contexto

O relato original indicava que `ARITY = 2` seria ignorado pelo compilador. A investigação não confirma isso.

### O que foi encontrado

A validação de ARITY está corretamente implementada em `semantic/validator.py:_validate_chain_arity()` (linhas 787–817):

```python
op, raw_value = field_spec.arity.split()  # ex: "= 2" → op="=", raw_value="2"
target = int(raw_value)
if op == "=":
    ok = count == target
elif op == ">=":
    ok = count >= target
# ... etc.
```

Todos os cinco operadores (`=`, `>=`, `<=`, `>`, `<`) são tratados. A validação é chamada em `_validate_chains()` (linha 821) e testes cobrem ao menos os casos `>= 3` (violação) e `>= 2` (satisfeito).

### Ponto de atenção: o que `count` representa

O `count` passado para `_validate_chain_arity` é `len(codes)`, onde `codes` são os **elementos conceituais** da cadeia — não o número total de tokens. Para uma cadeia qualificada:

```
A -> INFLUENCIA -> B -> MODIFICA -> C
```

Os elementos extraídos são `[A, B, C]` (posições pares), então `count = 3`. `ARITY = 3` seria satisfeito; `ARITY = 2` seria violado.

Para uma cadeia simples (sem RELATIONS):

```
A, B, C
```

`count = 3` igualmente.

Essa semântica é correta e consistente, mas pode surpreender usuários que esperam que `ARITY` conte o número de **pares** ou **relações** em vez de **conceitos**.

### Possível causa do relato original

Se o campo CHAIN não se chama literalmente `"chain"`, a validação de arity em v0.5.3 (antes do fix de v0.5.4) era silenciosamente ignorada — porque `_validate_chains` não encontrava o campo. Com o fix de v0.5.4, `_chain_field_specs` é construído por `FieldType.CHAIN`, então a validação passa a funcionar independentemente do nome. **O bug de ARITY em campos com nome customizado foi corrigido em v0.5.4 como efeito colateral da correção de campos CHAIN.**

### Ressalva: `int()` em ARITY decimal

A linha `target = int(raw_value)` em `_validate_chain_arity` converte o valor para inteiro via `int()`. Se um template declarar `ARITY = 2.0` (número com decimal, aceito pela gramática via `NUMBER`), `int("2.0")` levanta `ValueError` — capturado silenciosamente com `return None` (linha 799), ignorando a validação. O template_loader detecta isso via `DecimalInIntegerScale` (erro 26), mas apenas para campos `SCALE` — não para `ARITY`. **Esse é um bug menor**: `ARITY = 2.0` no template é aceito pela gramática e pelo transformer, mas silenciosamente ignorado na validação semântica.

### Severidade do item 3 principal: **NÃO CONFIRMADO** (comportamento correto)
### Severidade do bug secundário (`ARITY = 2.0`): **BAIXA**

---

## Resumo

| # | Problema | Status | Severidade | Arquivo principal |
|---|---|---|---|---|
| 1 | `_has_chain_relations` em json_export usa nome literal `"chain"` | **Confirmado** | Alta | `exporters/json_export.py` |
| 2 | Colisão de FIELD_NAME com keywords de tipo (`TEXT`, `CODE`, etc.) | **Provável** (verificar empiricamente) | Média | `grammar/synesis.lark` |
| 3a | `ARITY = N` ignorado pelo compilador | **Não confirmado** — validação funciona | — | — |
| 3b | `ARITY = 2.0` (decimal) aceito pelo parser mas ignorado na validação | **Confirmado** (bug menor) | Baixa | `semantic/validator.py:799` |
