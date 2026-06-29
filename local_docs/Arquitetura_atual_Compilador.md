# Arquitetura do Compilador Synesis

> Última atualização: 2026-06-18 — baseada no código-fonte em `d:\GitHub\synesis\`

---

## 1. Visão Geral

O compilador Synesis transforma arquivos `.syn` (anotações), `.syno` (ontologia) e `.synt` (template) em saídas estruturadas (JSON, CSV, Excel, ALPACA). O orchestrador central é `SynesisCompiler` em `compiler.py`, que coordena oito estágios em sequência estrita. Erros em qualquer estágio são acumulados em `ValidationResult` e nunca lançam exceções não controladas para o chamador.

---

## 2. Estrutura de Módulos

```
synesis/
├── cli.py                   # Entrypoint CLI (Click)
├── api.py                   # API em-memória: synesis.load()
├── compiler.py              # SynesisCompiler — orquestrador
├── lsp_adapter.py           # Bridge para LSP (arquivo único)
├── error_handler.py         # Mensagens pedagógicas de erro
│
├── ast/
│   ├── nodes.py             # Dataclasses da AST (frozen não-aplicado, mas imutáveis por convenção)
│   ├── results.py           # Result[T,E], Ok/Err, ValidationResult, ValidationError
│   └── normalize.py         # normalize_code, normalize_bibref
│
├── parser/
│   ├── lexer.py             # Wrapper Lark LALR(1), SynesisSyntaxError
│   ├── transformer.py       # Parse tree → nós AST tipados
│   ├── template_loader.py   # Parsing .synt → TemplateNode
│   ├── bib_loader.py        # Parsing BibTeX → Dict[str, BibEntry]
│   └── parse_cache.py       # Cache (path, mtime) → List[nodes]
│
├── semantic/
│   ├── validator.py         # SemanticValidator: campos, tipos, bundles, bibrefs
│   └── linker.py            # Linker: vincula ITEMs a SOURCEs, constrói LinkedProject
│
├── exporters/
│   ├── json_export.py       # JSON hierárquico v2.0
│   ├── csv_export.py        # CSV multi-tabela
│   ├── xls_export.py        # Excel multi-sheet
│   ├── alpaca_export.py     # Formato ALPACA
│   └── _helpers.py          # Funções utilitárias compartilhadas
│
└── grammar/
    └── synesis.lark         # Gramática LALR(1) — CONGELADA para v1.x
```

---

## 3. Pipeline de Compilação

O método `SynesisCompiler.compile()` executa os estágios abaixo em ordem. Erros são **acumulados**, não interrompem o fluxo (exceto template ausente, que aborta cedo).

```mermaid
flowchart TD
    A([.synp — arquivo de projeto]) --> B

    subgraph S1["① DISCOVERY — parse_project()"]
        B[parse_file → Lark LALR] --> C[SynesisTransformer → ProjectNode]
        C --> D{validate_project_structure}
        D -->|erros 61-67| E[(ValidationResult)]
    end

    S1 --> S2

    subgraph S2["② TEMPLATE LOADING — _safe_load_template()"]
        F[load_template .synt] --> G[TemplateNode\nFieldSpec × Scope × FieldType]
        G --> H[validate_template\nerros 6,18,39-60,69]
        H -->|erros| E
    end

    S2 -->|template ausente → aborta| FAIL([CompilationResult: success=False])
    S2 --> S3

    subgraph S3["③ BIBLIOGRAPHY — load_bibliography()"]
        I[bib_loader → BibEntry\ndetect_malformed_entries] -->|erros 63,72| E
        I --> J[(Dict bibkey → BibEntry)]
    end

    S3 --> S4

    subgraph S4["④ PARSING — parse_ontologies / parse_annotations()"]
        K[parse_file .syno → Lark] --> L[Transformer → OntologyNode list]
        M[parse_file .syn → Lark\n≤3 arquivos: sequencial\n>3 arquivos: ProcessPoolExecutor] --> N[Transformer → SourceNode + ItemNode lists]
        M --> O[(parse_cache\npath × mtime → nodes)]
    end

    S4 --> S5

    subgraph S5["⑤ SEMANTIC VALIDATION — validate_all()"]
        P[SemanticValidator\ntemplate + bibliography + ontology_index]
        P --> P1[validate_project]
        P --> P2[validate_source × N]
        P --> P3[validate_item × N\nCHECKS: campos, tipos, bibrefs,\nbundles, chains, arity, ENUMERATED,\nSCALE, ORDERED, CODEs definidos]
        P --> P4[validate_ontology × N]
        P1 & P2 & P3 & P4 -->|erros/warnings| E
    end

    S5 --> S6

    subgraph S6["⑥ LINKING — link_all() → Linker.link()"]
        Q[Linker\nsources + items + ontologies]
        Q --> Q1[Índice SOURCE por bibref normalizado]
        Q --> Q2[Associa ITEMs a SOURCEs\nOrphanItem / SourceWithoutItems]
        Q --> Q3[Índice de ontologia / grafo IS_A\npor parent_chains]
        Q --> Q4[Coleta all_triples de CHAINs\naugmenta code_locations]
        Q1 & Q2 & Q3 & Q4 --> R[(LinkedProject)]
        Q -->|erros| E
    end

    S6 --> S7

    subgraph S7["⑦ STATS — _compute_stats()"]
        S8[source_count / item_count / ontology_count\ncode_count / chain_count / triple_count]
    end

    S7 --> S8b{has_errors?}
    S8b -->|Sim| FAIL
    S8b -->|Não| SUCCESS

    subgraph S8["⑧ EXPORT — CompilationResult.to_*()"]
        T1[export_json → JSON v2.0]
        T2[export_csv → CSV multi-tabela]
        T3[export_xls → Excel multi-sheet]
        T4[export_alpaca → ALPACA]
    end

    SUCCESS --> S8
    FAIL --> END([Diagnósticos para CLI / LSP])
    S8 --> END2([Arquivos de saída])
```

---

## 4. Nós da AST (`ast/nodes.py`)

Todos os nós são `@dataclass` e expõem `to_dict()` para serialização.

```mermaid
classDiagram
    class SourceLocation {
        +file: Path
        +line: int
        +column: int
    }

    class ProjectNode {
        +name: str
        +template_path: Path
        +includes: List[IncludeNode]
        +metadata: Dict[str, str]
        +description: Optional[str]
        +location: SourceLocation
    }

    class TemplateNode {
        +name: str
        +field_specs: Dict[str, FieldSpec]
        +required_fields: Dict[Scope, List[str]]
        +optional_fields: Dict[Scope, List[str]]
        +forbidden_fields: Dict[Scope, List[str]]
        +bundled_fields: Dict[Scope, List[Tuple]]
    }

    class FieldSpec {
        +name: str
        +type: FieldType
        +scope: Scope
        +arity: Optional[str]
        +relations: Optional[Dict]
        +values: Optional[List[OrderedValue]]
    }

    class SourceNode {
        +bibref: str
        +fields: Dict[str, Any]
        +items: List[ItemNode]
        +location: SourceLocation
    }

    class ItemNode {
        +bibref: str
        +quote: str
        +codes: List[str]
        +notes: List[str]
        +chains: List[ChainNode]
        +extra_fields: Dict[str, Any]
        +code_locations: Dict[str, List[SourceLocation]]
    }

    class OntologyNode {
        +concept: str
        +description: str
        +fields: Dict[str, Any]
        +parent_chains: List[ChainNode]
    }

    class ChainNode {
        +nodes: List[str]
        +relations: List[str]
        +node_locations: List[SourceLocation]
        +to_triples(has_relations) List~Tuple~
    }

    ProjectNode "1" --> "*" IncludeNode
    ProjectNode --> SourceLocation
    TemplateNode "1" --> "*" FieldSpec
    SourceNode "1" --> "*" ItemNode
    ItemNode "1" --> "*" ChainNode
    OntologyNode "1" --> "*" ChainNode
```

### Enums de domínio

| Enum | Valores |
|------|---------|
| `Scope` | `SOURCE`, `ITEM`, `ONTOLOGY` |
| `FieldType` | `QUOTATION`, `MEMO`, `CODE`, `CHAIN`, `TEXT`, `DATE`, `SCALE`, `ENUMERATED`, `ORDERED`, `TOPIC` |

---

## 5. Sistema de Erros (`ast/results.py`)

```mermaid
classDiagram
    class Ok~T~ {
        +value: T
        +is_ok() bool
        +unwrap() T
        +map(fn) Result
    }

    class Err~E~ {
        +error: E
        +is_err() bool
        +unwrap_or(default) T
    }

    class ValidationError {
        <<abstract>>
        +location: SourceLocation
        +severity: Severity
        +code: int
        +to_diagnostic() str
        +to_cli_line() str
    }

    class ValidationResult {
        +errors: List[ValidationError]
        +warnings: List[ValidationError]
        +info: List[ValidationError]
        +has_errors() bool
        +add(error)
        +to_diagnostics(verbose) str
    }

    Ok --|> Result
    Err --|> Result
    ValidationResult "1" --> "*" ValidationError
```

**Arquitetura dual de mensagens:**
- `to_diagnostic()` — mensagem verbosa, para LSP e LLMs (inclui contexto, sugestões)
- `to_cli_line()` — mensagem enxuta, para saída no terminal

---

## 6. Camada de Parser (`parser/`)

```mermaid
flowchart LR
    subgraph Entrada
        F1[".syn / .syno / .synp"]
        F2[".synt"]
        F3[".bib"]
    end

    subgraph lexer.py
        L1[load_grammar\nimportlib.resources] --> L2[create_parser\nLark LALR regex=True]
        L2 --> L3[parse_file / parse_string\n→ Lark Tree]
        L3 -->|UnexpectedToken\nUnexpectedChars| L4[SynesisSyntaxError\n+ error_handler.py\nmensagens pedagógicas]
    end

    subgraph transformer.py
        T1[SynesisTransformer\nextends Lark.Transformer] --> T2[Métodos por regra gramatical\nex: item_block, source_block]
        T2 --> T3["List[ProjectNode | SourceNode\n| ItemNode | OntologyNode]"]
    end

    subgraph template_loader.py
        TL1[parse_file .synt] --> TL2[SynesisTransformer parcial]
        TL2 --> TL3[TemplateNode\n+ validate_template]
    end

    subgraph bib_loader.py
        BL1[bibtexparser] --> BL2["Dict[str, BibEntry]"]
        BL1 --> BL3[detect_malformed_entries]
    end

    subgraph parse_cache.py
        PC["(path, mtime) → List[nodes]\ncache global por processo"]
    end

    F1 --> lexer.py
    F2 --> template_loader.py
    F3 --> bib_loader.py
    lexer.py --> transformer.py
    transformer.py <--> parse_cache.py
```

**Cache de parsing** (`parse_cache.py`): chave `(path.resolve(), mtime)` → `List[nodes]`. Beneficia compilações repetidas no mesmo processo (LSP, testes, API). A CLI não se beneficia (novo processo por invocação).

---

## 7. Validação Semântica (`semantic/validator.py`)

`SemanticValidator` recebe o `TemplateNode` como fonte da verdade e valida cada nó contra ele.

```mermaid
flowchart TD
    SV[SemanticValidator\ntemplate + bibliography + ontology_index]

    SV --> VP[validate_project\nMetadados PROJECT]
    SV --> VS[validate_source\n• bibref existe no .bib\n• campos de escopo SOURCE\n• REQUIRED / OPTIONAL / FORBIDDEN]
    SV --> VI[validate_item\n• bibref existe no .bib\n• campos de escopo ITEM\n• REQUIRED/OPTIONAL/FORBIDDEN\n• BUNDLE integridade\n• CHAIN: arity, relações, qualified/simple\n• CODE: definido na ontologia\n• ENUMERATED, SCALE, ORDERED\n• EmptyItemBlock]
    SV --> VO[validate_ontology\n• campos ONTOLOGY\n• ConceptWithSpaces\n• ConceptNameMatchesRelation\n• TOPIC, CHAIN IS_A]

    VP & VS & VI & VO --> VR[(ValidationResult)]
```

**Checagens notáveis em `validate_item`:**

| Verificação | Erro emitido |
|------------|--------------|
| Campo desconhecido | `UnknownFieldName` (com sugestão fuzzy) |
| Campo REQUIRED ausente | `MissingRequiredField` |
| Campo FORBIDDEN presente | `ForbiddenFieldPresent` |
| BUNDLE incompleto | `MissingBundleField` / `BundleCountMismatch` |
| CHAIN sem operador `->` | `ChainWithoutArrowOperator` |
| CHAIN qualificada malformada | `MalformedQualifiedChain` |
| ARITY violada | `ChainArityViolation` |
| CODE não definido na ontologia | `UndefinedCode` (warning) |
| Bibref não encontrado no .bib | `UnregisteredSource` |

---

## 8. Vinculação (`semantic/linker.py`)

`Linker` constrói o `LinkedProject` — estrutura consolidada para exportação.

```mermaid
flowchart TD
    LI[Linker\nsources + items + ontologies\n+ project + template]

    LI --> L1[Indexar SOURCEs por bibref normalizado\nDuplicateSourceBibref se colisão]
    LI --> L2[Associar ITEMs a SOURCEs\nOrphanItem se bibref do ITEM sem SOURCE\nSourceWithoutItems se SOURCE sem ITEMs]
    LI --> L3[Indexar ontologia: concept → OntologyNode\nDuplicateOntologyConcept / DuplicateOntologyDescription]
    LI --> L4[Construir grafo IS_A\npor parent_chains nos OntologyNodes]
    LI --> L5[Coletar all_triples das CHAINs\n_augment_item_field_locations\ncode_locations por campo]

    L1 & L2 & L3 & L4 & L5 --> LP[(LinkedProject\nproject\nsource_index\nontology_index\nall_triples\nitem_field_locations)]
    L1 & L2 & L3 -->|erros| VR[(ValidationResult)]
```

---

## 9. Exportadores (`exporters/`)

```mermaid
flowchart LR
    LP[(LinkedProject\n+ TemplateNode\n+ bibliography)]

    LP --> J[json_export.py\nexport_json\nJSON v2.0 hierárquico\nrastreabilidade completa]
    LP --> C[csv_export.py\nexport_csv\nCSV multi-tabela\nSOURCE / ITEM / CHAIN / ONTOLOGY]
    LP --> X[xls_export.py\nexport_xls\nExcel multi-sheet\nautosized columns]
    LP --> A[alpaca_export.py\nexport_alpaca\nformato ALPACA]

    J --> O1[".json"]
    C --> O2[".csv × N tabelas"]
    X --> O3[".xlsx"]
    A --> O4[".alpaca"]
```

**Regra de exportação:** exportação só ocorre quando `not has_errors()`. Com `--force` na CLI, a restrição é levantada.

---

## 10. Pontos de Integração

```mermaid
flowchart TD
    CLI["cli.py\nsynesis compile / check\nsynesis validate-template\nsynesis init"]
    API["api.py\nsynesis.load()\ncompile_string()\nMemoryCompilationResult"]
    LSP["lsp_adapter.py\nvalidate_single_file(path, content, ctx)\nDescobre .synp → carrega contexto\nCache por workspace + mtime"]

    CLI --> SC[SynesisCompiler]
    API --> SC
    LSP --> SV2[SemanticValidator\n+ parse_string\nsem disco]

    SC --> VR[(ValidationResult)]
    SV2 --> VR

    VR -->|CLI| TERM[Terminal\nfile:line:col: [SEVERITY] msg]
    VR -->|LSP| DIAG[LSP Diagnostics\nJSON-RPC → VSCode]
    VR -->|API| MEM[MemoryCompilationResult\nto_json_dict / to_csv_dict]
```

### Descoberta de contexto no LSP (`lsp_adapter.py`)

O `validate_single_file` opera em arquivo único mas tenta enriquecer a validação com o contexto do projeto:

1. Detecta raiz do workspace (marcadores: `.git`, `.vscode`, `.synp`)
2. Busca `.synp` na raiz
3. Carrega `TemplateNode` e `bibliography` a partir do `.synp`
4. Cache de contexto por workspace com invalidação por `mtime`

Sem `.synp` encontrado → emite warning, valida apenas sintaxe.

---

## 11. Paralelismo no Parsing de Anotações

```mermaid
flowchart TD
    PA[parse_annotations\nList[Path]]
    PA --> N{N arquivos}
    N -->|N ≤ 3| SEQ[Sequential\n_parse_annotations_sequential]
    N -->|N > 3| PAR[ProcessPoolExecutor\nmax_workers = min 4 N\n_parse_single_annotation por processo]
    SEQ & PAR --> RS[List[SourceNode]\n+ List[ItemNode]]
```

`_parse_single_annotation` é uma função module-level (necessário para pickling com `multiprocessing`). Cada worker cria seu próprio parser e transformer — não há estado compartilhado.

---

## 12. Template como Fonte da Verdade

O `TemplateNode` é carregado no estágio ② e propagado para todos os estágios seguintes. Nenhum componente assume nomes de campos fixos — a estrutura é sempre derivada do template em tempo de execução.

```mermaid
flowchart LR
    T[(.synt\nTemplateNode)]
    T --> SV3[SemanticValidator\nvalida campos pelo nome]
    T --> LK[Linker\naugmenta field_locations\npor tipo de campo]
    T --> JE[json_export\nprojeta campos por escopo]
    T --> CE[csv_export\ncolunas dinâmicas]
    T --> XE[xls_export\nsheets por escopo]
    T --> AE[alpaca_export]
    T --> LA[lsp_adapter\nschema para LSP]
```

---

## 13. Gramática (`grammar/synesis.lark`)

Parser LALR(1) construído com Lark. Usa `regex=True` para suportar Unicode (`\p{L}`, `\p{N}`) em identificadores e valores.

**Status:** CONGELADA para v1.x. Alterações breaking requerem v2.0.

O arquivo `synesis_standalone.py` em `grammar/` é uma versão auto-contida do parser gerada para distribuição sem dependência de arquivo externo.

---

## 14. Fluxo Completo — Diagrama de Sequência

```mermaid
sequenceDiagram
    participant U as Usuário / LSP
    participant CLI as cli.py / api.py
    participant Comp as SynesisCompiler
    participant Lex as lexer.py
    participant Tr as transformer.py
    participant TL as template_loader.py
    participant Bib as bib_loader.py
    participant Val as SemanticValidator
    participant Lnk as Linker
    participant Exp as Exporters

    U->>CLI: synesis compile projeto.synp
    CLI->>Comp: SynesisCompiler(project_path).compile()

    Comp->>Lex: parse_file(.synp)
    Lex-->>Comp: Lark Tree
    Comp->>Tr: SynesisTransformer.transform(tree)
    Tr-->>Comp: ProjectNode

    Comp->>Comp: validate_project_structure()

    Comp->>TL: load_template(.synt)
    TL->>Lex: parse_file(.synt)
    TL-->>Comp: TemplateNode

    Comp->>TL: validate_template(template)

    Comp->>Bib: load_bibliography(.bib)
    Bib-->>Comp: Dict[bibkey, BibEntry]

    Comp->>Lex: parse_file(.syno × N)
    Lex-->>Comp: Trees
    Comp->>Tr: transform → OntologyNode list

    Comp->>Lex: parse_file(.syn × N) [± ProcessPool]
    Lex-->>Comp: Trees
    Comp->>Tr: transform → SourceNode + ItemNode lists

    Comp->>Val: validate_all(project, template, bib, sources, items, ontologies)
    Val-->>Comp: ValidationResult (erros + warnings)

    Comp->>Lnk: link_all(...)
    Lnk-->>Comp: LinkedProject + ValidationResult adicional

    Comp-->>CLI: CompilationResult

    alt sem erros
        CLI->>Exp: export_json / export_csv / export_xls
        Exp-->>U: arquivos de saída
    else com erros
        CLI-->>U: diagnósticos arquivo:linha:col
    end
```
