# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.2.2]: https://github.com/synesis-lang/synesis/releases/tag/v0.2.2
[0.2.1]: https://github.com/synesis-lang/synesis/releases/tag/v0.2.1
[0.2.0]: https://github.com/synesis-lang/synesis/releases/tag/v0.2.0
[0.1.0]: https://github.com/synesis-lang/synesis/releases/tag/v0.1.0
