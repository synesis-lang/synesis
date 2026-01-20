# Developer Documentation

Internal documentation for Synesis compiler developers.

## Project Architecture

```
synesis/
├── __init__.py              # Package initialization
├── cli.py                   # Click-based CLI interface
├── compiler.py              # Main compilation orchestrator
├── error_handler.py         # Error message formatting
├── lsp_adapter.py           # Language Server Protocol adapter
├── ast/                     # Abstract Syntax Tree
│   ├── nodes.py            # AST node dataclasses
│   └── results.py          # Result types (Ok/Err)
├── parser/                  # Parsing layer
│   ├── lexer.py            # Lark parser wrapper
│   ├── transformer.py      # Parse tree → AST transformation
│   ├── template_loader.py  # Template file parsing
│   ├── bib_loader.py       # BibTeX parsing
│   └── error_handler.py    # Parser-specific errors
├── semantic/                # Semantic analysis
│   ├── validator.py        # Field, chain, bundle validation
│   └── linker.py           # Reference resolution and indexing
├── exporters/               # Output formats
│   ├── json_export.py      # JSON v2.0 hierarchical export
│   ├── csv_export.py       # Tabular CSV export
│   └── xls_export.py       # Excel workbook export
└── grammar/
    └── synesis.lark        # LALR(1) grammar definition
```

## Compilation Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│ 1. DISCOVERY                                                │
│    • Load .synp project file                                │
│    • Resolve include paths                                  │
│    • Build file manifest                                    │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. TEMPLATE LOADING                                         │
│    • Parse .synt template                                   │
│    • Extract FIELD definitions                              │
│    • Build constraint rules (REQUIRED/OPTIONAL/BUNDLE)      │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. BIBLIOGRAPHY LOADING                                     │
│    • Parse .bib files with bibtexparser                     │
│    • Normalize bibkeys (lowercase, trim)                    │
│    • Index for fast lookup                                  │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. PARSING (Syntactic)                                      │
│    • Lark LALR(1) parser processes .syn, .syno files        │
│    • Generate concrete parse trees                          │
│    • Track source locations (file:line:column)              │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. TRANSFORMATION                                           │
│    • Convert parse trees → typed AST nodes                  │
│    • Attach SourceLocation to every node                    │
│    • Normalize values (trim, dedent, etc.)                  │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 6. SEMANTIC VALIDATION                                      │
│    • Check REQUIRED/OPTIONAL/FORBIDDEN fields               │
│    • Validate BUNDLE co-occurrence                          │
│    • Verify @bibref exists in bibliography                  │
│    • Validate CHAIN structure and relations                 │
│    • Check ARITY constraints                                │
│    • Verify ENUMERATED/ORDERED values                       │
│    • Generate fuzzy suggestions for errors                  │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 7. LINKING                                                  │
│    • Build ontology index (concept → OntologyNode)          │
│    • Link ITEMs to SOURCEs by @bibref                       │
│    • Extract code frequency                                 │
│    • Generate chain triples (from → relation → to)          │
│    • Build topic hierarchy                                  │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 8. EXPORT                                                   │
│    • JSON: Hierarchical with full traceability              │
│    • CSV: Relational tables (sources, items, chains, etc.)  │
│    • Excel: Multi-sheet workbook with formatting            │
└─────────────────────────────────────────────────────────────┘
```

## Key Design Principles

### 1. Separation of Concerns

- **Parser**: Purely syntactic, no semantic knowledge
- **Validator**: Semantic rules, no awareness of export formats
- **Exporters**: Read-only AST traversal, no validation logic

### 2. Result-Based Error Handling

Inspired by Elm and Rust, we use `Result[T, E]` types instead of exceptions:

```python
from synesis.ast.results import Ok, Err, ValidationResult

def validate_field(value: str) -> ValidationResult:
    if not value:
        return Err(MissingRequiredField(...))
    return Ok(value)

result = validate_field("")
if result.is_ok():
    print(result.value)
else:
    print(result.error.to_diagnostic())
```

### 3. Immutable AST

All AST nodes are frozen dataclasses:

```python
@dataclass(frozen=True)
class ItemNode:
    bibref: str
    quote: str
    codes: List[str]
    location: SourceLocation
```

This prevents accidental mutation during validation/export.

### 4. Source Location Tracking

Every AST node has a `SourceLocation` with file, line, and column:

```python
@dataclass
class SourceLocation:
    file: Path
    line: int      # 1-based
    column: int    # 1-based
```

This enables precise error messages and CSV traceability.

## Grammar Modification Protocol

⚠️ **Grammar is frozen for v1.x** - breaking changes require v2.0.

If you must modify `synesis/grammar/synesis.lark`:

1. **Update grammar file** with detailed comments
2. **Update transformer** (`synesis/parser/transformer.py`)
3. **Add AST nodes** if needed (`synesis/ast/nodes.py`)
4. **Write tests** covering new syntax
5. **Update specification** (`index.md`)
6. **Update CHANGELOG** with breaking change notice

### Example: Adding New Field Type

```lark
# In synesis.lark
KW_NEWTYPE: /newtype/i
simple_type: ... | KW_NEWTYPE
```

```python
# In transformer.py
def field_def_block(self, items):
    # Handle KW_NEWTYPE case
    ...
```

```python
# In nodes.py
class FieldType(Enum):
    ...
    NEWTYPE = "NEWTYPE"
```

## Testing Strategy

### Test Organization

```
tests/
├── conftest.py                    # Shared fixtures
├── fixtures/                      # Test data
│   ├── minimal.synt              # Minimal template
│   ├── energy.synt               # Full template example
│   ├── valid_project/            # Complete valid project
│   ├── invalid_syntax/           # Syntax error cases
│   └── invalid_semantic/         # Semantic error cases
├── test_parser.py                # Lexer, parser, transformer
├── test_validator.py             # Semantic validation
├── test_linker.py                # Index and linking
├── test_exporters.py             # JSON, CSV, Excel
└── test_error_handler.py         # Error messages
```

### Running Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=synesis --cov-report=html

# Specific test file
pytest tests/test_validator.py

# Specific test function
pytest tests/test_validator.py::test_required_fields

# Verbose output
pytest -v

# Stop on first failure
pytest -x
```

### Writing Tests

Use fixtures from `conftest.py`:

```python
def test_validate_item(minimal_template, base_location):
    validator = SemanticValidator(minimal_template, {}, {})
    item = ItemNode(
        bibref="test2024",
        quote="Sample quote",
        codes=[],
        location=base_location
    )
    result = validator.validate_item(item)
    assert result.is_valid()
```

## Error Message Guidelines

Error messages must be:
1. **Precise**: Include file:line:column
2. **Pedagogical**: Teach correct syntax
3. **Actionable**: Suggest specific fixes

### Good Error Message

```
error: annotations/sample.syn:3:26: Multiple codes must be separated by comma.
    code: Climate Belief Risk Perception
                         ^~~~ missing comma before "Risk"

Use comma to separate codes:
    code: Climate Belief, Risk Perception

OR specify each code on separate line:
    code: Climate Belief
    code: Risk Perception
```

### Bad Error Message

```
error: Invalid syntax at line 3
```

## Performance Considerations

- **Target**: Compile 500 ITEMs in < 10 seconds
- **Parser**: Lark LALR(1) is O(n) in input size
- **Validation**: O(n) for each validation pass
- **Linking**: O(n log n) for index building

### Optimization Tips

- Use `@lru_cache` for expensive computations
- Build indices once, reuse for validation
- Stream large files instead of loading entirely
- Use generators for export when possible

## Code Style

### Docstring Requirements

Every module must have:

```python
"""
module_name.py - Brief description

Purpose:
    Module responsibilities (3-4 lines max)

Components:
    - Class/Function 1: what it does
    - Class/Function 2: what it does

Dependencies:
    - module: why it's used

Generated conforming to: Synesis Specification v1.1
"""
```

### Type Hints

All functions must have complete type annotations:

```python
def validate_chain(
    chain: ChainNode,
    field_spec: FieldSpec,
    ontology_index: Dict[str, OntologyNode]
) -> ValidationResult:
    """Validate chain semantics."""
    ...
```

### Design Philosophy

- **Procedural where appropriate**: Functions over classes when no state needed
- **No premature abstraction**: Three similar lines > unnecessary helper
- **Explicit over implicit**: Clear code > clever code

## LSP Integration

The `lsp_adapter.py` module provides Language Server Protocol support:

- **Pure Python**: No Node.js dependencies
- **Stateless**: Each request is independent
- **Cached**: Template/bibliography loaded once

### LSP Flow

```
VSCode Extension (TypeScript)
        ↓ JSON-RPC
LSP Server (Python, stdio transport)
        ↓
lsp_adapter.py (calls compiler)
        ↓
compiler.py → validator.py
        ↓
Returns diagnostics to LSP Server
        ↓ JSON-RPC
VSCode displays errors inline
```

## Release Process

1. **Update version** in `pyproject.toml`
2. **Update CHANGELOG.md** with release notes
3. **Run all tests**: `pytest`
4. **Build package**: `python -m build`
5. **Check distribution**: `twine check dist/*`
6. **Upload to TestPyPI**: `twine upload --repository testpypi dist/*`
7. **Test installation**: `pip install -i https://test.pypi.org/simple/ synesis`
8. **Upload to PyPI**: `twine upload dist/*`
9. **Create git tag**: `git tag -a v0.1.0 -m "Release v0.1.0"`
10. **Push tag**: `git push origin v0.1.0`
11. **Create GitHub release** with artifacts

See `PUBLISHING.md` for detailed instructions.

## Troubleshooting

### Import errors after installation

Check `synesis/__init__.py` exports:

```python
from synesis.compiler import compile_project
from synesis.ast.nodes import *
from synesis.ast.results import ValidationResult

__all__ = ["compile_project", "ValidationResult", ...]
```

### Tests fail in CI but pass locally

- Check Python version compatibility (3.10+)
- Ensure fixtures use relative paths
- Verify dependencies are installed

### Grammar changes don't take effect

- Lark caches parsed grammars
- Delete `__pycache__` and `.pytest_cache`
- Reinstall in editable mode: `pip install -e .`

## Resources

- **Lark Documentation**: https://lark-parser.readthedocs.io
- **Python Packaging**: https://packaging.python.org
- **Type Hints**: https://mypy.readthedocs.io
- **LSP Specification**: https://microsoft.github.io/language-server-protocol

## Contact

For questions or discussions:
- GitHub Issues: https://github.com/synesis-lang/synesis/issues
- GitHub Discussions: https://github.com/synesis-lang/synesis/discussions
