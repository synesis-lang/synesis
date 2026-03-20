# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.7] - 2026-03-19

### Fixed
- **Race condition no parser paralelo** (`synesis/parser/lexer.py`)
  - O `SynesisIndenter` era singleton via `@lru_cache`, compartilhado entre todas as threads do `ThreadPoolExecutor` usado em `parse_annotations`. O estado mutável do Indenter (`indent_level`, `paren_level`) era corrompido quando múltiplas threads chamavam `parser.parse()` simultaneamente, produzindo erros espúrios de indentação (`_INDENT` inesperado) em projetos com mais de 2 arquivos `.syn`.
  - Fix: `create_parser()` migrado de `@lru_cache` para `threading.local` — cada thread recebe sua própria instância do parser (incluindo `SynesisIndenter`), criada uma vez na primeira chamada por thread.
  - Custo: ~4ms na primeira chamada por thread; zero nas subsequentes. Compilação sequencial (≤2 arquivos) não é afetada.

- **TAB misturado com espaços causa falha de parse** (`synesis/parser/lexer.py`)
  - O parser standalone Lark trata TAB e espaços como tokens distintos no terminal `NEWLINE`. Arquivos `.syn` com TAB em uma linha e espaços nas demais (comportamento comum de editores com `insertSpaces=false`) causavam `UnexpectedToken(_INDENT)` mesmo que a indentação numérica fosse equivalente (1 TAB = 4 espaços).
  - Fix: normalização `\t → "    "` em `parse_string()` antes do parse, com guard `if "\t" in content` para custo zero em arquivos sem TAB.

## [0.4.6] - 2026-03-19

### Fixed
- **`DuplicateSourceBibref` (E070) não reportado pelo LSP** (`synesis/lsp_adapter.py`)
  - `validate_single_file` validava cada `SourceNode` isoladamente via `SemanticValidator` — nunca acumulava o conjunto completo para checar bibrefs duplicados entre blocos SOURCE.
  - O erro era detectado apenas pelo CLI (fase de linking no `Linker._check_duplicate_source_bibrefs`), invisível no VSCode.
  - Fix: adicionada checagem cross-node em `_validate_semantics` após coleta dos sources — replica exatamente a lógica do Linker usando `normalize_bibref` para consistência (case-insensitive).
  - Fix: `filename` na mensagem de diagnóstico decodificado via `urllib.parse.unquote` — evita exibição de `%3A` em vez de `:` em paths Windows.

## [0.4.5] - 2026-03-18

### Fixed
- **API pública do `lsp_adapter.py`** — 3 funções privadas promovidas a nomes públicos com aliases backward-compat:
  - `_find_workspace_root` → `find_workspace_root`
  - `_discover_context` → `discover_context`
  - `_invalidate_cache` → `invalidate_cache`
  - Aliases `_find_workspace_root = find_workspace_root` etc. garantem que imports existentes não quebram.
  - Chamadas internas (`validate_single_file`, `discover_context`) atualizadas para usar os nomes públicos.

### Removed
- **`synesis/parser/error_handler.py`** — arquivo de código morto deletado.
  - Continha `SynesisErrorHandler` como `@dataclass(frozen=True)` com API incompatível com o handler ativo (`synesis/error_handler.py`).
  - Zero imports em qualquer repositório do ecossistema. Nunca exportado por `synesis/parser/__init__.py`.

## [0.4.4] - 2026-03-17

### Fixed
- **Ontologia não carregada no contexto LSP** (`synesis/lsp_adapter.py`)
  - `_load_context_from_project` carregava template e bibliografia mas retornava sempre `ontology_index={}` — o campo `INCLUDE ONTOLOGY` do `.synp` era ignorado. Resultado: `validate_single_file` via LSP reportava todos os códigos como "não definidos na ontologia", mesmo com a ontologia corretamente declarada.
  - Fix: adicionado bloco "3. CARREGAR ONTOLOGIAS" em `_load_context_from_project` — itera `project.includes`, filtra `include_type == "ONTOLOGY"`, parseia cada `.syno` via `parse_file` + `SynesisTransformer` e popula `ontology_index` com os `OntologyNode` encontrados. Mesmo padrão já usado pelo compilador (`compiler.py:parse_ontologies`).
  - Verificado: `validate_single_file` no projeto Basic agora encontra `['Social_Cohesion', 'Collective_Action']` na ontologia e retorna 0 erros.

## [0.4.3] - 2026-03-17

### Fixed
- **`_find_workspace_root` e `_discover_context` falham silenciosamente no Windows** (`synesis/lsp_adapter.py`)
  - `Path(file_uri.replace("file://", ""))` transformava `file:///C:/...` em `/C:/...` — caminho inválido no Windows — fazendo `_find_workspace_root` retornar `None`. `_discover_context` então retornava contexto vazio e `validate_single_file` validava arquivos sem template, gerando **zero diagnósticos** mesmo com erros reais presentes.
  - Fix: substituído por `urlparse` + `unquote` com normalização de drive Windows (`/C:/...` → `C:/...`) — mesmo padrão já usado em `server.py:_normalize_workspace_path`. Aplicado em dois locais: `_find_workspace_root` (linha 484) e `_discover_context` (linha 355).
  - Verificado: `validate_single_file` com URI `file:///` passou de 0 para 10 diagnósticos no case-study T01.

## [0.4.2] - 2026-03-15

### Fixed
- **Bloco `GUIDELINES` aceita qualquer conteúdo de texto** (`grammar/synesis.lark`, `parser/transformer.py`, `grammar/synesis_standalone.py`)
  - O lexer tokenizava keywords (`CODE`, `CHAIN`, `DESCRIPTION`, etc.) com prioridade `.5` antes do terminal `TEXT_LINE` (.3), causando falha de parse quando linhas do GUIDELINES continham nomes de campos ou commands (ex: `CODE: Use taxonomy codes`).
  - Solução: regra `guideline_line` + `guideline_token` que aceita explicitamente qualquer keyword, `IDENTIFIER`, `FIELD_NAME`, `NUMBER`, `BIBREF`, `COLON`, `","`, `"->"` como texto. O transformer `guideline_line` reconstrói a linha sem espaço desnecessário antes de `:`.
  - `synesis_standalone.py` regenerado com a nova gramática.

## [0.4.1] - 2026-03-15

### Added

- `ast/results.py`: 38 novas subclasses `ValidationError` cobrindo erros de template (Fase 1),
  anotações (Fase 2), entidades cruzadas (Fase 3) e estrutura de projeto (Fase 4) — elevando de
  19 para 57 subclasses tipadas no total:
  - **Fase 1 — Validação estrutural de template:** `DuplicateFieldName`, `UndefinedFieldInScopeFields`,
    `OrphanFieldDefinition`, `SingleFieldBundle`, `FieldScopeListMismatch`, `ChainWithoutArity`,
    `ArityRelationsMismatch`, `OrderedWithoutValues`, `EnumeratedWithoutValues`, `ScaleWithoutFormat`,
    `InvalidFormatSyntax`, `InvalidArityOperator`, `FormatOnNonScale`, `ArityOnNonChain`,
    `RelationsOnNonChain`, `DuplicateScopeBlock`, `ValueWithWhitespace`, `DuplicateValue`
    (erros 18, 39–59, 69 do inventory).
  - **Fase 2 — Validação semântica de anotações:** `OntologyWithoutTemplateFields`,
    `QualifiedChainWithoutRelations`, `SimpleChainWithRelationsRequired`, `EmptyItemBlock`,
    `DecimalInIntegerScale`, `DuplicateCodeInField`, `TopicWithSpaces`, `InvalidIdentifierCharacter`
    (erros 5, 8, 9, 23, 26, 31–33).
  - **Fase 3 — Validação cross-entity:** `ChainWithoutArrowOperator`, `ConceptNameMatchesRelation`,
    `ConceptWithSpaces`, `DuplicateOntologyConcept`, `DuplicateSourceBibref`,
    `DuplicateOntologyDescription` (erros 6, 13–15, 68, 70, 71).
  - **Fase 4 — Estrutura de projeto:** `MissingAnnotationsInclude`, `MissingOntologyInclude`,
    `MissingBibliographyFile`, `MissingTemplateDeclaration`, `DuplicateProjectBlock`,
    `ModifiedBeforeCreated` (erros 61–63, 65–67).
- `parser/template_loader.py`: função `validate_template()` com 16 funções auxiliares que realiza
  validação estrutural completa do `TemplateNode` após parsing — substituindo os `TemplateLoadError`
  pontuais por `ValidationResult` acumulável compatível com o pipeline LSP/diagnósticos.
- `semantic/validator.py`: validações para erros 5, 8, 9, 23, 26, 31 integradas ao
  `SemanticValidator`; novo método `_validate_code_fields_duplicates` e helper `_validate_identifier`.
- `semantic/linker.py`: detecção de `DuplicateOntologyConcept` (erro 68), `DuplicateSourceBibref`
  (erro 70) e `DuplicateOntologyDescription` (erro 71) integradas ao `Linker`.
- `compiler.py`: chamada a `validate_template()` inserida no pipeline entre `load_template()` e
  `validate_all()`; verificações de estrutura de projeto (erros 61–67) integradas a `compile()`.
- `ast/nodes.py`: campo `parse_errors` adicionado a `TemplateNode` para propagar erros de parsing
  de template pelo pipeline `ValidationResult`.

### Changed

- `cli.py`: saída do comando `compile` reformulada para eliminar "ansiedade de tela preta" em
  projetos grandes. O pipeline agora é executado etapa a etapa com feedback visual em tempo real:
  spinner animado por etapa (`⠋ Lendo anotacoes...`), substituído por linha de conclusão com
  checkmark verde, tempo decorrido e contagem relevante (`✔ Lendo anotacoes  484 sources, 1.614 items  (1.2s)`).
  Em terminais não-TTY (pipe, redirect, CI) o spinner é desativado e as etapas são impressas como
  linhas simples sem animação.
- `cli.py`: mensagens de erro e aviso migradas para formato compacto de uma linha via novo método
  `to_cli_line()` na hierarquia de `ValidationError`. A mensagem pedagógica completa permanece em
  `to_diagnostic()` para uso no LSP/hover do VSCode.
- `cli.py`: localização nos diagnósticos exibe caminho relativo ao diretório do projeto em vez do
  caminho absoluto. Colunas de localização e label `[ERROR]`/`[WARNING]` alinhadas tabulariamente.
- `cli.py`: estatísticas (`--stats`) removem `Triples` (métrica técnica interna sem significado
  direto para o usuário) e exibem separador de milhar com ponto (`1.614`), alinhamento à direita
  dos números e título `Estatisticas da Compilacao:` em negrito.
- `cli.py`: cabeçalho `SYNESIS v{VERSION}  Compile seu pensamento.` exibido no início de cada
  compilação.
- `ast/results.py`: `ValidationError` recebe método `to_cli_line()` com implementação padrão
  (extrai primeira linha de `to_diagnostic()`). Todas as 57 subclasses implementam a versão
  especializada com mensagem de uma linha contendo dado principal + sugestão de correção quando
  disponível. Sugestões usam padrão uniforme `"Sugestao de correcao -> \`valor\`"`.

## [0.4.0] - 2026-03-13

### Added
- `ast/normalize.py`: módulo centralizado com `normalize_code()` e `normalize_bibref()`,
  substituindo 9 cópias independentes de `_norm_code` dispersas entre `validator.py`,
  `linker.py` e os 7 módulos do `synesis-lsp`. Cache opcional por compilação via `dict`
  passado explicitamente (`norm_cache`).
- `parser/parse_cache.py`: cache por arquivo `(path, mtime) → list[nodes]` para compilação
  incremental. Evita re-parsing de arquivos não modificados entre compilações no mesmo
  processo. API: `get_cached_nodes`, `put_cached_nodes`, `invalidate_cache`.
- `grammar/synesis_standalone.py`: parser LALR precompilado gerado via
  `lark.tools.standalone`, eliminando custo de cold-start (~52ms → ~8ms, redução ~84%).
  Ativado automaticamente em `create_parser()`; fallback para compilação da gramática se
  ausente.

### Changed
- `compiler.py`: `compile()` cria `norm_cache: dict` compartilhado entre `validate_all()`
  e `link_all()`, eliminando normalizações redundantes entre as duas fases.
- `compiler.py`: `parse_annotations()` paraleliza o parsing de >2 arquivos `.syn` via
  `ThreadPoolExecutor(max_workers=min(4, N))`. Projetos com 1-2 arquivos usam path
  sequencial sem overhead. Extrai `_parse_single_annotation()` como função de módulo
  (thread-safe).
- `compiler.py`: `_parse_nodes()` consulta `parse_cache` antes de parsear; armazena
  resultado no cache após parse+transform.
- `semantic/validator.py`: `SemanticValidator.__post_init__` pré-indexa `_code_field_names`
  (fields `CODE` no scope `ITEM`) — elimina iteração O(total_specs × total_items) em
  `_collect_item_codes()`. Remove `_norm_code()`; usa `normalize_code()` centralizado.
- `semantic/linker.py`: `Linker.link()` computa `has_relations` uma única vez antes do
  loop de items (era recalculado por chain). Remove `_norm_code()` e `_norm_bibref()`;
  usa `normalize_code()` e `normalize_bibref()` centralizados.
- `parser/lexer.py`: `create_parser()` tenta importar o parser standalone primeiro,
  patcheando `Tree`, `Token`, `UnexpectedToken` e `UnexpectedCharacters` para as classes
  oficiais do Lark antes de instanciar `Lark_StandAlone`.

### Fixed
- `semantic/validator.py`, `semantic/linker.py`: fields do tipo `CODE` com múltiplos valores
  separados por vírgula (ex: `topic: CREATOR, EARTH, HEAVENS_THE_NATURAL`) eram tratados como
  um único código, gerando falsos warnings de "código não definido na ontologia". Causa raiz:
  o token `TEXT_LINE` (prioridade 3) prevalece sobre `CODE_ELEMENT` (prioridade 2) no lexer
  contextual do Lark, tornando a regra `code_list` da gramática inacessível nesse contexto.
  Fix: `_extract_code_values()` faz split por vírgula quando o valor é uma `str` com vírgulas.

### Performance (medido em projetos reais)
| Otimização | Ganho estimado |
|---|---|
| Normalização com cache compartilhado | ~96% menos chamadas `split+join+lower` |
| Pre-indexação de field specs | ~88% menos iterações em `_collect_item_codes` |
| Parser standalone (cold-start) | ~84% (52ms → 8ms) |
| Parsing paralelo (>2 arquivos .syn) | ~70% no tempo de parse (4 workers) |
| Cache por arquivo (recompilação) | ~95% (só re-parseia arquivos modificados) |

## [0.3.0] - 2026-03-06

### Added
- `grammar/synesis.lark`: keyword `KW_GUIDELINES` e regras `guidelines_block` / `guidelines_lines`
  para suporte ao bloco `GUIDELINES...END GUIDELINES` dentro de `FIELD...END FIELD`.
- `ast/nodes.py`: campo `guidelines: Optional[str] = None` em `FieldSpec`; serializado
  automaticamente via `to_dict()` como `"guidelines"` no JSON exportado.
- `parser/transformer.py`: handler `KW_GUIDELINES`, transformers `guidelines_lines` e
  `guidelines_block`, detecção em `field_props()`, extração em `field_def_block()`.

### Notes
- Adição aditiva: templates sem `GUIDELINES` continuam compilando sem alteração.
- Semântica pass-through: o compilador armazena e exporta o conteúdo sem interpretá-lo.
- Consumidores (MCP Server, agentes de IA) lêem `guidelines` via `synesis.load()` → JSON.

## [0.2.11] - 2026-03-06

### Fixed
- `transformer.py`: replaced `@v_args(meta=True)` with `@v_args(tree=True)` in all 10
  Transformer methods to fix cross-platform incompatibility. Different Lark builds (e.g.
  Homebrew on macOS vs pip on Windows) pass arguments to `_vargs_meta` in opposite orders
  (`f(children, meta)` vs `f(meta, children)`). `@v_args(tree=True)` passes a single
  `Tree` object whose `.meta` and `.children` attributes are always stable, eliminating the
  build-dependent argument-order ambiguity that caused `'Meta' object is not subscriptable`
  on macOS.

## [0.2.10] - 2026-02-24

### Fixed
- Grammar now accepts empty SOURCE, ITEM, and ONTOLOGY blocks (no fields required for parsing).
  Previously, blocks with no fields caused a syntax error because the `_INDENT`/`_DEDENT` tokens
  were not emitted by the indentation lexer, failing before semantic validation.
  Empty blocks are now valid syntax; required-field enforcement is delegated to the semantic validator.

### Changed
- `synesis init`: renamed generated field `code_description` to `definition` in template and ontology
  files to avoid collision with the `KW_CODE` keyword token in the Lark lexer.

## [0.2.9] - 2026-02-04 - Consolidates changes since version 0.2.2

### Fixed
- Deduplication of `code_locations` in the linker to prevent duplicate CODE/CHAIN locations (transformer + linker)
- VSCode Explorer tree views now show only 1 occurrence per CODE/CHAIN (no more ITEM + CODE duplicates)
- Definitive fix for the duplication bug in CODE/CHAIN fields in the Explorer

## [0.2.8] - 2026-02-04

### Changed
- Consolidation release for CODE/CHAIN location fixes

## [0.2.7] - 2026-02-04

### Fixed
- `code_locations` now accumulates locations from multiple CODE lines instead of overwriting
- `value()` function preserves Token (subclass of str) to keep location metadata (fixes navigation in Code Explorer)

## [0.2.6] - 2026-02-04

### Added
- Post-processing with template to generate exact locations in TYPE CODE/CHAIN fields with a custom name.

### Changed
- Preservation of line tokens for single-line fields, enabling exact column calculation after parsing.

## [0.2.5] - 2026-02-04

### Added
- Exact location for TYPE CODE/CHAIN fields with a custom name, using the template after parsing.

### Changed
- Items now carry multiline line tokens to allow position calculation for CODE/CHAIN defined in the template.

## [0.2.4] - 2026-02-04

### Added
- AST now stores `code_locations` (ItemNode) and `node_locations` (ChainNode) for exact CODE/CHAIN positions, including multiline values.

### Changed
- Transformer preserves `TEXT_LINE` tokens to calculate exact columns in multiline CODE/CHAIN fields.
- Package version centralized in `pyproject.toml` (fallback via metadata/pyproject).

## [0.2.3] - 2026-02-03

### Added
- LinkedProject now includes `relation_index` with chain location/type provenance to support LSP relation navigation.

## [0.2.2] - 2026-01-23

### Fixed
- Dependencies `click` and `openpyxl` moved to required (were optional extras causing installation failures with `pipx install synesis`)
- Removed `[cli]`, `[excel]`, `[full]` extras - all compiler features now available in base installation

## [0.2.1] - 2026-01-22

### Fixed
- CI: correct Codecov v4 inputs and add optional token support
- Add regex dependency required by Lark when regex=True

## [0.2.0] - 2026-01-21

### Added
- `synesis.load()` in-memory compilation API (no disk I/O)
- `synesis.compile_string()` for single file parsing
- `MemoryCompilationResult` with `to_json_dict()`, `to_csv_tables()`, `to_dataframe()` methods
- `load_template_from_string()` in template_loader.py
- `load_bibliography_from_string()` in bib_loader.py
- `build_json_payload()` in json_export.py for in-memory JSON construction
- `build_csv_tables()` in csv_export.py for in-memory table construction
- `build_xls_workbook()` in xls_export.py for in-memory Workbook construction
- Pandas integration via `to_dataframe()` and `to_dataframes()`
- Tests for new API in tests/test_api.py
- In-memory API documentation

### Changed
- Dependencies `click` and `openpyxl` are now optional
- Reorganized dependencies in pyproject.toml: `[cli]`, `[excel]`, `[full]`, `[dev]`
- Exporters refactored to separate data construction from disk writing

  

## [0.1.0] - 2026-01-19

### Added

#### Language Features
- LALR(1) grammar with case-insensitive keywords
- Template system with REQUIRED/OPTIONAL/FORBIDDEN field constraints
- BUNDLE modifier for co-occurring field groups
- CHAIN type with qualified relations (A -> RELATION -> B)
- TOPIC type for dynamic hierarchical categorization
- Support for concepts with spaces in CODE and CHAIN elements
- Comprehensive field types: QUOTATION, MEMO, CODE, CHAIN, TEXT, DATE, SCALE, ENUMERATED, ORDERED, TOPIC
- Scientific notation support in TEXT fields (n=2383, p<0.05, etc.)

#### Compiler Features
- Full parsing pipeline with Lark-based parser
- AST construction with complete type safety
- Semantic validation with pedagogical error messages
- BibTeX integration with fuzzy matching for suggestions
- Source location tracking for all AST nodes (file:line:column)
- Result-based error handling (Ok/Err pattern inspired by Elm/Rust)
- Template validation ensuring consistency across annotations
- Ontology validation and indexing
- ARITY validation for chain cardinality
- BUNDLE validation ensuring paired field occurrences

#### Export Formats
- JSON v2.0 export with hierarchical structure
- CSV export generating multiple relational tables:
  - sources.csv
  - items.csv
  - codes.csv
  - chains.csv (triples format)
  - ontologies.csv
  - topics.csv
- Excel export with multi-sheet workbook
- Full traceability in all exports (source_file, source_line, source_column)

#### CLI Commands
- `synesis compile` - Compile project with multiple export options
- `synesis check` - Validate single file syntax
- `synesis validate-template` - Validate template structure
- `synesis init` - Initialize new project with examples

#### Development
- Comprehensive test suite with 1,713 lines of tests
- pytest-based testing framework
- Test fixtures for valid and invalid cases
- Module docstrings following strict guidelines
- Type hints throughout entire codebase

### Technical Details

#### Architecture
- 6,434 lines of production Python code
- 6 subpackages: ast, parser, semantic, exporters, grammar, tests
- Procedural style where appropriate, OOP where beneficial
- No redundant abstractions or premature optimization
- Clean separation of concerns

#### Dependencies
- lark >= 1.1 (LALR parser)
- bibtexparser >= 1.4 (BibTeX parsing)
- click >= 8.0 (CLI framework)
- openpyxl >= 3.0 (Excel export)
- pytest >= 7.0 (testing, dev only)

#### Compatibility
- Python >= 3.10
- Cross-platform (Windows, macOS, Linux)
- UTF-8 encoding (no BOM)

### Documentation
- Full language specification (v1.1)
- Comprehensive README with Quick Start
- Implementation guides and coding patterns
- Error handling documentation
- LSP adapter documentation
---

[0.4.6]: https://github.com/synesis-lang/synesis/releases/tag/v0.4.6
[0.4.5]: https://github.com/synesis-lang/synesis/releases/tag/v0.4.5
[0.4.4]: https://github.com/synesis-lang/synesis/releases/tag/v0.4.4
[0.4.3]: https://github.com/synesis-lang/synesis/releases/tag/v0.4.3
[0.4.2]: https://github.com/synesis-lang/synesis/releases/tag/v0.4.2
[0.4.1]: https://github.com/synesis-lang/synesis/releases/tag/v0.4.1
[0.4.0]: https://github.com/synesis-lang/synesis/releases/tag/v0.4.0
[0.3.0]: https://github.com/synesis-lang/synesis/releases/tag/v0.3.0
[0.2.2]: https://github.com/synesis-lang/synesis/releases/tag/v0.2.2
[0.2.1]: https://github.com/synesis-lang/synesis/releases/tag/v0.2.1
[0.2.0]: https://github.com/synesis-lang/synesis/releases/tag/v0.2.0
[0.1.0]: https://github.com/synesis-lang/synesis/releases/tag/v0.1.0
