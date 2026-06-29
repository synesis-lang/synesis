# OPTIONAL BUNDLE — Estudo de Viabilidade

**Data:** 2026-06-16
**Status:** Em avaliação

---

## 1. Contexto

O compilador Synesis suporta `REQUIRED BUNDLE campo1, campo2`, que define um grupo de campos
de co-ocorrência obrigatória: se um campo do bundle aparece, todos devem aparecer com a mesma
contagem, e ao menos uma ocorrência do grupo completo é exigida.

A instrução `OPTIONAL BUNDLE campo1, campo2` **não é aceita** pela gramática atual (v1.1).

---

## 2. Semântica Proposta

> "Os campos são opcionais, mas se qualquer um aparecer, todos devem aparecer juntos com a mesma
> contagem."

Distinção em relação ao `REQUIRED BUNDLE`:

| Instrução | Ausência total do bundle | Presença parcial | Contagens diferentes |
|---|---|---|---|
| `REQUIRED BUNDLE` | ❌ Erro | ❌ Erro | ❌ Erro |
| `OPTIONAL BUNDLE` | ✅ OK | ❌ Erro | ❌ Erro |

---

## 3. Análise de Impacto por Módulo

### 3.1 Gramática — `synesis/grammar/synesis.lark` ⚠️ BLOQUEADOR

A mudança necessária é mínima (uma linha):

```lark
# Atual:
requirement_clause: KW_REQUIRED bundle_modifier? field_names
                  | KW_OPTIONAL field_names

# Proposto:
requirement_clause: KW_REQUIRED bundle_modifier? field_names
                  | KW_OPTIONAL bundle_modifier? field_names
```

**Restrição:** A gramática está congelada para v1.x. Alterações breaking requerem v2.0.
Decisão necessária: adicionar `bundle_modifier?` ao `OPTIONAL` constitui breaking change?
Argumentos:
- **Não é breaking** para arquivos `.syn` existentes (a mudança é apenas no `.synt`).
- **Pode ser considerado breaking** no sentido de que o parser do template passa a aceitar
  combinações antes rejeitadas.

### 3.2 Transformer — `synesis/parser/transformer.py` — Esforço: Baixo

Função `requirement_clause` (linha ~790): branch `OPTIONAL` precisa detectar `BUNDLE` na lista
de itens, analogo ao que já existe para `REQUIRED`:

```python
# Atual:
if items[0] == "OPTIONAL":
    return ("optional", items[1])

# Proposto:
if items[0] == "OPTIONAL":
    has_bundle = "BUNDLE" in items
    names = items[-1]
    return ("optional", has_bundle, names)
```

Função `field_spec_block` (linha ~765): adicionar tratamento do novo formato de tupla para
`optional`, construindo `optional_bundles` análogo a `bundles`.

**Arquivos afetados:** `synesis/parser/transformer.py`
**Linhas estimadas:** ~8 linhas

### 3.3 AST / TemplateNode — `synesis/ast/nodes.py` — Esforço: Baixo

`TemplateNode` precisa de um novo campo:

```python
optional_bundles: Dict[Scope, List[Tuple[str, ...]]]
```

`to_dict()` precisa serializá-lo (padrão idêntico ao `bundled_fields`).

**Arquivos afetados:** `synesis/ast/nodes.py`
**Linhas estimadas:** ~6 linhas

### 3.4 Template Loader — `synesis/parser/template_loader.py` — Esforço: Baixo-Médio

- Inicializar `optional_bundles` no dicionário de construção (~3 linhas)
- Popular no loop de `spec_blocks` (~4 linhas)
- Espelhar os 5 loops de validação de `bundled_fields` (linhas 277–353) para `optional_bundles`

**Arquivos afetados:** `synesis/parser/template_loader.py`
**Linhas estimadas:** ~25 linhas

### 3.5 Validador Semântico — `synesis/semantic/validator.py` — Esforço: Médio ⚠️ RISCO ALTO

`validate_bundle` (linha 350) é classificado como **CRITICAL** pelo GitNexus:
- Callers diretos (d=1): `validate_source`, `validate_item`, `validate_ontology`
- Callers indiretos (d=2): `_validate_semantics`, `validate_all`, `api.load`
- Entry points (d=3): `validate_single_file`, `compile`, `cli.compile`
- Processos afetados: 20 flows de execução

A lógica de validação diverge entre REQUIRED e OPTIONAL:

**REQUIRED BUNDLE** (comportamento atual):
1. Ausência total → `MissingBundleField` (erro)
2. Presença parcial → `MissingBundleField` (erro)
3. Contagens diferentes → `BundleCountMismatch` (erro)

**OPTIONAL BUNDLE** (comportamento novo):
1. Ausência total → OK
2. Presença parcial → `MissingBundleField` (erro)
3. Contagens diferentes → `BundleCountMismatch` (erro)

**Estratégia recomendada:** criar `validate_optional_bundle` separado (não modificar a assinatura
de `validate_bundle` existente) e chamá-lo nos 3 métodos `validate_source/item/ontology`.

**Arquivos afetados:** `synesis/semantic/validator.py`
**Linhas estimadas:** ~35 linhas (nova função + 3 chamadas)

### 3.6 Exporters — Esforço: Baixo-Médio

Os 3 exporters leem `bundled_fields` para lógica de emparelhamento:

| Arquivo | Linha | O que faz |
|---|---|---|
| `synesis/exporters/csv_export.py` | 153 | emparelha colunas de bundle |
| `synesis/exporters/xls_export.py` | 164 | idem para Excel |
| `synesis/exporters/alpaca_export.py` | 683 | gera pares de treino |

Cada um precisaria iterar também `optional_bundles`. O comportamento de exportação é idêntico ao
do `REQUIRED BUNDLE` quando os campos estão presentes.

**Arquivos afetados:** 3 exporters
**Linhas estimadas:** ~5 linhas por arquivo

### 3.7 synesis-lsp — Esforço: Nenhum

O LSP delega 100% ao compilador via `validate_single_file`. Herda a feature automaticamente.

### 3.8 synesis-explorer — Esforço: Nenhum

Depende exclusivamente do LSP. Nenhuma lógica de template hardcoded.

---

## 4. Resumo de Esforço

| Arquivo | Esforço | Linhas est. |
|---|---|---|
| `synesis/grammar/synesis.lark` | Mínimo (decisão política) | 1 |
| `synesis/parser/transformer.py` | Baixo | ~8 |
| `synesis/ast/nodes.py` | Baixo | ~6 |
| `synesis/parser/template_loader.py` | Baixo-Médio | ~25 |
| `synesis/semantic/validator.py` | Médio | ~35 |
| 3 exporters | Baixo-Médio | ~15 |
| Testes novos | Médio | ~60 |
| `synesis-lsp` | Nenhum | — |
| `synesis-explorer` | Nenhum | — |

**Esforço total estimado:** ~1 dia de trabalho.

---

## 5. Decisão Pendente

> **A alteração na gramática (`synesis.lark`) é compatível com v1.x?**

- A mudança não altera tokens existentes nem quebra arquivos `.syn` já escritos.
- Quebra apenas parsers que assumam que `OPTIONAL BUNDLE` gera erro de parse (nenhum consumidor
  externo documentado faz essa suposição).
- Posição conservadora: exige v2.0.
- Posição pragmática: é uma adição não-breaking ao template parser, aceitável em v1.x como
  MINOR bump (ex: v0.6.0).

---

## 6. Próximos Passos (se aprovado)

1. Definir posição sobre versionamento (v1.x MINOR vs v2.0)
2. Implementar na ordem: gramática → transformer → AST → template_loader → validator → exporters
3. Criar fixture `T04-OptionalBundle` com casos: ausência total (OK), presença parcial (erro),
   contagens erradas (erro), bundle completo (OK)
4. Adicionar testes em `test_validator.py` (`TestOptionalBundleValidation`)
5. Adicionar testes de integração em `test_integration.py`
6. Atualizar `CHANGELOG.md` na seção `[Unreleased]`
