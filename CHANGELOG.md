# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

## [0.2.0] - 2026-01-21

### Added
- `synesis.load()` API para compilacao em memoria (sem I/O em disco)
- `synesis.compile_string()` para parsing de arquivos unicos
- `MemoryCompilationResult` com metodos `to_json_dict()`, `to_csv_tables()`, `to_dataframe()`
- `load_template_from_string()` em template_loader.py
- `load_bibliography_from_string()` em bib_loader.py
- `build_json_payload()` em json_export.py para construcao de JSON em memoria
- `build_csv_tables()` em csv_export.py para construcao de tabelas em memoria
- `build_xls_workbook()` em xls_export.py para construcao de Workbook em memoria
- Integracao com Pandas via `to_dataframe()` e `to_dataframes()`
- Testes para nova API em tests/test_api.py

### Changed
- Dependencias `click` e `openpyxl` agora sao opcionais
- Reorganizacao de dependencias em pyproject.toml: `[cli]`, `[excel]`, `[full]`, `[dev]`
- Exportadores refatorados para separar construcao de dados de escrita em disco

### Migration
- Para uso da biblioteca importavel: `pip install synesis`
- Para CLI: `pip install synesis[cli]`
- Para exportacao Excel: `pip install synesis[excel]`
- Para todos os recursos: `pip install synesis[full]`

## [Unreleased]

### Planned Features
- LSP server integration for IDE support
- VSCode extension
- Additional export formats (GraphML, DOT)
- Performance optimizations for large corpora
- Incremental compilation support
- Watch mode for continuous validation

---

[0.1.0]: https://github.com/synesis-lang/synesis/releases/tag/v0.1.0
