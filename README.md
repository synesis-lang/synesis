# Synesis

> **The confluence of information into intelligence.**

A Domain-Specific Language (DSL) compiler that transforms qualitative research annotations into canonical knowledge structures.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

## Philosophy

Human knowledge is naturally intricate, full of nuances and deep connections. This is **complexity**—and it is valuable. **Complication** arises only when we lack adequate methods for organizing knowledge.

Synesis is a declarative Domain-Specific Language created for those who need more than simple annotations. It is a method for **knowledge consolidation**.

Unlike traditional tools, Synesis acts as a **compiler for your analytical thinking**: it receives your interpretations and annotations in plain text files, validates their logical consistency, and transforms them into canonical, rigorous knowledge structures.

Many believe that technical rigor stifles creativity. Synesis proves otherwise: **discipline is the true form of freedom**. By delegating logical organization to a canonical structure, your mind is freed for what truly matters: interpretation, nuance, and insight.

The result is true **σύνεσις** (sýnesis): the convergence of information fragments into an intelligible, auditable, and technically structured whole.

## What Synesis Does

- **Formal syntax** for annotating research sources with structured metadata
- **Template-based validation** ensuring consistency across annotations
- **BibTeX integration** for bibliographic reference management
- **Semantic validation** of codes, chains, ontologies, and field bundles
- **Multiple export formats** (JSON, CSV, Excel) for downstream analysis
- **Comprehensive error reporting** with precise source location tracking

## Features

- **LALR(1) Parser**: Fast, deterministic parsing with Lark grammar
- **Type-Safe AST**: Full type hints throughout the codebase
- **Pedagogical Error Messages**: Clear, actionable error messages with suggestions
- **Template System**: Define custom field schemas with REQUIRED/OPTIONAL/FORBIDDEN constraints
- **BUNDLE Validation**: Enforce co-occurring field groups (e.g., note + chain pairs)
- **Chain Semantics**: Validate qualified chains (A -> INFLUENCES -> B) with relation types
- **Ontology Support**: Define hierarchical concept vocabularies with ORDERED/ENUMERATED types
- **Source Traceability**: Every AST node tracks file, line, and column location

## Installation

### From PyPI (Coming Soon)

```bash
pip install synesis
```

### From TestPyPI

```bash
pip install -i https://test.pypi.org/simple/ synesis
```

### From Source

```bash
git clone https://github.com/synesis-lang/synesis.git
cd synesis
pip install -e .
```

## Quick Start

### 1. Create a Project File (`project.synp`)

```synesis
PROJECT MyResearch
    TEMPLATE "template.synt"
    INCLUDE BIBLIOGRAPHY "references.bib"
    INCLUDE ANNOTATIONS "annotations.syn"
    INCLUDE ONTOLOGY "ontologies.syno"

    DESCRIPTION
        Climate Change Perception Study
    END METADATA
END PROJECT
```

### 2. Define a Template (`template.synt`)

```synesis
TEMPLATE QualitativeAnalysis

SOURCE FIELDS
    REQUIRED date, country
    OPTIONAL keywords
END SOURCE FIELDS

ITEM FIELDS
    REQUIRED quote
    REQUIRED BUNDLE note, chain
    OPTIONAL tags
END ITEM FIELDS

ONTOLOGY FIELDS
    REQUIRED description
    OPTIONAL topic
END ONTOLOGY FIELDS

FIELD quote TYPE QUOTATION
    SCOPE SOURCE
    DESCRIPTION Extracted text from source
END FIELD

FIELD note TYPE MEMO
    SCOPE ITEM
    DESCRIPTION Analytical annotation
END FIELD

FIELD chain TYPE CHAIN
    SCOPE ITEM
    ARITY >= 2
    RELATIONS
        INFLUENCES: Causal influence relationship
        ENABLES: Enabling relationship
    END RELATIONS
END FIELD
```

### 3. Add Bibliography (`references.bib`)

```bibtex
@article{smith2024,
    author = {Smith, John},
    title = {Climate Beliefs and Policy Support},
    year = {2024},
    journal = {Environmental Research}
}
```

### 4. Create Annotations (`annotations/sample.syn`)

```synesis
SOURCE @smith2024
    date: 2024-03-15
    country: United States
END SOURCE

ITEM @smith2024
    quote: Public acceptance is crucial for climate policy implementation.

    note: Identifies acceptance as key factor
    chain: Public_Acceptance -> INFLUENCES -> Policy_Support

    note: Links to economic barriers
    chain: Policy_Support -> ENABLES -> Climate_Action
END ITEM
```

### 5. Define Ontology (`ontologies/concepts.syno`)

```synesis
ONTOLOGY Public_Acceptance
    description: Community-level support for climate policies
    topic: Social_Factors
END ONTOLOGY

ONTOLOGY Policy_Support
    description: Governmental and institutional backing
    topic: Political_Factors
END ONTOLOGY
```

### 6. Compile the Project

```bash
# Validate syntax and semantics
synesis compile project.synp

# Export to JSON
synesis compile project.synp --json output.json

# Export to CSV
synesis compile project.synp --csv output_dir/

# Export to Excel
synesis compile project.synp --xls analysis.xlsx
```

## CLI Commands

### `synesis compile`

Compile a Synesis project and generate outputs.

```bash
synesis compile PROJECT.synp [OPTIONS]

Options:
  --json PATH       Export to JSON format
  --csv PATH        Export to CSV directory (creates multiple tables)
  --xls PATH        Export to Excel workbook
  --force           Generate outputs even with validation errors
  --verbose         Show detailed compilation progress
```

### `synesis check`

Validate syntax of a single file without full compilation.

```bash
synesis check FILE.syn
```

### `synesis validate-template`

Validate a template file structure.

```bash
synesis validate-template TEMPLATE.synt
```

### `synesis init`

Initialize a new Synesis project with example files.

```bash
synesis init [PROJECT_NAME]
```

## Python API

Use Synesis directly in Python scripts and Jupyter Notebooks without file I/O.

### Quick Example

```python
import synesis

result = synesis.load(
    project_content='PROJECT Demo TEMPLATE "t.synt" END PROJECT',
    template_content='''
        TEMPLATE Demo
        SOURCE FIELDS
            OPTIONAL date
        END SOURCE FIELDS
        ITEM FIELDS
            REQUIRED quote
        END ITEM FIELDS
        FIELD date TYPE DATE SCOPE SOURCE END FIELD
        FIELD quote TYPE QUOTATION SCOPE ITEM END FIELD
        END TEMPLATE
    ''',
    annotation_contents={
        "data.syn": '''
            SOURCE @ref2024
                date: 2024-01-15
                ITEM
                    quote: Technology shows promising results.
                END ITEM
            END SOURCE
        '''
    },
    bibliography_content='@article{ref2024, author={Silva}, year={2024}}'
)

if result.success:
    # Export to pandas DataFrame
    df = result.to_dataframe("items")

    # Export to dict (JSON-serializable)
    data = result.to_json_dict()

    # Get all tables as DataFrames
    dfs = result.to_dataframes()
```

### Available Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `to_dataframe(table)` | `pd.DataFrame` | Single table as DataFrame |
| `to_dataframes()` | `Dict[str, DataFrame]` | All tables as DataFrames |
| `to_json_dict()` | `Dict` | Full JSON structure as dict |
| `to_csv_tables()` | `Dict[str, tuple]` | Tables as (headers, rows) |

## Output Formats

### JSON Export

Hierarchical structure preserving SOURCE → ITEM relationships:

```json
{
  "project": {
    "name": "MyResearch",
    "template": "template.synt",
    "metadata": {...}
  },
  "sources": [
    {
      "bibref": "smith2024",
      "fields": {"date": "2024-03-15", "country": "United States"},
      "items": [
        {
          "quote": "Public acceptance is crucial...",
          "notes": ["Identifies acceptance as key factor"],
          "chains": [
            {
              "nodes": ["Public_Acceptance", "INFLUENCES", "Policy_Support"],
              "triples": [["Public_Acceptance", "INFLUENCES", "Policy_Support"]]
            }
          ],
          "source_file": "annotations/sample.syn",
          "source_line": 7,
          "source_column": 1
        }
      ]
    }
  ],
  "ontologies": [...]
}
```

### CSV Export

Generates separate tables with full traceability:

- `sources.csv`: Bibliography entries with fields
- `items.csv`: Annotated excerpts with metadata
- `codes.csv`: All applied codes with frequency
- `chains.csv`: Relational triples (from, relation, to)
- `ontologies.csv`: Concept definitions
- `topics.csv`: Hierarchical topic groupings

Each row includes `source_file`, `source_line`, `source_column` for traceability.

### Excel Export

Multi-sheet workbook combining all tables with formatting.

## Language Specification

Full language specification available at: [https://synesis-lang.github.io/synesis-docs](https://synesis-lang.github.io/synesis-docs)

### Core Concepts

- **PROJECT**: Root container defining template and includes
- **SOURCE**: Contextualizes items with bibliographic reference
- **ITEM**: Analytical unit containing quote, codes, memos, chains
- **ONTOLOGY**: Concept definition with description and metadata
- **TEMPLATE**: Meta-schema defining field requirements and types
- **FIELD**: Type declaration (QUOTATION, MEMO, CODE, CHAIN, TEXT, DATE, SCALE, ENUMERATED, ORDERED, TOPIC)

### Field Types

| Type | Scope | Description |
|------|-------|-------------|
| QUOTATION | ITEM | Verbatim text excerpt from source |
| MEMO | ITEM | Researcher's analytical annotation |
| CODE | ITEM | Categorical label (concept reference) |
| CHAIN | ITEM | Qualified relational structure (A → REL → B) |
| TEXT | Any | Free-form text field |
| DATE | SOURCE | Temporal metadata |
| SCALE | Any | Numeric value with range constraints |
| ENUMERATED | Any | Closed-list categorical value |
| ORDERED | ONTOLOGY | Hierarchical indexed value |
| TOPIC | ONTOLOGY | Dynamic category grouping |

## Development

### Running Tests

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run all tests
pytest

# Run with coverage
pytest --cov=synesis --cov-report=html
```

### Project Structure

```
synesis/
├── synesis/              # Main package
│   ├── cli.py           # Command-line interface
│   ├── compiler.py      # Compilation orchestrator
│   ├── ast/             # AST node definitions
│   ├── parser/          # Parsing and loading
│   ├── semantic/        # Validation and linking
│   ├── exporters/       # Output format generators
│   └── grammar/         # Lark grammar file
└── tests/               # Test suite with fixtures
```

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Documentation

- **Homepage**: [https://synesis-lang.github.io/synesis-docs](https://synesis-lang.github.io/synesis-docs)
- **Repository**: [https://github.com/synesis-lang/synesis](https://github.com/synesis-lang/synesis)
- **Issue Tracker**: [https://github.com/synesis-lang/synesis/issues](https://github.com/synesis-lang/synesis/issues)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Citation

If you use Synesis in your research, please cite:

```bibtex
@software{synesis2026,
  title = {Synesis: A Domain-Specific Language for Qualitative Research},
  author = {{De Britto, Christian Maciel}},
  year = {2026},
  url = {https://github.com/synesis-lang/synesis},
  version = {0.2.0}
}
```

## Acknowledgments

Synesis implements a Result-based error handling system inspired by Elm and Rust, ensuring robust compilation without uncontrolled exceptions.
