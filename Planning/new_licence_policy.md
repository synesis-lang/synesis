# Estudo de Política de Licenciamento — MIT → AGPL-3.0-only WITH Synesis-data-output-exception

**Data:** 2026-06-21
**Status:** Em avaliação (decisão de política, não de engenharia)
**Escopo:** ecossistema Synesis (core + pacotes derivados)

---

## 1. Pergunta

Avaliar a viabilidade de mudar a licença do compilador Synesis de **MIT** para **`AGPL-3.0-only WITH Synesis-data-output-exception`**.

A motivação implícita: garantir que melhorias ao *compilador* permaneçam abertas (copyleft forte da AGPL, que cobre inclusive uso em rede/SaaS), **sem** onerar os *dados de pesquisa* gerados pelos usuários (a exceção de output).

---

## 2. Estado Atual

| Pacote | Licença atual |
|---|---|
| synesis (core) | MIT |
| synesis-lsp | MIT |
| synesis-graph | MIT |
| synesis-coder | não declara licença explícita (**verificar**) |
| synesis-explorer | (VSCode/JS — verificar `package.json`) |
| zotero-synesis-export | (JS — verificar) |

**Copyright:** Christian Maciel De Britto (autor declarado no `LICENSE` do core).

---

## 3. Viabilidade Jurídica — VIÁVEL

### 3.1 Titularidade

O autor detém o copyright integral (autor único declarado). Pode relicenciar livremente:

- MIT é permissiva e **não impede** o relicenciamento de versões futuras.
- Versões **já publicadas** sob MIT permanecem MIT (a licença concedida é irrevogável para aqueles releases), mas isso **não impede** que a **v0.6.0+** adote AGPL.
- Quem já obteve uma cópia MIT continua com os direitos MIT sobre aquela cópia — não é possível "recolher" a licença antiga, apenas mudar a licença dali em diante.

### 3.2 Compatibilidade de Dependências (verificado)

| Dependência | Licença | Compatível como upstream de AGPL-3.0? |
|---|---|---|
| lark | MIT | ✅ |
| bibtexparser | LGPLv3 or BSD | ✅ |
| regex | Apache-2.0 AND CNRI-Python | ✅ |
| click | BSD-3-Clause | ✅ |
| openpyxl | MIT | ✅ |

Todas permissivas ou LGPL — **todas podem ser incorporadas por um projeto AGPL-3.0**. Nenhum bloqueador. Apache-2.0 é compatível com GPLv3/AGPLv3 na direção Apache→AGPL (o inverso não vale, mas não é o caso aqui).

### 3.3 A Exceção de Output ("Synesis-data-output-exception") — NECESSÁRIA

Este é o ponto central. AGPL-3.0 "pura" poderia ser interpretada como **contaminando a saída** do compilador (o JSON/CSV/Excel/grafo gerado a partir das anotações do usuário). Isso afastaria pesquisadores que não querem que seus *dados de pesquisa* fiquem sujeitos à AGPL.

A exceção deve declarar explicitamente, em linguagem análoga à **GCC Runtime Library Exception** ou à **Bison parser exception**, que:

> "A saída produzida pela execução do compilador Synesis sobre arquivos de entrada do usuário (`.syn`/`.synt`/`.synp`/`.syno`) — incluindo artefatos JSON, CSV, Excel, grafo e datasets — NÃO é considerada obra derivada do compilador e não fica sujeita aos termos da AGPL. O usuário detém todos os direitos sobre seus dados de entrada e sobre a saída gerada."

Sem essa exceção, a adoção da AGPL seria **contraproducente** para uma ferramenta de pesquisa acadêmica.

**Precedentes a espelhar:**
- **GCC Runtime Library Exception** (FSF) — o caso canônico: o código gerado pelo GCC não vira GPL por causa das bibliotecas de runtime.
- **Bison parser exception** — o parser gerado pelo Bison não herda a GPL do Bison.
- **GMP / Classpath exception** — modelo de redação para "linking exception".

A redação deve ser feita ou revisada por alguém com competência jurídica em licenças de software livre, ou adaptada cuidadosamente de um dos textos acima (que são considerados sólidos e testados).

---

## 4. Riscos e Considerações Práticas

| Item | Avaliação |
|---|---|
| **Ecossistema:** synesis-lsp/graph importam `synesis` como biblioteca | AGPL é "viral" sobre obras derivadas e linkagem. synesis-lsp/graph passariam a precisar ser AGPL também (ou compatível). **Decidir se o ecossistema inteiro migra ou só o core.** |
| **synesis-explorer (VSCode, JS)** | Consome o core via LSP (processo separado, JSON-RPC). A fronteira de processo geralmente **NÃO** dispara contaminação AGPL — comunicação por protocolo entre processos distintos é o caso clássico de não-derivação. Confirmar com a redação da exceção e, se possível, declaração explícita. |
| **synesis-coder** | Importa `synesis` + `anthropic`/`openai`. Se migrar para AGPL, verificar compatibilidade dos SDKs (geralmente MIT/Apache — OK). |
| **Contribuições externas** | Um CLA (Contributor License Agreement) pode ser necessário se houver contribuidores além do autor, para preservar a capacidade de relicenciar no futuro. Atualmente parece autor único — confirmar via histórico git. |
| **PyPI / empacotamento** | Trocar `license = "MIT"` → `license = "AGPL-3.0-only WITH Synesis-data-output-exception"` em `pyproject.toml`; substituir o arquivo `LICENSE`; adicionar arquivo de texto da exceção. |
| **Identificador SPDX** | SPDX aceita expressões `WITH` apenas para **exceções registradas** na lista oficial. Uma exceção *custom* (`Synesis-data-output-exception`) **não está** na lista SPDX — exigirá `LicenseRef-` (ex.: `AGPL-3.0-only WITH LicenseRef-Synesis-data-output-exception`) ou texto livre no campo `license`. **Verificar a forma exata aceita pelos validadores de metadados (twine/PyPI).** |
| **Reversibilidade** | Uma vez publicado sob AGPL no PyPI, esse release é irrevogável. A decisão deve ser deliberada — não há "desfazer" para versões publicadas. |
| **Adoção** | AGPL pode reduzir adoção corporativa (algumas empresas proíbem AGPL por política). Para uma ferramenta de pesquisa acadêmica, o impacto tende a ser menor, mas é um trade-off real a ponderar. |

---

## 5. Recomendação

**Viável e defensável** para uma ferramenta de pesquisa cujo autor deseja garantir que melhorias ao *compilador* permaneçam abertas, sem onerar os *dados* dos pesquisadores.

A combinação AGPL + exceção de output é o desenho correto para esse objetivo: protege o software, libera os dados.

---

## 6. Pré-requisitos Antes de Executar

Status após verificação empírica (2026-06-21):

1. ⏳ **Redigir o texto formal da exceção** — espelhar a GCC Runtime Library Exception; revisar juridicamente. *(Tarefa de redação — não automatizável.)*

2. ✅ **Escopo VERIFICADO — deve ser o ecossistema Python inteiro.** Os três pacotes importam o core por linkagem Python (mesmo processo), confirmado por inspeção de código + `pyproject.toml`:
   | Pacote | Dependência | Imports |
   |---|---|---|
   | synesis-lsp | `synesis>=0.5.5` | `from synesis.ast.nodes`, `.compiler`, `.results`, … |
   | synesis-graph | `synesis>=0.5.5` | `import synesis`, `from synesis` |
   | synesis-coder | `synesis>=0.5.5` | `from synesis.ast.nodes`, `.exporters.alpaca_export`, … |

   Como AGPL é copyleft sobre obras derivadas e a linkagem Python é no mesmo processo, **se o core migrar para AGPL, os três precisam migrar junto** (ou tornar-se incompatíveis). `synesis-explorer` (VSCode/JS) consome só via LSP (processo separado) — fica de fora da contaminação.

3. ⚠️ **SPDX VERIFICADO — a sintaxe `WITH` NÃO funciona para a exceção custom.** Validação com a lib oficial `license-expression`:
   ```
   AGPL-3.0-only WITH Synesis-data-output-exception   → INVÁLIDO ("Unknown license key")
   AGPL-3.0-only WITH GCC-exception-3.1               → VÁLIDO (exceção registrada SPDX)
   AGPL-3.0-only AND LicenseRef-Synesis-data-output-exception → sintaxe VÁLIDA (PEP 639)
   ```
   **A operação `WITH` é reservada a exceções da lista oficial SPDX.** Uma exceção custom não pode usá-la. **Caminho correto (PEP 639 / `packaging` ≥ 24):** declarar como
   ```toml
   license = "AGPL-3.0-only AND LicenseRef-Synesis-data-output-exception"
   ```
   e incluir o texto da exceção via `license-files`. O nome conceitual "AGPL-3.0-only WITH Synesis-data-output-exception" permanece válido em prosa/README, mas o **identificador de metadados** deve usar `AND LicenseRef-`.

4. ✅ **Contribuidores VERIFICADO — autor único em todos os 6 repos.** `git log --all` em synesis, synesis-lsp, synesis-graph, synesis-coder, synesis-explorer, zotero-synesis-export retorna **um único autor**: `Dr. Christian De Britto <chriseana@gmail.com>`. **Nenhum CLA necessário**; relicenciamento livre de todos os repos.

5. ⏳ **Avaliar impacto de adoção** — confirmar que o público-alvo (pesquisadores, universidades) não é afetado por políticas anti-AGPL. *(Decisão de produto — não automatizável.)*

**Verificação adicional — deps extras do synesis-coder (compatibilidade AGPL):** `anthropic` (MIT), `openai` (Apache-2.0), `click` (BSD-3-Clause) — todas ✅ compatíveis como upstream de AGPL. Sem bloqueador.

---

## 7. Arquivos Afetados (se aprovado)

| Arquivo | Mudança |
|---|---|
| `LICENSE` | Substituir texto MIT pelo texto AGPL-3.0 |
| `LICENSE.exception` (novo) | Texto formal da Synesis-data-output-exception |
| `pyproject.toml` | Campo `license = "AGPL-3.0-only AND LicenseRef-Synesis-data-output-exception"` (PEP 639 — **não** usar `WITH`, ver §6.3) + `license-files` apontando para o texto da exceção |
| Headers de arquivos (opcional) | Atualizar boilerplate de licença |
| `README.md` | Seção de licença |
| synesis-lsp / synesis-graph / synesis-coder | Espelhar tudo acima **se o escopo for o ecossistema** |
| synesis-explorer (`package.json`) | Atualizar campo `license` se aplicável |

---

## 8. Conclusão

Não há **bloqueador jurídico ou técnico**. A decisão é de **política do projeto**:

- O autor pode relicenciar (titularidade integral).
- As dependências são compatíveis.
- A exceção de output é o elemento essencial e tem precedentes sólidos (GCC/Bison).

As únicas pendências reais são **decisões** (escopo do ecossistema, redação da exceção, validade do identificador SPDX) — não impedimentos. Recomenda-se tratar em **ciclo próprio**, desacoplado de releases técnicos, a menos que se queira marcar a virada de licença junto com uma virada de versão significativa (ex.: 0.6.0 ou 1.0.0).

---

## 9. Varredura Completa do Ecossistema — Recomendações por Módulo

**Data:** 2026-06-22  
**Escopo:** Todos os repositórios do ecossistema (varredura de `pyproject.toml`, `package.json`, `LICENSE` e dependências transitivas via `pip show` / `node_modules`)

### 9.1 Mapa de Dependências e Compatibilidade

| Dependência | Licença | Compatível com AGPL-3.0? |
|---|---|---|
| `lark` | MIT | ✅ |
| `bibtexparser` | LGPLv3 OR BSD | ✅ (use cláusula BSD; LGPL é upstream válido de AGPL) |
| `regex` | Apache-2.0 | ✅ |
| `click` | BSD-3-Clause | ✅ |
| `openpyxl` | MIT | ✅ |
| `pygls` | Apache-2.0 | ✅ |
| `lsprotocol` | MIT | ✅ |
| `neo4j` (driver oficial) | Apache-2.0 | ✅ |
| `anthropic` | MIT | ✅ |
| `openai` | Apache-2.0 | ✅ |
| `tenacity` | Apache-2.0 | ✅ |
| `graphqlite` | MIT | ✅ |
| `vscode-languageclient` | MIT | N/A (JS) ✅ |
| `bibtex-parse-js` | MIT | N/A (JS) ✅ |

**Conclusão:** Nenhuma dependência usa GPL-2.0-only, LGPL-2.0-only ou licença proprietária. O stack inteiro é compatível com AGPL-3.0.

> **Nota sobre `bibtexparser`:** A versão 1.x declara "LGPLv3 OR BSD". Como `synesis` incorpora `bibtexparser` por importação dinâmica (não estática), a LGPL permite isso sem contaminar a licença do projeto. A cláusula "OR BSD" torna tudo ainda mais simples.

---

### 9.2 Tabela de Recomendações por Módulo

| Módulo | Função | Licença Atual | Licença Recomendada | Justificativa Estratégica | Pontos de Atenção |
|---|---|---|---|---|---|
| **`synesis`** (compilador) | Núcleo da DSL: parser, compilador, CLI, AST, linker | MIT | **AGPL-3.0-only AND LicenseRef-Synesis-data-output-exception** | Coração da linguagem. AGPL garante que melhorias ao compilador em servidores/SaaS voltem à comunidade. A data-output-exception impede contaminação dos dados de pesquisa gerados. | Mudança MIT→AGPL é irreversível para versões futuras; releases já publicados permanecerão MIT. Identificador SPDX deve usar `AND LicenseRef-` (não `WITH`) — ver §6.3. |
| **`synesis-lsp`** | Language Server Protocol: servidor LSP, diagnósticos, hover, completions | MIT | **AGPL-3.0-only AND LicenseRef-Synesis-data-output-exception** | Importa `synesis` no mesmo processo Python (`from synesis.ast.nodes`, `.compiler`, `.results`) — linkagem direta aciona o copyleft AGPL. Deve migrar junto com o core. | `pygls` (Apache-2.0): compatível. O LSP comunica-se com editores por JSON-RPC (processo separado) — a fronteira de processo protege editores proprietários de contaminação. |
| **`synesis-coder`** | Agente de codificação com LLMs (Anthropic/OpenAI): automação de anotações | **Sem LICENSE** | **AGPL-3.0-only AND LicenseRef-Synesis-data-output-exception** | Importa `synesis` no mesmo processo Python — linkagem direta aciona copyleft. **Urgente: criar arquivo `LICENSE`** (atualmente "todos os direitos reservados" de facto). SDKs `anthropic` (MIT) e `openai` (Apache-2.0) são compatíveis com AGPL. | Criar `LICENSE` imediatamente, independentemente da decisão final de licença. |
| **`synesis-graph`** | Pipeline para Neo4j / HTML: backend de exportação e visualização | MIT | **AGPL-3.0-only AND LicenseRef-Synesis-data-output-exception** | Importa `synesis` no mesmo processo (`import synesis`, `from synesis`) — linkagem direta aciona copyleft. Driver `neo4j` (Apache-2.0): compatível. | O backend Neo4j usa o driver oficial Apache-2.0: sem conflito. Backend HTML usa `graphqlite` (MIT): sem conflito. |
| **`synesis-explorer`** | Extensão VS Code: UI, tree views, syntax highlighting, integração LSP/coder | MIT | **MIT** (manter) | Consome compilador e LSP exclusivamente via processos externos (JSON-RPC/stdio IPC) — fronteira de processo não aciona copyleft AGPL. Manter MIT maximiza adoção: extensão é o ponto de entrada do usuário final. | Nunca fazer bundle do compilador ou LSP dentro do VSIX — manter como dependências externas instaladas via pip. `vscode-languageclient` e `bibtex-parse-js` são MIT: sem conflito. |
| **`synesis-docs`** | Documentação publicada (site HTML gerado via Quarto) | **Sem LICENSE** | **CC BY 4.0** | Documentação não é software — licenças de software são tecnicamente inadequadas para prosa e imagens. CC BY 4.0 é o padrão de facto para documentação técnica acadêmica: permite citação, tradução e redistribuição com atribuição. | **Urgente: adicionar `LICENSE` (CC BY 4.0) e nota no rodapé do site.** Verificar atribuição de imagens de terceiros. |
| **`synesis-docs-sources`** | Fontes Quarto (`.qmd`, `.scss`, templates, `.bib`) | **Sem LICENSE** | **CC BY 4.0** (conteúdo `.qmd`) + **MIT** (infra de build: `.scss`, `_quarto.yml`, scripts) | Arquivos de documento → CC BY 4.0. Infraestrutura de build → MIT (permite reuso como boilerplate por outros projetos Quarto sem restrições). Separação por tipo de artefato é padrão em projetos como The Turing Way e rOpenSci. | Documentar no `README.md` quais arquivos têm qual licença. Verificar a licença do `apa.csl` específico usado (CSL styles são tipicamente CC BY-SA — confirmar compatibilidade). |

---

### 9.3 Estratégia de Implementação (Ordem de Prioridade)

**Fase 1 — Urgente (repos sem LICENSE = "todos os direitos reservados"):**

1. **`synesis-coder`**: Criar `LICENSE` imediatamente (MIT provisório ou AGPL definitivo — qualquer um é melhor que ausência). Atualizar `pyproject.toml`.
2. **`synesis-docs`** e **`synesis-docs-sources`**: Criar `LICENSE` CC BY 4.0. Adicionar rodapé ao site gerado.

**Fase 2 — Mudança estratégica (migração AGPL do ecossistema Python):**

3. Redigir o texto formal da `Synesis-data-output-exception` (pendência §6.1 acima).
4. Aplicar em bloco nos 4 pacotes Python: `synesis`, `synesis-lsp`, `synesis-coder`, `synesis-graph`.
   - Substituir arquivo `LICENSE` em cada repo.
   - Adicionar arquivo `LICENSE.exception` com o texto da exceção.
   - Atualizar `pyproject.toml`: `license = "AGPL-3.0-only AND LicenseRef-Synesis-data-output-exception"` + `license-files = ["LICENSE", "LICENSE.exception"]`.
   - Atualizar `README.md` de cada repo com seção de licença.

**Fase 3 — Manutenção:**

5. **`synesis-explorer`**: Permanece MIT. Verificar que o `LICENSE` existente tem o ano correto (2026).

---

### 9.4 Diagrama do Ecossistema Licenciado

```
┌─────────────────────────────────────────────────────────────────┐
│  synesis-docs / synesis-docs-sources                            │
│  CC BY 4.0 (conteúdo .qmd) + MIT (build scripts)              │
└───────────────────────────┬─────────────────────────────────────┘
                            │ documenta
┌───────────────────────────▼─────────────────────────────────────┐
│  synesis-explorer (MIT)                                         │
│  VS Code Extension — ponto de entrada do usuário final          │
└──────┬──────────────────────────────────────┬───────────────────┘
       │ JSON-RPC / stdio (processo separado) │ CLI externa
┌──────▼──────────────────┐           ┌───────▼──────────────────┐
│  synesis-lsp            │           │  synesis-coder            │
│  AGPL-3.0 + exception   │           │  AGPL-3.0 + exception     │
└──────┬──────────────────┘           └───────┬──────────────────┘
       │ import Python (mesmo processo)       │ import Python
       └──────────────────┬────────────────────┘
                          │
             ┌────────────▼────────────────┐
             │  synesis (compilador)        │
             │  AGPL-3.0-only AND           │
             │  LicenseRef-Synesis-         │
             │  data-output-exception       │
             └────────────┬────────────────┘
                          │ import Python
             ┌────────────▼────────────────┐
             │  synesis-graph (AGPL-3.0    │
             │  + exception)               │
             │  backends: Neo4j, HTML      │
             └─────────────────────────────┘
```

> **Fronteira crítica:** `synesis-explorer` comunica-se com o ecossistema exclusivamente por processos externos (JSON-RPC com o LSP, chamada CLI ao coder). Essa fronteira de processo é o que permite manter o explorer em MIT enquanto o restante migra para AGPL.
