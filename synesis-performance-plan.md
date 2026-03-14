# Synesis Compiler — Estudo de Performance Baseado em textX

> **Objetivo:** Identificar os pontos de maior impacto para melhorar a performance do compilador Synesis em projetos grandes, comparar com padrões arquiteturais do textX, e propor refatorações concretas mantendo 100% o estilo procedural do projeto.

> **Restrição inviolável:** Todas as sugestões usam apenas funções puras (ou com estado mínimo passado explicitamente), módulos simples e dataclasses leves. NENHUMA introdução de classes com herança, visitor pattern, ou abstrações OOP.

> **Coordenação com LSP:** Este plano coordena com o [synesis-lsp-performance-plan.md](../synesis-lsp/synesis-lsp-performance-plan.md) do LSP. A Fase 1 aqui (`synesis.ast.normalize.normalize_code`) é **pré-requisito** para a consolidação das 7 cópias de `_normalize_code` no synesis-lsp. A Fase 5 aqui (`synesis/parser/parse_cache.py`) será consumida pelo LSP — quando o LSP invalida cache de workspace (ao salvar `.synt`/`.synp`), deve chamar `parse_cache.invalidate_cache()` para garantir consistência.

---

## Sumário Executivo

O compilador Synesis já possui uma excelente base de performance: parser Lark LALR cacheado via `@lru_cache`, pipeline linear de 8 passes, e AST com dataclasses leves. Comparado ao textX, o Synesis é **mais eficiente** em parsing (LALR vs PEG) e **mais simples** em instanciação (lru_cache vs blueprint+clone). As oportunidades de melhoria estão em: (1) normalização de códigos repetida 14.000+ vezes, (2) parsing sequencial de múltiplos arquivos de anotação, (3) iterações redundantes sobre field_specs, (4) precompilação do parser para cold-start, e (5) cache por arquivo para compilação incremental. Este estudo propõe **5 otimizações** em **5 fases** independentes com verificação por fase.

---

## PARTE I — Arquitetura do textX (Referência)

### 1.1 Parser Blueprint + Clone

**Arquivos-chave:**
- `COMPILER_Study/textX/textx/lang.py` (linhas 1088-1157) — cache do parser de gramática
- `COMPILER_Study/textX/textx/model.py` (linhas 310-333) — clone do parser

O textX separa a **criação** do parser da sua **utilização** através do padrão Blueprint+Clone:

```
1. Grammar parsing (uma vez por sessão):
   textX_parsers[debug] → parser Arpeggio cacheado (meta-gramática)

2. Blueprint creation (uma vez por metamodelo):
   grammar → TextXVisitor → PEG rules (2-pass resolution)
   metamodel._parser_blueprint = lang_parser

3. Per-parse clone (a cada model_from_str):
   parser = self._parser_blueprint.clone()  → copy.copy() + reset state
   clone compartilha PEG rules, reseta _inst_stack, _instances, _crossrefs
```

**Comparação com Synesis:** O `@lru_cache(maxsize=1)` em `create_parser()` (`synesis/parser/lexer.py:71-83`) alcança o mesmo efeito de forma mais simples. O parser Lark LALR é criado uma vez e reutilizado em todas as chamadas a `parse_string()`. Não há necessidade de clone porque o Lark parser é stateless após construção — o estado de parsing é local à chamada `parser.parse()`.

**Veredito:** Synesis é equivalente e mais simples. Nenhuma mudança necessária.

### 1.2 Lazy Reference Resolution via ObjCrossRef

**Arquivos-chave:**
- `COMPILER_Study/textX/textx/model.py` (linhas 230-260) — placeholders ObjCrossRef
- `COMPILER_Study/textX/textx/model.py` (linhas 1068-1197) — ReferenceResolver

O textX usa **resolução deferida** de referências cruzadas:

```
Parsing Phase:
  → encontra referência → cria ObjCrossRef(obj_name, cls, scope_provider)
  → acumula em parser._crossrefs

Resolution Phase (após parsing completo):
  → ReferenceResolver.resolve_one_step() itera cross-refs
  → scope_provider(obj, attr, crossref) → objeto resolvido ou Postponed()
  → loop enquanto houver refs não resolvidas E progresso > 0
```

O padrão `Postponed()` permite dependências circulares e multi-arquivo.

**Comparação com Synesis:** O Synesis separa parsing (Transformer) de resolução (Linker) em passes explícitas. O pipeline garante ordem: ontologias antes de anotações, template antes de tudo. Não há referências circulares no domínio Synesis. A abordagem do Synesis é **mais eficiente** para o caso de uso (sem overhead de loop iterativo).

**Veredito:** Synesis é superior para o domínio. Nenhuma mudança necessária.

### 1.3 Meta-Modelo Leve vs AST Dataclasses

**Arquivo-chave:**
- `COMPILER_Study/textX/textx/metamodel.py` (linhas 131-163, 424-468) — TextXMetaClass, dynamic class creation

O textX cria classes Python dinamicamente a partir de regras da gramática. Cada regra → uma classe com `_tx_attrs` (OrderedDict de MetaAttr). Atributos são inicializados lazily se `auto_init_attributes=False`.

**Comparação com Synesis:** O Synesis usa dataclasses explícitas em `synesis/ast/nodes.py` (289 linhas). São mais leves que as classes dinâmicas do textX (sem metaclass overhead, sem `_tx_*` tracking). Acesso direto a campos sem interceptação.

**Veredito:** Synesis é mais eficiente. Dataclasses são a escolha ideal para AST procedural.

### 1.4 Object Processors vs Validator Explícito

O textX usa `obj_processors` registrados via `metamodel.register_obj_processors()`, chamados inline durante construção do modelo. Validação interleaved com construção.

**Comparação com Synesis:** O `SemanticValidator` (`synesis/semantic/validator.py`) roda como pass separada. Isto é **mais flexível** (pode validar relações cross-node como bundles e chains que requerem visão completa do nó) mas adiciona uma iteração extra sobre todos os nós.

**Veredito:** A separação do Synesis é correta para o domínio. O custo da iteração extra é linear e aceitável.

### 1.5 Precompilação de Gramática

O textX **não** precompila gramáticas — re-parseia o `.tx` a cada sessão (cacheado apenas in-process via dict). Arpeggio/PEG é inerentemente mais lento que LALR.

O Lark suporta **standalone mode** (`lark.tools.standalone`) que gera um módulo Python com tabelas LALR precompiladas. Isto elimina parsing de gramática e construção de tabelas no cold-start.

**Veredito:** Synesis tem vantagem potencial não explorada — standalone mode pode acelerar cold-start significativamente.

### 1.6 Arquivos-Chave do textX para Referência

| Arquivo | Localização | Padrão a Adaptar |
|---------|-------------|------------------|
| **lang.py** | `COMPILER_Study/textX/textx/lang.py:1088-1157` | Cache global de parser por chave |
| **model.py** | `COMPILER_Study/textX/textx/model.py:310-333` | Blueprint clone (shallow copy + reset) |
| **model.py** | `COMPILER_Study/textX/textx/model.py:230-260` | ObjCrossRef placeholders lazy |
| **model.py** | `COMPILER_Study/textX/textx/model.py:1068-1197` | ReferenceResolver multi-pass |
| **metamodel.py** | `COMPILER_Study/textX/textx/metamodel.py:424-468` | Dynamic class creation leve |
| **metamodel.py** | `COMPILER_Study/textX/textx/metamodel.py:578-608` | obj_processors inline |
| **scoping/providers.py** | `COMPILER_Study/textX/textx/scoping/providers.py` | Scope providers + Postponed() |

---

## PARTE II — Diagnóstico do Compilador Synesis Atual

### 2.1 Pipeline Atual (8 Passes)

```
compiler.py:99-133 — SynesisCompiler.compile()
═══════════════════════════════════════════════════════════

Pass 1: parse_project()           → parse .synp (1 arquivo, ~5ms)
Pass 2: load_template()           → parse .synt (1 arquivo, ~20ms)
Pass 3: load_bibliography()       → bibtexparser .bib (1 arquivo, ~10ms)
Pass 4: parse_ontologies()        → parse .syno (N arquivos, ~N×10ms)
Pass 5: parse_annotations()       → parse .syn (M arquivos, ~M×50ms)  ← MAIS PESADO
Pass 6: validate_all()            → SemanticValidator itera TUDO (~500ms para 2000 items)
Pass 7: link_all()                → Linker constrói índices (~300ms)
Pass 8: export (opcional)         → JSON/CSV/Excel (~100ms)

Total estimado (projeto grande):   ~3-4 segundos
```

### 2.2 O que já está BOM (não mexer)

| Componente | Arquivo | Por que é bom |
|------------|---------|---------------|
| Parser cacheado | `lexer.py:64-83` | `@lru_cache(maxsize=1)` em `load_grammar()` e `create_parser()` — zero overhead após primeira chamada |
| Lark LALR | `lexer.py:75-83` | Parsing linear O(n), deterministico, mais rápido que PEG |
| AST dataclasses | `nodes.py` | Leves, sem metaclass overhead, acesso direto |
| Transformer single-pass | `transformer.py` | Post-order traversal linear, sem passes intermediárias |
| Pipeline linear | `compiler.py:99-133` | Fluxo claro, sem dependências circulares |
| Context cache LSP | `lsp_adapter.py:90-161` | Cache workspace-scoped com mtime invalidation |

### 2.3 Os 7 Bottlenecks Identificados

#### Bottleneck #1: Normalização de Códigos Repetida (~14.000+ chamadas) — IMPACTO ALTO

**Localização:**
- `synesis/semantic/validator.py:546-547` — `_norm_code()` método
- `synesis/semantic/linker.py:416-417` — `_norm_code()` método (cópia idêntica)
- 7 cópias em `synesis-lsp/synesis_lsp/`: `explorer_requests.py:208`, `hover.py:151`, `graph.py:90`, `rename.py:247`, `references.py:202`, `definition.py:80`, `ontology_annotations.py:25`

**A função:**
```python
def _norm_code(self, code: str) -> str:
    return " ".join(code.strip().split()).lower()
```

**O problema:** Para um projeto com 500 conceitos de ontologia e 2000 items com 3 códigos cada:
- Validator `__post_init__`: 500 chamadas (normalizar ontology_index)
- Validator `_validate_codes_defined`: 6000 chamadas (3 códigos × 2000 items)
- Linker: 500 (ontology_index) + 6000 (code_usage) + 1000 (hierarchy) = 7500 chamadas
- **Total: ~14.000+ chamadas**, cada uma alocando lista intermediária via `split()` + join + lower

Além disso, o **mesmo código** é normalizado múltiplas vezes — uma vez no validator, outra no linker, outra no LSP. Sem compartilhamento de cache entre fases.

---

#### Bottleneck #2: Parsing Sequencial de Anotações (I/O bound) — IMPACTO ALTO

**Localização:** `synesis/compiler.py:161-172`

```python
def parse_annotations(self, project):
    paths = self._collect_include_paths(project, "ANNOTATIONS", allow_glob=True)
    sources, items = [], []
    for path in paths:                          # ← SEQUENCIAL
        nodes = self._parse_nodes(path)         # ← I/O + parse + transform por arquivo
        for node in nodes:
            if isinstance(node, SourceNode): sources.append(node)
            elif isinstance(node, ItemNode): items.append(node)
```

**O problema:** Para 20 arquivos de anotação, o loop é sequencial. Cada iteração faz:
1. `file_path.read_text()` — I/O disco
2. `parser.parse(content)` — LALR (rápido, mas blocked por I/O)
3. `SynesisTransformer(path).transform(tree)` — nova instância por arquivo

O parser Lark é thread-safe (stateless após criação). A transformação é per-file (instância isolada). **Paralelizar é seguro.**

---

#### Bottleneck #3: Iteração Redundante sobre `field_specs` no Validator — IMPACTO MÉDIO

**Localização:** `synesis/semantic/validator.py:563-573`

```python
def _collect_item_codes(self, node: ItemNode) -> list[str]:
    codes = list(node.codes)
    field_values = self._collect_fields(node)
    for name, spec in self.template.field_specs.items():   # ← itera TODOS os specs
        if spec.scope != Scope.ITEM or spec.type != FieldType.CODE:
            continue                                        # ← filtra runtime
        lname = name.lower()
        if lname in {"code", "codes"}:
            continue
        codes.extend(self._extract_code_values(field_values.get(name)))
    return codes
```

**O problema:** Para cada item (2000 items), itera todos os field_specs (20-30 entries) para encontrar os do tipo CODE no scope ITEM. O resultado é invariante — os mesmos specs são filtrados 2000 vezes. Deveria ser pré-computado uma vez no `__post_init__`.

**Mesmo padrão em:** `_has_chain_relations()` no linker (`linker.py:308-321`) — acessa `template.field_specs.get("chain")` em cada iteração do loop de items.

---

#### Bottleneck #4: Sem Cache por Arquivo para Compilação Incremental — IMPACTO MÉDIO

**Localização:** `synesis/compiler.py:247-252` e `synesis/lsp_adapter.py:90-161`

**O problema:** Quando o compilador (via CLI ou API) recompila um projeto:
- Todos os arquivos `.syn` são re-parseados, mesmo os que não mudaram
- O `lsp_adapter` tem cache de contexto (template/bib) por workspace, mas não de resultados de parse por arquivo
- Se 20 anotações existem e 1 muda, as outras 19 são re-parseadas desnecessariamente

**Padrão textX:** O `GlobalModelRepository` (`textX/textx/scoping/__init__.py:85-119`) cacheia modelos carregados para evitar re-loading. Synesis não tem equivalente para arquivos de anotação individuais.

---

#### Bottleneck #5: Cold-Start do Parser (primeira invocação) — IMPACTO MÉDIO

**Localização:** `synesis/parser/lexer.py:71-83`

```python
@lru_cache(maxsize=1)
def create_parser() -> Lark:
    grammar_text = load_grammar()
    return Lark(
        grammar_text,
        parser="lalr",
        lexer="contextual",
        regex=True,                    # ← compila regex Unicode (custoso)
        maybe_placeholders=False,
        postlex=SynesisIndenter(),
        propagate_positions=True,
    )
```

**O problema:** Na primeira chamada (cold-start), o Lark precisa:
1. Ler o arquivo `synesis.lark` (via `importlib.resources`)
2. Parsear a gramática (222 linhas EBNF)
3. Construir tabelas LALR
4. Compilar regex Unicode (`\p{L}`, `\p{N}` com `regex=True`)

Após a primeira chamada, `@lru_cache` elimina o custo. Mas em cenários onde cada invocação é um processo novo (CLI: `synesis compile`, `synesis check`), o cold-start é pago toda vez.

O Lark standalone mode gera um módulo Python importável com tabelas pré-computadas, eliminando passos 1-4.

---

#### Bottleneck #6: `SynesisTransformer` Instanciado por Arquivo — IMPACTO BAIXO

**Localização:** `synesis/compiler.py:249`

```python
def _parse_nodes(self, path: Path, only_type=None) -> List:
    tree = parse_file(path)
    nodes = SynesisTransformer(path).transform(tree)   # ← nova instância por arquivo
```

**O problema:** Um novo `SynesisTransformer` é criado para cada arquivo. A instanciação é barata (apenas armazena `file_path`), mas a chamada `super().__init__()` do Lark `Transformer` faz alguma reflexão sobre métodos.

**Severidade:** Muito baixa. Custo de instanciação é negligível comparado ao parsing.

---

#### Bottleneck #7: `_collect_fields()` Chamado Múltiplas Vezes por Nó — IMPACTO BAIXO

**Localização:** `synesis/semantic/validator.py:362-389`

**O problema:** `_collect_fields(node)` é chamada implicitamente em `_validate_declared_fields()` e em `_validate_fields()` e em `_collect_item_codes()`. A cada chamada, reconstrói um dict com aliases sintéticos (quote/quotation, code/codes, note/notes/memo/memos, chain/chains — 8+ entries criadas por reconstrução).

**Severidade:** Baixa. Dicts são rápidos em Python.

---

### 2.4 Fluxo Atual vs Fluxo Otimizado

```
FLUXO ATUAL (projeto com 20 anotações, 2000 items):
════════════════════════════════════════════════════

Parse 20 anotações SEQUENCIALMENTE:          20 × 50ms = ~1000ms
Validator itera 2000 items:
  _collect_item_codes: 2000 × 25 specs      = 50000 iterações
  _norm_code: ~14000 chamadas                = ~14000 split+join+lower
Linker _has_chain_relations: 2000 chamadas   = 2000 dict lookups redundantes

════════════════════════════════════════════════════
FLUXO OTIMIZADO (após todas as fases):
════════════════════════════════════════════════════

Parse 20 anotações EM PARALELO (4 workers):  ~300ms (vs 1000ms)
Validator com pre-índice:
  _collect_item_codes: lookup direto          = 2000 iterações (vs 50000)
  _norm_code com cache: ~500 unique + hits    = ~500 split+join+lower (vs 14000)
Linker com invariantes hoisted:
  has_relations: 1 chamada (vs 2000)

Ganho total estimado: ~40-50% em projetos grandes
```

---

## PARTE III — 5 Inconsistências Arquiteturais Synesis vs textX

### Inconsistência 1: Normalização Dispersa vs Centralizada

**textX:** Normalização case-insensitive ocorre na gramática (`ignore_case` flag no metamodelo). Nomes são armazenados como parseados mas comparados case-insensitively pelo próprio parser.

**Synesis:** Normalização ocorre em **3 camadas diferentes**:
- Transformer: `_normalize_field_name()` lowerca nomes ALL-CAPS (`CODE` → `code`)
- Validator: `_norm_code()` faz `split().join().lower()` (whitespace + case)
- Linker: `_norm_code()` — **cópia idêntica** da do Validator
- LSP: `_normalize_code()` — **7 cópias** em módulos diferentes

**Impacto:** O mesmo código é normalizado de formas potencialmente inconsistentes em lugares diferentes. Se um módulo usa `strip().lower()` e outro usa `split().join().lower()`, resultados podem divergir para códigos com whitespace interno.

**Alinhamento proposto:** Uma única função `normalize_code()` em módulo compartilhado, usada por compilador e LSP.

---

### Inconsistência 2: Cache Granular vs Monolítico

**textX:** `GlobalModelRepository` cacheia modelos individuais por arquivo. Quando um arquivo muda, apenas ele é re-parseado.

**Synesis:** Cache opera em dois extremos:
- **Parser:** Cacheado globalmente (bom)
- **Contexto LSP:** Cacheado por workspace (bom para template/bib)
- **Arquivos de anotação:** NENHUM cache individual. Recompilação requer re-parsear TODOS os `.syn`

**Impacto:** Para projetos com 20+ anotações onde apenas 1 muda, 95% do trabalho de parsing é desperdiçado.

**Alinhamento proposto:** Cache por arquivo `(path, mtime) → list[nodes]` no pipeline do compilador.

---

### Inconsistência 3: Pre-indexação de Tipos vs Iteração Runtime

**textX:** `MetaAttr` armazena tipo, multiplicidade e containment. Durante parsing, o tipo do campo é consultado diretamente — sem iteração sobre todos os atributos.

**Synesis:** O Validator itera `template.field_specs.items()` **inteiro** em cada chamada a `_collect_item_codes()` para filtrar por tipo CODE e scope ITEM. O resultado do filtro é invariante por compilação.

**Impacto:** O(total_specs × total_items) em vez de O(code_specs × total_items). Com 25 specs e 2000 items: 50.000 iterações vs ~6.000.

**Alinhamento proposto:** Pre-indexar `code_fields_by_scope` no `__post_init__` do Validator.

---

### Inconsistência 4: Precompilação de Gramática

**textX:** Não precompila gramáticas. Re-parseia `.tx` a cada sessão (PEG, mais lento).

**Synesis:** Não precompila gramáticas. Re-constrói tabelas LALR a cada sessão (mais rápido que PEG, mas ainda evitável).

**Ambos** pagam custo de cold-start desnecessário. O Lark oferece standalone mode que o textX/Arpeggio **não** oferece — vantagem não explorada pelo Synesis.

**Alinhamento proposto:** Usar `lark.tools.standalone` para eliminar cold-start.

---

### Inconsistência 5: Acumulação de Erros Heterogênea

**textX:** Falha rápido — exceções imediatas (`TextXSemanticError`, `TextXSyntaxError`). Sem acumulação.

**Synesis:** Acumula erros em `ValidationResult`, nunca lança durante validação. Porém, a acumulação é **inconsistente** entre Validator e Linker:
- Validator: retorna `ValidationResult` por chamada, requer merge manual em `compiler.py:254-257`
- Linker: acumula em `self.validation_result` interno, requer acesso externo em `compiler.py:207`

**Impacto:** Dois padrões de acumulação no mesmo pipeline criam risco de erros perdidos.

**Alinhamento proposto:** Unificar: o Linker poderia receber `ValidationResult` como parâmetro (como já faz) e popular diretamente, eliminando a necessidade de merge externo. Alternativamente, ambos retornam `ValidationResult` e o compilador faz merge (padrão atual do Validator, mais funcional/procedural).

---

## PARTE IV — 5 Otimizações Concretas (Estilo Procedural)

### Otimização 1: Consolidação + Cache de Normalização

> **Impacto:** ALTO | **Risco:** MUITO BAIXO | **Esforço:** 2h

**O que:** Criar uma única função `normalize_code()` compartilhada com cache opcional por compilação.

**Pseudocódigo procedural:**

```python
# NOVO ARQUIVO: synesis/ast/normalize.py (módulo puro, sem classes)

def normalize_code(code: str, cache: dict | None = None) -> str:
    """Normaliza código: colapsa whitespace e converte para lowercase."""
    if cache is not None and code in cache:
        return cache[code]
    result = " ".join(code.strip().split()).lower()
    if cache is not None:
        cache[code] = result
    return result

def normalize_bibref(bibref: str) -> str:
    """Normaliza bibref: remove @ e converte para lowercase."""
    return bibref.lstrip("@").strip().lower()
```

**Uso no pipeline (compiler.py):**
```python
def compile(self) -> CompilationResult:
    norm_cache = {}  # compartilhado entre validator e linker

    # ... parsing ...

    validator = SemanticValidator(template, bibliography, ontology_index,
                                  norm_cache=norm_cache)
    # ... validação ...

    linker = Linker(sources, items, ontologies, project=project,
                    template=template, norm_cache=norm_cache)
    # ... linking ...
```

**Uso no validator (substituir método por chamada):**
```python
# ANTES (validator.py:546-547):
def _norm_code(self, code: str) -> str:
    return " ".join(code.strip().split()).lower()

# DEPOIS:
from synesis.ast.normalize import normalize_code

# Em cada uso: normalize_code(code, self.norm_cache)
```

**Arquivos afetados:**
- Novo: `synesis/ast/normalize.py`
- Modificar: `synesis/semantic/validator.py` — remover `_norm_code`, importar `normalize_code`, adicionar `norm_cache` param
- Modificar: `synesis/semantic/linker.py` — remover `_norm_code`, importar `normalize_code`, adicionar `norm_cache` param
- Modificar: `synesis/compiler.py` — criar e passar `norm_cache`
- Modificar: `synesis/lsp_adapter.py` — importar `normalize_code` do compilador

**Coordenação LSP:** Após esta fase, a Fase 0 do LSP ([synesis-lsp-performance-plan.md](../synesis-lsp/synesis-lsp-performance-plan.md)) deve ser executada para substituir as 7 cópias de `_normalize_code` nos módulos LSP por `from synesis.ast.normalize import normalize_code`.

---

### Otimização 2: Pre-indexação de Field Specs no Validator

> **Impacto:** MÉDIO | **Risco:** BAIXO | **Esforço:** 1h

**O que:** No `__post_init__` do Validator, pré-computar quais fields são do tipo CODE por scope.

**Pseudocódigo procedural:**

```python
# validator.py — Adicionar ao __post_init__

def __post_init__(self) -> None:
    self.ontology_index = {
        normalize_code(key, self.norm_cache): value
        for key, value in self.ontology_index.items()
    }

    # PRE-INDEXAR: fields CODE por scope (invariante por compilação)
    self._code_fields_by_scope: dict[Scope, list[str]] = {}
    self._chain_spec = None
    if self.template:
        for name, spec in self.template.field_specs.items():
            if spec.type == FieldType.CODE:
                self._code_fields_by_scope.setdefault(spec.scope, []).append(name)
            if spec.type == FieldType.CHAIN and name.lower() == "chain":
                self._chain_spec = spec

# Então _collect_item_codes torna-se:
def _collect_item_codes(self, node: ItemNode) -> list[str]:
    codes = list(node.codes)
    field_values = self._collect_fields(node)
    for name in self._code_fields_by_scope.get(Scope.ITEM, []):
        if name.lower() in {"code", "codes"}:
            continue
        codes.extend(self._extract_code_values(field_values.get(name)))
    return codes
```

**Também no Linker — hoist invariantes:**

```python
# linker.py — No início de link(), antes do loop de items

def link(self) -> LinkedProject:
    # Computar UMA VEZ (não por item/chain)
    has_relations = self._has_chain_relations()
    code_field_names = self._get_code_field_names()

    # ... usar has_relations e code_field_names nos loops ...
```

**Arquivos afetados:**
- `synesis/semantic/validator.py` — `__post_init__`, `_collect_item_codes`
- `synesis/semantic/linker.py` — início de `link()`

---

### Otimização 3: Lark Standalone Mode (Precompiled Parser)

> **Impacto:** MÉDIO (cold-start) | **Risco:** BAIXO | **Esforço:** 2h

**O que:** Gerar módulo Python com tabelas LALR precompiladas para eliminar custo de cold-start.

**Pseudocódigo procedural:**

```python
# lexer.py — Modificar create_parser para preferir standalone

@lru_cache(maxsize=1)
def create_parser() -> Lark:
    """Cria parser LALR, preferindo versão precompilada se disponível."""
    try:
        from synesis.grammar.synesis_standalone import Lark_StandAlone
        return Lark_StandAlone(postlex=SynesisIndenter())
    except ImportError:
        # Fallback: compilar da gramática (modo desenvolvimento)
        grammar_text = load_grammar()
        return Lark(
            grammar_text,
            parser="lalr",
            lexer="contextual",
            regex=True,
            maybe_placeholders=False,
            postlex=SynesisIndenter(),
            propagate_positions=True,
        )
```

**Script de build (novo):**
```bash
# generate_standalone.sh
python -m lark.tools.standalone \
    synesis/grammar/synesis.lark \
    > synesis/grammar/synesis_standalone.py
```

**Advertência:** O Lark standalone mode pode não suportar `regex=True` (que habilita `\p{L}`/`\p{N}` via módulo `regex`). **Deve ser verificado antes de implementar.** Se incompatível, há duas alternativas:
1. Reescrever tokens Unicode sem `\p{L}`/`\p{N}` (usar ranges explícitos)
2. Manter o fallback e usar standalone apenas quando `regex` não é necessário

**Arquivos afetados:**
- `synesis/parser/lexer.py` — `create_parser()`
- Novo: `synesis/grammar/synesis_standalone.py` (gerado)
- Novo: script de build

---

### Otimização 4: Parsing Paralelo de Anotações

> **Impacto:** ALTO para projetos grandes | **Risco:** MÉDIO | **Esforço:** 2h

**O que:** Parsear múltiplos arquivos `.syn` em paralelo usando `ThreadPoolExecutor`.

**Pseudocódigo procedural:**

```python
# compiler.py — Modificar parse_annotations

from concurrent.futures import ThreadPoolExecutor

def parse_annotations(self, project: ProjectNode) -> tuple[list, list]:
    paths = self._collect_include_paths(project, "ANNOTATIONS", allow_glob=True)

    if len(paths) <= 2:
        # Não vale paralelizar para 1-2 arquivos
        return self._parse_annotations_sequential(paths)

    # Garantir que o parser está cacheado ANTES de spawnar threads
    from synesis.parser.lexer import create_parser
    create_parser()  # popula lru_cache no thread principal

    sources, items = [], []
    with ThreadPoolExecutor(max_workers=min(4, len(paths))) as executor:
        results = list(executor.map(_parse_single_annotation, paths))

    for file_sources, file_items in results:
        sources.extend(file_sources)
        items.extend(file_items)
    return sources, items

def _parse_annotations_sequential(self, paths):
    """Fallback sequencial."""
    sources, items = [], []
    for path in paths:
        nodes = self._parse_nodes(path)
        for node in nodes:
            if isinstance(node, SourceNode): sources.append(node)
            elif isinstance(node, ItemNode): items.append(node)
    return sources, items


# Função de nível de módulo (não método) para ser picklable
def _parse_single_annotation(path: Path) -> tuple[list, list]:
    """Parseia uma anotação. Thread-safe: parser cacheado, transformer per-file."""
    from synesis.parser.lexer import parse_file
    from synesis.parser.transformer import SynesisTransformer
    from synesis.ast.nodes import SourceNode, ItemNode

    tree = parse_file(path)
    nodes = SynesisTransformer(path).transform(tree)
    sources = [n for n in nodes if isinstance(n, SourceNode)]
    items = [n for n in nodes if isinstance(n, ItemNode)]
    return sources, items
```

**Requisitos de thread-safety:**
1. ✅ Lark LALR parser é stateless após construção (cacheado via `lru_cache`)
2. ✅ `SynesisTransformer` é instanciado por arquivo (sem estado compartilhado)
3. ⚠️ `SynesisIndenter` — verificar se Lark cria cópia por `parse()` ou reutiliza. Se reutiliza, é **blocker**.

**Verificação de segurança necessária:** Testar com `ThreadPoolExecutor(max_workers=4)` parseando 4 arquivos simultaneamente e comparar resultados com parsing sequencial.

**Arquivos afetados:**
- `synesis/compiler.py` — `parse_annotations`, nova `_parse_single_annotation`

---

### Otimização 5: Cache por Arquivo para Compilação Incremental

> **Impacto:** ALTO para recompilações | **Risco:** BAIXO | **Esforço:** 2-3h

**O que:** Cachear resultado de parse por arquivo `(path, mtime) → nodes`, evitando re-parsing de arquivos não modificados.

**Pseudocódigo procedural:**

```python
# NOVO: synesis/parser/parse_cache.py (módulo puro, sem classes)

import os
from pathlib import Path
from typing import Optional

# Cache global por processo (similar ao padrão textX GlobalModelRepository)
_parse_cache: dict[tuple[str, float], list] = {}

def get_cached_nodes(path: Path) -> Optional[list]:
    """Retorna nós cacheados se arquivo não mudou, ou None."""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None

    key = (str(path.resolve()), mtime)
    return _parse_cache.get(key)

def put_cached_nodes(path: Path, nodes: list) -> None:
    """Armazena nós no cache."""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return

    key = (str(path.resolve()), mtime)

    # Limpar entradas antigas do mesmo arquivo
    to_remove = [k for k in _parse_cache if k[0] == str(path.resolve()) and k[1] != mtime]
    for k in to_remove:
        del _parse_cache[k]

    _parse_cache[key] = nodes

def invalidate_cache() -> None:
    """Limpa todo o cache (ex: após mudança em .synt)."""
    _parse_cache.clear()
```

**Uso no compiler.py:**

```python
# compiler.py — Modificar _parse_nodes

from synesis.parser.parse_cache import get_cached_nodes, put_cached_nodes

def _parse_nodes(self, path: Path, only_type=None) -> list:
    # Tentar cache
    cached = get_cached_nodes(path)
    if cached is not None:
        if only_type:
            return [n for n in cached if isinstance(n, only_type)]
        return cached

    # Cache miss: parsear
    tree = parse_file(path)
    nodes = SynesisTransformer(path).transform(tree)

    # Armazenar no cache
    put_cached_nodes(path, nodes)

    if only_type:
        return [n for n in nodes if isinstance(n, only_type)]
    return nodes
```

**Nota:** Este cache é útil quando o compilador é invocado múltiplas vezes no mesmo processo (ex: testes, LSP via `lsp_adapter`, API). Para CLI (`synesis compile`), cada invocação é um processo novo — o cache não persiste. Para persistência cross-processo, seria necessário serializar AST (escopo futuro).

**Coordenação LSP:** O `synesis-lsp` deve chamar `invalidate_cache()` quando arquivos de contexto (`.synt`, `.synp`, `.bib`) mudam. Sem isso, nós cacheados podem ser reutilizados com template desatualizado. Ver Fase 2 do LSP ([synesis-lsp-performance-plan.md](../synesis-lsp/synesis-lsp-performance-plan.md)) — comentário no `did_save`.

**Arquivos afetados:**
- Novo: `synesis/parser/parse_cache.py`
- Modificar: `synesis/compiler.py` — `_parse_nodes`

---

## PARTE V — Fases de Implementação

### Dependências entre Fases

```
Fase 1 (Normalização)        ─── independente ─── fundação para Fase 2
  │
  ▼
Fase 2 (Pre-indexação)       ─── depende da Fase 1 (usa normalize_code)

Fase 3 (Standalone)          ─── totalmente independente

Fase 4 (Parallelismo)        ─── totalmente independente

Fase 5 (Cache por arquivo)   ─── totalmente independente, combina com Fase 4
```

### Cronograma Sugerido

| Sprint | Fase | Foco | Esforço | Risco |
|--------|------|------|---------|-------|
| **Sprint 1** | Fase 1 | Consolidar normalização + cache | ~2h | Muito baixo |
| **Sprint 2** | Fase 2 | Pre-indexar field specs | ~1h | Baixo |
| **Sprint 3** | Fase 3 | Standalone parser (verificar `regex=True`) | ~2h | Baixo-Médio |
| **Sprint 4** | Fase 4 | Parsing paralelo (verificar thread-safety) | ~2h | Médio |
| **Sprint 5** | Fase 5 | Cache por arquivo | ~2-3h | Baixo |

### Impacto Cumulativo Estimado

| Cenário | Antes | Após Todas as Fases | Redução |
|---------|-------|---------------------|---------|
| Normalização (14000 chamadas) | 14000 split+join+lower | ~500 unique + cache hits | **~96%** chamadas eliminadas |
| Parse 20 anotações (sequencial) | 20 × 50ms = 1000ms | ~300ms (4 workers) | **~70%** tempo de parse |
| Validator field iteration (2000 items) | 2000 × 25 specs = 50000 iter | 2000 × 3 code_specs = 6000 iter | **~88%** iterações eliminadas |
| Cold-start parser | ~100-200ms | ~5-10ms (standalone) | **~95%** |
| Recompilação (1 arquivo mudou) | Re-parse 20 arquivos | Re-parse 1 arquivo | **~95%** |

---

## PARTE VI — Verificação por Fase (Projetos Reais)

> **Projetos de teste:** Todos os testes usam projetos reais da pasta `case-studies/` (repositório irmão).
>
> | Projeto | Caminho | Escala | Uso |
> |---------|---------|--------|-----|
> | **Basic** | `case-studies/Basic/project.synp` | 1 source, 1 item, 2 ontologies | Smoke test |
> | **AIDS Corpus** | `case-studies/Sociology/iramuteq_aids_corpus/aids_corpus.synp` | 5 sources, 5 items, 2 ontologies | Funcional pequeno |
> | **Social Acceptance** | `case-studies/Sociology/Social_Acceptance/social_acceptance.synp` | 484 sources, 1614 items, 1388 ontologies | Benchmark médio |
> | **Thompson** | `case-studies/Theology/Thompson_Chain_Reference/thompson_bible.synp` | 1 source, 15757 items, 1728 ontologies | Stress test grande |
> | **Nave** | `case-studies/Theology/Nave_Topical_Concordance/nave.synp` | 1 source, 82826 items, 5317 ontologies | Escala máxima |

### Fase 1: Consolidação de Normalização

```bash
# 1. Testes unitários existentes
pytest tests/ -v

# 2. Smoke test — Basic (compilação mínima)
synesis compile ../case-studies/Basic/project.synp --output-json /tmp/basic_after.json
# Comparar com output gerado ANTES da mudança (salvo previamente)
diff /tmp/basic_before.json /tmp/basic_after.json  # deve ser idêntico

# 3. Volume test — Social Acceptance (1388 ontologias = ~14000 chamadas normalize)
synesis compile ../case-studies/Sociology/Social_Acceptance/social_acceptance.synp \
    --output-json /tmp/sa_after.json
diff /tmp/sa_before.json /tmp/sa_after.json  # deve ser idêntico

# 4. Stress test — Nave (5317 ontologias, 82826 items)
synesis compile ../case-studies/Theology/Nave_Topical_Concordance/nave.synp \
    --output-json /tmp/nave_after.json
diff /tmp/nave_before.json /tmp/nave_after.json  # deve ser idêntico

# 5. Verificar que cache dict é populado (via log ou debugger)
# normalize_code("  FOO  BAR  ", cache) == "foo bar"
# Segunda chamada com mesmo input → cache hit (sem split/join)
```

### Fase 2: Pre-indexação de Field Specs

```bash
# 1. Testes unitários
pytest tests/test_validator.py -v
pytest tests/test_linker.py -v

# 2. Social Acceptance — projeto com CODE fields, bundles e chains
synesis compile ../case-studies/Sociology/Social_Acceptance/social_acceptance.synp \
    --output-json /tmp/sa_phase2.json
diff /tmp/sa_before.json /tmp/sa_phase2.json  # deve ser idêntico

# 3. Basic — edge case com template mínimo (poucos field_specs)
synesis compile ../case-studies/Basic/project.synp \
    --output-json /tmp/basic_phase2.json
diff /tmp/basic_before.json /tmp/basic_phase2.json  # deve ser idêntico

# 4. Thompson — 15757 items exercitam o loop otimizado intensivamente
synesis compile ../case-studies/Theology/Thompson_Chain_Reference/thompson_bible.synp \
    --output-json /tmp/thompson_phase2.json
diff /tmp/thompson_before.json /tmp/thompson_phase2.json  # deve ser idêntico
```

### Fase 3: Standalone Parser

```bash
# 1. Gerar standalone
python -m lark.tools.standalone synesis/grammar/synesis.lark > synesis/grammar/synesis_standalone.py

# 2. Equivalência de AST — parsear TODOS os projetos com ambos os parsers
# Para cada .syn/.syno/.synp dos 5 projetos:
#   parse_with_standalone(content).pretty() == parse_with_grammar(content).pretty()
# Projetos a testar:
#   - Basic (1 .syn, 1 .syno) — mínimo
#   - AIDS Corpus (1 .syn, 1 .syno) — pequeno
#   - Social Acceptance (1 .syn, 1 .syno) — médio, 18819+20819 linhas
#   - Thompson (1 .syn, 1 .syno) — grande, 78787+6911 linhas
#   - Nave (1 .syn, 1 .syno) — máximo, 489898+21267 linhas

# 3. Benchmark cold-start (limpar lru_cache entre medições)
# Medir create_parser() com Nave como payload (arquivo mais pesado para exercitar parser)
# Esperado: standalone ~5-10ms vs grammar ~100-200ms

# 4. CI: adicionar step que regenera standalone e verifica diff
```

### Fase 4: Parsing Paralelo

```bash
# NOTA: Os projetos atuais em case-studies/ usam 1 arquivo .syn por projeto.
# Paralelismo é relevante quando INCLUDE ANNOTATIONS referencia múltiplos arquivos.
# Para verificação funcional, usar projetos existentes e confirmar que NÃO há regressão.

# 1. Determinismo — compilar Social Acceptance 20 vezes
for i in $(seq 1 20); do
    synesis compile ../case-studies/Sociology/Social_Acceptance/social_acceptance.synp \
        --output-json /tmp/sa_run_$i.json
done
# Verificar: todos os 20 outputs idênticos
md5sum /tmp/sa_run_*.json | awk '{print $1}' | sort -u | wc -l  # deve ser 1

# 2. Fallback sequencial — Basic (1 arquivo) deve usar path sequencial
synesis compile ../case-studies/Basic/project.synp  # logs: "sequential path"

# 3. Stress test sem regressão — Nave (489K linhas, 1 arquivo)
synesis compile ../case-studies/Theology/Nave_Topical_Concordance/nave.synp \
    --output-json /tmp/nave_phase4.json
diff /tmp/nave_before.json /tmp/nave_phase4.json  # deve ser idêntico

# 4. FUTURO: Quando existir projeto com múltiplos .syn (split annotations),
#    medir wall-clock sequencial vs paralelo (4 workers)
```

### Fase 5: Cache por Arquivo

```bash
# 1. Cache hit — compilar Social Acceptance duas vezes consecutivas
synesis compile ../case-studies/Sociology/Social_Acceptance/social_acceptance.synp
# → logs: parse + transform para todos os arquivos
synesis compile ../case-studies/Sociology/Social_Acceptance/social_acceptance.synp
# → logs: "cache hit" para .syn e .syno (mtime não mudou)

# 2. Cache invalidação parcial — tocar apenas o .syn
touch ../case-studies/Sociology/Social_Acceptance/social_acceptance.syn
synesis compile ../case-studies/Sociology/Social_Acceptance/social_acceptance.synp
# → logs: cache miss para .syn, cache hit para .syno

# 3. Cache invalidação total — tocar o .synt (contexto)
touch ../case-studies/Sociology/Social_Acceptance/social_acceptance.synt
synesis compile ../case-studies/Sociology/Social_Acceptance/social_acceptance.synp
# → logs: todos os caches invalidados (parse_cache.invalidate_cache())

# 4. Output idêntico com e sem cache
synesis compile ../case-studies/Theology/Thompson_Chain_Reference/thompson_bible.synp \
    --output-json /tmp/thompson_nocache.json
synesis compile ../case-studies/Theology/Thompson_Chain_Reference/thompson_bible.synp \
    --output-json /tmp/thompson_cached.json
diff /tmp/thompson_nocache.json /tmp/thompson_cached.json  # deve ser idêntico
```

### Benchmark Template (medir antes e depois de cada fase)

```
| Projeto            | Items  | Ontologias | Antes (ms) | Depois (ms) | Redução |
|--------------------|--------|------------|------------|-------------|---------|
| Basic              | 1      | 2          |            |             |         |
| AIDS Corpus        | 5      | 2          |            |             |         |
| Social Acceptance  | 1614   | 1388       |            |             |         |
| Thompson           | 15757  | 1728       |            |             |         |
| Nave               | 82826  | 5317       |            |             |         |
```

Medir com:
```python
import time
t0 = time.perf_counter()
result = compiler.compile()
elapsed = (time.perf_counter() - t0) * 1000
print(f"{elapsed:.1f}ms")
```

### Checklist de Segurança por Fase

| Fase | O que NÃO pode quebrar | Projeto de Teste | Indicador de falha |
|------|------------------------|------------------|-------------------|
| 1 | Validação de códigos undefined | Social Acceptance (1388 ontologias) | Códigos válidos reportados como undefined |
| 2 | Validação de bundles e chains | Social Acceptance (chains complexos) | Bundle violations não detectadas |
| 3 | Parsing de qualquer arquivo válido | Todos os 5 projetos | Parse errors em arquivos válidos |
| 4 | Ordem de items e sources | Social Acceptance (484 sources) | Items associados a sources erradas |
| 5 | Diagnósticos após edição | Thompson (15757 items) | Diagnósticos stale (de cache desatualizado) |

---

*Documento gerado em: 2026-03-13*
*Baseado em: textX (COMPILER_Study/) + synesis v0.2.6*
*Estilo: 100% procedural — funções puras, dataclasses leves, sem OOP*
