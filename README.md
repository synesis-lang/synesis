# Synesis

**The confluence of evidence into auditable knowledge.**

A Domain-Specific Language and toolchain for transforming qualitative research annotations into structured, validated, and fully traceable knowledge artifacts.

[![PyPI version](https://img.shields.io/pypi/v/synesis)](https://pypi.org/project/synesis/)
[![Python 3.10+](https://img.shields.io/pypi/pyversions/synesis)](https://pypi.org/project/synesis/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/synesis-lang/synesis/blob/main/LICENSE)

> **Copyright (c) 2011–2026 Christian Maciel de Britto**
> [`https://github.com/synesis-lang`](https://github.com/synesis-lang) · [`ORCID`](https://orcid.org/0000-0003-1431-3924)

---

## What is Synesis?

Qualitative research — literature reviews, grounded theory, case studies, systematic reviews — generates enormous interpretive work that is typically scattered across unstructured notes, spreadsheets, or proprietary software locked to a single vendor.

Synesis is a **semantic compiler for analytical thinking**: you write your interpretations in plain-text files with a clean declarative syntax, and the toolchain validates, structures, and exports them as canonical knowledge artifacts. Every concept is traceable to its source file, line, and column. No silent errors. No orphaned codes. No ambiguous relations.

The name comes from the Greek *σύνεσις* — the convergence of evidence fragments into an intelligible whole. In its biblical sense (Colossians 1:9, *synesei pneumatikei*), it denotes a form of understanding that connects rather than merely accumulates.

**The core differentiator:** validation happens at **compile time**, not at retrieval or graph construction. If a code does not exist in the declared ontology, the compiler rejects the annotation at the source — before any output is produced. This is the architectural distinction that separates Synesis from all known CAQDAS alternatives and RAG pipeline tooling.

---

## The Ecosystem

```
📚 Zotero                    🤖 synesis-coder
   PDF annotations    ──►       AI-assisted annotation
   (zotero-synesis-export)       generates full .syn files
         │                              │
         ▼                              ▼
    📄 .syn / .synt / .syno / .synp  (Synesis source files)
         │
         ▼
    ⚙️  Synesis Compiler  (this package)
    LALR(1) parser · AST validator · multi-artifact exporter
         │
    ┌────┴──────────────────────────────────┐
    ▼                                       ▼
🐍 Python API                          📊 Structured outputs
   synesis.load()                         JSON · CSV · Excel
   to_dataframe()                         REFI-QDA · DOCX · Alpaca JSONL
         │                                       │
         ▼                                       ▼
📓 Jupyter Notebooks               🕸️  Neo4j / Memgraph
   data science · visualization        graph queries via MCP
         │
    🧠 synesis-lsp  ──►  🖥️  Synesis Explorer (VS Code)
       Language Server      real-time diagnostics · graph viewer
```

| Repository | Language | Role |
|---|---|---|
| **synesis** ← this | Python | Compiler, parser, validator, exporters, Python API |
| synesis-lsp | Python | Language Server — diagnostics, hover, completion, semantic tokens |
| synesis-explorer | JS/TS | VS Code extension — tree views, graph viewer, themes |
| zotero-synesis-export | JavaScript | Zotero 7 plugin — exports PDF highlights as plain `.syn` |
| synesis-graph | Python | Import compiled knowledge into Neo4j / Memgraph |
| synesis-coder | Python | AI-assisted annotation — generates fully coded `.syn` files |

---

## Installation

```bash
pip install synesis
```

Requires Python 3.10+.

---

## A Complete Example

### `references.bib`
```bibtex
@article{smith2024,
    author  = {Smith, Jane},
    title   = {Understanding Community Resilience},
    journal = {Journal of Social Research},
    year    = {2024},
    volume  = {12},
    pages   = {45--67}
}
```

### `template.synt` — field schema and validation rules
```synesis
SOURCE FIELDS
    OPTIONAL description
END SOURCE FIELDS

FIELD description TYPE TEXT
    SCOPE SOURCE
    DESCRIPTION General context or summary of the data source
    GUIDELINES
        Summarize the source purpose in 1-2 sentences.
        Do not add analytical interpretation.
    END GUIDELINES
END FIELD

ITEM FIELDS
    REQUIRED citation, note, code
END ITEM FIELDS

FIELD citation TYPE QUOTATION
    SCOPE ITEM
    DESCRIPTION Direct quote or selected excerpt from the data source
    GUIDELINES
        Extract a complete, self-contained excerpt of 1-3 sentences.
        Preserve the original wording. Do not paraphrase.
    END GUIDELINES
END FIELD

FIELD note TYPE MEMO
    SCOPE ITEM
    DESCRIPTION Analytical memo recording interpretations or causal reasoning
    GUIDELINES
        Explain the analytical significance in 1-3 sentences.
        Distinguish textual evidence from your interpretation.
    END GUIDELINES
END FIELD

FIELD code TYPE CODE
    SCOPE ITEM
    DESCRIPTION Ontology codes applied to this excerpt
    GUIDELINES
        Apply only codes supported by the excerpt.
        Every code must have a corresponding ONTOLOGY entry.
    END GUIDELINES
END FIELD

ONTOLOGY FIELDS
    REQUIRED definition, group
END ONTOLOGY FIELDS

FIELD definition TYPE TEXT
    SCOPE ONTOLOGY
    DESCRIPTION Clear definition of the code with inclusion/exclusion criteria
END FIELD

FIELD group TYPE TOPIC
    SCOPE ONTOLOGY
    DESCRIPTION Broader thematic domain that groups related codes
END FIELD
```

### `annotations.syn` — your research data
```synesis
SOURCE @smith2024
    description: Qualitative study on community resilience strategies in urban contexts.
END SOURCE

ITEM @smith2024
    citation: "People here look out for each other. When the flood came, nobody waited
        for official help — neighbors just organized themselves."

    note: Participant describes spontaneous collective action as a primary resilience
        mechanism, bypassing formal institutions. Suggests strong bonding social capital.

    code: Social_Cohesion, Collective_Action
END ITEM
```

### `ontology.syno` — controlled vocabulary
```synesis
ONTOLOGY Social_Cohesion
    definition: The degree to which community members trust, support, and cooperate
        with one another. Applies when participants describe solidarity or mutual aid.
    group: Community_Resilience
END ONTOLOGY

ONTOLOGY Collective_Action
    definition: Coordinated efforts by community members to address shared challenges
        without formal institutional direction.
    group: Community_Resilience
END ONTOLOGY
```

### `project.synp` — the entry point
```synesis
PROJECT demo
    TEMPLATE "template.synt"
    INCLUDE BIBLIOGRAPHY "references.bib"
    INCLUDE ANNOTATIONS "annotations.syn"
    INCLUDE ONTOLOGY    "ontology.syno"
END PROJECT
```

---

## CLI

```bash
# Compile a project and generate all output artifacts
synesis compile project.synp --output results/

# Validate syntax and integrity without generating output
synesis check annotations.syn

# Validate template structure and consistency
synesis validate-template template.synt

# Show version and authorship
synesis --version

# Show full intellectual genealogy
synesis --credits
```

---

## Python API

Compile entirely in-memory — no file I/O required:

```python
import synesis

result = synesis.load(
    project_content   = open("project.synp").read(),
    template_content  = open("template.synt").read(),
    annotation_contents = {"annotations.syn": open("annotations.syn").read()},
    ontology_contents   = {"ontology.syno": open("ontology.syno").read()},
    bibliography_content = open("references.bib").read(),
)

if result.success:
    # Export as pandas DataFrames
    items_df  = result.to_dataframe("items")
    codes_df  = result.to_dataframe("codes")
    chains_df = result.to_dataframe("chains")

    # Export as JSON
    data = result.to_json_dict()

    # Compilation stats
    print(result.stats)
    # CompilationStats(source_count=1, item_count=1, ontology_count=2, code_count=2)
else:
    for diagnostic in result.get_diagnostics():
        print(diagnostic)
```

Available tables: `sources`, `items`, `ontologies`, `codes`, `chains`.

---

## Language Features

**Sources & Items** — Every annotation is traceable to a BibTeX reference. The compiler validates each `@key` against the bibliography at compile time.

**Templates** — Define field schemas with types (`CODE`, `TEXT`, `CHAIN`, `SCALE`, `QUOTATION`, `MEMO`...), validation rules (`REQUIRED`, `OPTIONAL`, `FORBIDDEN`), and constraints (`ARITY`, `BUNDLE`, `VALUES`). The template is the contract between the researcher and the compiler.

**Ontologies** — Controlled vocabularies validated at compile time. Every code must exist in the declared ontology — typos and orphaned concepts are caught immediately, at the source.

**Chains** — Causal or relational links: `Trust -> ENABLES -> Acceptance`. Validated against declared `RELATIONS` and `ARITY` constraints.

**GUIDELINES** — Instructional prose embedded in template field definitions, visible to human annotators and LLM coders, never parsed as code.

**Deterministic multi-artifact emission** — A single compilation pass produces JSON, CSV, Excel, REFI-QDA, DOCX, and Alpaca JSONL simultaneously. All-or-nothing: either every artifact is valid, or nothing is emitted.

---

## File Types

| Extension | Purpose |
|---|---|
| `.syn` | Annotation files — sources and items |
| `.synp` | Project file — declares template, bibliography, includes |
| `.synt` | Template file — field schema and validation rules |
| `.syno` | Ontology file — controlled vocabulary of codes |
| `.bib` | BibTeX bibliography (standard format) |

---

## Potential Applications

| Domain | How Synesis helps |
|---|---|
| Systematic literature reviews | Annotate hundreds of papers with a shared template; export clean datasets for meta-analysis |
| Grounded Theory / Thematic Analysis | Build and validate code systems with ontological constraints; trace every code to its source |
| Mixed-methods research | Bridge qualitative interpretation with quantitative formats for R or Python workflows |
| Knowledge graphs | Compile research findings into Neo4j; model causal chains as graph edges |
| AI-augmented analysis | Feed structured annotations as context to LLMs via MCP; responses traceable to source evidence |
| Biblical / exegetical studies | Code canonical texts with relational chains; integrate classical and patristic corpora |
| Longitudinal projects | Template versioning and strict validation prevent concept drift across research phases |

---

## Architecture

```
synesis compile project.synp
         │
    Lark LALR(1) parser
         │
    AST Transformer
         │
    Semantic Validator ◄── ontology · bibliography · template contract
         │
    Exporters (single pass, all-or-nothing)
    ├── JSON
    ├── CSV
    ├── Excel
    ├── REFI-QDA
    ├── DOCX
    └── Alpaca JSONL  (fine-tuning datasets for open-weight LLMs)
```

The compiler exposes `compile_string()` for integration with `synesis-lsp`, enabling real-time diagnostics in the VS Code extension without spawning a subprocess.

---

## VS Code Integration

The **Synesis Explorer** extension (requires `synesis-lsp`) provides:

- Real-time diagnostics — errors and warnings as you type
- Semantic syntax highlighting — AST-driven, not regex
- Tree explorers for References, Codes, Relations, and Ontology
- Go-to-definition, rename, and hover documentation
- Relation graph viewer (Mermaid → SVG)
- Abstract viewer with BibTeX highlights
- Synesis Dark and Light themes

---

## Compatibility

| Package | Latest | Requires synesis | Python |
|---|---|---|---|
| synesis | 0.6.0 | — | ≥ 3.10 |
| synesis-coder | 0.4.1 | ≥ 0.5.5 | ≥ 3.10 |
| synesis-lsp | 0.16.0 | ≥ 0.5.5 | ≥ 3.10 |
| synesis-graph | 0.2.0 | ≥ 0.5.5 | ≥ 3.10 |

---

## Intellectual Genealogy

Synesis is the formal culmination of a research and development trajectory spanning more than a decade. Its architecture, domain vocabulary, and methodological requirements emerged from successive implementations across qualitative research, professional consultancy, and biblical hermeneutics:

| Period | Work | Contribution |
|---|---|---|
| 2011–2013 | BDM — Banco de Dados Multimodal | First definition of: sources, items, factors, relations, ontology, knowledge graph as an integrated structure |
| 2016–2018 | SocioAtlas | CAQDAS ecosystem integrating annotations, audit trails, Zotero, and graph visualization |
| 2019–2020 | DSAP annotation pipeline | Professional validation of the corpus → item → summary → theme → score audit trail |
| 2022 | SocioAtlas para Google Sheets | Collaborative access; first attempt at systematic theological annotation in the same framework |
| 2024 | DGT7 | Text-file knowledge representation; exposed the need for formal, validatable syntax |

All prior works are authored by Christian Maciel de Britto. The `NOTICE` file in the repository records the formal copyright notices for each predecessor work.

---

## License

MIT — see [LICENSE](https://github.com/synesis-lang/synesis/blob/main/LICENSE).

The outputs generated by Synesis (compiled knowledge artifacts — JSON, CSV, Excel, REFI-QDA, DOCX, Alpaca JSONL) are **not** covered by this license. You retain full ownership of your research data and all compiled outputs.

> A license change to **AGPL-3.0-only** (with Synesis Data Output Exception) is planned for an upcoming release. This will not affect existing users' right to use their compiled outputs.

---

## Author

**Dr. Christian Maciel de Britto**
Researcher · Software author · Knowledge engineer

[GitHub](https://github.com/synesis-lang) · [ORCID](https://orcid.org/0000-0003-1431-3924) · [Lattes](https://lattes.cnpq.br/2334832147379385)

*"True σύνεσις — the convergence of evidence fragments into an intelligible, auditable, and technically rigorous whole."*