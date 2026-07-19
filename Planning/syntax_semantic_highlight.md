# Colorização de Sintaxe: Estudo e Fases de Implementação

**Status:** Proposta — não implementado
**Data:** 2026-07-18
**Escopo:** `synesis-lsp/semantic_tokens.py`, `synesis-vscode/syntaxes/synesis.tmLanguage.json`

---

## 1. Problema

A colorização do Synesis no VSCode é produzida por **duas listas de keywords escritas à mão em regex**, ambas independentes da gramática:

| Camada | Arquivo | Natureza |
|---|---|---|
| TextMate | `synesis-vscode/syntaxes/synesis.tmLanguage.json` | Regex |
| LSP semantic tokens | `synesis-lsp/synesis_lsp/semantic_tokens.py` | Regex (scan linha a linha) |

Quando a gramática ganha um construto novo, **nenhuma das duas é atualizada automaticamente**. Sintomas confirmados:

### 1.1 `IDENTIFIES` / `REFERS TO` sem cor

Implementados em `synesis.lark` (`KW_IDENTIFIES`, `KW_REFERS`, `KW_TO`) como modificadores de `FIELD`:

```lark
field_modifier: KW_IDENTIFIES entity_label
              | KW_REFERS KW_TO entity_label
```

Ausentes em ambas as camadas de colorização. Em `semantic_tokens.py` a linha `IDENTIFIES researcher` (sem `:`) não casa `_RE_FIELD_LINE` nem a regra de chain — cai num `continue` silencioso e **não emite token algum**.

### 1.2 Keywords coloridas dentro de `DESCRIPTION` (bug estrutural)

A gramática define o conteúdo como texto livre:

```lark
description: KW_DESCRIPTION NEWLINE description_lines KW_END KW_DESCRIPTION NEWLINE?
description_lines: (TEXT_LINE NEWLINE | NEWLINE)+
```

O lexer contextual do Lark respeita isso. Verificado:

```
4:5  KW_DESCRIPTION  'DESCRIPTION'
5:5  TEXT_LINE       'Aqui FIELD e TYPE sao texto: nao keywords'
6:5  KW_END          'END'
```

A linha inteira volta como **um único `TEXT_LINE`**. Já o `semantic_tokens.py` tem flag manual `in_guidelines` para GUIDELINES, mas **nenhum tratamento equivalente para DESCRIPTION** — continua aplicando `_RE_FIELD_LINE` e regexes de keyword lá dentro. O `.tmLanguage.json` tem o mesmo buraco (`guidelines_block` existe, `description_block` não).

**O compilador nunca teve esse bug.** É artefato exclusivo da duplicação em regex.

---

## 2. Pesquisa: como projetos consagrados resolvem

### 2.1 VSCode — a arquitetura de duas camadas é normativa

> "Semantic highlighting is an addition to syntax highlighting... VS Code uses TextMate grammars as the **main tokenization engine**. The editor applies the highlighting from semantic tokens **on top of** the highlighting from grammars."

Mecanismo de máscara:

> "Semantic tokens always overwrite TextMate tokens, and the overwrite works **like a mask** — if a range is **not covered** by a semantic token, the **TextMate token is used instead**."

Consequência: TextMate **não é só bootstrap**. Cobre permanentemente todo range que o LSP não emitir.

Remover a grammar é tecnicamente possível, com custo conhecido: *"without a TextMate grammar, text would appear as plaintext until the semantic token provider responds."*

### 2.2 rust-analyzer — mantém, por um motivo não óbvio

Tem semantic tokens vindos do compilador real, mais precisos que qualquer regex. Mantém a grammar TextMate porque:

> "TextMate grammars can be used to provide syntax highlighting in contexts where semantic highlighting isn't available, such as **in on-hover messages or markdown fenced code blocks**."

Aplica-se ao Synesis: `synesis-lsp/hover.py` existe. Código em hovers, diagnósticos e blocos ```` ```synesis ```` em Markdown é colorido **só** por TextMate.

### 2.3 Langium — o precedente decisivo

Framework líder de DSLs com gramática como fonte única. **Gera** o `.tmLanguage.json` a partir da gramática, mas o maintainer é explícito sobre o limite:

> "The generated textMate syntax highlighting file is **basically just a starting help**... It's basically **impossible to infer accurate syntactical highlighting just based on a grammar**."

E na prática: **o próprio time Langium desativa a geração e mantém o TextMate escrito à mão.**

### 2.4 Conclusão da pesquisa

**"Fonte única de verdade que se propaga automaticamente" não é alcançável no VSCode.** Nem rust-analyzer nem Langium conseguiram — não por falta de tentativa.

O que é alcançável, e é o padrão consagrado:

> **Fonte única para a _correção_ (LSP ← gramática); TextMate como camada de base assumidamente aproximada.**

A divergência se administra tornando o TextMate deliberadamente **grosso**. Uma regra que não tenta distinguir `IDENTIFIES` nunca fica dessincronizada quando `IDENTIFIES` é adicionado.

---

## 3. Viabilidade técnica — medições

Testes executados contra o código real.

### 3.1 O lexer expõe posições

`create_parser().lex(src)` retorna tokens com `.line`, `.column`, `.type`, `.value`. 39 terminais `KW_*` enumeráveis em runtime via `parser.terminals` — **é isso que torna a propagação automática real**.

### 3.2 Resiliência a documento inválido (risco principal — descartado)

Semantic tokens são pedidos a cada tecla, com o documento quase sempre inválido.

| Cenário | Resultado |
|---|---|
| Bloco não fechado | ✅ tokeniza até onde dá |
| Lixo (`@@@ !!! ###`) | ✅ vira `TEXT_LINE` |
| Palavra solta / vazio | ✅ sem crash |

Nenhuma exceção. `p.lex()` não passa pelo parser — `parse_string()` levantaria `SynesisSyntaxError`, `lex()` não.

### 3.3 Performance

`lattes.synt` — 1044 linhas, 58KB: **7.0ms mediano** (min 6.7 / max 9.8). `create_parser()` cacheado em 0ms. O cache por `hash(source)` já existente absorve repetições.

### 3.4 Limitações descobertas — decisivas para o desenho

Duas medições que **invalidam uma reescrita puramente sobre o lexer**:

**(a) Chains não são decompostas.**

```
2:5  KW_CHAIN      'chain'
2:10 CONCEPT_NAME  ': Trust -> INFLUENCES -> CCS_Support'
```

O valor volta como **um `CONCEPT_NAME` opaco**. As relações (`INFLUENCES`, ...) vêm do **template**, não da gramática — por isso o código atual recebe `relation_names` como parâmetro. A tokenização fina de chain (`_tokenize_chain_value`) **precisa ser preservada**.

**(b) `@bibref` não é token próprio no contexto de bloco.**

```
1:1  KW_SOURCE   'SOURCE'
1:8  TEXT_LINE   '@silva2020'      ← não BIBREF
```

O lexer contextual colapsa em `TEXT_LINE`. A AST tem o valor (`SourceNode.bibref`) mas `field_locations` vem `None` — **não fornece a coluna** para emitir o token.

**Consequência:** uma reescrita ingênua *perderia* a coloração de bibref que hoje funciona. O desenho correto é **híbrido**, não substituição.

---

## 4. Arquitetura proposta

| Camada | Papel | Fonte | Ação |
|---|---|---|---|
| **LSP semantic tokens** | Autoridade; precisão total | `p.lex()` + pós-processamento | **Reescrever (híbrido)** |
| **TextMate** | Máscara de base; hover/markdown | Regex | **Manter, engrossar** |

Princípio: o LSP deriva da gramática tudo que a gramática sabe; o pós-processamento cobre o que o lexer colapsa (chain, bibref); o TextMate é deliberadamente grosso para não poder divergir.

---

## Fase 0 — Reverter o paliativo

Remover `_RE_FIELD_MODIFIER` e a regra "item 3" de `semantic_tokens.py`, adicionados como correção pontual para `IDENTIFIES`. Viram código morto na Fase 2.

**Critério:** suíte do `synesis-lsp` verde (baseline atual: 34 testes).

---

## Fase 1 — API pública `lex_tokens()` no compilador

Expor no pacote `synesis`:

```python
def lex_tokens(source: str) -> list[LexToken]:
    """Tokens posicionais. Nunca levanta exceção — documento inválido é normal."""
```

`LexToken`: `type`, `value`, `line` (1-based), `column` (1-based), `end_line`, `end_column`. Verificado: os tokens do Lark já expõem `end_line`/`end_column` preenchidos — basta copiá-los, sem cálculo próprio.

Requisitos:
- Envolver `p.lex()` em try/except; retornar o que foi tokenizado até o ponto de falha.
- **Observabilidade no caminho de erro:** logar em `debug` linha/coluna onde o lex truncou. Tolerant Reader ≠ erro invisível — silêncio total vira *failure masking*.
- Reusar o parser cacheado (`create_parser()` já é 0ms).
- Não expor objeto `Token` do Lark — desacoplar do backend de parsing (Adapter/ACL: se o Lark for trocado, só esta função muda).

**Por que no `synesis` e não no LSP:** `synesis-graph` e `synesis-coder` têm a mesma necessidade. Evita um terceiro reimplementador de regex.

**Testes:** documento válido; não fechado; lixo; vazio; posições conferidas contra offsets conhecidos.

**Critérios de saída:**
1. Suíte do `synesis` verde (baseline: 264 testes).
2. **Bump de versão do `synesis` e atualização do constraint `synesis>=X.Y` no `pyproject.toml` do `synesis-lsp`** (regra de sincronização do ecossistema). Sem isso, `synesis-lsp` novo com `synesis` antigo falha com `ImportError` em runtime, não em install.

---

## Fase 2 — Reescrever `semantic_tokens.py` (núcleo)

Substituir `_extract_tokens_from_source` (scan linha a linha) por consumo de `lex_tokens()`.

### 2.1 Mapa terminal → tokenType

```python
_TERMINAL_MAP = {
    "COMMENT": _TK_COMMENT,
    "BIBREF": _TK_VARIABLE,
    "STRING": _TK_STRING,
    "FIELD_NAME": _TK_PROPERTY,
    "TEXT_LINE": _TK_STRING,
    "CONCEPT_NAME": _TK_ENUM_MEMBER,
    # ...
}

_NAMESPACE_KW = {"KW_PROJECT", "KW_TEMPLATE", "KW_INCLUDE",
                 "KW_BIBLIOGRAPHY", "KW_ANNOTATIONS"}
```

**Regra de fallback — o coração da propagação automática:**

```python
if terminal.startswith("KW_"):
    return _TK_NAMESPACE if terminal in _NAMESPACE_KW else _TK_KEYWORD
```

Qualquer `KW_*` novo na gramática **já nasce colorido**, sem tocar em código. Resolve `IDENTIFIES`, `REFERS TO` e todo caso futuro.

### 2.2 Pós-processamento (o que o lexer colapsa)

Preservar a lógica existente para os dois casos da §3.4:

- **Chain:** ao encontrar `KW_CHAIN` seguido de `CONCEPT_NAME`, aplicar `_tokenize_chain_value()` sobre o valor, com `relation_names` do template. **Manter intacto.**
- **Bibref:** ao encontrar `TEXT_LINE` iniciado por `@` logo após `KW_SOURCE`/`KW_ITEM`, emitir `_TK_VARIABLE`. Sub-scan localizado e explicitamente delimitado.

Ambos ficam isolados numa função `_refine_opaque_tokens()`, com comentário registrando **por que** existem (o lexer não decompõe) — para não serem removidos por engano depois.

### 2.3 O que se resolve de graça — **e o que não** (corrigido pós-implementação)

- `IDENTIFIES`/`REFERS TO`: cobertos pelo fallback `KW_*`. **Confirmado:** funcionaram sem nenhum caso especial.
- `DESCRIPTION`/`GUIDELINES`: **a previsão original estava errada.** O estudo
  afirmava que o rastreamento manual de bloco poderia ser removido. Não pode.
  O lexer marca o *conteúdo* como `TEXT_LINE`, mas **continua reconhecendo
  keywords soltas na prosa** — `FORMATO DE ORIGEM` tokeniza como
  `KW_FORMAT` + `TEXT_LINE('O DE ORIGEM')`. Foi necessário rastrear
  profundidade de bloco explicitamente e suprimir toda tokenização dentro dele.

Outras três descobertas da implementação, não previstas aqui:

1. **Comentários não vêm do lexer.** A gramática declara `%ignore COMMENT`
   (`synesis.lark:260`), então `lex_tokens()` nunca os emite dentro de blocos.
   Exige passe dedicado sobre o texto. Fora de bloco, chegam como `TEXT_LINE`.
2. **`nome_campo:` colapsa em `TEXT_LINE`** quando o nome não colide com nenhum
   terminal (`citation:`, `note:`) — o rótulo precisa ser separado do valor.
3. **Nomes de campo que colidem com keywords** (`description:`, `code:`) chegam
   como `KW_*` e devem virar `property`, não `keyword`.

**Lição para a Fase 3:** derivar da gramática elimina a divergência de
*keywords*, não a necessidade de conhecer a *estrutura* da linguagem.

### 2.4 Corrigir o cache de passagem

O `_TOKENS_CACHE` atual tem dois defeitos que a reescrita não deve herdar:

1. **Chave por `hash(source)`** — hash de string do Python é salted por processo e colisível. Trocar por digest de conteúdo (ex.: `hashlib.blake2b`, rápido) ou comparação direta do texto.
2. **`_TOKENS_CACHE.clear()` mantém uma entrada global** — alternar entre dois arquivos abertos invalida sempre (thrashing). Trocar por cache **por URI**: `dict[uri] → (content_digest, relations, result)`, com invalidação natural em `didClose`.

### 2.5 Testes

Duas camadas complementares (uma testa o *desejado*, a outra detecta o *não previsto*):

1. **Characterization/golden tests (Feathers) — ANTES da reescrita:** capturar com o motor regex atual os tokens serializados de fixtures reais (`lattes.synt` completo e um `.syn` de projeto real), commitá-los como snapshot. Diferenças após a troca de motor devem ser **revisadas uma a uma**: as esperadas (DESCRIPTION corrigido, IDENTIFIES colorido) confirmam o objetivo; qualquer outra é regressão.
2. **Suíte nova** — recriar `tests/test_semantic_tokens.py` (o fonte sumiu; só restou `.pyc`). Casos: DESCRIPTION com keywords no corpo; GUIDELINES idem; `IDENTIFIES`/`REFERS TO`; chain com relações do template; bibref em SOURCE e ITEM; documento inválido; **teste de contrato** iterando `parser.terminals` e afirmando que todo `KW_*` da gramática recebe algum tokenType (falha em CI se alguém adicionar keyword sem cor — o invariante da propagação automática, executável).

---

## Fase 3 — Recalibrar o TextMate pelo critério de volatilidade

Há uma tensão que uma poda ingênua ignoraria: §2.2 justifica manter o TextMate *por causa* de hover e blocos ```` ```synesis ```` em Markdown — mas remover todas as listas finas de keywords deixaria exatamente esses contextos **mais pobres** do que hoje (o rust-analyzer mantém grammar completa por isso). A resolução consagrada é particionar por **volatilidade**, não por granularidade:

| Classe | Keywords | TextMate | Racional |
|---|---|---|---|
| **Estáveis** | `SOURCE ITEM ONTOLOGY FIELD END PROJECT TEMPLATE INCLUDE BIBLIOGRAPHY ANNOTATIONS FIELDS METADATA GUIDELINES DESCRIPTION TYPE SCOPE` + tipos (`TEXT CODE CHAIN MEMO QUOTATION DATE SCALE ENUMERATED ORDERED TOPIC`) | **Manter** | Mudá-las quebraria todo arquivo `.syn` existente — risco de dessincronização ≈ 0 por definição. Preservam a fidelidade do hover/markdown. |
| **Voláteis** | Modificadores em evolução: `IDENTIFIES`, `REFERS TO`, `ON`, `SHARED` e futuros | **Omitir** | São a fronteira ativa da gramática — exatamente onde a lista regex diverge. O LSP cobre no editor; no hover ficam sem cor, custo aceitável. |

Mudanças concretas:

1. **Adicionar `description_block`**, espelhando o `guidelines_block` existente, consumindo a linha inteira como `string.unquoted.description.synesis`. Corrige §1.2 nos contextos sem LSP.
2. **Reorganizar as listas de keywords** conforme a tabela acima, com comentário no JSON declarando o critério ("apenas keywords cuja mudança quebraria arquivos existentes — modificadores novos são responsabilidade do LSP").
3. Reverter a entrada `IDENTIFIES|REFERS\s+TO` adicionada como paliativo — é keyword volátil.

**Racional:** a lista não diverge porque só contém o que não pode mudar. A fronteira ativa da linguagem fica exclusivamente com o LSP, que a deriva da gramática.

**Verificação:** abrir `.synt` com `editor.semanticHighlighting.enabled: false` e confirmar: (a) blocos/tipos/comentários/strings coloridos; (b) nada colorido *errado* dentro de DESCRIPTION; (c) hover com código Synesis mantém a colorização de blocos e tipos.

---

## Fase 4 — Propagação ao ecossistema

**Auditoria realizada — escopo menor que o previsto.** O estudo supunha
duplicação de regex em três repositórios; a verificação encontrou apenas um.

| Alvo | Situação real | Ação |
|---|---|---|
| `synesis-lsp/blocks.py` | Fallback regex casa `^\s*SOURCE\s+@x` em qualquer linha, inclusive na prosa de `GUIDELINES`/`DESCRIPTION` → **reporta blocos fantasma** | **Migrado** |
| `synesis-graph` | Já consome `SynesisCompiler`. As regex existentes são para rótulos Cypher e sufixos de ID de nó — não parseiam Synesis | Nenhuma |
| `synesis-coder` | Já consome `synesis.compile_string` / `synesis.ast`. Regex são de processamento de texto e extração de resposta de LLM | Nenhuma |

A extração de blocos passou a degradar em escada — **AST → lexer → regex** —
com o regex mantido como último recurso.

**Ganho medido.** Onde o fallback realmente roda (documento inválido), lexer e
regex dão resultado idêntico em bloco aberto, indentação quebrada e bibref
unicode. A diferença aparece no caso do bloco fantasma:

```
SOURCE @real
    GUIDELINES
Exemplo de bloco:
SOURCE @ficticio        ← prosa, não declaração
    END GUIDELINES
END SOURCE

regex: [SOURCE @real, SOURCE @ficticio]   ← fantasma
lexer: [SOURCE @real]
```

**Custo:** 9.7ms (lexer) vs 1.5ms (regex) no `lattes.synt`. Aceitável: o
caminho só roda quando o documento não compila.

**Nota honesta:** o lexer sozinho *não* resolve isso — em coluna 1 ele também
emite `KW_SOURCE` para a prosa, porque o DEDENT fecha o bloco. Foi preciso
replicar o rastreamento de profundidade de texto livre da Fase 2. Confirma a
lição da §2.3: derivar da gramática elimina a divergência de *keywords*, não a
necessidade de conhecer a *estrutura*.

---

## 5. Sequenciamento e risco

| Fase | Entrega | Risco | Depende |
|---|---|---|---|
| 0 | Reverter paliativo | Nenhum | — |
| 1 | `lex_tokens()` + bump `synesis>=` | Baixo — API nova, aditiva | — |
| 2 | Reescrita do LSP (golden tests antes) | **Médio** — troca o motor | 1 |
| 3 | TextMate recalibrado por volatilidade | Baixo | 2 |
| 4 | Ecossistema | Baixo | 2 |

**Fase 2 é a única de risco real.** Mitigação em duas camadas: golden tests capturados com o motor atual (§2.5.1) detectam regressões não previstas; a suíte nova (§2.5.2) fixa o comportamento desejado. Rollback operacional: o gate `synesis.semanticHighlighting.enabled` já existente no cliente desliga o caminho novo sem release. Fases 1 e 2 são avaliáveis no editor antes de tocar no TextMate.

---

## Fase 5 — Ampliação do protocolo de testes

A reescrita expôs uma assimetria: as fixtures curadas cobrem bem a **gramática**
(38 das 39 keywords são exercitadas), mas mal a **camada semântica** e nada dos
caminhos de erro não antecipados. Três técnicas complementares, cada uma
validada por achar algo real.

### 5.1 Fuzzing de mutação — `tests/test_fuzz_robustness.py`

Muta fixtures válidas com seeds fixas e verifica o contrato: para qualquer
entrada, `compile_string()` compila ou levanta `SynesisSyntaxError` — nunca
exceção de biblioteca.

**Achou:** `lark.indenter.DedentError` vazava cru pela API pública. Indentação
inconsistente é erro comum de usuário; a CLI mostraria traceback. `parse_string`
capturava `UnexpectedToken`/`UnexpectedCharacters` mas não `DedentError`, e
nenhum consumidor tratava o tipo. **Corrigido** — a posição é recuperada
re-tokenizando com `lex_tokens()`, já que o `DedentError` não carrega linha.

### 5.2 Differential testing — `tests/test_grammar_differential.py`

Compara `synesis.lark` (fonte) com `synesis_standalone.py` (gerado). Previne o
modo de falha registrado na memória do projeto: editar a gramática sem
regenerar o standalone deixa a suíte verde e a mudança sem efeito.

**Armadilha encontrada na própria implementação:** a primeira versão comparava
só *nomes* de terminais e **não detectava drift**. Verifiquei injetando uma
alteração real no regex de `KW_IDENTIFIES` — os dois parsers divergiam de fato
(`KW_IDENTIFIES` vs `TEXT_LINE`), e os 77 testes passavam. Duas causas:

1. Lark **poda terminais não referenciados** por nenhuma regra — um terminal
   novo mas não usado nunca aparece em `.terminals`.
2. Alterar o *padrão* de um terminal existente mantém o conjunto de nomes
   idêntico.

Corrigido comparando a **assinatura** (nome + padrão regex) e o conjunto de
regras. Re-testado com a mesma injeção: agora falha e nomeia o terminal.

> Lição: um teste-guarda precisa ser verificado contra a falha que promete
> pegar. Sem a injeção deliberada, teria ficado no repositório dando confiança
> falsa.

### 5.3 Inventário do catálogo de erros — `tests/test_error_coverage.py`

Auditoria: **22 dos 69 códigos** `SYNESIS_E/W/I` sem nenhum teste — caminhos que
o usuário atinge e ninguém exercita.

Quatro cobertos com gatilho confirmado empiricamente (`E003`, `E022`, `W031`,
`E033`); o restante travado por um teste-catraca que falha se a dívida crescer
**e** avisa quando pode ser reduzida.

**Nota sobre a medição:** a primeira auditoria reportou 28/71, contando nomes de
classe. Os testes asseveram sobre **códigos**, não classes — refazendo a medição
pelo critério certo, são 22/69.

**Por que não Hypothesis:** cada código exige um projeto estruturalmente
específico (template + anotações + ontologia coerentes). Geração aleatória
produziria quase sempre os mesmos erros triviais (`E020`/`E022`). O gargalo é
construir o gatilho certo, não gerar volume.

**Também documentado:** `SYNESIS_E064` é compartilhado por `MissingProjectFile`,
`MissingTemplateFile` e `InvalidProjectFile` — ambiguidade de diagnóstico real,
mas renumerar quebra contrato com LSP e CLI. Travado por teste para não crescer
sem decisão explícita.

### 5.4 O que ficou de fora

- **Grammar fuzzer generativo** — menor retorno, dada a cobertura de 38/39
  keywords pelas fixtures.
- **Mutation testing** — com 15 códigos ainda sem teste, reportaria centenas de
  mutantes sobreviventes já conhecidos. Vale depois de reduzir a dívida de 5.3.
- **Property-based (Hypothesis)** — ver justificativa em 5.3.

---

## 6. Limitações assumidas

Registradas explicitamente para não serem redescobertas como bugs:

1. **O mapa `KW_* → tokenType` continua sendo tabela em código.** A propagação é automática para *existir cor* (via fallback), mas escolher *qual* cor para uma keyword nova é decisão manual. Só seria eliminável anotando a própria gramática — fora de escopo.

2. **Chain e bibref exigem pós-processamento.** Consequência direta do lexer contextual (§3.4). Não é dívida técnica: é o desenho correto dado o que o Lark entrega.

3. **TextMate permanece.** Não por dívida, mas por restrição do VSCode (§2.1) e pelo caso hover/markdown (§2.2). Duas camadas é o padrão consagrado, não um compromisso.

4. **Relações de chain vêm do template, não da gramática.** `relation_names` continua parâmetro. Fora do alcance de qualquer solução baseada só em gramática.

5. **Somente `semanticTokens/full` por ora.** O protocolo LSP oferece `full/delta` e `range` exatamente para o ciclo por-tecla; com 7ms medidos, não se justificam agora. Registrado aqui como evolução conhecida — se arquivos crescerem uma ordem de magnitude, implementar `range` primeiro (ganho maior, menor complexidade que `delta`).

6. **Keywords voláteis sem cor em hover/markdown** (consequência da Fase 3). Custo aceito conscientemente: a alternativa — lista completa no TextMate — é a causa raiz do bug §1.1. Se um modificador se tornar estável (anos sem mudança, uso disseminado), promovê-lo à lista estável é uma edição de uma linha.

---

## Referências

- [Semantic Highlight Guide — VSCode API](https://code.visualstudio.com/api/language-extensions/semantic-highlight-guide)
- [Syntax Highlight Guide — VSCode API](https://code.visualstudio.com/api/language-extensions/syntax-highlight-guide)
- [Semantic Highlighting Overview — microsoft/vscode Wiki](https://github.com/microsoft/vscode/wiki/Semantic-Highlighting-Overview)
- [rust-analyzer #4595 — TextMate grammar para hover](https://github.com/rust-lang/rust-analyzer/issues/4595)
- [Langium Discussion #604 — Extend or customize syntax highlighting](https://github.com/eclipse-langium/langium/discussions/604)
- [langium-cli — geração de TextMate](https://www.npmjs.com/package/langium-cli)
