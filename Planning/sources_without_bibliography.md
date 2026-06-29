# Estudo de Viabilidade: SOURCE sem Vínculo Bibliográfico Obrigatório

## Contexto

A proposta desvincula o conceito de **SOURCE** da obrigatoriedade de uma referência bibliográfica externa, mantendo o identificador único (`@bibref`) como chave interna da linguagem. A validação bibliográfica passa a depender da presença de `INCLUDE BIBLIOGRAPHY` no projeto: quando presente, os identificadores são verificados contra a base; quando ausente, os identificadores são tratados como chaves internas válidas sem correspondência externa exigida.

---

## Estado Atual do Compilador

### O que já funciona assim

A análise do código revela que o compilador **já implementa parcialmente esse comportamento**:

- **`INCLUDE BIBLIOGRAPHY` é opcional** no `.synp` — o compilador retorna `{}` se ausente, sem erro.
- **`semantic/validator.py:_validate_bibref()`** verifica `if self.bibliography is None: return` — se a bibliografia está vazia, a validação de bibrefs é **silenciosamente ignorada**.
- **`lsp_adapter.py`** passa `bibliography=None` ao `SemanticValidator` quando não há .bib disponível — mesma omissão silenciosa.

Em outras palavras: **projetos sem `INCLUDE BIBLIOGRAPHY` já aceitam qualquer `@identificador` em SOURCE sem erro.** A proposta está, em grande medida, *já implementada por omissão*.

Adicionalmente, a **consistência interna entre SOURCEs é garantida independentemente da bibliografia**: a detecção de chaves duplicadas (`DuplicateSourceBibref`, E070) opera sobre a lista de `SourceNode` do projeto via `normalize_bibref()`, sem consultar o arquivo `.bib`. Isso ocorre tanto no compilador (`semantic/linker.py:_check_duplicate_source_bibrefs`) quanto no LSP adapter (`lsp_adapter.py`, validação por arquivo). Portanto, a ausência de `INCLUDE BIBLIOGRAPHY` **não cria risco de inconsistência interna**: dois SOURCEs com a mesma chave continuam sendo detectados e reportados como E070.

### O que ainda está acoplado

| Ponto de acoplamento | Arquivo | Detalhe |
|---|---|---|
| Gramática: `BIBREF` obrigatório no `source_block` | `grammar/synesis.lark` | `source_block: KW_SOURCE BIBREF ...` — `@` e identificador são exigidos sintaticamente |
| `SourceNode.bibref: str` obrigatório | `ast/nodes.py` | Campo requerido no dataclass |
| `BIBREF` token restrito a `@[a-zA-Z][a-zA-Z0-9_-]*` | `grammar/synesis.lark` | Identificador deve começar com letra |
| Mensagem de erro E001 nomeia o conceito como "referência bibliográfica" | `ast/results.py` | Texto pedagógico descreve o problema como "não encontrado no arquivo .bib" |
| `DuplicateSourceBibref` (E070) — nome do erro | `ast/results.py` | Nome da classe implica vínculo com bib |
| Documentação/mensagens de erro | vários | "bibref", "bibliography", "BibTeX" em mensagens visíveis ao usuário |

---

## Análise de Impacto por Componente

### 1. Gramática (`grammar/synesis.lark`) — **Impacto: ZERO**

O token `BIBREF` (`@identificador`) **não precisa ser renomeado ou alterado**. Ele já funciona como chave interna: o `@` é um prefixo sintático que sinaliza "este é um identificador de fonte", não "este deve estar em um .bib". A gramática está congelada para v1.x — nenhuma mudança é necessária ou desejável.

### 2. AST (`ast/nodes.py`) — **Impacto: ZERO**

`SourceNode.bibref: str` permanece como está. O campo armazena a chave interna da fonte — o nome "bibref" é uma convenção interna que não precisa mudar para que a semântica do identificador se amplie.

### 3. Compilador (`compiler.py`) — **Impacto: MÍNIMO**

A lógica de `load_bibliography()` já retorna `{}` quando não há `INCLUDE BIBLIOGRAPHY`. Nenhuma alteração estrutural é necessária.

Única revisão possível: tornar o comportamento explícito na documentação de código (comentário em `load_bibliography`), não no comportamento em si.

### 4. Validador Semântico (`semantic/validator.py`) — **Impacto: BAIXO**

`_validate_bibref()` já pula a validação se `self.bibliography is None`. O comportamento correto já existe.

Revisão possível: a condição atual é `if self.bibliography is None: return` — mas quando não há `INCLUDE BIBLIOGRAPHY`, o compilador passa `{}` (dicionário vazio), não `None`. Verificar se a condição deveria ser `if not self.bibliography: return`. **Isso pode ser um bug latente** onde projetos sem bib ainda tentam validar bibrefs contra um dicionário vazio, gerando E001 para todas as fontes.

> **Ação recomendada:** Auditar `_validate_bibref()` para confirmar que `bibliography = {}` (sem declaração de bib) e `bibliography = None` (contexto LSP sem bib) produzem o mesmo comportamento (sem validação).

### 5. LSP Adapter (`lsp_adapter.py`) — **Impacto: ZERO**

Já passa `bibliography=None` quando não há .bib disponível. Comportamento correto.

### 6. Mensagens de Erro (`ast/results.py`) — **Impacto: BAIXO (cosmético)**

Os erros E001 (`UnregisteredSource`), E063 (`MissingBibliographyFile`) e E072 (`MalformedBibliographyEntry`) têm mensagens que mencionam "arquivo .bib" e "referência bibliográfica". Na proposta ampliada, essas mensagens continuam corretas **para projetos com bibliografia** — são exibidas apenas quando `INCLUDE BIBLIOGRAPHY` está presente. Nenhuma alteração urgente.

Revisão futura possível: generalizar a mensagem de E001 para "identificador de fonte não encontrado na bibliografia declarada" — mas isso é refinamento, não bloqueador.

### 7. Erros de Estrutura de Projeto — **Impacto: ZERO**

- `MissingBibliographyFile` (E063): só é disparado quando `INCLUDE BIBLIOGRAPHY` está declarado mas o arquivo não existe. Comportamento permanece correto.
- `MalformedBibliographyEntry` (E072): idem — só relevante quando há bib.

### 8. synesis-lsp, synesis-explorer, synesis-graph — **Impacto: ZERO**

Nenhum desses componentes assume que toda SOURCE tem correspondência em .bib. Todos consomem a estrutura compilada via `synesis.load()` ou LSP diagnostics — se o compilador aceita o SOURCE sem erro, o ecossistema inteiro aceita.

---

## Veredicto de Viabilidade

| Dimensão | Avaliação |
|---|---|
| **Compatibilidade retroativa** | Total — projetos com bib continuam funcionando identicamente |
| **Esforço de implementação** | Muito baixo — o comportamento já existe por omissão |
| **Risco arquitetural** | Baixo — nenhuma mudança na gramática ou no AST |
| **Consistência da linguagem** | Alta — `@identificador` como chave interna já é o modelo mental correto |
| **Escopo de aplicação expandido** | Significativo — pesquisa qualitativa, campo, documentos institucionais, vídeos, entrevistas |

**A proposta é viável e o mecanismo central já está implementado.**

---

## Itens Pendentes para Formalização

### P1 — Verificação de bug latente (prioritário)

Auditar `_validate_bibref()` em `semantic/validator.py` para confirmar o comportamento quando `bibliography = {}` vs `bibliography = None`. Se a condição atual `if self.bibliography is None` não cobre o caso `{}`, projetos sem bib podem estar recebendo E001 espúrios. Corrigir para `if not self.bibliography`.

### P2 — Teste explícito de cobertura

Adicionar teste em `tests/` cobrindo o cenário: projeto com múltiplos SOURCEs usando identificadores arbitrários (`@entrevista_01`, `@doc_institucional`, `@campo_2024`), sem `INCLUDE BIBLIOGRAPHY`, compilando sem erros E001.

### P3 — Documentação (baixa prioridade)

Atualizar docstring de `load_bibliography()` e comentário em `_validate_bibref()` para tornar explícito que a validação bibliográfica é opcional e condicional à presença de `INCLUDE BIBLIOGRAPHY`.

### P4 — Mensagens de erro (opcional, v0.6+)

Generalizar texto de E001 de "referência não encontrada no arquivo .bib" para "identificador de fonte não encontrado na bibliografia declarada" — mais preciso para o modelo conceitual ampliado.

---

## Conclusão

A separação conceitual entre "identificador de fonte" e "referência bibliográfica" já está presente na arquitetura do compilador. A proposta não requer nenhuma alteração breaking, não toca na gramática congelada, e não cria tipos novos de SOURCE. O único trabalho real é (P1) confirmar/corrigir o comportamento quando `bibliography = {}` e (P2) cobrir o cenário com testes. O restante é documentação e refinamento de mensagens.
