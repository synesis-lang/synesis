# `IDENTIFIES` / `REFERS TO` — Ligação entre projetos Synesis independentes

Proposta de design para triangular corpora heterogêneos (currículos, abstracts, GitHub, LinkedIn, startups) **sem** transformá-los numa única unidade de compilação. Cada projeto continua independente, rápido e autônomo; a ligação entre eles é declarada no template e resolvida num **passo de linkagem** disparado explicitamente na CLI — nunca no LSP.

O modelo mental é o do **linker de C/C++**: cada unidade compila isolada e expõe seus *símbolos externos não resolvidos*; um passo de link (`synesis compile p1.synp p2.synp`) resolve os símbolos entre unidades e produz o agregado.

> **Status: TODAS AS 5 ETAPAS IMPLEMENTADAS.** Etapas 1–3 no repo `synesis`, Etapa 4 no `synesis-graph`, Etapa 5 no `synesis-lsp` + `synesis-vscode` — `IDENTIFIES`/`REFERS TO`/`ON BIBLIOGRAPHY`, validações E077–E082/I080/W083, e o passo de linkagem CLI (`synesis compile p1 p2 …`) com pacote de saída v3.1. **Aceite no corpus real (§12.3.5) PASSOU:** migração não-destrutiva de `Dados_Lattes`+`Dados_Abstracts` (em scratchpad, corpus original intocado) resolveu as **7 arestas `researcher`** esperadas (7 abstracts → 1 currículo `3474…167`, n:1), zero órfãos; e o bibref compartilhado `@thiago-nogueira-60854758` (presente em `linkedin.bib` E `posts.bib`) **não colide** após namespacing por alias (`linkedin:@…` ≠ `posts:@…`). **Etapa 3 concluída:** `INCLUDE SHARED ONTOLOGY` resolve `..`/rede/drive; `INCLUDE ONTOLOGY` sem `SHARED` mantém `ESCAPES_PROJECT` byte-idêntico (incl. LSP); `SHARED` com tipo ≠ ontologia → `SharedOnlyForOntology` (E084). **Correção de contradição do plano:** §9 mandava restringir `SHARED` a ONTOLOGY *na gramática*, o que tornaria o `SharedOnlyForOntology` do §12.2 inalcançável (viraria erro de sintaxe). Resolvido: gramática permissiva (`KW_SHARED?` antes de qualquer tipo) + erro **semântico** — mensagem pedagógica em vez de parse error. **Etapa 4 concluída** (`synesis-graph`, 244 testes): `--project` repetível reifica `(:Researcher {entity_id})` a partir de `IDENTIFIES` e desenha `(:Source)-[:REFERS_TO {entity}]->(:Entidade)`; bibrefs/item ids qualificados por alias (verificado no pior caso: mesmo projeto sob dois aliases não colide); nó nasce só de `IDENTIFIES`, órfão não vira stub. Entrada por múltiplos `--project` (não pelo pacote v3.1) porque o export v3.0 **já carrega** as declarações em `field_specs`. Reificação no **HTML adiada** — é grafo de conceitos e exige design de camada próprio; a CLI recusa multi-projeto ali. **Etapa 5 concluída** (`synesis-lsp` 34 testes, `synesis-vscode` 133): watcher reintroduzido nos alvos dos `INCLUDE SHARED` com índice reverso `alvo→projetos`. **Defeito não previsto pelo plano, achado e corrigido na Etapa 5:** o `_compute_workspace_fingerprint` do LSP fazia `os.walk` só na raiz do workspace, então a ontologia compartilhada (que vive fora dela) **não entrava no fingerprint** — editá-la não invalidava o cache e o `loadProject` devolvia dado obsoleto. O watcher sozinho não resolveria: ele chamaria `loadProject` e receberia o cache velho. Corrigir o fingerprint é **pré-requisito** do watcher. Verificado E2E: edição puramente externa (`+Reciprocidade`) agora chega ao contexto do LSP.

**Pendências remanescentes (nenhuma bloqueia o uso):** reificação no backend HTML (§7 — exige design da camada de identidade sobre o grafo de conceitos) e o açúcar `REFERS TO <e> AS <relação>` (§7, adiado desde a Rev. 2 — o default `[:REFERS_TO]{entity}` funciona sem ele). Os invariantes de não-regressão estão na §11 e o protocolo do implementador na §12.
>
> **Histórico de revisões (2026-07-15):**
> - **Rev. 7** — revisão de verificação contra o código-fonte antes de implementar. Correções factuais e um furo estrutural fechado:
>   1. **`ON BIBLIOGRAPHY` restrito a `requirement_clause` de campo único** (§2.3, §9): a regra real `field_names: field_key ("," field_key)*` aceita lista (`REQUIRED a, b, c`), o que tornaria `ON BIBLIOGRAPHY` ambíguo numa lista multi-campo. Decidido: o sufixo só é válido quando a cláusula tem **um** campo (`REQUIRED lattes_id ON BIBLIOGRAPHY`); lista + `ON BIBLIOGRAPHY` = erro de sintaxe.
>   2. **Wiring do `SHARED` corrigido** (§9, §12.4): `resolve_include` tem **11 call sites** (compiler.py ×6, lsp_adapter.py ×5) e o `IncludeNode` **já carrega `include_type`** — os sites de ontologia são só **dois** (compiler.py:258 via `_collect_include_paths(project, "ONTOLOGY")`; lsp_adapter.py:673). O flag `shared` recebe **default `False`** e só os dois sites de ontologia o passam; os outros 9 ficam byte-idênticos. Não é mudança de assinatura global arriscada.
>   3. **Números de teste fixos (229/214) substituídos por baseline dinâmico** — o `synesis` já tem ~255 funções `test_`, não 229; contagem hardcoded envelheceu. O invariante passa a ser "baseline coletado com `pytest --collect-only` no início de cada etapa".
>   4. Removida duplicata da linha de histórico da Rev. 2.
> - **Rev. 6** — três decisões que fecham as fronteiras de segurança e contrato (as únicas partes que a crítica externa furou como ainda abertas):
>   1. **`IDENTIFIES`/`REFERS TO` reenquadrados como PK/FK** (§2.3, §2.4): `IDENTIFIES` = chave primária da entidade (única, dona, cria o nó); `REFERS TO` = chave estrangeira (aponta, repete, não cria nó). OWL rebaixado a **nota de exportação** — não é mais fundamento da validação (a validação é *candidate key* / integridade fechada, mundo-fechado; `owl:hasKey` é mundo-aberto e não impõe unicidade). Colapsar num único verbo foi rejeitado: sem lado proprietário, a reificação e o `DuplicateIdentityValue` não têm âncora.
>   2. **`.synstudy` eliminado** (§2.2): a contenção por *geometria de path* (âncora de pasta / ancestral comum / workspace) é o modelo errado — obriga subprojetos no mesmo ancestral de disco e é **incapaz** de autorizar ontologia em rede (`\\servidor\...`) ou outro drive. Substituído por autorização **na declaração**: nova keyword **`INCLUDE SHARED ONTOLOGY`** autoriza qualquer path externo; `INCLUDE ONTOLOGY` comum mantém `ESCAPES_PROJECT`. `SHARED` só vale para `ONTOLOGY` nesta fase.
>   3. **Descoberta automática de comando de link removida** (§5): sem âncora não há onde varrer `.synt` — e a varredura era vulnerável a cópias (`lattes - Copia.synt` no corpus real). Fica só a **mensagem INFO genérica**, que já é correta e completa. O usuário passa os projetos que quer linkar.
> - **Rev. 2** — keywords renomeadas de `KEY`/`REFERENCE` para `IDENTIFIES`/`REFERS TO` (§2.4); exemplo de compilação isolada corrigido (§5 — o aviso original era semanticamente impossível e sugeria um comando inconstruível); regras de colisão de bibref, dono único de rótulo (§4) e contrato do agregado (§6).
> - **Rev. 3** — verificação contra o corpus real Lattes+Abstracts: qualificador `ON BIBLIOGRAPHY` no `SOURCE FIELDS` (§2.3 — o valor de `lattes_id` vive só no `.bib`; forçar `SCOPE SOURCE` extraível mentiria sobre o dado); distinção **proveniência n:1 ≠ autoria n:n** (§3.1).
> - **Rev. 4** — casos de borda: `TypeMismatchInLinkage` (§4); **rejeição deliberada da normalização automática de caixa** com a alternativa do warning de quase-casamento (§4); reintrodução consciente do `FileSystemWatcher` no LSP (§2.2, Etapa 5).
> - **Rev. 5** — consolidação final: duplicatas removidas, grafo de dependências corrigido, números dos exemplos alinhados ao corpus real, §12 (protocolo do implementador) adicionada.

---

## 1. Motivação e alternativas descartadas

O caso Quinto Andar crescerá para ~6 corpora numa estrela dupla (pesquisador via Lattes, cruzada pela organização). Três abordagens foram consideradas e descartadas:

| Abordagem | Por que foi descartada |
|---|---|
| **Bloco `STUDY` / masterproject** ([proposta_master_project.md](../../case-studies/Quinto_Andar/proposta_master_project.md)) | Torna o agregado uma **unidade de compilação**. Com subprojetos grandes, o LSP recompila/mantém em memória o conjunto inteiro a cada save. Sobrecarga inaceitável. |
| **Parâmetro `--link "k1 -> k2 -> k3"`** no synesis-graph | O `->` como reconciliação (`owl:sameAs`) só modela **1:1** — "esta pessoa É aquela pessoa". Colapsa em **n:1 e n:n**: muitos abstracts → um pesquisador não é identidade, é relação. Fundir seria errado. |
| **`REFERENCE ... ON TEMPLATE abstracts`** (acoplado a arquivo) | O hub (`lattes.synt`) passa a **nomear** cada corpus periférico. Adicionar um 3º corpus exige editar o hub — o oposto de autônomo. |

A solução adotada mantém o que essas tentativas tinham de bom (declaração versionada, autonomia, cardinalidade livre) e remove seus defeitos: **compilação separada com linkagem na CLI**, com ligações declaradas por **rótulo de entidade**.

---

## 2. As três peças

### 2.1 Projetos independentes (mantido)

Cada `.synp` compila isolado — rápido, com cache por fingerprint isolado e autonomia total. É o modo default do compilador e do LSP. **Nada muda neste caminho.**

### 2.2 Ontologia externa unificada

Para unificar o vocabulário conceitual (códigos/chains) sem duplicar a ontologia em cada projeto, ela mora numa pasta compartilhada externa, referenciada por vários projetos.

Isso exige relaxar a contenção de include — hoje `INCLUDE ONTOLOGY "../shared/ontologia.syno"` é recusado com `ESCAPES_PROJECT` ([paths.py:141-142](../synesis/parser/paths.py#L141)). **A autorização mora na declaração, não numa âncora de pasta:**

```
# ontologia compartilhada — path arbitrário, autorizado pela keyword SHARED
INCLUDE SHARED ONTOLOGY "../shared/ontologia.syno"
INCLUDE SHARED ONTOLOGY "\\servidor\equipe\ontologia.syno"
INCLUDE SHARED ONTOLOGY "Z:/estudo/onto.syno"
```

**Por que não uma âncora de pasta (`.synstudy`, ancestral comum, workspace root).** Toda contenção por *geometria de path* pressupõe que os `.synp` vivem sob um **ancestral de disco comum** — imposição de layout que nada tem a ver com o estudo (`C:\Lattes\` + `D:\Abstracts\` não têm ancestral comum útil). Pior: é **geometricamente incapaz** de autorizar uma ontologia em rede (`\\servidor\...`) ou noutro drive, que nunca estará "dentro" de raiz local nenhuma. O modelo correto para um recurso *deliberadamente externo* não é proximidade, é **permissão explícita por referência**.

- **`INCLUDE SHARED ONTOLOGY "..."`** — o autor declara a intenção: "isto é externo e eu autorizo". Aceita rede, drive, `..`, caminho absoluto — a autorização é a keyword, não a localização. Versionada e auditável no próprio `.syn`.
- **`INCLUDE ONTOLOGY "..."` (sem `SHARED`)** — mantém o `ESCAPES_PROJECT` atual. Projetos avulsos ficam **byte-idênticos** ao comportamento de hoje; `paths.py` (compartilhado CLI/LSP) só relaxa quando vê a intenção `shared`.
- **Restrição de tipo:** só `ONTOLOGY` aceita `SHARED` nesta fase. `INCLUDE SHARED BIBLIOGRAPHY`/`TEMPLATE`/`ANNOTATIONS` → erro. O escape não vaza para tipos que a motivação (compartilhar vocabulário conceitual) não pediu.
- **Segunda barreira no editor (opcional):** no VS Code, o Workspace Trust nativo pode gatear o `SHARED` — pasta não confiável bloqueia o include externo mesmo com a keyword. Reforço, não substituto (a CLI pura não tem Workspace Trust).

Cada membro **mantém** seu próprio `INCLUDE SHARED ONTOLOGY` apontando ao arquivo compartilhado (necessário para compilar isolado). Não há bloco de ontologia "do estudo".

**Nota para o LSP (Etapa 5 futura) — reintrodução consciente de `FileSystemWatcher`:** a ontologia compartilhada vive fora da pasta do projeto aberto. O mecanismo atual de refresh é `onDidSaveTextDocument` ([extension.js:681](../../synesis-vscode/extension.js#L681)), que **só dispara para documentos abertos no editor** — e os `FileSystemWatcher` foram *deliberadamente removidos* no passado por "redundantes" ([CHANGELOG:446,470](../../synesis-vscode/CHANGELOG.md#L446)). Essa premissa (projeto único auto-contido) **quebra** aqui: a ontologia compartilhada pode ser editada sem estar aberta (git pull, outro processo, outra janela, arquivo de rede), e o `onDidSave` do projeto que a inclui nunca vê o evento → validação em tempo real fica obsoleta silenciosamente. Logo, a Etapa 5 deve **reintroduzir** um `FileSystemWatcher` observando os alvos dos `INCLUDE SHARED ONTOLOGY` — não basta ampliar o `onDidSave`. Isso exige um **índice reverso** `include_alvo → projetos que o incluem` (senão o watcher sabe *que* algo mudou, mas não *quais* projetos invalidar). É uma reversão consciente de decisão anterior, justificada pela premissa que mudou. Não bloqueia o design; registrado para a etapa de LSP.

### 2.3 Ligação: par `IDENTIFIES` / `REFERS TO`

Dois modificadores de `FIELD` no template `.synt`, casados por **rótulo de entidade**:

```
# lattes.synt — este corpus EXPORTA a identidade "researcher" (símbolo público)
# lattes_id é extraído do documento (currículo) → campo SOURCE normal
SOURCE FIELDS
    REQUIRED lattes_id, nome, cargo_institucional
END SOURCE FIELDS

FIELD lattes_id TYPE TEXT
    SCOPE SOURCE
    IDENTIFIES researcher
    DESCRIPTION ID Lattes (16 dígitos)
END FIELD

# abstracts.synt — este corpus REFERENCIA a identidade "researcher" (símbolo externo)
# lattes_id NÃO é extraído do abstract — é proveniência de coleta, vive no .bib
SOURCE FIELDS
    REQUIRED description, knowledge_area, method
    REQUIRED lattes_id ON BIBLIOGRAPHY       ← valor lido do .bib, não do texto
END SOURCE FIELDS

FIELD lattes_id TYPE TEXT
    SCOPE SOURCE
    REFERS TO researcher
    DESCRIPTION ID Lattes de proveniência (de qual currículo o artigo foi coletado)
END FIELD
```

O par se lê diretamente como **Primary Key / Foreign Key** — o modelo relacional clássico, familiar mesmo a quem não é DBA:

- **`IDENTIFIES <entidade>` = chave primária da `<entidade>`.** O campo **é a PK** do rótulo: valor único no corpus (`DuplicateIdentityValue` = violação de PK, §4), corpus **dono** do rótulo (`DuplicateEntityOwner`, §4), e o **nó reificado nasce só daqui** (§7). Propriedade **local** do corpus — zero acoplamento a outros projetos. O verbo carrega a unicidade naturalmente: identificar é apontar *um*.
- **`REFERS TO <entidade>` = chave estrangeira para `<entidade>`.** O campo **aponta** para a PK de outro corpus. Pode **repetir** (é o que dá n:1 e n:n, §3), **não cria nó**, e um valor sem PK correspondente é um **FK órfão** (warning, §4). Não nomeia o arquivo alvo nem acopla ao projeto dono — casa por rótulo + igualdade de valor, como uma FK casa por domínio de chave, não por nome de tabela física.

**Nota de exportação (não é fundamento da validação):** na exportação semântica, `IDENTIFIES` pode ser materializado como `owl:hasKey` e `REFERS TO` como `owl:ObjectProperty`. Mas a **validação do Synesis é PK/FK de mundo-fechado** (candidate key relacional, integridade referencial fechada — ISO/IEC 9075), **não** semântica OWL: OWL é mundo-aberto, não assume *unique name*, e `owl:hasKey` não impõe unicidade nem funcionalidade. Usar OWL como fundamento da validação estaria errado; a analogia serve só para descrever a saída RDF. Do mesmo modo, `owl:sameAs` (colapso de identidade) foi rejeitado como modelo de ligação porque fundiria entidades que a fonte considera distintas (§1) — `REFERS TO` é aresta, não fusão.

Casam por rótulo (`researcher`), por igualdade de valor. Nenhum projeto conhece o outro pelo nome. Adicionar um terceiro corpus (`github.synt`) que aponta ao pesquisador = criar `REFERS TO researcher` nele; **zero edição** nos existentes.

**Origem do valor — `ON BIBLIOGRAPHY`.** Um campo pode ser preenchido de duas fontes: **extraído do documento** pelo coder (default) ou **lido do `.bib`** (proveniência/metadado de coleta, não extraível do texto). No corpus real, `lattes_id` do abstracts é do segundo tipo — verificado: [abstracts.synt:224-227](../../case-studies/Quinto_Andar/Dados_Abstracts/abstracts.synt#L224) declara `description, knowledge_area, method` no SOURCE; `lattes_id` está **só no `.bib`** ([abstracts.bib:13](../../case-studies/Quinto_Andar/Dados_Abstracts/abstracts.bib#L13)).

Forçar `lattes_id` a ser extraído do texto seria **mentir sobre o dado** — o coder não pode gerar do abstract um ID que não está nele. A declaração honesta usa o qualificador de origem no `SOURCE FIELDS`:

```
SOURCE FIELDS
    REQUIRED description, knowledge_area, method    # extraídos do texto
    REQUIRED lattes_id ON BIBLIOGRAPHY              # valor vem do .bib
END SOURCE FIELDS
```

`ON BIBLIOGRAPHY` é ortogonal ao `SCOPE`: o `FIELD lattes_id` continua `SCOPE SOURCE` (é propriedade do artigo-SOURCE — sua proveniência), mas seu *valor* é resolvido do `.bib`, não do documento. Sem preenchimento em nenhuma fonte → erro (o campo é `REQUIRED`).

**Encaixe gramatical — sufixo só em cláusula de campo único (verificado, Rev. 7).** A regra real é `requirement_clause: KW_REQUIRED bundle_modifier? field_names` com `field_names: field_key ("," field_key)*` ([synesis.lark:132,150](../synesis/grammar/synesis.lark#L132)) — ou seja, uma cláusula pode listar **vários** campos (`REQUIRED description, knowledge_area, method`). Anexar `ON BIBLIOGRAPHY` a uma cláusula multi-campo seria **ambíguo** (aplica-se a qual campo?). Decisão: uma **nova alternativa de campo único** em `requirement_clause`, distinta da que aceita lista:

```
requirement_clause: KW_REQUIRED bundle_modifier? field_names
                  | KW_OPTIONAL bundle_modifier? field_names
                  | KW_FORBIDDEN field_names
                  | KW_REQUIRED field_key KW_ON KW_BIBLIOGRAPHY   ← nova, 1 campo só
                  | KW_OPTIONAL field_key KW_ON KW_BIBLIOGRAPHY
```

`REQUIRED a, b ON BIBLIOGRAPHY` (lista + sufixo) fica fora da gramática → erro de sintaxe claro. Reusa `KW_BIBLIOGRAPHY` já existente; só `KW_ON` é novo. O corpus real satisfaz isso: `description, knowledge_area, method` ficam na cláusula-lista; `lattes_id ON BIBLIOGRAPHY` numa cláusula própria de um campo.

**Migração do caso real:** `abstracts.synt` ganha a linha `REQUIRED lattes_id ON BIBLIOGRAPHY` no `SOURCE FIELDS` e o `FIELD lattes_id ... REFERS TO researcher`. **Nenhum dado muda** — os valores já estão no `.bib`.

Forma verbosa opcional para desambiguar: `REFERS TO researcher FROM lattes` (açúcar, não default).

### 2.4 Por que não `KEY` / `REFERENCE` (terminologia)

O público do Synesis são pesquisadores qualitativos (NVivo/ATLAS.ti/MAXQDA), não engenheiros de banco de dados:

- **`REFERENCE` colide frontalmente com "referência bibliográfica"** — e a colisão é *interna à DSL*: já existem `INCLUDE BIBLIOGRAPHY`, bibrefs (`@silva2020`), `.bib`. Um pesquisador leria `REFERENCE` num campo como "este campo contém uma citação".
- **`KEY`** evoca "key theme"/"key informant" em contexto qualitativo, não identificador único.
- `RELATION` (Dublin Core `dc:relation`) foi considerado e descartado: colide com o `KW_RELATIONS` já existente na gramática.

O par verbal `IDENTIFIES`/`REFERS TO` lê como discurso — alinhado à filosofia discursiva da DSL (`REQUIRED`/`OPTIONAL`, cardinalidade discursiva) — e mapeia sem folga para PK/FK (§2.3). A entidade reificada (pesquisador, organização) corresponde ao conceito de **case** do NVivo (*case classifications*), familiar ao público.

**Por que dois verbos, e não um só (`REFERS TO` com o nome do campo como entidade).** Tentador colapsar em um verbo e deixar o *nome do campo* ser a entidade (campo chamado `Researcher` em vez de `lattes_id`). Rejeitado — reintroduz dois defeitos que o corpus real expõe:

1. **Acopla rótulo ↔ nome do campo.** O hub Lattes identifica a mesma pessoa por eixos distintos (`lattes_id`, `github_id` em `links_externos`, `orcid`) — se o nome do campo *é* a entidade, não cabem dois campos identificando `researcher`. E o `lattes_id` de abstracts vem do `.bib` (`ON BIBLIOGRAPHY`): o campo **tem** que se chamar `lattes_id` porque é a chave do `.bib`, não pode virar `Researcher`. Rótulo e nome de campo precisam ser independentes.
2. **Apaga o lado proprietário.** Sem `IDENTIFIES`, ninguém declara o dono da identidade: o nó `Researcher` nasceria de qualquer valor em qualquer `REFERS TO`, um FK digitado errado criaria nó fantasma sem contra o quê validar, e some a constraint de unicidade (PK) — que é justamente o ganho concreto que o `IDENTIFIES` entrega já na Etapa 1. A intuição correta ("o papel do identificador é não permitir chaves repetidas, como Primary Key") **é exatamente `IDENTIFIES`**; removê-lo remove a constraint.

---

## 3. Cardinalidade — por que resolve n:1 e n:n

`REFERS TO` produz uma **aresta**, não uma fusão. A restrição de cardinalidade do `sameAs` (que exige 1:1) desaparece:

| Cardinalidade | Exemplo | Como o modelo cobre |
|---|---|---|
| **n:1** | muitos abstracts → um pesquisador | muitos `REFERS TO researcher` apontando ao mesmo valor de `IDENTIFIES researcher` = muitas arestas para um nó |
| **n:n** | muitos posts ↔ muitos perfis | múltiplos campos `REFERS TO` (eixos distintos), cada um um conjunto de arestas |
| **1:1** | um perfil GitHub ↔ um pesquisador | caso degenerado — uma aresta única |

A cardinalidade **observada** vira propriedade do grafo materializado; não é uma restrição imposta no template.

**Campo multi-valorado:** se o campo com `REFERS TO` é uma lista (ex. `links_externos` do Lattes), **cada valor gera uma aresta**. É o caso natural do hub Lattes apontando a múltiplos perfis externos.

**Confirmação nos dados reais:** [abstracts.bib:13](../../case-studies/Quinto_Andar/Dados_Abstracts/abstracts.bib#L13) já contém `lattes_id = {3474555741700167}` escrito à mão. A ligação n:1 abstract→pesquisador **já existe no corpus** — o design apenas a declara e materializa.

### 3.1 Proveniência ≠ autoria — o que os dados suportam hoje

Um ponto crítico revelado pelo corpus real: `lattes_id` no `.bib` de abstracts é **proveniência de coleta**, não **autoria**. São eixos semânticos distintos, e só um tem dado:

| Eixo | Pergunta que responde | Dado disponível hoje | Cardinalidade |
|---|---|---|---|
| **Proveniência** | "de qual currículo este artigo foi coletado?" | `lattes_id` (1 valor, populado) + `lattes_origin_count` | **n:1** ✅ |
| **Autoria** | "quais pesquisadores do estudo assinam este artigo?" | só `author` (texto livre, nomes) | **n:n** ❌ sem dado resolvido |

Verificado: todos os 7 abstracts têm `lattes_id = 3474...167` e `lattes_origin_count = 1` — vieram todos do currículo de um pesquisador. Mas o campo `author` mostra co-autoria real: `machado2022` tem **8 autores**, `alvarenga2021` tem **8**. Se vários deles tivessem currículo no estudo, o artigo ligaria a N pesquisadores (n:n).

**Por que a autoria n:n não se implementa agora:** ligar por `author` exigiria casar `"Hanriot, Vítor M."` / `"Vitor Mourão Hanriot"` / `"Hanriot, Vitor M."` (sem acento, em `assis2021`) com o `nome` do currículo — exatamente o **casamento fuzzy por nome que o §4 proíbe**. O modelo `REFERS TO` **já suporta n:n tecnicamente** (campo multi-valorado → uma aresta por valor, acima); o que falta é o **dado resolvido**: uma lista de `lattes_id`s de co-autores, produzida por um passo de **resolução de identidade upstream** (nomes → IDs, com revisão humana), fora do compilador:

```
# .bib enriquecido por resolução de identidade (trabalho de pipeline, não do compilador):
lattes_coautores = {3474555741700167, 1234567890123456}   # → REFERS TO researcher (n:n)
```

Este é o mesmo princípio que rege o Synesis inteiro: **o compilador verifica integridade, não adivinha identidade.** A autoria n:n entra sem mudança de linguagem no dia em que o corpus tiver os IDs resolvidos. Até lá, a ligação materializada é a **proveniência n:1**, que os dados suportam integralmente.

---

## 4. Integridade referencial

A ligação é integridade referencial — o mesmo gênero de verificação que o Synesis já faz com `OrphanItem` (ITEM→SOURCE) e "undefined code" (chain→ontologia). Todos os erros/avisos novos seguem o padrão do ecossistema: **número de erro alocado na sequência de `results.py` + arquitetura dual de mensagem** (`to_diagnostic` verboso para LSP+LLM, `to_cli_line` enxuto — ver `diagnostics_dual_message_architecture`).

- **Unicidade do `IDENTIFIES` (na origem):** dois SOURCEs do mesmo corpus com o mesmo valor de campo `IDENTIFIES` → **erro `DuplicateIdentityValue`** na compilação do **próprio membro**, antes de qualquer linkagem. É o ganho concreto e imediato: um defeito de dados hoje silencioso vira erro. Garante que cada valor casa com **um** Source (sem fan-out ambíguo).
- **Dono único do rótulo:** dois projetos declarando `IDENTIFIES researcher` no mesmo link step → **erro `DuplicateEntityOwner`**. Um rótulo tem um corpus proprietário. Identidade entre esquemas de ID distintos (Lattes vs ORCID vs GitHub) **não** se resolve com dois `IDENTIFIES` — os valores nunca casariam (nós duplicados da mesma pessoa). Resolve-se com o hub referenciando a periferia: o Lattes já captura `github_id` em `links_externos` → vira `REFERS TO` do hub para o rótulo do corpus GitHub (aresta, não fusão).
- **Consistência de tipo (`TypeMismatchInLinkage`):** todos os campos que participam da mesma entidade (um `IDENTIFIES <e>` e todos os `REFERS TO <e>`) devem ter **`TYPE` idêntico** — validado no link step. O valor resolvido é sempre string (do texto ou do `.bib`), então o mismatch não quebra a comparação tecnicamente; é **sintoma de erro de modelagem** — se um lado declara `TYPE DATE` e o outro `TYPE TEXT`, os dois não modelam a mesma entidade. `IDENTIFIES` sobre `TYPE CODE` (referência a conceito da ontologia) vs `REFERS TO` sobre `TYPE TEXT` é o caso clássico a barrar. Erro duro, não warning.
- **Casamento por igualdade exata — decisão deliberada contra normalização automática:** valor comparado após `trim` de espaços/invisíveis nas bordas; **sem** case-folding, **sem** normalização silenciosa, sem fuzzy. A tentação (IDs textuais como `@ThiagoNogueira` vs `@thiagonogueira` em GitHub/LinkedIn) é rejeitada por princípio: normalização automática é uma heurística que **acerta em sistemas case-insensitive e cria falsos positivos em sistemas case-sensitive** (slugs, DOIs, handles legados) — fundindo entidades que a fonte considera distintas, de forma **invisível e não-auditável**. Um casamento por lowercase automático é indistinguível de um casamento legítimo; se estava errado, o painel mente com confiança. A canonização correta acontece **na origem, visível**: o pipeline de coleta canoniza o valor ao gravá-lo no `.bib` (porque conhece a regra *daquele* sistema), e o compilador compara exato.
- **Quase-casamento é warning elevado, não fusão:** para não ser punitivo com o erro honesto de caixa, o link step **detecta** (sem ligar) órfãos cujo valor casaria sob normalização e emite diagnóstico acionável — a normalização vira heurística de *suspeita*, nunca de *fusão*:
  ```
  ⚠ REFERS TO órfão: '@ThiagoNogueira' (researcher) sem IDENTIFIES correspondente.
    Casamento próximo: '@thiagonogueira' difere apenas em caixa.
    Se são a mesma entidade, canonize o valor na origem (.bib/SOURCE).
  ```
  O compilador avisa que *talvez* você tenha errado; nunca conserta o que *acha* que você errou.
- **`REFERS TO` órfão (caso geral):** valor sem `IDENTIFIES` correspondente no link step → **warning legítimo** (ex. abstract de autor externo sem currículo no corpus). Não é erro; não cria nó. O quase-casamento acima é o subcaso enriquecido deste warning.
- **Colisão de bibref entre membros:** os bibrefs são **locais ao membro**; no agregado, são qualificados pelo alias do membro (derivado do nome do arquivo: `linkedin.synp` → `linkedin:@thiago-nogueira-…`). Isto é necessário nos dados reais **hoje**: `linkedin.bib` e `posts.bib` compartilham o bibref `@thiago-nogueira-60854758`. O namespacing elimina a colisão por construção — a junção de identidade passa **exclusivamente** por `IDENTIFIES`/`REFERS TO`, nunca por igualdade acidental de bibref. (Dissolve o `CrossMemberBibrefCollision` que a proposta `STUDY` precisava.)

---

## 5. Modelo de execução — compilação separada + linkagem

### Compilação isolada (default, LSP e CLI)

Um projeto que só declara `IDENTIFIES` não tem nada a resolver — é uma *definição*, e um `IDENTIFIES` sem `REFERS TO` em outro projeto é indetectável isoladamente (por construção: o compilador não conhece os demais projetos). A comunicação acontece **apenas no lado `REFERS TO`**, com severidade **INFO** — não warning: um aviso que aparece em todo save de todo projeto com `REFERS TO` seria ruído permanente, e warnings ignorados degradam a credibilidade do painel (mesmo argumento da regra anti-fuzzy).

**Mensagem genérica (o compilador não conhece outros projetos):**

```
$ synesis compile abstracts.synp
✓ compilado.
ℹ 1 referência externa declarada: 'researcher' (REFERS TO em lattes_id).
  As ligações não estão materializadas neste artefato. Para resolvê-las,
  compile este projeto junto com o projeto que declara IDENTIFIES 'researcher'.
```

**Sem descoberta automática de comando concreto (Rev. 6).** Uma versão anterior varria os `.synt` sob uma raiz `.synstudy` para sugerir o comando exato (`synesis link a.synp b.synp`). Removido com a âncora: sem raiz declarada não há escopo de varredura, e a varredura era **vulnerável a cópias** — o corpus real tem `Dados_Lattes/lattes - Copia.synt`, que uma varredura cega trataria como segundo dono de `researcher` (falso `DuplicateEntityOwner`) ou sugeriria um projeto que nenhum `.synp` referencia. A descoberta correta seria `.synp declarados → TEMPLATE de cada um`, nunca `todos os .synt`; como nada declara os membros fora do comando, a sugestão automática sai. A mensagem genérica é **válida e completa** para o membro (princípio da autonomia); o usuário passa os projetos que quer linkar. O INFO é o *unresolved external symbol* do linker C.

### Passo de linkagem (agregação sob demanda)

```
$ synesis compile lattes.synp abstracts.synp
✓ 2 projetos linkados. 7 arestas 'researcher' resolvidas (n:1).
⚠ 1 REFERS TO órfão (valor sem IDENTIFIES correspondente — ex. autor externo).
```

(Números do corpus real: 7 abstracts, todos com `lattes_id = 3474…167` → 7 arestas para o nó do pesquisador; o órfão é ilustrativo.)

O agregado só existe quando **você** passa múltiplos `.synp`. É batch, offline, disparado explicitamente. No link step, órfãos **são** warning (não INFO): aqui o usuário pediu a resolução, e um valor não casado é informação acionável.

### Fronteira crítica: agregação é modo de CLI, nunca de LSP

> O **LSP/editor nunca carrega o agregado.** Abre um projeto por vez e mostra o INFO de referência externa como diagnóstico informativo. A triangulação resolvida vive **apenas** no artefato compilado da CLI e no Neo4j.

Esta é a fronteira que evita a sobrecarga que descartou o `STUDY`: o custo do LSP permanece **exatamente igual ao de hoje**, por projeto. Se no futuro o editor precisar exibir a triangulação em tempo real, isso é uma decisão separada com o custo de agregado assumido conscientemente — não é pré-requisito.

---

## 6. Artefatos do link step

O contrato de exportação do agregado (a proposta `STUDY` §6 tinha isto; preservado aqui):

| Formato | Comportamento |
|---|---|
| **JSON** | Agrega num único arquivo. Schema **v3.1 aditivo** sobre o v3.0: campos anotados com `identifies`/`refers_to`, seção nova `links` (arestas resolvidas + órfãos), bibrefs qualificados por alias de membro. Consumidores v3.0 ignoram as chaves novas. |
| **CSV / XLS** | Tabular **por membro** — os `SOURCE FIELDS` de membros distintos são incompatíveis; não há tabela única coerente. Reusa os exportadores atuais por membro, sem alterá-los. |

O nome do agregado vem do flag `--name` (se passado) ou é derivado dos membros. Pacote de saída:

```
quinto_andar_export/
├── lattes/       { lattes_sources.csv, … }
├── abstracts/    { … }
├── links.csv     ← arestas resolvidas (rótulo, valor, origem, destino) + órfãos
└── export.json   ← agregado v3.1
```

---

## 7. Materialização no grafo (synesis-graph)

```
synesis-graph neo4j --project lattes.synp --project abstracts.synp --project github.synp
```

O `synesis-graph` lê os `IDENTIFIES`/`REFERS TO` dos JSONs e:
- cria um **nó de identidade reificado** `(:Researcher {id: <valor>})` por valor distinto de `IDENTIFIES researcher` (label do nó = rótulo capitalizado/sanitizado);
- desenha arestas `(:Source)-[:<relação>]->(:Researcher)` para cada `REFERS TO` casado.

**Nome da relação:** default derivado do rótulo (`[:REFERS_TO_RESEARCHER]` é pobre; melhor default: `[:REFERS_TO]` com propriedade `entity`). Para semântica rica, açúcar opcional no template: `REFERS TO researcher AS <relação>` → `[:<RELAÇÃO>]`. Este açúcar é o que distingue os eixos de §3.1: `REFERS TO researcher AS collected_from` (proveniência, n:1, hoje) ≠ `REFERS TO researcher AS authored` (autoria, n:n, quando houver dado resolvido) ≠ `AS founded` (organização). Decisão fina adiada para a Etapa 4 — o default `[:REFERS_TO]{entity}` funciona sem ela.

O nó reificado **nasce só de `IDENTIFIES`** — a identidade tem dono único. `REFERS TO` órfão não cria nó stub (fica warning).

**Traversal multi-hop** — "posts LinkedIn de pesquisadores com publicações em IA que fundaram startups do setor X" — é **Cypher nativo do usuário** sobre os nós reificados, não uma feature nova. Forçar isso num parâmetro de CLI reinventaria Cypher pela metade — não se constrói.

`synesis-graph` já constrói nós `Source` com `source_fields` como propriedades dinâmicas ([core.py:121](../../synesis-graph/synesis_graph/core.py#L121)) e já grava no Neo4j; a CLI Click já aceita `--project` ([cli.py:230](../../synesis-graph/synesis_graph/cli.py#L230)). Aceitar múltiplos `--project` + reificar é aditivo.

---

## 8. Comparação das abordagens

| | `STUDY`/master | `--link "k1->k2"` | `REFERENCE ON TEMPLATE` | **`IDENTIFIES`+`REFERS TO`** |
|---|---|---|---|---|
| n:1 / n:n | ✅ (SHARED/BRIDGE) | ❌ só 1:1 | ✅ | ✅ |
| Carga do LSP | ❌ agregado pesa | ✅ | ✅ | ✅ (CLI-only) |
| Ligação versionada | ✅ | ❌ ad-hoc | ✅ | ✅ (no template) |
| Projeto nomeia o outro? | — | não | ⚠️ sim | **não** |
| Adicionar corpus novo | editar `STUDY` | novo `--link` | ⚠️ editar hub | **só criar `REFERS TO`** |
| Termo legível p/ pesquisador qualitativo | — | — | ⚠️ colide c/ bibliografia | ✅ verbal, discursivo |

---

## 9. Pontos de inserção no código (verificados)

| Camada | Mudança | Custo / risco |
|---|---|---|
| **Gramática — modificadores** ([synesis.lark:161](../synesis/grammar/synesis.lark#L161)) | tokens `KW_IDENTIFIES`/`KW_REFERS`/`KW_TO` + 2 alternativas em `field_props`, análogas a `KW_SCOPE`. Tokens **livres** (verificado). `KW_TO` exige lookahead de fronteira `(?![\p{L}\p{N}_-])`, como `KW_TOPIC` | Trivial — aditivo |
| **Gramática — `ON BIBLIOGRAPHY`** ([synesis.lark:132](../synesis/grammar/synesis.lark#L132)) | **nova alternativa de campo único** em `requirement_clause`: `KW_REQUIRED field_key KW_ON KW_BIBLIOGRAPHY` (idem `OPTIONAL`), **separada** da alternativa que aceita lista — evita a ambiguidade de `ON` numa lista multi-campo (§2.3). `KW_BIBLIOGRAPHY` **já existe** (reuso); só `KW_ON` é novo | Trivial — aditivo |
| **Gramática — `INCLUDE SHARED`** ([synesis.lark:89-90](../synesis/grammar/synesis.lark#L89)) | `include_type` (hoje `KW_BIBLIOGRAPHY \| KW_ANNOTATIONS \| KW_ONTOLOGY`) ganha alternativa opcional `KW_SHARED? KW_ONTOLOGY`. Só `KW_SHARED` é novo; **restrito a `ONTOLOGY`** (não `KW_SHARED KW_BIBLIOGRAPHY`) | Trivial — aditivo |
| **AST** ([nodes.py:90](../synesis/ast/nodes.py#L90)) | classe real é `FieldSpec` (campos atuais verificados: `name, type, scope, format, description, values, relations, arity, guidelines, location`). Add `identifies`, `refers_to` (`Optional[str]`, default `None`) e `value_origin` (`"document"`\|`"bibliography"`, default `"document"`) + entradas no `to_dict()`. Defaults preservam o baseline de testes | Trivial |
| **transformer.py** | métodos de `field_props` e de `requirement_clause` (para `ON BIBLIOGRAPHY`) setam os campos | Baixo |
| **Validação / erros** | Novos erros com **número na sequência de `results.py`** e **mensagem dual** (`to_diagnostic`/`to_cli_line`): `DuplicateIdentityValue`, `DuplicateEntityOwner`, `TypeMismatchInLinkage` (tipos divergentes na mesma entidade), conflito SOURCE×`.bib`, campo `ON BIBLIOGRAPHY` ausente no `.bib`, INFO de referência externa, warning de quase-casamento (difere só em caixa). `REFERS TO`/`IDENTIFIES` válidos em campo SOURCE cujo valor venha do texto **ou** de `ON BIBLIOGRAPHY`; em `ITEM`/`ONTOLOGY` → erro | Baixo — é o ganho |
| **json_export.py** | schema **v3.1 aditivo** (anotações `identifies`/`refers_to`, seção `links`); teste explícito de que consumidor v3.0 ignora as chaves novas | Baixo |
| **CLI `compile`** ([cli.py:367-376](../synesis/cli.py#L367)) | `@click.argument` passa a `nargs=-1`, mas o corpo atual (~130 linhas) é **extraído verbatim** para `_compile_single(project, ...)` e `compile` vira **dispatcher fino**: `len(projects) == 1` → chama `_compile_single` (byte-idêntico — é o mesmo código); `> 1` → nova rotina `_link_projects(...)`. Mantém o modelo `compile p1 p2` do doc sem tocar a lógica de 1 projeto. Sem descoberta automática — só a mensagem INFO genérica | Baixo (dispatch isola o risco) |
| **paths.py** | `resolve_include(project_dir, raw)` ([paths.py:126](../synesis/parser/paths.py#L126)) ganha param opcional **`shared: bool = False`**; quando `True`, pula a checagem `is_within` ([paths.py:141](../synesis/parser/paths.py#L141)). **11 call sites** (compiler.py ×6, lsp_adapter.py ×5); o `IncludeNode` **já carrega `include_type`** (verificado), então só os **2 sites de ontologia** (compiler.py:258 via `_collect_include_paths(..., "ONTOLOGY")`; lsp_adapter.py:673) passam `shared=` conforme a keyword — os outros 9 ficam **byte-idênticos** pelo default. `INCLUDE ONTOLOGY` sem `SHARED` → `ESCAPES_PROJECT` intacto. `gitnexus_impact` em `resolve_include` obrigatório antes de tocar (11 dependentes) | Baixo — default seguro, mas compartilhado |
| **synesis-graph** | múltiplos `--project`; reificação em nós+arestas | Médio |

Um `.syn`/`.synp` sem os modificadores compila exatamente como hoje.

---

## 10. Plano de implementação

Ordenado para entregar valor cedo; `IDENTIFIES` sozinho já é útil (validação de unicidade) e é pré-requisito de `REFERS TO`.

### Etapa 1 — `IDENTIFIES` + unicidade (core, isolado)
Gramática (`KW_IDENTIFIES`, `field_props`), AST (`identifies` em `FieldSpec`), transformer, validação de unicidade (`DuplicateIdentityValue`, com número e mensagem dual), anotação no JSON (v3.1).
**Aceite:** template com `IDENTIFIES researcher` parseia; corpus com valor duplicado → erro; JSON anota o campo; consumidor v3.0 ignora as chaves novas (teste explícito); baseline de testes verde + novos.
**Repos:** `synesis`.

### Etapa 2 — `REFERS TO` + `ON BIBLIOGRAPHY` + link step na CLI
Gramática (`KW_REFERS`/`KW_TO` com lookahead; nova alternativa de campo único `KW_REQUIRED field_key KW_ON KW_BIBLIOGRAPHY` em `requirement_clause`, §2.3), AST (`refers_to`, `value_origin`), transformer. CLI: `nargs=-1`; 1 arg = caminho atual intacto; N args = link step (resolve rótulo+valor sobre a visão unificada por bibref, qualifica bibrefs por alias, valida `DuplicateEntityOwner` e `TypeMismatchInLinkage`, reporta arestas, órfãos e quase-casamentos, gera pacote §6). Compilação isolada emite o **INFO genérico** no lado `REFERS TO`.
**Aceite:** isolado emite INFO; junto resolve n:1; tipos divergentes → `TypeMismatchInLinkage`; órfão que difere só em caixa → warning de quase-casamento (sem fundir); bibref repetido entre membros (caso real linkedin/posts) não colide; caminho de arg único byte-idêntico; baseline de testes verde.
**Repos:** `synesis`.

### Etapa 3 — `INCLUDE SHARED ONTOLOGY` (ontologia externa autorizada)
Gramática (`KW_SHARED` opcional em `include_type`, só antes de `KW_ONTOLOGY`); `resolve_include` ganha `shared: bool = False` e pula `is_within` quando `True` (aceita rede/drive/`..`) — **só os 2 call sites de ontologia** (compiler.py:258, lsp_adapter.py:673) passam a keyword adiante, os outros 9 sites ficam byte-idênticos pelo default; `INCLUDE ONTOLOGY` comum mantém `ESCAPES_PROJECT`; `INCLUDE SHARED` com tipo ≠ ontologia → `SharedOnlyForOntology`. **Sem `.synstudy`, sem descoberta** — a mensagem INFO da Etapa 2 permanece genérica. Rodar `gitnexus_impact` em `resolve_include` antes de tocar.
**Aceite:** `INCLUDE SHARED ONTOLOGY "../shared/ontologia.syno"` resolve; o mesmo em `\\rede\...`/`Z:/...` resolve; `INCLUDE ONTOLOGY "../shared/..."` (sem `SHARED`) continua `ESCAPES_PROJECT` byte-idêntico; `INCLUDE SHARED BIBLIOGRAPHY` → erro; testes de contenção existentes verdes.
**Repos:** `synesis`.

### Etapa 4 — Reificação no synesis-graph
Múltiplos `--project`; nós `:Researcher`/`:Company` a partir de `IDENTIFIES`; arestas a partir de `REFERS TO` (default `[:REFERS_TO]{entity}`; avaliar açúcar `AS <relação>`).
**Aceite:** grafo Neo4j unificado por entidade; query multi-hop de exemplo retorna; baseline de testes do graph verde.
**Repos:** `synesis-graph`.

### Etapa 5 — LSP + extensão VSCode (watcher multi-root)
**Reintroduz `FileSystemWatcher`** observando os alvos dos `INCLUDE SHARED ONTOLOGY` — o `onDidSave` atual ([extension.js:681](../../synesis-vscode/extension.js#L681)) não cobre arquivos não-abertos, e os watchers foram removidos sob a premissa (agora inválida) de projeto auto-contido (§2.2). Exige um **índice reverso** `alvo→projetos que o incluem` para saber quais invalidar. Debounce reaproveitável do histórico (300ms).
**Aceite:** editar a ontologia compartilhada fora do editor dispara revalidação nos projetos que a incluem; projeto sem `INCLUDE SHARED`, comportamento atual intacto; testes de LSP verdes.
**Repos:** `synesis-vscode`, `synesis-lsp`.

### Dependências

```
Etapa 1 ──> Etapa 2 ──┬──> Etapa 4  (reificação consome o JSON v3.1 do link step)
                      │
                      └──> Etapa 3 ──> Etapa 5  (watcher observa os alvos de INCLUDE SHARED)
```

- **Etapa 3** (`INCLUDE SHARED ONTOLOGY`) é independente das Etapas 1–2 (só toca gramática + `paths.py`) e pode começar em paralelo. Não há mais sub-metade de "descoberta" — foi removida (§5).
- **Etapas 4 e 5** são independentes entre si após seus pré-requisitos.
- `IDENTIFIES` (Etapa 1) entrega valor sozinho — a validação de unicidade — mesmo que nada mais seja implementado.

---

## 11. Não-regressão

- **Aditivo:** um projeto sem `IDENTIFIES`/`REFERS TO` compila idêntico ao de hoje. O **baseline de testes** do core e do `synesis-graph` (coletado com `pytest --collect-only` no início de cada etapa) é o invariante — nenhum teste existente pode quebrar.
- **Fail-safe:** onde os modificadores encontram código legado, a comunicação é explícita (INFO/warning com número e mensagem dual), nunca corrupção silenciosa.
- **LSP intocado:** a agregação vive só na CLI e no graph; o LSP não carrega agregado. O único código compartilhado tocado é `paths.py` (Etapa 3), com o relaxamento condicionado à keyword `INCLUDE SHARED` — `INCLUDE ONTOLOGY` comum fica byte-idêntico.
- **JSON:** v3.1 estritamente aditivo sobre v3.0; consumidores existentes (synesis-graph pré-Etapa-4) ignoram as chaves novas — coberto por teste.

---

## 12. Protocolo do implementador

### 12.1 Registro de decisões fechadas (não reabrir sem motivo novo)

| # | Decisão | Onde está o porquê |
|---|---|---|
| D1 | Projetos independentes; **nenhuma** unidade de compilação agregada (sem `STUDY`) | §1 |
| D2 | Agregação é **modo de CLI** (N args) e do graph; **LSP nunca carrega agregado** | §5 |
| D3 | Keywords `IDENTIFIES` / `REFERS TO` (não `KEY`/`REFERENCE`, não `RELATION`), **lidas como PK/FK**; **não** colapsar num verbo só (perde o lado dono e a unicidade); OWL só como nota de exportação, não fundamento da validação | §2.3, §2.4 |
| D4 | Casamento por **rótulo de entidade**, nunca por nome de arquivo/template | §1, §2.3 |
| D5 | Rótulo tem **dono único** (`DuplicateEntityOwner`); identidade cross-esquema = hub `REFERS TO` periferia | §4 |
| D6 | Origem de valor via `ON BIBLIOGRAPHY` no `SOURCE FIELDS` (não `SCOPE` novo, não `SCOPE SOURCE` forçado) | §2.3 |
| D7 | Igualdade **exata** pós-trim; **normalização automática rejeitada**; quase-casamento = warning, nunca fusão | §4 |
| D8 | Tipos idênticos por entidade (`TypeMismatchInLinkage`, erro duro) | §4 |
| D9 | Compilação isolada: **INFO** só no lado `REFERS TO`; **sem descoberta automática** — só mensagem genérica (Rev. 6) | §5 |
| D10 | Bibrefs locais ao membro, qualificados por alias no agregado | §4 |
| D11 | Nó reificado nasce **só** de `IDENTIFIES`; órfão não cria stub | §7 |
| D12 | Proveniência (n:1, hoje) ≠ autoria (n:n, exige resolução de identidade upstream) | §3.1 |
| D13 | Escape de path autorizado por **`INCLUDE SHARED ONTOLOGY`** (declaração), **não** por âncora de pasta/ancestral comum/workspace (geometria de path não autoriza rede/drive). `INCLUDE ONTOLOGY` comum mantém `ESCAPES_PROJECT`; `SHARED` só para `ONTOLOGY`. `.synstudy` **eliminado** (Rev. 6) | §2.2 |
| D14 | Etapa 5 **reintroduz** `FileSystemWatcher` (nos alvos dos `INCLUDE SHARED`, com índice reverso `alvo→projetos`) — reversão consciente da remoção histórica | §2.2 |

### 12.2 Inventário de diagnósticos novos

Todos com número alocado na sequência de `results.py` e mensagem dual (`to_diagnostic`/`to_cli_line`):

| Diagnóstico | Severidade | Camada | Dispara quando |
|---|---|---|---|
| `DuplicateIdentityValue` | Erro | compilação do membro | dois SOURCEs do corpus com o mesmo valor de campo `IDENTIFIES` |
| conflito SOURCE×`.bib` | Erro | compilação do membro | campo com valor divergente nas duas fontes |
| campo `ON BIBLIOGRAPHY` ausente | Erro | compilação do membro | campo `REQUIRED ... ON BIBLIOGRAPHY` sem valor no `.bib` do bibref |
| modificador em `ITEM`/`ONTOLOGY` | Erro | compilação do membro | `IDENTIFIES`/`REFERS TO` fora de campo SOURCE |
| referência externa declarada | **INFO** | compilação isolada | projeto tem `REFERS TO` (§5; nunca warning) |
| `DuplicateEntityOwner` | Erro | link step | dois membros declaram `IDENTIFIES` do mesmo rótulo |
| `TypeMismatchInLinkage` | Erro | link step | `TYPE` divergente entre campos da mesma entidade |
| `REFERS TO` órfão | Warning | link step | valor sem `IDENTIFIES` correspondente |
| quase-casamento | Warning | link step | órfão que casaria sob normalização (caixa/invisíveis) — detecta, **não** liga |
| `ESCAPES_PROJECT` (mantido) | Erro | resolução de include | `INCLUDE ONTOLOGY` (sem `SHARED`) com path que escapa do projeto — comportamento atual intacto |
| `SharedOnlyForOntology` | Erro | resolução de include | `INCLUDE SHARED` com tipo ≠ `ONTOLOGY` (`BIBLIOGRAPHY`/`TEMPLATE`/`ANNOTATIONS`) |

### 12.3 Protocolo de execução por etapa

1. **Antes de editar qualquer símbolo** dos repos `synesis`/`synesis-vscode`: rodar `gitnexus_impact` sobre o símbolo (obrigação do CLAUDE.md dos repos — ex.: `FieldSpec`, `compile` da CLI, `resolve_include`). Reportar blast radius antes de tocar.
2. **Fixtures de teste** seguem o padrão existente `tests/fixtures/T##-Nome/` (ex. `T06-Project-Structure`) — cada erro novo ganha uma fixture mínima que o dispara e uma que passa.
3. **Suítes como gate de etapa:** coletar o baseline (`pytest --collect-only`) **no início** da etapa; `synesis` e `synesis-graph` verdes **antes e depois** de cada etapa; nenhum teste existente é editado para passar.
4. **Ordem dentro de cada etapa:** gramática → AST/transformer → validação → export → CLI — cada camada com seus testes antes da próxima.
5. **Corpus real como teste de aceitação final** (Etapas 2 e 4): `Dados_Lattes` + `Dados_Abstracts` do caso Quinto Andar — 7 arestas `researcher` esperadas; bibref compartilhado linkedin/posts não colide.

### 12.4 Armadilhas conhecidas (não recair)

- **Não** normalizar valores na comparação (nem lowercase, nem Unicode NFC silencioso) — D7; a heurística só pode *detectar suspeita* (warning), nunca *fundir*.
- **Não** ligar co-autoria pelo campo `author` (texto livre) — é o fuzzy por nome proibido; autoria n:n espera o dado resolvido (§3.1).
- **Não** deixar o caminho de 1 argumento da CLI mudar nem um byte — é o risco real do `nargs=-1` (§9).
- **Não** relaxar `..` sem a keyword `SHARED` — `paths.py` serve também ao LSP; `INCLUDE ONTOLOGY` comum mantém `ESCAPES_PROJECT` byte-idêntico (D13). E **não** derivar contenção de geometria de path (âncora/ancestral/workspace): não autoriza rede nem outro drive.
- **Não** confiar em `onDidSaveTextDocument` para a ontologia externa — só dispara para arquivos abertos; o watcher da Etapa 5 é obrigatório (D14).
- **Não** derivar heurísticas de proximidade para deduplicação em nenhuma camada nova — lição documentada do ecossistema (bug CHAIN last-occurrence-only): deduplicação é sempre por chave exata.
