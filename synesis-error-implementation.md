# Estudo de Implementação — 52 Mensagens de Erro Pendentes

## Visão Geral

| Métrica | Valor |
|---|---|
| Erros especificados | 71 |
| Implementados (antes da Fase 1) | 19 |
| **Implementados após Fase 1** | **~35** |
| Pendentes após Fase 1 | ~36 |
| Novas subclasses `ValidationError` (Fase 1) | 19 |
| Arquivos modificados na Fase 1 | 4 (`results.py`, `template_loader.py`, `compiler.py`, `nodes.py`) |
| Fases restantes | 5 |

### Princípios de Design

1. **Padrão existente é lei** — toda nova validação segue o padrão `frozen dataclass` + `ValidationError` + `to_diagnostic()` + `DEFAULT_SEVERITY: ClassVar`
2. **Gramática CONGELADA** — `synesis.lark` não muda para v1.x; toda validação nova é semântica
3. **Template como fonte única de verdade** — sem nomes de campo hardcoded
4. **LSP delega ao compilador** — zero lógica de validação no LSP
5. **Mensagens pedagógicas** — estrutura tripartite: o que aconteceu, por quê, o que fazer
6. **Sugestões por similaridade** — `difflib.get_close_matches` (já usado em `InvalidChainRelation`)
7. Codificação em estilo prioritariamente procedural.

---

## Arquitetura do Pipeline Atual

```
.synp → parse_project() → load_template() → load_bibliography()
     → parse_ontologies() → parse_annotations()
     → validate_all(SemanticValidator) → link_all(Linker)
     → CompilationResult → lsp_adapter → converters → VSCode Diagnostics
```

**Ponto de inserção para erros de template:** entre `load_template()` e `validate_all()`.
**Ponto de inserção para erros de projeto:** em `parse_project()` e início de `compile()`.

### Arquivos-chave e suas responsabilidades

| Arquivo | Responsabilidade | Erros atuais |
|---|---|---|
| `ast/results.py` | 19 subclasses `ValidationError` | Todos os 19 |
| `compiler.py` | Pipeline: parse → validate → link | `MissingProjectFile`, `MissingTemplateFile`, `InvalidProjectFile` |
| `parser/template_loader.py` | `load_template()`, `TemplateLoadError` (exceção) | Nenhum (usa exceções) |
| `semantic/validator.py` | `SemanticValidator` — validate source/item/ontology/chain/bundle | 12 tipos |
| `semantic/linker.py` | `Linker` — orphan items, undefined codes, source-without-items | 4 tipos |
| `lsp_adapter.py` | `validate_single_file()` + context discovery | `MissingProjectFile`, `MissingTemplateFile`, `InvalidProjectFile` |

---

## Status de Implementação — Fase 2 ✅ CONCLUÍDA

**Erros implementados:** 5, 8, 9, 23, 26, 31
**Erros postergados (quebrariam projetos existentes):**
- Erro 32 (TopicWithSpaces): projetos reais usam espaços em valores TOPIC (ex: `Justice & Ethics`)
- Erro 33 (InvalidIdentifierCharacter): projetos bíblicos usam hífens em nomes de conceitos (ex: `LIGHT-DARKNESS`)
- Ambos requerem migração dos projetos existentes antes de ativar

**Arquivos modificados:**
- `synesis/ast/results.py` — 8 novas subclasses: `OntologyWithoutTemplateFields`, `QualifiedChainWithoutRelations`, `SimpleChainWithRelationsRequired`, `EmptyItemBlock`, `DecimalInIntegerScale`, `DuplicateCodeInField`, `TopicWithSpaces`, `InvalidIdentifierCharacter`
- `synesis/semantic/validator.py` — implementação dos erros 5, 8, 9, 23, 26, 31; novo método `_validate_code_fields_duplicates`; novo helper `_validate_identifier`
- `synesis/tests/test_validator.py` — atualização de teste + novo teste `test_empty_item_generates_error`

**Validado com:** `pytest` (94/94 ✅), projetos reais (0 regressões)

---

## Status de Implementação — Fase 1 ✅ CONCLUÍDA

**Erros implementados:** 6, 18, 39, 40, 41, 42, 47, 48, 49, 50, 51, 54, 55, 56, 59, 69
**Erros confirmados como syntax errors (capturados pelo parser Lark):** 43, 44, 45, 46, 52, 53, 60
**Erro 57 (DuplicateScopeBlock):** parser agrega blocos silenciosamente — requer rastreamento no transformer (postergado)
**Erro 58 (ValueWithWhitespace):** transformer faz trim dos labels antes da semântica — não detectável via `validate_template()` (postergado)

**Arquivos modificados:**
- `synesis/ast/results.py` — 19 novas subclasses `ValidationError`
- `synesis/ast/nodes.py` — campo `parse_errors` no `TemplateNode`
- `synesis/parser/template_loader.py` — `validate_template()` + 16 funções auxiliares + migração de `TemplateLoadError` para `ValidationResult`
- `synesis/compiler.py` — integração de `validate_template()` no pipeline

**Validado com:** `pytest` (93/93 ✅), `t05.synt` (14 erros + 11 avisos detectados), `Basic/project.synp` e `Social_Acceptance/social_acceptance.synp` (0 regressões)

---

## Fase 1 — Validação Estrutural de Template

**Erros:** 18, 39–60, 69 (24 erros, ~22 novas subclasses)
**Prioridade:** ALTA — bloqueia todas as outras fases (template inválido = validação impossível)
**Risco:** BAIXO — isolada do pipeline de anotações

### 1.1 Decisão arquitetural: `TemplateLoadError` → `ValidationResult`

**Problema atual:** `template_loader.py` levanta `TemplateLoadError` (exceção Python) para campos sem FIELD ou duplicatas. Exceções:
- Abortam no primeiro erro (sem acumulação)
- Não passam pelo pipeline `ValidationResult → converters → LSP Diagnostics`
- Exigem try/except especial no `compiler.py` e `lsp_adapter.py`

**Solução proposta:** criar `validate_template(template: TemplateNode, file_path: Path) → ValidationResult` em `template_loader.py`:

```python
def validate_template(template: TemplateNode, file_path: Path) -> ValidationResult:
    """Valida estrutura interna do template APÓS parsing bem-sucedido."""
    result = ValidationResult()
    _check_duplicate_fields(template, file_path, result)       # erro 69
    _check_fields_without_definition(template, file_path, result)  # erros 39-41
    _check_orphan_field_definitions(template, file_path, result)   # erro 42
    _check_missing_scope(template, file_path, result)           # erro 43
    _check_missing_type(template, file_path, result)            # erro 44
    _check_invalid_scope(template, file_path, result)           # erro 45
    _check_duplicate_type(template, file_path, result)          # erro 46
    _check_chain_without_arity(template, file_path, result)     # erro 47
    _check_arity_relations_mismatch(template, file_path, result)   # erro 48
    _check_ordered_without_values(template, file_path, result)  # erro 49
    _check_enumerated_without_values(template, file_path, result)  # erro 50
    _check_scale_without_format(template, file_path, result)    # erro 51
    _check_format_syntax(template, file_path, result)           # erro 52
    _check_invalid_arity_operator(template, file_path, result)  # erro 53
    _check_format_on_non_scale(template, file_path, result)     # erro 54
    _check_arity_on_non_chain(template, file_path, result)      # erro 55
    _check_relations_on_non_chain(template, file_path, result)  # erro 56
    _check_duplicate_scope_blocks(template, file_path, result)  # erro 57
    _check_values_whitespace(template, file_path, result)       # erro 58
    _check_values_duplicates(template, file_path, result)       # erro 59
    _check_guidelines_unclosed(template, file_path, result)     # erro 60
    _check_single_field_bundle(template, file_path, result)     # erro 18
    return result
```

**Integração no pipeline** (`compiler.py`):

```python
def compile(self) -> CompilationResult:
    project = self.parse_project()
    template = self.load_template(project)

    # NOVO: validação estrutural do template
    template_result = validate_template(template, template_path)

    bibliography = self.load_bibliography(project)
    # ... resto do pipeline

    # Merge template_result no validation_result final
    self._merge(validation_result, template_result)
```

**Preservação de `TemplateLoadError`:** manter para erros fatais que impedem construção do `TemplateNode` (parsing falhou). A nova `validate_template()` opera APÓS parsing bem-sucedido.

### 1.2 Novas subclasses em `results.py`

| Erro | Classe | Severidade | Campos |
|---|---|---|---|
| 18 | `SingleFieldBundle` | ERROR | `bundle_name: str`, `field_name: str` |
| 39 | `UndefinedFieldInSourceFields` | ERROR | `field_name: str` |
| 40 | `UndefinedFieldInItemFields` | ERROR | `field_name: str` |
| 41 | `UndefinedFieldInOntologyFields` | ERROR | `field_name: str` |
| 42 | `OrphanFieldDefinition` | WARNING | `field_name: str`, `scope: str` |
| 43 | `MissingScopeDeclaration` | ERROR | `field_name: str` |
| 44 | `MissingTypeDeclaration` | ERROR | `field_name: str` |
| 45 | `InvalidScopeValue` | ERROR | `field_name: str`, `value: str` |
| 46 | `DuplicateTypeDeclaration` | ERROR | `field_name: str` |
| 47 | `ChainWithoutArity` | ERROR | `field_name: str` |
| 48 | `ArityRelationsMismatch` | ERROR | `field_name: str`, `arity: int`, `n_relations: int` |
| 49 | `OrderedWithoutValues` | ERROR | `field_name: str` |
| 50 | `EnumeratedWithoutValues` | ERROR | `field_name: str` |
| 51 | `ScaleWithoutFormat` | ERROR | `field_name: str` |
| 52 | `InvalidFormatSyntax` | ERROR | `field_name: str`, `format_str: str` |
| 53 | `InvalidArityOperator` | ERROR | `field_name: str`, `operator: str` |
| 54 | `FormatOnNonScale` | ERROR | `field_name: str`, `field_type: str` |
| 55 | `ArityOnNonChain` | ERROR | `field_name: str`, `field_type: str` |
| 56 | `RelationsOnNonChain` | ERROR | `field_name: str`, `field_type: str` |
| 57 | `DuplicateScopeBlock` | ERROR | `scope: str` |
| 58 | `ValueWithWhitespace` | ERROR | `field_name: str`, `value: str` |
| 59 | `DuplicateValue` | ERROR | `field_name: str`, `value: str` |
| 60 | `UnclosedGuidelines` | ERROR | `field_name: str` |
| 69 | `DuplicateFieldName` | ERROR | `field_name: str` |

> **Nota:** Erros 39, 40, 41 podem ser unificados em uma única classe `UndefinedFieldInScopeFields` com campo `scope: str`. Decisão de implementação — a classe unificada é preferível se o `to_diagnostic()` for parametrizado por scope.

### 1.3 Dados disponíveis no `TemplateNode`

Para implementar as validações, é necessário verificar quais dados o `TemplateNode` e `FieldSpec` expõem:

```python
# Em ast/nodes.py (existente)
@dataclass
class FieldSpec:
    name: str
    field_type: FieldType      # TEXT, QUOTATION, CODE, CHAIN, DATE, SCALE, ENUMERATED, ORDERED, TOPIC, MEMO
    scope: Scope               # SOURCE, ITEM, ONTOLOGY
    constraint: FieldConstraint # REQUIRED, OPTIONAL, FORBIDDEN
    format_range: Optional[Tuple[float, float]]  # Para SCALE
    values: Optional[List[str]]                   # Para ENUMERATED/ORDERED
    relations: Optional[List[str]]                # Para CHAIN
    arity: Optional[str]                          # Ex: ">= 2"
    guidelines: Optional[str]                     # Texto livre
    location: SourceLocation

@dataclass
class TemplateNode:
    field_specs: Dict[str, FieldSpec]
    source_fields: List[str]      # Nomes em SOURCE FIELDS
    item_fields: List[str]        # Nomes em ITEM FIELDS
    ontology_fields: List[str]    # Nomes em ONTOLOGY FIELDS
    bundles: List[Tuple[str, ...]]
```

**Disponibilidade de dados para cada erro:**

| Erro | Dados necessários | Disponível em TemplateNode? |
|---|---|---|
| 39-41 | `source_fields`/`item_fields`/`ontology_fields` vs `field_specs` | ✅ Sim |
| 42 | `field_specs` vs todas as listas `*_fields` | ✅ Sim |
| 43 | `FieldSpec.scope` ser None/inválido | ⚠️ Depende — se parser falhar antes, nunca chega aqui |
| 44 | `FieldSpec.field_type` ser None | ⚠️ Depende — idem |
| 45-46 | Verificação de valores de scope/type | ⚠️ Pode ser pré-validação no transformer |
| 47 | `FieldSpec.field_type == CHAIN` e `arity is None` | ✅ Sim |
| 48 | `FieldSpec.arity` vs `len(FieldSpec.relations)` | ✅ Sim |
| 49-50 | `FieldSpec.field_type` vs `FieldSpec.values` | ✅ Sim |
| 51-52 | `FieldSpec.field_type == SCALE` vs `format_range` | ✅ Sim |
| 53 | Operador extraído de `FieldSpec.arity` string | ✅ Sim (parse da string) |
| 54 | `FieldSpec.format_range is not None` e `field_type != SCALE` | ✅ Sim |
| 55 | `FieldSpec.arity is not None` e `field_type != CHAIN` | ✅ Sim |
| 56 | `FieldSpec.relations is not None` e `field_type != CHAIN` | ✅ Sim |
| 57 | Contagem de blocos `*_fields` | ⚠️ Pode precisar rastreamento no transformer |
| 58-59 | Iteração sobre `FieldSpec.values` | ✅ Sim |
| 60 | GUIDELINES sem END | ⚠️ Normalmente capturado pelo parser Lark |
| 69 | Nomes duplicados em `field_specs` | ⚠️ Dict sobrescreve — detectar no transformer |

**Erros 43-46, 57, 60, 69 — ação requerida no transformer:**

Os erros marcados ⚠️ exigem alteração no `parser/transformer.py` para preservar informação que hoje é descartada ou que causa sobrescrita silenciosa:

- **Erro 69 (campos duplicados):** `field_specs` é um `Dict` — a segunda definição sobrescreve a primeira. Solução: acumular em lista no transformer e detectar duplicatas em `validate_template()`.
- **Erro 57 (blocos duplicados):** se o parser aceita dois `ONTOLOGY FIELDS`, o transformer produz duas listas. Solução: contar ocorrências no transformer.
- **Erros 43-44 (scope/type ausente):** se a gramática exige SCOPE e TYPE, nunca chega sem eles. Se a gramática os torna opcionais, o transformer pode produzir `None`. **Verificar gramática antes de implementar.**
- **Erro 60 (GUIDELINES sem END):** provavelmente capturado pelo parser LALR antes da semântica. Adicionar validação defensiva (nunca ativada se parser já captura).

### 1.4 Migração de `TemplateLoadError` existentes

Os dois `TemplateLoadError` atuais em `_validate_field_names()` correspondem aos erros 39-41 (campo listado em FIELDS sem FIELD correspondente). A migração:

1. Mover lógica de `_validate_field_names()` para `validate_template()`
2. Em `load_template()`, remover a chamada a `_validate_field_names()`
3. Em `validate_template()`, usar `UndefinedFieldInScopeFields` em vez de `TemplateLoadError`
4. Manter `TemplateLoadError` para erros fatais de parsing (try/except no compiler continua funcionando)

### 1.5 Testes

- Projetos `T05-Template-Declaration/` cobre erros 39–60, 69
- Projetos `T03-Bundle/` cobre erro 18
- Criar unit tests em `tests/test_template_validation.py` para cada subclasse

---

## Fase 2 — Validação Semântica de Anotações

**Erros:** 5, 8, 9, 23, 26, 31–33 (8 erros, 8 novas subclasses)
**Prioridade:** ALTA — erros frequentes em uso real
**Risco:** BAIXO — extensões do `SemanticValidator` existente

### 2.1 Novas subclasses em `results.py`

| Erro | Classe | Severidade | Campos | Onde validar |
|---|---|---|---|---|
| 5 | `OntologyWithoutTemplateFields` | ERROR | — | `validator.validate_project()` |
| 8 | `QualifiedChainWithoutRelations` | ERROR | `field_name: str` | `validator.validate_chain()` |
| 9 | `SimpleChainWithRelationsRequired` | ERROR | `field_name: str`, `valid_relations: list[str]` | `validator.validate_chain()` |
| 23 | `EmptyItemBlock` | ERROR | — | `validator.validate_item()` |
| 26 | `DecimalInIntegerScale` | ERROR | `field_name: str`, `value: str`, `min_val: int`, `max_val: int` | `validator._validate_scale()` |
| 31 | `DuplicateCodeInField` | WARNING | `field_name: str`, `code: str` | `validator.validate_item()` |
| 32 | `TopicWithSpaces` | ERROR | `field_name: str`, `value: str` | `validator.validate_item()` |
| 33 | `InvalidIdentifierCharacter` | ERROR | `name: str`, `invalid_char: str` | `validator.validate_item()` / `validate_ontology()` |

### 2.2 Pontos de inserção no `SemanticValidator`

**Erro 5 — `OntologyWithoutTemplateFields`:**
Em `validate_project()` (atualmente no-op). Checar se `template.ontology_fields` está vazio quando existem ontologias:
```python
def validate_project(self, project: ProjectNode) -> ValidationResult:
    result = ValidationResult()
    if self.ontology_index and not self.template.ontology_fields:
        result.add(OntologyWithoutTemplateFields(location=project.location))
    return result
```
**Nota:** `validate_project()` precisa receber `ontologies` ou o validator precisa armazenar se há ontologias. Avaliar se passa lista de ontologias para o método ou se adiciona flag no `__init__`.

**Erros 8 e 9 — Chain com/sem relations:**
Em `validate_chain()`, antes da validação de arity. Verificar se chain tem relações (posições pares não-None) vs template exige/proíbe relations:
```python
# Erro 8: chain qualificada mas template não tem RELATIONS
if chain_has_relations and not field_spec.relations:
    result.add(QualifiedChainWithoutRelations(...))
# Erro 9: chain simples mas template exige RELATIONS
if not chain_has_relations and field_spec.relations:
    result.add(SimpleChainWithRelationsRequired(...))
```

**Erro 23 — Item vazio:**
No início de `validate_item()`:
```python
if not item.fields:  # ou len(item.fields) == 0
    result.add(EmptyItemBlock(location=item.location))
    return result  # skip demais validações
```

**Erro 26 — Decimal em SCALE inteiro:**
Em `_validate_scale()`, após verificar range. Se `min_value` e `max_value` são inteiros e valor tem casas decimais:
```python
if min_value == int(min_value) and max_value == int(max_value):
    if '.' in str(raw_value):
        result.add(DecimalInIntegerScale(...))
```

**Erro 31 — Código duplicado no mesmo campo:**
Em `validate_item()`, ao processar campos CODE. Manter set de códigos já vistos por campo:
```python
seen_codes = set()
for code in extracted_codes:
    normalized = normalize_code(code)
    if normalized in seen_codes:
        result.add(DuplicateCodeInField(...))
    seen_codes.add(normalized)
```

**Erro 32 — TOPIC com espaços:**
Na validação de campos TOPIC, checar se valor contém espaços.

**Erro 33 — Caracteres inválidos em identificador:**
Criar helper `_validate_identifier(name: str)` que verifica regex `^[a-zA-Z][a-zA-Z0-9_]*$`. Usar em validação de CODE e ONTOLOGY concept names.

### 2.3 Testes

- Projeto `T04-Fields-Types-Scope/` cobre erros 23, 26, 31–33
- Projeto `T01-Bibliographic-Ontology-Links/` cobre erro 5
- Projeto `T02-Chain-Relations/` cobre erros 8, 9

---

## Fase 3 — Validação Cross-Entity

**Erros:** 6, 13–15, 68, 70, 71 (7 erros, ~6 novas subclasses)
**Prioridade:** MÉDIA — requerem múltiplas entidades carregadas
**Risco:** MÉDIO — modificações no Linker requerem cuidado com o `ontology_index`

### 3.1 Novas subclasses em `results.py`

| Erro | Classe | Severidade | Campos | Onde validar |
|---|---|---|---|---|
| 6 | `FieldInScopeFieldsWithoutMatchingScope` | ERROR | `field_name: str`, `listed_scope: str`, `actual_scope: str` | `validate_template()` |
| 13 | `ChainWithoutArrowOperator` | ERROR | `raw_value: str` | `validator.validate_chain()` |
| 14 | `ConceptNameMatchesRelation` | ERROR | `name: str`, `field_name: str` | `validator.validate_chain()` |
| 15 | `ConceptWithSpaces` | ERROR | `concept: str` | `validator.validate_chain()` |
| 68 | `DuplicateOntologyConcept` | ERROR | `concept_name: str`, `file_a: str`, `file_b: str` | `linker.link()` ou `compiler.validate_all()` |
| 70 | `DuplicateSourceBibref` | ERROR | `bibref: str`, `file: str` | `linker.link()` ou `validator.validate_source()` |
| 71 | `DuplicateOntologyDescription` | WARNING | `concept_a: str`, `concept_b: str` | `linker.link()` |

### 3.2 Pontos de inserção

**Erro 6 — Campo em ONTOLOGY FIELDS sem SCOPE ONTOLOGY:**
Na verdade é validação de template (move para Fase 1 `validate_template()`). Checar se cada campo em `template.ontology_fields` tem `field_specs[name].scope == Scope.ONTOLOGY`:
```python
for name in template.ontology_fields:
    if name in template.field_specs:
        spec = template.field_specs[name]
        if spec.scope != Scope.ONTOLOGY:
            result.add(FieldInScopeFieldsWithoutMatchingScope(
                field_name=name, listed_scope="ONTOLOGY", actual_scope=spec.scope.value, ...))
```
Idem para `source_fields` → `Scope.SOURCE` e `item_fields` → `Scope.ITEM`.

**Erro 13 — Chain sem `→`:**
Normalmente capturado pela gramática Lark. Adicionar validação defensiva em `validate_chain()`:
```python
if len(elements) == 1 and '->' not in raw_value:
    result.add(ChainWithoutArrowOperator(...))
```

**Erro 14 — Conceito = nome de relação:**
Em `validate_chain()`, para cadeias qualificadas:
```python
relation_names = set(field_spec.relations or [])
for concept in concept_elements:
    if normalize_code(concept) in {normalize_code(r) for r in relation_names}:
        result.add(ConceptNameMatchesRelation(...))
```

**Erro 15 — Conceito com espaços:**
Normalmente capturado pela gramática. Validação defensiva similar ao erro 13.

**Erro 68 — Ontologia duplicada:**
No `linker.py`, o `ontology_index` atual usa `{normalize_code(o.concept): o for o in ontologies}` que sobrescreve silenciosamente. Solução:
```python
# Em Linker.__init__ ou link()
seen_concepts = {}
for o in ontologies:
    key = normalize_code(o.concept)
    if key in seen_concepts:
        self.validation_result.add(DuplicateOntologyConcept(
            concept_name=o.concept,
            file_a=seen_concepts[key].location.file,
            file_b=o.location.file,
            location=o.location))
    seen_concepts[key] = o
```

**Erro 70 — SOURCE duplicado no mesmo arquivo:**
No `linker.py` ou `validator.py`. Agrupar sources por `(file, bibref)` e detectar duplicatas:
```python
source_keys = {}
for source in sources:
    key = (source.location.file, source.bibref)
    if key in source_keys:
        result.add(DuplicateSourceBibref(...))
    source_keys[key] = source
```

**Erro 71 — Ontologias com descrição idêntica:**
No `linker.py`, após construir `ontology_index`. Agrupar por `description` e emitir warning para duplicatas:
```python
desc_index = {}
for o in ontologies:
    desc = getattr(o, 'description', None)
    if desc and desc in desc_index:
        result.add(DuplicateOntologyDescription(...))
    if desc:
        desc_index[desc] = o
```

### 3.3 Testes

- Projeto `T01-Bibliographic-Ontology-Links/` cobre erros 68, 70, 71
- Projeto `T02-Chain-Relations/` cobre erros 13–15
- Projeto `T01-Bibliographic-Ontology-Links/` cobre erro 6 (via template)

---

## Fase 4 — Validação de Estrutura de Projeto

**Erros:** 61–63, 65–67 (6 erros, 6 novas subclasses)
**Prioridade:** MÉDIA — proteção contra configuração inválida
**Risco:** MÉDIO — modificações em `compiler.py` e `lsp_adapter.py`

### 4.1 Novas subclasses em `results.py`

| Erro | Classe | Severidade | Campos |
|---|---|---|---|
| 61 | `MissingAnnotationsInclude` | ERROR | `filename: str` |
| 62 | `MissingOntologyInclude` | ERROR | `filename: str` |
| 63 | `MissingBibliographyFile` | ERROR | `filename: str` |
| 65 | `MissingTemplateDeclaration` | ERROR | — |
| 66 | `DuplicateProjectBlock` | ERROR | — |
| 67 | `ModifiedBeforeCreated` | WARNING | `modified: str`, `created: str` |

### 4.2 Pontos de inserção

**Erros 61-62 — Arquivo sem INCLUDE:**
Estes erros se aplicam quando o compilador detecta arquivos `.syn`/`.syno` no diretório que não estão referenciados no `.synp`. Implementar em `compiler.py` ou criar helper `_check_project_completeness()`:
```python
def _check_project_completeness(self, project: ProjectNode) -> ValidationResult:
    result = ValidationResult()
    included_annotations = set(self._collect_include_paths(project, "ANNOTATIONS", allow_glob=True))
    included_ontologies = set(self._collect_include_paths(project, "ONTOLOGY"))

    # Verificar .syn no diretório
    for syn_file in self.project_dir.glob("*.syn"):
        if syn_file not in included_annotations:
            result.add(MissingAnnotationsInclude(filename=syn_file.name, location=project.location))

    # Verificar .syno no diretório
    for syno_file in self.project_dir.glob("*.syno"):
        if syno_file not in included_ontologies:
            result.add(MissingOntologyInclude(filename=syno_file.name, location=project.location))
    return result
```

**Nota:** Esta verificação pode gerar falsos positivos se houver arquivos auxiliares no diretório. Considerar usar severidade WARNING em vez de ERROR, ou documentar que o diretório do projeto deve conter apenas arquivos do projeto.

**Erro 63 — Arquivo `.bib` não encontrado:**
Em `compiler.py`, no `load_bibliography()`:
```python
def load_bibliography(self, project: ProjectNode):
    for include in project.includes:
        if include.include_type.upper() == "BIBLIOGRAPHY":
            path = self.project_dir / include.path
            if not path.exists():
                # Retornar ValidationResult com erro em vez de propagar exceção
                return {}, ValidationResult(errors=[MissingBibliographyFile(
                    filename=include.path, location=include.location)])
            return load_bibliography(path), ValidationResult()
    return {}, ValidationResult()
```

**Alternativa mais limpa:** manter `load_bibliography()` como está e adicionar verificação de existência em `compile()` antes de chamar.

**Erro 65 — PROJECT sem TEMPLATE:**
Em `compiler.py`, verificar se `project.template_path` é None ou vazio:
```python
if not project.template_path:
    result.add(MissingTemplateDeclaration(location=project.location))
    # early return — sem template, validação semântica é impossível
```

**Erro 66 — Dois blocos PROJECT:**
Em `parse_project()`, contar quantos `ProjectNode` foram encontrados:
```python
project_nodes = [n for n in nodes if isinstance(n, ProjectNode)]
if len(project_nodes) > 1:
    result.add(DuplicateProjectBlock(location=project_nodes[1].location))
```
**Problema:** `parse_project()` hoje retorna o primeiro ProjectNode. Precisa retornar `ValidationResult` também, ou a verificação deve ser movida para `compile()`.

**Erro 67 — MODIFIED < CREATED:**
Em `compile()` ou `validate_project()`, após parsear metadados:
```python
if project.metadata:
    created = project.metadata.get('created')
    modified = project.metadata.get('modified')
    if created and modified and modified < created:
        result.add(ModifiedBeforeCreated(
            modified=modified, created=created, location=project.location))
```

### 4.3 Impacto no `lsp_adapter.py`

O `lsp_adapter.py` precisa propagar os mesmos erros. Atualmente `validate_single_file()` trata `MissingProjectFile` e `MissingTemplateFile` com lógica própria. Os novos erros de projeto devem ser detectados pelo mesmo caminho — passando pelo `SynesisCompiler`.

**Ação:** garantir que `lsp_adapter.validate_single_file()` use `SynesisCompiler.compile()` e não reimplemente verificações.

### 4.4 Testes

- Projeto `T06-Project-Structure/` cobre todos os 6 erros (múltiplos `.synp` variantes)

---

## Fase 5 — LSP Code Actions e Migração

**Prioridade:** BAIXA — melhoria de UX, não funcionalidade
**Risco:** MÉDIO — envolve dois repositórios (synesis-lsp, synesis-explorer)

### 5.1 `Diagnostic.code` para Code Actions type-safe

**Problema atual:** `code_actions.py` faz matching por substrings da mensagem de diagnóstico para oferecer quick fixes. Isso é frágil — qualquer mudança no texto da mensagem quebra os code actions.

**Solução:**
1. Adicionar campo `code: ClassVar[str]` em cada `ValidationError` subclass:
   ```python
   class UndefinedCode(ValidationError):
       CODE: ClassVar[str] = "SYNESIS_E003"
       # ... resto da classe
   ```
2. Em `converters.py`, passar `error.CODE` para `Diagnostic.code`:
   ```python
   diagnostic = Diagnostic(
       range=...,
       message=error.to_diagnostic(),
       severity=...,
       source="synesis",
       code=error.CODE,  # NOVO
   )
   ```
3. Em `code_actions.py`, matchar por `diagnostic.code` em vez de `diagnostic.message`:
   ```python
   if diagnostic.code == "SYNESIS_E003":  # UndefinedCode
       # offer "Create ONTOLOGY block" quick fix
   ```

**Catálogo de códigos proposto:**
- `SYNESIS_E001` a `SYNESIS_E071` (mapeamento direto para números do inventory)
- Prefixo `E` para ERROR, `W` para WARNING, `I` para INFO

### 5.2 Remoção de `template_diagnostics.py`

**Problema:** `template_diagnostics.py` no synesis-lsp duplica validação que o compilador deve fazer. Usa regex heurístico para detectar campos desconhecidos, escopo incorreto, campos obrigatórios ausentes.

**Plano de migração:**

1. Após Fases 1-4, o compilador emite todos os erros que `template_diagnostics.py` cobre
2. Verificar que cada heurística de `template_diagnostics.py` tem equivalente no compilador:
   - Campos desconhecidos → `UnknownFieldName` (já implementado)
   - Escopo incorreto → `ForbiddenFieldPresent` (já implementado)
   - Campos obrigatórios → `MissingRequiredField` (já implementado)
   - Outros padrões → verificar caso a caso
3. Desativar `template_diagnostics.py` em `server.py`
4. Rodar suíte de testes completa
5. Remover arquivo

**Impacto no synesis-explorer:** Nenhum. O explorer consome diagnostics do LSP que continua vindo pelo mesmo canal.

### 5.3 Coordenação com `synesis-explorer-performance-plan.md`

O plano de performance do explorer (6 fases, 8 bottlenecks) é independente das mudanças de erro. Os dois planos podem ser executados em paralelo sem conflito:
- Performance plan modifica: `dataService.js`, `extension.js`, tree providers
- Error implementation modifica: `converters.py`, `code_actions.py`, `server.py`

Única interseção potencial: se o performance plan alterar como diagnostics são consumidos em `dataService.js`. **Ação:** verificar no momento da implementação.

---

## Fase 6 — Testes de Integração e Hardening

**Prioridade:** CRÍTICA — validação end-to-end
**Risco:** BAIXO

### 6.1 Testes com projetos `case-studies-Tests/`

| Projeto | Erros cobertos | Tipo de teste |
|---|---|---|
| T01-Bibliographic-Ontology-Links | 1, 2, 3, 4, 5, 6, 24, 68, 70, 71 | Compilação CLI + LSP |
| T02-Chain-Relations | 7–15 | Compilação CLI + LSP |
| T03-Bundle | 16–19 | Compilação CLI + LSP |
| T04-Fields-Types-Scope | 20–38 | Compilação CLI + LSP |
| T05-Template-Declaration | 39–60, 69 | Compilação CLI + LSP |
| T06-Project-Structure | 5–6, 61–67 | Compilação CLI + LSP |

### 6.2 Checklist de validação

Para cada novo erro:
- [ ] Subclass `ValidationError` criada em `results.py`
- [ ] `to_diagnostic()` retorna mensagem pedagógica conforme inventory
- [ ] `DEFAULT_SEVERITY` correto (ERROR/WARNING/INFO)
- [ ] Validação inserida no ponto correto do pipeline
- [ ] Unit test com fixture que trigger o erro
- [ ] Unit test com fixture que NÃO trigger o erro (caso válido)
- [ ] Erro aparece no terminal via `synesis compile`
- [ ] Erro aparece como diagnostic no VSCode via LSP
- [ ] Code action disponível (quando aplicável)
- [ ] Nenhuma regressão nos testes existentes

### 6.3 Testes de regressão

- Rodar `pytest` completo após cada fase
- Compilar caso de estudo real (ex: `case-studies/`) para verificar ausência de falsos positivos
- Verificar que erros existentes (19 implementados) continuam funcionando inalterados

---

## Cronograma Sugerido de Implementação

| Fase | Escopo | Dependências |
|---|---|---|
| **1** | Template validation (24 erros) | Nenhuma |
| **2** | Annotation semantics (8 erros) | Nenhuma (paralelo com F1) |
| **3** | Cross-entity (7 erros) | F1 (para erro 6) |
| **4** | Project structure (6 erros) | Nenhuma (paralelo com F1-F3) |
| **5** | LSP code actions + cleanup | F1-F4 (todos os erros implementados) |
| **6** | Integration testing | F1-F5 |

**Fases 1, 2 e 4 são independentes** e podem ser implementadas em paralelo.
**Fase 3** depende de Fase 1 (erro 6 é validação de template).
**Fase 5** depende de todas as fases anteriores.

---

## Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| Erros 43-46 já capturados pela gramática | Alta | Baixo | Verificar gramática; se capturado, adicionar validação defensiva (nunca ativada) |
| Erro 60 (GUIDELINES) capturado pelo parser | Alta | Baixo | Idem — validação defensiva |
| Erro 69 (campos duplicados) — Dict sobrescreve | Alta | Médio | Alterar transformer para acumular em lista |
| `TemplateLoadError` existentes quebram se removidos | Média | Alto | Manter para erros fatais; migrar apenas validações acumuláveis |
| Code actions quebram com novas mensagens | Média | Médio | Migrar para `Diagnostic.code` antes de alterar mensagens |
| Falsos positivos em erros 61-62 (arquivos não incluídos) | Média | Médio | Usar WARNING em vez de ERROR; documentar |

---

## Decisões Pendentes

1. **Erros 39-41 unificados?** Uma classe `UndefinedFieldInScopeFields(scope)` vs três classes separadas. Recomendação: unificar.
2. **Erro 5 — como passar informação de ontologias para `validate_project()`?** Opções: (a) flag `has_ontologies` no SemanticValidator, (b) lista de ontologias como parâmetro.
3. **Erros 61-62 — severidade ERROR ou WARNING?** Arquivos `.syn`/`.syno` não incluídos podem ser intencionais (rascunhos). Recomendação: WARNING.
4. **Erros 43-46 — verificar se a gramática Lark permite campos sem SCOPE/TYPE.** Se não permite, essas validações são defensivas e nunca serão ativadas. Implementar mesmo assim por segurança.
