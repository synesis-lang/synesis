# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.9] - 2026-02-04

### Fixed
- Deduplicação de `code_locations` no linker para prevenir localizações duplicadas de CODE/CHAIN (transformer + linker)
- Tree views do VSCode Explorer agora mostram apenas 1 ocorrência por CODE/CHAIN (não mais duplicatas ITEM + CODE)
- Correção definitiva do bug de duplicação em campos CODE/CHAIN no Explorer

## [0.2.8] - 2026-02-04

### Changed
- Versão de consolidação das correções de localização CODE/CHAIN

## [0.2.7] - 2026-02-04

### Fixed
- `code_locations` agora acumula localizações de múltiplas linhas CODE em vez de sobrescrever
- Função `value()` preserva Token (subclasse de str) para manter metadata de localização (fix navegação no Code Explorer)

## [0.2.6] - 2026-02-04

### Added
- Pós-processamento com template para gerar localizações exatas em campos TYPE CODE/CHAIN com nome customizado.

### Changed
- Preservação de tokens de linha para campos single-line, permitindo cálculo de colunas exatas após o parse.

## [0.2.5] - 2026-02-04

### Added
- Localização exata para campos TYPE CODE/CHAIN com nome customizado, usando o template após o parse.

### Changed
- Itens agora carregam tokens de linhas multiline para permitir cálculo de posições em CODE/CHAIN definidos no template.

## [0.2.4] - 2026-02-04

### Added
- AST agora armazena `code_locations` (ItemNode) e `node_locations` (ChainNode) para posições exatas de CODE/CHAIN, inclusive em valores multiline.

### Changed
- Transformer preserva tokens `TEXT_LINE` para calcular colunas exatas em campos CODE/CHAIN multiline.
- Versão do pacote centralizada no `pyproject.toml` (fallback via metadata/pyproject).

## [0.2.3] - 2026-02-03

## Added
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
