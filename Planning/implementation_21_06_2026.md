# Plano de Implementação — 21/06/2026

**Versão-alvo:** synesis 0.6.0 (MINOR — adições retrocompatíveis + correções de bug)
**Base:** synesis 0.5.7
**Estudos reunidos:** `sources_without_bibliography.md`, `optional_bundles.md`, `minor_inconsistencies.md`

---

## Contexto

Este plano consolida três estudos de viabilidade e os resultados de uma **verificação empírica aprofundada** do compilador (executada contra os case-studies reais em `D:\GitHub\case-studies\` e as fixtures `tests/fixtures/`). A verificação confirmou os bugs relatados, **refutou** uma premissa central de um dos estudos e **descobriu um bug crítico** que estava mascarado.

O objetivo é entregar, num único ciclo de release (0.6.0):

1. **Correção de um bug crítico** que impede o uso da Synesis sem bibliografia (bloqueia a proposta `sources_without_bibliography`).
2. **Correção de dois bugs confirmados** (export de CHAIN qualificada com nome customizado; colisão de nomes de campo com keywords).
3. **Implementação da feature `OPTIONAL BUNDLE`**.
4. Correções menores e cobertura de testes.

### Achado que altera a premissa de um estudo

O estudo `sources_without_bibliography.md` afirmava que a proposta "já estava implementada por omissão". **Isso é falso.** A verificação empírica mostrou o oposto:

```
case-study Basic, sem INCLUDE BIBLIOGRAPHY:
  success: False
  errors: {'UnregisteredSource': 1}
```

**Causa raiz:** `compiler.load_bibliography()` retorna `{}` (dict vazio) quando não há `INCLUDE BIBLIOGRAPHY`, mas `validator._validate_bibref()` só pula a validação com a guarda `if self.bibliography is None`. Como `{} is not None`, todo `@bibref` é checado contra um dicionário vazio e falha com E001. A proposta **não funciona hoje** — está quebrada, não "pronta".

---

## Itens de Trabalho (ordenados por severidade)

### WI-1 — [CRÍTICO] SOURCE sem bibliografia: corrigir guarda `is None` → falsy

**Bug:** projeto sem `INCLUDE BIBLIOGRAPHY` falha com `UnregisteredSource` (E001) em toda fonte.

**Confirmado empiricamente:** case-study `Basic` sem a linha de bibliografia → `success: False`, 1× E001.

**Correção mínima:** `synesis/semantic/validator.py:425`

```python
# Atual:
if self.bibliography is None:
    return
# Corrigido:
if not self.bibliography:   # cobre None E {} (sem INCLUDE BIBLIOGRAPHY)
    return
```

**Análise de impacto (rodar antes de editar):**
`gitnexus_impact({target: "_validate_bibref", direction: "upstream"})` — `_validate_bibref` é chamado por `validate_source`. Risco esperado: médio (caminho de validação central). A mudança é estritamente *menos restritiva* (só adiciona o caso `{}` ao skip), portanto não quebra projetos com bibliografia.

**Semântica resultante:**
- **Com** `INCLUDE BIBLIOGRAPHY` → bibliografia não-vazia → validação E001 ativa (inalterado).
- **Sem** `INCLUDE BIBLIOGRAPHY` → `{}` → bibrefs tratados como chaves internas válidas (novo, correto).
- Consistência interna (E070 `DuplicateSourceBibref`) já é garantida sem bib — verificado: opera sobre `SourceNode` via `normalize_bibref()`, sem consultar `.bib`.

**PROVA EMPÍRICA da preservação de E070 (case-insensitive) pós-correção:** simulei a correção (`load_bibliography` retornando `None` sem `INCLUDE BIBLIOGRAPHY`) num projeto com `SOURCE @silva2026` + `SOURCE @SILVA2026`:

```
ANTES da correção:  errors = {UnregisteredSource: 2, DuplicateSourceBibref: 1}
DEPOIS da correção: errors = {DuplicateSourceBibref: 1}
```

→ O E001 espúrio **desaparece**, e o E070 (duplicação case-insensitive, `@silva2026` ≡ `@SILVA2026`) **permanece intacto**. A detecção de referências duplicadas é ortogonal à bibliografia e sobrevive perfeitamente à correção. **Requisito do usuário atendido:** desbloquear SOURCE sem bibliografia NÃO enfraquece a verificação de chaves duplicadas.

**Ressalva a investigar durante a implementação:** confirmar que `bibliography vazia` não suprime erroneamente o E001 quando o usuário *declara* `INCLUDE BIBLIOGRAPHY` apontando para um `.bib` que existe mas está vazio. Caso de borda: bib declarada porém vazia deveria ainda validar (e falhar). Se necessário, distinguir "sem declaração" de "declarada-mas-vazia" passando `None` explicitamente em `load_bibliography()` quando não há `INCLUDE BIBLIOGRAPHY` — esta é a **alternativa mais limpa** e preferível à guarda falsy:

```python
# synesis/compiler.py:load_bibliography — retornar None quando não há INCLUDE BIBLIOGRAPHY
def load_bibliography(self, project):
    for include in project.includes:
        if include.include_type.upper() == "BIBLIOGRAPHY":
            path = self.project_dir / include.path
            return load_bibliography(path) if path.exists() else {}
    return None  # nenhum INCLUDE BIBLIOGRAPHY → desativa validação de bibref
```

> **Decisão de design:** preferir a correção em `compiler.load_bibliography()` (retornar `None`) em vez de relaxar a guarda do validador. Isso preserva a distinção semântica entre "sem bibliografia" (None → não valida) e "bibliografia vazia/declarada" ({} → valida e reporta). Manter a guarda `is None` no validador. Validar ambos os caminhos (CLI compile e LSP) com testes.

**Arquivos:** `synesis/compiler.py` (principal), possível ajuste em `synesis/api.py` (espelhar comportamento da API in-memory).

**Testes:** novo caso em `tests/` — projeto multi-SOURCE com identificadores arbitrários (`@entrevista_01`, `@doc_institucional`) sem `INCLUDE BIBLIOGRAPHY` → 0 erros E001. Adicionar fixture `T07-No-Bibliography`. Note que já existe `test_none_bibliography_skips_validation` cobrindo o caso `None`, mas **falta** o caso "compilador sem INCLUDE BIBLIOGRAPHY" end-to-end — este é o gap.

---

### WI-2 — [ALTO] Export de CHAIN qualificada com nome customizado

**Bug:** `json_export._has_chain_relations()` (linha 183) usa `template.field_specs.get("chain")` — nome literal. Campos CHAIN com nome customizado + RELATIONS são exportados como cadeias simples.

**Confirmado empiricamente:** fixture T02 com campo CHAIN renomeado `chain`→`causal_chain` → JSON triples saem com `relation='IMPLICIT'` em vez de `INFLUENCES`/`CORRELATES`.

**Correção:** `synesis/exporters/json_export.py:173-187` — substituir pelo padrão já existente em `semantic/linker.py:321-333`:

```python
def _has_chain_relations(template: Optional[TemplateNode]) -> bool:
    if not template:
        return False
    for spec in template.field_specs.values():
        if spec.type == FieldType.CHAIN and spec.relations:
            return True
    return False
```

**Impacto:** `gitnexus_impact` em `_has_chain_relations` — consumidores: `_build_chain_usage`, `_build_triples_index`, `_build_item_data` (todos em json_export). Risco baixo (função interna ao exporter). Verificar import de `FieldType` no módulo.

**Testes:** fixture com campo CHAIN de nome customizado + RELATIONS; asserir que o JSON contém as relações nomeadas corretas (não `IMPLICIT`).

---

### WI-3 — [MÉDIO/ALTO] Colisão de nome de campo com keywords de tipo

**Bug:** campos cujo nome começa com keyword de `field_key` (`text`, `code`, `chain`, `date`, `memo`, `quotation`, `scale`, `enumerated`, `ordered`, `topic`, `description`) falham no parse.

**Confirmado empiricamente:**
```
texto         → FAIL UnexpectedToken ('o: ...')
code_quality  → FAIL UnexpectedToken ('_quality: ...')
chain_length  → FAIL UnexpectedToken ('_length: ...')
date_created  → FAIL UnexpectedToken
topic_area    → FAIL UnexpectedToken
Endurecimento → PASS (lookahead de END protege)
```

**Causa raiz:** no lexer contextual do Lark, `KW_CODE` (prio 5, `/code/i`) vence `FIELD_NAME` (prio 1) e casa só o prefixo `code`, deixando `_quality: x` como `TEXT_LINE` órfão. O `\b` em `(?![eE][nN][dD]\b)` não ajuda os demais porque o lookahead só existe para END.

**Correção recomendada:** estender o lookahead negativo de `FIELD_NAME` em `synesis/grammar/synesis.lark:215` para cobrir todas as keywords que aparecem como alternativas em `field_key`, exigindo que sejam seguidas de **fim de palavra de campo** (espaço, `:`, vírgula, EOL). O `\b` padrão é insuficiente porque `_` é word-char; usar lookahead que trate `_` e `-` como continuação:

```
FIELD_NAME.1: /(?!(?:end|code|chain|text|date|memo|quotation|scale|enumerated|ordered|topic|description)(?=:|\s|$))[\p{L}_][\p{L}\p{N}_\-]*/iu
```

A condição `(?=:|\s|$)` garante que só bloqueamos quando a keyword forma o nome **inteiro** do campo (ex.: `code:`), permitindo `code_quality`, `texto`, `chain_length`. Campos que SÃO exatamente a keyword (`code`, `chain`) continuam roteados via as alternativas explícitas de `field_key`.

> **Verificação obrigatória após mudança:** regenerar `synesis/grammar/synesis_standalone.py` via `lark.tools.standalone` e rodar **toda** a suíte de parser/integração. A gramática está congelada para v1.x, mas esta é uma correção **não-breaking** (apenas amplia nomes de campo aceitos; nenhum arquivo válido existente muda de comportamento). Confirmar que keywords ainda funcionam como keywords em `field_def_block` (`FIELD code TYPE ...`).

**Risco:** alterar `FIELD_NAME` pode ter efeitos colaterais em outros contextos. Testar exaustivamente: nomes que SÃO keywords, que COMEÇAM com keyword, e o conjunto de fixtures completo. Considerar fixture dedicada `T08-Field-Name-Collision`.

**Arquivos:** `synesis/grammar/synesis.lark`, `synesis/grammar/synesis_standalone.py` (regenerado).

**Testes:** parametrizar parse de `texto`, `code_quality`, `chain_length`, `date_created`, `memo_text`, `topic_area`, `scale_value` + casos exatos `code`, `chain` (devem continuar válidos como nome de campo via field_key).

---

### WI-4 — [FEATURE] OPTIONAL BUNDLE

Implementar conforme `optional_bundles.md`. Semântica: ausência total OK; presença parcial ou contagens divergentes → erro.

**Ordem de implementação:**
1. **Gramática** (`synesis.lark`): `requirement_clause` ganha `KW_OPTIONAL bundle_modifier? field_names`. Regenerar standalone.
2. **Transformer** (`transformer.py`, ~linha 790): branch OPTIONAL detecta `BUNDLE`, retorna tupla `("optional", has_bundle, names)`.
3. **AST** (`nodes.py`): `TemplateNode.optional_bundles: Dict[Scope, List[Tuple[str,...]]]` + `to_dict()`.
4. **Template loader** (`template_loader.py`): popular `optional_bundles`; espelhar os 5 loops de validação de `bundled_fields`.
5. **Validador** (`validator.py`): **nova** função `validate_optional_bundle` (NÃO modificar `validate_bundle`, classificada CRITICAL pelo GitNexus). Chamar nos 3 `validate_source/item/ontology`. Reusar `MissingBundleField`/`BundleCountMismatch`.
6. **Exporters**: `csv_export.py:153`, `xls_export.py:164`, `alpaca_export.py:683` iteram também `optional_bundles`.

**Decisão de versionamento:** tratar como adição não-breaking ao template parser → **MINOR 0.6.0** (posição pragmática do estudo). Arquivos `.syn` existentes não mudam de comportamento; nenhum consumidor externo depende de `OPTIONAL BUNDLE` gerar erro.

**Impacto:** `gitnexus_impact({target: "validate_bundle"})` antes de tocar no validador. Por isso a estratégia de função separada.

**Testes:** fixture `T09-OptionalBundle` (ausência total OK; parcial erro; contagem errada erro; completo OK) + `TestOptionalBundleValidation` em `test_validator.py` + integração.

---

### WI-5 — [BAIXO] ARITY decimal silenciosamente ignorado

**Bug relatado:** `ARITY = 2.0` no template é aceito pela gramática mas `int("2.0")` em `_validate_chain_arity` (validator.py:797) lança `ValueError`, capturado com `return None` → validação de arity silenciosamente desativada para aquele campo.

**Status:** plausível por leitura de código; **não foi possível confirmar empiricamente** nesta sessão (o template de teste falhou por outro motivo). **Confirmar durante a implementação** com a fixture T02 (que tem `ARITY >= 2`): trocar para `ARITY >= 2.0` e checar se a validação some.

**Correção (se confirmado):** detectar ARITY decimal na validação de template (`template_loader.py`), emitindo erro análogo a `DecimalInIntegerScale` (erro 26) mas para ARITY — em vez de aceitar e ignorar depois. Alternativamente, `int(float(raw_value))` se a intenção for tolerar `2.0` como `2`. Preferir o erro explícito (consistente com a filosofia pedagógica do compilador).

**Nota de não-bug:** a alegação original "`ARITY = 2` é ignorado" foi **refutada** — a validação funciona para todos os operadores (`=`, `>=`, `<=`, `>`, `<`), confirmado em `test_validator.py`. O relato provavelmente derivava do bug pré-v0.5.4 de campos CHAIN com nome customizado, já corrigido. Documentar isso no CHANGELOG para evitar reabertura.

---

### WI-6 — [MÉDIO] Identificador de fonte puramente numérico

**Pergunta do usuário:** o identificador de referência pode ser apenas numérico (ex.: `@2026`, `@001`)?

**Confirmado empiricamente — NÃO, hoje falha:**
```
@silva2026  → PASS
@2026       → FAIL UnexpectedToken
@123abc     → FAIL UnexpectedToken
@2026_main  → FAIL UnexpectedToken
```

**Causa raiz:** `synesis/grammar/synesis.lark:203`
```lark
BIBREF: "@" /[a-zA-Z][a-zA-Z0-9_-]*/   # primeiro char DEVE ser letra
```

**Relevância para a proposta `sources_without_bibliography`:** com SOURCE atuando como "unidade de evidência genérica", identificadores numéricos são um caso de uso legítimo (numeração de entrevistas `@001`, anos `@2026`, IDs de documentos institucionais). A restrição atual é uma herança da convenção BibTeX, onde chaves quase sempre começam com o sobrenome do autor.

**Correção (verificada como não-breaking):** relaxar o primeiro caractere para alfanumérico:
```lark
BIBREF: "@" /[a-zA-Z0-9][a-zA-Z0-9_-]*/
```

**Verificação empírica do relaxamento:** reconstruí a gramática LALR com esse padrão e testei:
```
@2026       → PASS
@123abc     → PASS
@silva2026  → PASS  (casos existentes intactos)
```
A gramática compila sem conflito; o `@` inicial é desambiguador suficiente — não há colisão com `NUMBER` (que não tem `@`) nem com `TEXT_LINE`.

**Ressalvas:**
1. **Regenerar** `synesis/grammar/synesis_standalone.py` (terminais são compilados em tabelas; a regeneração já é exigida por WI-3/WI-4).
2. **Compatibilidade BibTeX:** o BibTeX permite chaves com dígito inicial, então projetos COM `INCLUDE BIBLIOGRAPHY` e chaves numéricas passam a funcionar de ponta a ponta. Verificar que `bib_loader.normalize` e `find_bibref` não assumem letra inicial (inspeção rápida: usam `.lower().strip()`, sem restrição de primeiro char — OK).
3. Avaliar se `@-` ou `@_` (começo com hífen/underscore) deve ser permitido — **recomendação: não**, manter `[a-zA-Z0-9]` como primeiro char para evitar identificadores visualmente ambíguos.

**Decisão:** mudança de uma linha na gramática, agrupar com WI-3 (que já toca `synesis.lark` + standalone). Risco baixo, ganho alinhado à proposta de evidência genérica.

**Arquivos:** `synesis/grammar/synesis.lark:203`, `synesis_standalone.py` (regenerado).
**Testes:** parse de `@2026`, `@001`, `@123abc`, `@2026_main`; e end-to-end com `INCLUDE BIBLIOGRAPHY` apontando para `.bib` com chave numérica.

---

> **Nota:** o estudo de mudança de licença (MIT → AGPL-3.0-only WITH Synesis-data-output-exception), antes listado aqui como WI-7, foi movido para documento próprio: **`new_licence_policy.md`**. É decisão de política/jurídica, desacoplada deste ciclo técnico de engenharia.

---

## Ordem de Execução Recomendada

```
1. WI-1 (crítico, desbloqueia sources_without_bibliography)   — compiler.py + api.py + testes
2. WI-2 (alto, isolado no exporter)                            — json_export.py + testes
3. WI-5 (baixo, confirmar primeiro)                            — validator/template_loader
4. WI-3 + WI-6 (gramática congelada — fazer juntos)            — synesis.lark + standalone + testes
5. WI-4 (feature, maior superfície)                            — 6 módulos + fixtures
```

Razão: WI-1/WI-2/WI-5 são correções localizadas e de baixo risco; entregar primeiro. WI-3 e WI-6 mexem ambos em `synesis.lark` e exigem a mesma regeneração do standalone + suíte completa — **agrupar numa única passada na gramática** para regenerar o standalone uma vez só. WI-4 é a maior mudança e se beneficia da base já estável.

> A mudança de licença (ver `new_licence_policy.md`) é trilha de política separada, desacoplada deste plano técnico.

---

## Protocolo por Item (obrigatório — AI_INSTRUCTIONS §10)

Para cada WI, antes de editar:
1. `gitnexus_impact({target, direction: "upstream"})` → reportar blast radius.
2. Se HIGH/CRITICAL → avisar antes de prosseguir.
3. Editar.
4. `gitnexus_detect_changes()` → confirmar escopo.
5. Reindexar após commit (`npx gitnexus analyze`).

---

## Verificação End-to-End

```bash
# Suíte completa
cd d:/GitHub/synesis && pytest

# WI-1: projeto real sem bibliografia deve compilar limpo
python -c "from pathlib import Path; from synesis.compiler import SynesisCompiler; \
  r=SynesisCompiler(str(Path('tests/fixtures/T07-No-Bibliography/p.synp').resolve())).compile(); \
  print('success', r.success, 'E001', sum('Unregistered' in type(e).__name__ for e in r.validation_result.errors))"
# Esperado: success True, E001 0

# WI-2: CHAIN customizado exporta relações nomeadas (não IMPLICIT)
# (fixture com FIELD causal_chain TYPE CHAIN + RELATIONS → checar JSON)

# WI-3: nomes de campo colidentes parseiam
python -c "from synesis.parser.lexer import create_parser; p=create_parser(); \
  [p.parse(f'ITEM @x\n    {n}: v\nEND ITEM\n') for n in ['texto','code_quality','chain_length','date_created']]; \
  print('all field-name collisions parse OK')"

# WI-6: bibref numérico parseia
python -c "from synesis.parser.lexer import create_parser; p=create_parser(); \
  [p.parse(f'SOURCE {b}\n    \nEND SOURCE\n') for b in ['@2026','@001','@123abc']]; \
  print('numeric bibrefs parse OK')"

# WI-1+E070: dedup case-insensitive sobrevive sem bibliografia
#   projeto com @silva2026 + @SILVA2026, sem INCLUDE BIBLIOGRAPHY
#   → esperado: 0× UnregisteredSource, 1× DuplicateSourceBibref

# WI-4: OPTIONAL BUNDLE — fixture T09
# WI-5: ARITY decimal — confirmar erro/coerção explícita

# Lint/type (toolchain unificada)
ruff check synesis && ruff format --check synesis && mypy synesis
```

---

## Atualizações de Documentação (DoD)

- `CHANGELOG.md` seção `[Unreleased]` → consolidar em `[0.6.0]`:
  - **Fixed:** WI-1 (E001 espúrio sem bibliografia), WI-2 (CHAIN customizado no JSON), WI-3 (colisão field/keyword), WI-5 (ARITY decimal).
  - **Added:** WI-4 (OPTIONAL BUNDLE).
- Bump `version` para `0.6.0` em `pyproject.toml`.
- Verificar constraint `synesis>=0.5.5` em synesis-coder/lsp/graph — WI-1 muda comportamento observável (projetos sem bib agora compilam); se algum consumidor dependia do erro, ajustar para `synesis>=0.6.0`.
- Memória: atualizar `sources_without_bibliography.md` com a correção da premissa (não era "pronto por omissão" — era bug).

---

## Resumo

| WI | Tipo | Severidade | Status verificação | Arquivos núcleo |
|----|------|-----------|--------------------|-----------------|
| WI-1 | Bug | **Crítico** | ✅ Confirmado (case-study Basic) | `compiler.py`, `api.py` |
| WI-2 | Bug | Alto | ✅ Confirmado (T02 renomeado) | `json_export.py` |
| WI-3 | Bug | Médio-Alto | ✅ Confirmado (parse empírico) | `synesis.lark` + standalone |
| WI-4 | Feature | — | Especificado | 6 módulos |
| WI-5 | Bug | Baixo | ⚠️ A confirmar na impl. | `validator.py`/`template_loader.py` |
| WI-6 | Bug/Feature | Médio | ✅ Confirmado (parse + relaxamento testado) | `synesis.lark:203` + standalone |

> Estudo de licenciamento (MIT → AGPL): ver **`new_licence_policy.md`** (trilha de política, fora deste plano técnico).

**Garantias verificadas para os requisitos do usuário nesta rodada:**
- ✅ Dedup case-insensitive (`@silva2026` ≡ `@SILVA2026`) **sobrevive** ao desbloqueio sem bibliografia (E070 preservado, E001 removido) — provado empiricamente.
- ✅ Bibref puramente numérico (`@2026`) hoje **falha**; relaxamento de uma linha em `BIBREF` resolve sem regressão — provado empiricamente.

**Estimativa total (WI técnicos):** ~2–3 dias (WI-4 ~1 dia; WI-1/2/5 ~0.5 dia; WI-3+WI-6 ~0.5–1 dia pela gramática congelada e regeneração única do standalone).

---

## Etapas de Implementação

### Etapa 1 — WI-1: Corrigir `load_bibliography` no compilador

**Objetivo:** projetos sem `INCLUDE BIBLIOGRAPHY` compilam sem E001 espúrio.

**1.1 — Impact analysis (obrigatório antes de editar)**
```
gitnexus_impact({target: "load_bibliography", direction: "upstream"})
```
Reportar blast radius. Se CRITICAL, parar e consultar.

**1.2 — Editar `synesis/compiler.py`**

Localizar `load_bibliography` e alterar o `return` final:
```python
# Antes (retornava {})
return {}
# Depois (retorna None → sinaliza "sem declaração")
return None
```
Garantir que o loop interno (quando encontra `INCLUDE BIBLIOGRAPHY`) continua retornando `{}` para arquivo declarado-mas-vazio e o resultado de `load_bibliography(path)` para arquivo existente. O comportamento do `validator._validate_bibref` (guarda `is None`) permanece intocado.

**1.3 — Verificar `synesis/api.py`**

Inspecionar se a API in-memory inicializa `bibliography` diretamente. Se sim, garantir que o caminho "sem `INCLUDE BIBLIOGRAPHY`" também resulta em `None` (não `{}`).

**1.4 — Confirmar caso de borda: bib declarada mas vazia**

Com `INCLUDE BIBLIOGRAPHY` apontando para `.bib` existente e vazio:
- `load_bibliography(path)` deve retornar `{}` (dict vazio, não `None`).
- Validador lê `if self.bibliography is None` → False → valida → falha com E001 (correto: bib declarada, fonte não registrada).

**1.5 — Criar fixture `tests/fixtures/T07-No-Bibliography/`**

Estrutura mínima:
```
T07-No-Bibliography/
  p.synp          # sem linha INCLUDE BIBLIOGRAPHY
  template.synt   # template com pelo menos um campo SOURCE
  data.syn        # ao menos um SOURCE @entrevista_01 e um SOURCE @doc_institucional
```

**1.6 — Escrever testes em `tests/`**

- `test_compiler_no_bibliography` — end-to-end com T07: `result.success is True`, zero erros E001.
- `test_bibliography_declared_empty_still_validates` — bib declarada + `.bib` vazio → E001 presente.
- Verificar que `test_none_bibliography_skips_validation` (existente) ainda passa.
- Adicionar caso: `@silva2026` + `@SILVA2026` sem bib → 0× E001, 1× E070 (preservação do dedup).

**1.7 — Rodar suíte e verificar**
```bash
pytest tests/ -k "bibliography" -v
pytest tests/ -x
```

**1.8 — `gitnexus_detect_changes()` antes do commit**

Confirmar que apenas `compiler.py`, `api.py` (se alterado) e arquivos de teste mudaram.

---

### Etapa 2 — WI-2: Corrigir `_has_chain_relations` no JSON exporter

**Objetivo:** campos CHAIN com nome customizado exportam relações nomeadas (não `IMPLICIT`).

**2.1 — Impact analysis**
```
gitnexus_impact({target: "_has_chain_relations", direction: "upstream"})
```

**2.2 — Editar `synesis/exporters/json_export.py` (linhas 173–187)**

Substituir a implementação atual pela variante que itera `field_specs.values()`:
```python
def _has_chain_relations(template: Optional[TemplateNode]) -> bool:
    if not template:
        return False
    for spec in template.field_specs.values():
        if spec.type == FieldType.CHAIN and spec.relations:
            return True
    return False
```

Verificar que `FieldType` já está importado no módulo; adicionar import se necessário.

**2.3 — Criar/adaptar fixture com CHAIN de nome customizado**

Usar T02 ou nova fixture: campo declarado como `FIELD causal_chain TYPE CHAIN` com `RELATIONS INFLUENCES, CORRELATES`.

**2.4 — Escrever teste**

Asserir que o JSON exportado contém as relações nomeadas (`INFLUENCES`, `CORRELATES`) e não `IMPLICIT`.

**2.5 — Rodar suíte e `gitnexus_detect_changes()`**
```bash
pytest tests/ -k "chain" -v
pytest tests/ -x
```

---

### Etapa 3 — WI-5: Confirmar e corrigir ARITY decimal

**Objetivo:** `ARITY = 2.0` emite erro explícito em vez de silenciosamente desativar a validação.

**3.1 — Confirmar o bug empiricamente**

Na fixture T02 (que tem `ARITY >= 2`), trocar para `ARITY >= 2.0` e compilar:
```bash
python -c "from synesis.compiler import SynesisCompiler; r = SynesisCompiler('tests/fixtures/T02-.../p.synp').compile(); print(r.validation_result.errors)"
```
Se a validação de arity sumir → bug confirmado. Se erro for emitido → não é bug; documentar como "não confirmado" no CHANGELOG e encerrar este WI.

**3.2 — Se confirmado: editar `synesis/semantic/template_loader.py`**

```
gitnexus_impact({target: "_validate_chain_arity", direction: "upstream"})
```

Na função que processa o valor de `ARITY`, detectar ponto decimal e emitir erro análogo a `DecimalInIntegerScale`:
```python
raw = ...  # valor lido do template
if '.' in str(raw):
    # emitir erro de ARITY decimal explícito
    ...
value = int(raw)
```
Não usar `int(float(raw))` — preferir o erro explícito (filosofia pedagógica do compilador).

**3.3 — Testes**

- `ARITY = 2` → validação ativa (regressão).
- `ARITY = 2.0` → erro explícito de "ARITY deve ser inteiro".
- Operadores `>=`, `<=`, `>`, `<` com valor decimal → idem.

**3.4 — `gitnexus_detect_changes()` antes do commit**

---

### Etapa 4 — WI-3 + WI-6: Correções na gramática (passada única)

**Objetivo:** (WI-3) nomes de campo que começam com keyword parseiam corretamente; (WI-6) bibrefs numéricos são aceitos.

> Agrupar numa única passada porque ambos tocam `synesis.lark` e exigem a mesma regeneração do standalone.

**4.1 — Impact analysis para `FIELD_NAME` e `BIBREF`**
```
gitnexus_impact({target: "FIELD_NAME", direction: "upstream"})
gitnexus_impact({target: "BIBREF", direction: "upstream"})
```
A gramática é classificada como congelada para v1.x; ambas as correções são estritamente *additive* (ampliam o conjunto aceito). Reportar e prosseguir se risco for ≤ ALTO esperado.

**4.2 — Editar `synesis/grammar/synesis.lark`**

*WI-3* — linha ~215, ajustar `FIELD_NAME` com lookahead negativo + condição de fim de token:
```lark
FIELD_NAME.1: /(?!(?:end|code|chain|text|date|memo|quotation|scale|enumerated|ordered|topic|description)(?=:|\s|$))[\p{L}_][\p{L}\p{N}_\-]*/iu
```

*WI-6* — linha 203, relaxar primeiro caractere de `BIBREF`:
```lark
BIBREF: "@" /[a-zA-Z0-9][a-zA-Z0-9_-]*/
```

**4.3 — Regenerar `synesis/grammar/synesis_standalone.py`**
```bash
python -m lark.tools.standalone synesis/grammar/synesis.lark > synesis/grammar/synesis_standalone.py
```
Verificar que o arquivo gerado não tem erros de parse e que o tamanho/estrutura é compatível com a versão anterior.

**4.4 — Verificar que keywords continuam funcionando como keywords**

Campos cujos nomes SÃO exatamente uma keyword (`code`, `chain`, `text`, etc.) devem continuar sendo roteados corretamente pelas alternativas explícitas de `field_key` — testar:
```python
from synesis.parser.lexer import create_parser
p = create_parser()
# Deve continuar parseando (campo cujo TYPE é a keyword):
p.parse("FIELD code TYPE CODE\n")
p.parse("FIELD chain TYPE CHAIN\n")
# Deve agora parsear (nomes antes rejeitados):
for name in ['texto', 'code_quality', 'chain_length', 'date_created', 'topic_area']:
    p.parse(f"ITEM @x\n    {name}: v\nEND ITEM\n")
# Bibrefs numéricos:
for b in ['@2026', '@001', '@123abc', '@2026_main']:
    p.parse(f"SOURCE {b}\n\nEND SOURCE\n")
print("all OK")
```

**4.5 — Rodar suíte completa**
```bash
pytest tests/ -x
```
Qualquer regressão de parse deve ser investigada antes de prosseguir.

**4.6 — Criar fixture `T08-Field-Name-Collision`**

Arquivo `.syn` com campos `texto`, `code_quality`, `chain_length`, `date_created`, `memo_text`, `topic_area`, `scale_value` + casos exatos `code`, `chain` (nomeados via `field_key`). Asserir parse sem erros.

**4.7 — Escrever testes parametrizados**

Em `tests/test_parser.py` (ou equivalente):
```python
@pytest.mark.parametrize("name", ["texto", "code_quality", "chain_length", "date_created", "memo_text", "topic_area", "scale_value"])
def test_field_name_no_collision(name): ...

@pytest.mark.parametrize("bibref", ["@2026", "@001", "@123abc", "@2026_main"])
def test_numeric_bibref(bibref): ...
```

Adicionar também teste end-to-end com `INCLUDE BIBLIOGRAPHY` apontando para `.bib` com chave numérica.

**4.8 — `gitnexus_detect_changes()` antes do commit**

Verificar que apenas `synesis.lark`, `synesis_standalone.py` e arquivos de teste mudaram.

---

### Etapa 5 — WI-4: Implementar OPTIONAL BUNDLE

**Objetivo:** templates aceitam `OPTIONAL BUNDLE field1, field2`; ausência total é válida; presença parcial ou contagem divergente emite erro.

**5.1 — Impact analysis preventivo**
```
gitnexus_impact({target: "validate_bundle", direction: "upstream"})
gitnexus_impact({target: "bundled_fields", direction: "upstream"})
```
A estratégia de função separada (`validate_optional_bundle`) protege `validate_bundle` (CRITICAL). Confirmar e prosseguir.

**5.2 — Gramática: `synesis/grammar/synesis.lark`**

Localizar `requirement_clause` e adicionar alternativa `OPTIONAL`:
```lark
requirement_clause: KW_REQUIRED bundle_modifier? field_names
                  | KW_OPTIONAL bundle_modifier? field_names
```
Se `KW_OPTIONAL` não existe como terminal, declará-lo (prio adequada para não colidir com `FIELD_NAME`).

Regenerar standalone após esta etapa:
```bash
python -m lark.tools.standalone synesis/grammar/synesis.lark > synesis/grammar/synesis_standalone.py
```

**5.3 — Transformer: `synesis/parser/transformer.py` (~linha 790)**

Adicionar branch para `KW_OPTIONAL`:
```python
elif modifier == "OPTIONAL":
    return ("optional", has_bundle, names)
```

**5.4 — AST: `synesis/ast/nodes.py`**

Em `TemplateNode`:
```python
optional_bundles: Dict[Scope, List[Tuple[str, ...]]] = field(default_factory=dict)
```
Atualizar `to_dict()` para incluir `optional_bundles`.

**5.5 — Template loader: `synesis/semantic/template_loader.py`**

Popular `optional_bundles` espelhando os 5 loops de validação de `bundled_fields`. Nenhuma validação semântica aqui — apenas estrutura.

**5.6 — Validador: `synesis/semantic/validator.py`**

Criar **nova** função `validate_optional_bundle` (não tocar em `validate_bundle`):
```python
def validate_optional_bundle(self, item, template, scope):
    for bundle in template.optional_bundles.get(scope, []):
        present = [f for f in bundle if item.has_field(f)]
        if not present:
            continue  # ausência total → OK
        if len(present) != len(bundle):
            # presença parcial → MissingBundleField
            ...
        # verificar contagens se BUNDLE modifier presente
        ...
```
Reutilizar `MissingBundleField` e `BundleCountMismatch` existentes.

Chamar `validate_optional_bundle` nos 3 pontos: `validate_source`, `validate_item`, `validate_ontology`.

**5.7 — Exporters**

Nos três exporters, garantir que `optional_bundles` seja iterado junto com `bundled_fields`:
- `synesis/exporters/csv_export.py:153`
- `synesis/exporters/xls_export.py:164`
- `synesis/exporters/alpaca_export.py:683`

**5.8 — Criar fixture `T09-OptionalBundle`**

Quatro cenários em arquivos `.syn` separados (ou via parametrização):
1. Ausência total do bundle → 0 erros.
2. Presença parcial → `MissingBundleField`.
3. Contagem divergente (com BUNDLE modifier) → `BundleCountMismatch`.
4. Bundle completo → 0 erros.

**5.9 — Escrever testes**

- `tests/test_validator.py` → `TestOptionalBundleValidation` (4 cenários acima).
- Teste de integração com compilação end-to-end da fixture T09.
- Verificar que `validate_bundle` (REQUIRED) não regrediu.

**5.10 — Rodar suíte completa e `gitnexus_detect_changes()`**
```bash
pytest tests/ -x
gitnexus_detect_changes({scope: "all"})
```
Confirmar que `validate_bundle` não aparece no diff de lógica.

---

### Etapa 6 — Atualizar documentação e bumpar versão

**6.1 — `CHANGELOG.md`**

Mover entradas de `[Unreleased]` para `[0.6.0] — 2026-06-XX`:

```markdown
## [0.6.0] — 2026-06-XX

### Fixed
- WI-1: E001 (UnregisteredSource) espúrio em projetos sem `INCLUDE BIBLIOGRAPHY` — `compiler.load_bibliography()` agora retorna `None` quando não há declaração, preservando a distinção semântica com bib declarada-mas-vazia. ([#XX])
- WI-2: Campo CHAIN com nome customizado exportava relações como `IMPLICIT` no JSON; `_has_chain_relations` agora itera `field_specs.values()` por tipo, não por nome literal.
- WI-3: Nomes de campo que começam com keyword de tipo (`texto`, `code_quality`, `chain_length`, `date_created`, `topic_area`, etc.) falhavam no parse com `UnexpectedToken`; lookahead negativo em `FIELD_NAME` corrigido.
- WI-5: `ARITY = 2.0` era silenciosamente ignorado; agora emite erro explícito (se confirmado durante impl.).
- WI-6: Bibrefs puramente numéricos (`@2026`, `@001`) eram rejeitados; `BIBREF` relaxado para aceitar dígito como primeiro caractere.

### Added
- WI-4: Suporte a `OPTIONAL BUNDLE` em templates — ausência total é válida; presença parcial ou contagem divergente emitem `MissingBundleField`/`BundleCountMismatch`.

### Notes
- A alegação de que "`ARITY = 2` era ignorado" foi refutada; o relato derivava do bug de CHAIN com nome customizado, corrigido em v0.5.x.
```

**6.2 — `pyproject.toml`**

```toml
version = "0.6.0"
```

**6.3 — Verificar constraints de consumidores**

Checar `synesis>=` em:
- `synesis-coder/pyproject.toml`
- `synesis-lsp/pyproject.toml`
- `synesis-graph/pyproject.toml`

WI-1 muda comportamento observável (projetos sem bib antes falhavam, agora compilam). Qualquer consumidor que dependa do E001 para controle de fluxo deve bumpar para `synesis>=0.6.0`.

**6.4 — Atualizar memória do projeto**

Atualizar `sources_without_bibliography.md` na memória: a premissa "pronto por omissão" era falsa; a funcionalidade estava quebrada e foi corrigida em 0.6.0 via WI-1.

---

### Etapa 7 — Verificação end-to-end final

Rodar o checklist completo antes de taggear `v0.6.0`:

```bash
# Suíte completa (zero falhas)
cd d:/GitHub/synesis && pytest

# WI-1: projeto real sem bibliografia
python -c "
from pathlib import Path
from synesis.compiler import SynesisCompiler
r = SynesisCompiler(str(Path('tests/fixtures/T07-No-Bibliography/p.synp').resolve())).compile()
assert r.success, r.validation_result.errors
assert sum('Unregistered' in type(e).__name__ for e in r.validation_result.errors) == 0
print('WI-1 OK')
"

# WI-3 + WI-6: nomes e bibrefs
python -c "
from synesis.parser.lexer import create_parser
p = create_parser()
for n in ['texto', 'code_quality', 'chain_length', 'date_created']:
    p.parse(f'ITEM @x\n    {n}: v\nEND ITEM\n')
for b in ['@2026', '@001', '@123abc']:
    p.parse(f'SOURCE {b}\n\nEND SOURCE\n')
print('WI-3 + WI-6 OK')
"

# Lint e tipagem
ruff check synesis && ruff format --check synesis && mypy synesis
```

**Self-check GitNexus (obrigatório antes de fechar o ciclo):**
1. `gitnexus_impact` foi executado para todos os símbolos modificados?
2. Nenhum aviso HIGH/CRITICAL foi ignorado?
3. `gitnexus_detect_changes()` confirma que o escopo de mudanças está dentro do esperado?
4. Todos os dependentes d=1 (WILL BREAK) foram atualizados?
