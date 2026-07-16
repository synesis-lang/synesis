# Estudo de Política de Licenciamento — MIT → AGPL-3.0 + Synesis-data-output-exception

**Data:** 2026-06-21 · **Última revisão:** 2026-07-14
**Status:** Em avaliação (decisão de política/negócio, não de engenharia)
**Escopo:** ecossistema Synesis (core + pacotes derivados)

> **Objetivo:** avaliar a mudança de licença do compilador Synesis de **MIT** para **AGPL-3.0** acrescida de uma **exceção de output** (`Synesis-data-output-exception`).
>
> A motivação: garantir que melhorias ao *compilador* permaneçam abertas (copyleft forte da AGPL, que alcança uso em rede/SaaS), **sem** onerar os *dados de pesquisa* gerados pelos usuários. A escolha da AGPL abre ainda a porta para um modelo comercial **dual-license** (ver §7).

---

## 1. Estado Atual

| Pacote | Licença atual | Observação |
|---|---|---|
| synesis (core) | MIT | — |
| synesis-lsp | MIT | `license-files` já presente |
| synesis-graph | MIT | sintaxe legada `license = {text = "MIT"}` (pré-PEP 639) |
| synesis-coder | **sem `LICENSE`** | "todos os direitos reservados" de facto (verificado 14/07) |
| synesis-vscode (ex-synesis-explorer) | MIT | permanece MIT (ver §4) |
| synesis-docs / -docs-sources | **sem `LICENSE`** | documentação — tratar como CC BY 4.0 (ver §6) |
| zotero-synesis-export | MIT (JS) | fora do escopo AGPL (processo separado) |

**Copyright:** Christian Maciel De Britto — **titular único** de todos os repos (verificado via `git log --all`; o único outro "autor" é o `dependabot`, que só faz bumps de versão, não obra autoral). Sem contribuidores externos → relicenciamento livre hoje.

---

## 2. Viabilidade Jurídica — VIÁVEL

**Titularidade.** O autor detém o copyright integral e pode relicenciar versões futuras livremente. MIT não impede isso. Versões **já publicadas** sob MIT permanecem MIT (a licença concedida é irrevogável para aqueles releases), mas nada impede a próxima versão adotar AGPL.

**Reversibilidade.** Uma vez publicado sob AGPL no PyPI, aquele release é irrevogável — a decisão deve ser deliberada.

**Dependências.** Todas compatíveis como upstream de AGPL-3.0 — mapa completo em §5. Nenhum bloqueador.

---

## 3. A Exceção de Output — NECESSÁRIA (✅ redigida)

AGPL-3.0 "pura" poderia ser interpretada como **contaminando a saída** do compilador (JSON/CSV/Excel/grafo gerados a partir das anotações). Isso afastaria pesquisadores que não querem que seus *dados* fiquem sujeitos à AGPL. A exceção resolve isso declarando que a saída **não** é obra derivada do compilador.

**Precedentes espelhados:** GCC Runtime Library Exception (caso canônico), Bison parser exception, Classpath exception.

**Status:** ✅ **Texto redigido** — `LICENSE.exception` v1.0, presente em `synesis/` e `synesis-coder/` (idênticos). Estrutura: additional permission sob a seção 7 da AGPLv3, com definições de *Input*, *Output* e *Synesis Runtime Material*.

> **Ponto não-óbvio resolvido na redação — "Synesis Runtime Material".** Verificação empírica dos exporters revelou que o backend **HTML de grafo** (`synesis-graph/templates/graph.html.tmpl`, ~40 KB) **embute JavaScript e CSS autorais do Synesis** no `.html` gerado. Sem tratamento explícito, esse output ficaria preso na AGPL (o output *contém* código-fonte do Synesis). A exceção resolve com uma cláusula de runtime — modelo GCC — que distingue **código injetado automaticamente pelo compilador** (coberto pela exceção; output livre) de **código copiado à mão do fonte do Synesis** (permanece AGPL). Isso é essencial para o dual-license (§7): sem ele, um cliente não poderia publicar o grafo HTML sob licença fechada.

**Pendência:** revisão jurídica do texto antes de publicar (recomendado, não bloqueador técnico) — em especial a fronteira "injeção automática vs. cópia deliberada" da cláusula de runtime.

> ⚠️ **Gatilho de aplicabilidade — o aviso é obrigatório.** O texto da exceção se aplica a arquivo "that **bears a notice** placed by the copyright holder stating that the file is governed by the AGPLv3 with this Exception". Ou seja: **sem o aviso, a exceção não se aplica a nada.** A implementação DEVE incluir esse aviso — no mínimo um bloco padrão no `README.md` e no topo do `LICENSE` de cada repo ("This program is distributed under the AGPL-3.0-only license with the Synesis Data-Output Exception; see LICENSE.exception"), idealmente também como header nos arquivos-fonte principais. Headers por arquivo deixam de ser "opcionais" — pelo menos um aviso por repo é condição de eficácia da exceção. Item incluído no checklist (§8).

---

## 4. Escopo do Ecossistema (✅ verificado — Python inteiro)

`synesis-lsp`, `synesis-graph` e `synesis-coder` importam o core por **linkagem Python no mesmo processo** (`from synesis…` / `import synesis`), confirmado por inspeção de código + `pyproject.toml`. Como AGPL é copyleft sobre linkagem, **se o core migrar para AGPL, os três migram junto** — não é opção deixá-los em MIT.

**`synesis-vscode` permanece MIT.** Consome o ecossistema *exclusivamente* via processos externos (JSON-RPC com o LSP, CLI ao coder). A fronteira de processo não aciona o copyleft AGPL — é o caso clássico de não-derivação.

> **Fronteira crítica:** nunca fazer *bundle* do compilador/LSP dentro do `.vsix`. Mantê-los como dependências externas instaladas via pip é o que preserva o `synesis-vscode` em MIT.

---

## 5. Mapa de Dependências e Compatibilidade (✅ verificado)

| Dependência | Licença | Compatível com AGPL-3.0? | Usado por |
|---|---|---|---|
| lark | MIT | ✅ | core |
| bibtexparser | LGPLv3 OR BSD | ✅ (importação dinâmica; LGPL é upstream válido) | core, coder |
| regex | Apache-2.0 | ✅ | core |
| click | BSD-3-Clause | ✅ | core, graph, coder |
| openpyxl | MIT | ✅ | core |
| pygls | Apache-2.0 | ✅ | lsp |
| lsprotocol | MIT | ✅ | lsp |
| neo4j (driver oficial) | Apache-2.0 | ✅ | graph |
| graphqlite | MIT | ✅ | graph |
| anthropic | MIT | ✅ | coder |
| openai | Apache-2.0 | ✅ | coder |
| tenacity | Apache-2.0 | ✅ | coder |

**Conclusão:** nenhuma dependência usa GPL-2.0-only, LGPL-2.0-only ou licença proprietária. O stack inteiro é compatível com AGPL-3.0. Apache-2.0 é compatível na direção Apache→AGPL (o inverso não vale, mas não é o caso).

> **Disciplina a manter (crítica para o dual-license, §7):** nenhuma dependência **GPL/AGPL de terceiros** na base comum. Todas as deps atuais são permissivas — o que permite fechar uma Enterprise Edition sem conflito. Introduzir uma dep copyleft de terceiros quebraria isso.

---

## 6. Identificador SPDX (✅ resolvido)

`WITH` só vale para exceções **registradas na lista oficial SPDX**. Uma exceção custom não pode usá-la — nem na forma `WITH LicenseRef-` (também inválida). A forma correta (PEP 639) usa `AND LicenseRef-`.

Validado empiricamente com `packaging` 24.2 — a lib que PyPI/setuptools/twine efetivamente usam no gate de build/publish:

```python
from packaging.licenses import canonicalize_license_expression
canonicalize_license_expression("AGPL-3.0-only WITH Synesis-data-output-exception")
# -> InvalidLicenseExpression: Unknown license exception
canonicalize_license_expression("AGPL-3.0-only AND LicenseRef-Synesis-data-output-exception")
# -> OK
```

**Identificador de metadados:**
```toml
license = "AGPL-3.0-only AND LicenseRef-Synesis-data-output-exception"
license-files = ["LICENSE", "LICENSE.exception"]
```

O nome conceitual "AGPL-3.0-only WITH Synesis-data-output-exception" permanece válido em prosa/README; só o campo de metadados exige `AND LicenseRef-`.

> **Nota para `synesis-docs` / `-docs-sources`:** documentação não é software. Recomenda-se **CC BY 4.0** para o conteúdo (`.qmd`), e MIT para a infra de build (`.scss`, `_quarto.yml`, scripts). Verificar a licença do `apa.csl` usado (CSL styles são tipicamente CC BY-SA). Pendência separada — não bloqueia a migração AGPL do core.

---

## 7. Dual-Licensing / Commercial Edition (modelo estilo MySQL)

**Pergunta:** o modelo AGPL + exceção suporta duas edições — Community (aberta) e Enterprise (comercial fechada)?

**Resposta: sim — e a AGPL é o *alicerce* desse modelo, não um obstáculo.**

### 7.1 Por que a AGPL habilita o dual-license

O modelo open-core da MySQL/Oracle depende de duas condições, ambas satisfeitas aqui:

1. **Titularidade integral** — o autor detém 100% do copyright (✅ verificado, §1). Como titular, **não está vinculado à própria licença**: pode distribuir a Community sob AGPL *e* vender a mesma base (ou um superset) a clientes sob licença comercial fechada.
2. **Uma licença aberta restritiva** — é justamente o rigor da AGPL que dá **valor** à licença comercial. Uma empresa que não pode/não quer cumprir a AGPL (ex.: rodar Synesis como SaaS sem abrir suas modificações) **paga** para escapar dela.

> **Por isso a migração MIT→AGPL é pré-requisito do modelo de negócio, não um custo.** Com MIT, uso comercial fechado já é gratuito — não haveria o que vender. É a AGPL que cria o produto comercial.

### 7.2 A exceção de output *ajuda* o modelo

A `Synesis-data-output-exception` é ortogonal ao dual-licensing e **remove atrito comercial**: clientes enterprise ficam tranquilos de que seus dados e artefatos gerados (incl. o grafo HTML, via cláusula de runtime — §3) não têm amarra AGPL, em qualquer edição. **Não precisa mudar** para o dual funcionar.

### 7.3 Deps permitem Enterprise fechada

Todas as dependências atuais são permissivas (§5) → a Enterprise pode ser fechada sem conflito. Manter a disciplina de **não introduzir dep GPL/AGPL de terceiros** na base comum.

### 7.4 ⚠️ Bloqueador: CLA antes do primeiro PR externo

Hoje o autor é titular único, então pode dual-licenciar livremente. **Mas contribuições externas erodem isso:** cada contribuidor detém o copyright do trecho dele, e o projeto só recebe os direitos que a política de inbound conceder.

- **Hoje** o `CONTRIBUTING.md` diz "contributions licensed under MIT" — inbound MIT é sublicenciável e, a rigor, não bloquearia o dual. Mas apoiar um negócio em *inbound=outbound implícito* é frágil (a "assinatura" é inferida, o escopo é discutível).
- **Após a migração**, se o `CONTRIBUTING.md` passar a dizer apenas "AGPL", o problema se torna agudo: contribuições chegariam licenciadas *só sob AGPL*, e o autor **não** poderia vendê-las sob licença comercial fechada sem permissão de cada contribuidor. O modelo dual "vazaria" a cada PR aceito.

A solução (mesma da MySQL/Oracle e da maioria dos projetos open-core) é um **CLA (Contributor License Agreement)**: todo contribuidor concede ao autor uma licença ampla o suficiente para relicenciar comercialmente. Modelo pronto em **§9**.

> **Janela e opcionalidade:** hoje, sem contribuidores externos, o projeto está seguro. A janela fecha no **primeiro PR externo aceito**. **Recomenda-se adotar o CLA incondicionalmente** — mesmo que a decisão dual ainda não esteja tomada — porque a decisão pode vir *depois* das primeiras contribuições, e obter cessões retroativas de contribuidores dispersos é caro, lento e às vezes impossível (contribuidor inalcançável = trecho a reescrever). O CLA preserva a opcionalidade a custo quase zero; abrir mão dele é irreversível na prática.

### 7.5 Marca ("Synesis") e entidade jurídica

Dois ativos que a AGPL **não** protege e dos quais um modelo open-core depende:

1. **Marca.** Nem a AGPL nem a exceção concedem direitos sobre o nome/logotipo "Synesis" — e é a marca que impede um fork de se apresentar como o produto oficial (é o que sustenta o negócio da MySQL, Grafana, etc.). Providências: (a) verificar disponibilidade e **registrar a marca** (INPI no Brasil; considerar classes de software/SaaS), lembrando que "Synesis" é palavra de uso corrente e há risco de colisão; (b) incluir nos READMEs uma nota de que a licença não concede direitos de marca.
2. **Entidade.** Hoje o titular é pessoa física. Para vender licenças Enterprise, será prudente constituir uma entidade e **ceder/licenciar a ela** o copyright e a marca. O CLA em §9 já prevê "successors and assigns" justamente para que as licenças dos contribuidores acompanhem essa transferência sem re-assinatura.

---

## 8. Checklist de Execução (quando aprovado)

Ordem recomendada. Escopo = ecossistema Python (`synesis`, `synesis-lsp`, `synesis-graph`, `synesis-coder`).

**Licença (core + derivados):**
- [x] Redigir `LICENSE.exception` (texto único) — **feito** em `synesis/` e `synesis-coder/`
- [ ] Replicar `LICENSE.exception` para `synesis-lsp/` e `synesis-graph/`
- [ ] `synesis-coder`: criar `LICENSE` (AGPL-3.0) — resolve também a lacuna "sem licença"
- [ ] `synesis`: substituir `LICENSE` (MIT → texto integral AGPL-3.0) + adicionar `LICENSE.exception`
- [ ] Em cada `pyproject.toml`: `license = "AGPL-3.0-only AND LicenseRef-Synesis-data-output-exception"` + `license-files = ["LICENSE", "LICENSE.exception"]`
- [ ] `synesis-graph`: migrar a sintaxe legada `{text = "MIT"}` → string SPDX no mesmo passo
- [ ] **Aviso de aplicabilidade da exceção** (condição de eficácia — ver §3): bloco padrão no `README.md` e no topo do `LICENSE` de cada repo declarando "AGPL-3.0-only with the Synesis Data-Output Exception (see LICENSE.exception)"; idealmente header também nos fontes principais
- [ ] Atualizar `README.md` (seção de licença) dos 4 repos, incl. nota de que a licença não concede direitos de marca (§7.5)
- [ ] Atualizar `CITATION.cff` do core — **atenção:** o schema CFF 1.2.0 valida `license` contra o enum SPDX; `LicenseRef-` custom tende a **falhar** no `cffconvert`. Usar `license: AGPL-3.0-only` e mencionar a exceção no `abstract`/notes (validar com `cffconvert --validate` antes de commitar)
- [ ] Atualizar `CONTRIBUTING.md` do core ("contributions licensed under MIT" → AGPL + exception, **junto com** a adoção do CLA — não deixar o CONTRIBUTING declarar inbound "AGPL puro" sem CLA, ver §7.4)

**CLA (recomendado incondicionalmente — ver §7.4):**
- [ ] Adotar o CLA (§9), referenciá-lo no `CONTRIBUTING.md` e configurar o bot (CLA Assistant / EasyCLA) **antes de aceitar qualquer PR externo** — independentemente de a decisão dual já estar tomada

**Marca e entidade (se dual-license avançar — ver §7.5):**
- [ ] Verificar disponibilidade e registrar a marca "Synesis" (INPI; classes de software/SaaS)
- [ ] Avaliar constituição de entidade e cessão de copyright + marca a ela

**Documentação (pendência paralela):**
- [ ] `synesis-docs` / `-docs-sources`: criar `LICENSE` CC BY 4.0 (não bloqueia a migração do core)

**Validação e publicação:**
- [ ] Validar os 4 `pyproject.toml` com `packaging.licenses.canonicalize_license_expression` + `twine check`
- [ ] Publicar os 4 pacotes **em bloco** (mesma janela), para não publicar `lsp`/`graph`/`coder` AGPL apontando para um `synesis` ainda MIT
- [ ] `synesis-vscode`: confirmar que permanece MIT (nenhuma ação de licença)

**Timing:** tratar em ciclo próprio, desacoplado de releases técnicos — ou casar a virada de licença com uma virada de versão significativa (ex.: 1.0.0).

---

## 9. Modelo de CLA (Contributor License Agreement)

> **Uso:** adotar **antes do primeiro PR externo, independentemente da decisão dual** (ver §7.4 — preserva a opcionalidade; a alternativa DCO não sustenta relicenciamento comercial). Baseado no **Apache Individual CLA v2.0** (modelo testado e amplamente aceito), adaptado para: (a) permitir relicenciamento comercial pelo titular; (b) estender as licenças a **sucessores e cessionários** (essencial se o copyright/marca migrarem para uma entidade — §7.5); (c) cobrir contribuições anteriores à assinatura; (d) prever aceite eletrônico via bot. **Requer revisão jurídica antes de entrar em vigor** — em particular a cláusula de lei aplicável (nº 9, marcada como placeholder). Para contribuidores que atuam por conta de empregador, é usual acompanhar de um *Corporate CLA* — omitido aqui; derivar do ICLA quando necessário.

```
Synesis Individual Contributor License Agreement ("Agreement"), v1.0

Thank you for your interest in contributing to the Synesis project
("Synesis") maintained by Christian Maciel De Britto ("the Maintainer",
which term includes the Maintainer's successors and assigns, including
any legal entity to which the Maintainer may transfer ownership or
stewardship of Synesis).

This Agreement documents the rights granted by contributors to the
Maintainer. It is for your protection as a contributor as well as the
protection of Synesis and its users; it does not change your right to use
your own contributions for any other purpose. By submitting a Contribution
to Synesis, You accept and agree to the following terms and conditions.
This Agreement applies to all Contributions You submit, whether submitted
before or after the date You accept this Agreement.

1. Definitions.

   "You" (or "Your") means the individual copyright owner who submits a
   Contribution to the Maintainer.

   "Contribution" means any original work of authorship, including any
   modifications or additions to an existing work, that is intentionally
   submitted by You to the Maintainer for inclusion in, or documentation
   of, any of the projects owned or managed by the Maintainer (the
   "Work"). "Submitted" means any form of electronic, verbal, or written
   communication sent to the Maintainer or its representatives, including
   but not limited to communication on electronic mailing lists, source
   code control systems, and issue tracking systems that are managed by,
   or on behalf of, the Maintainer for the purpose of discussing and
   improving the Work, but excluding communication that is conspicuously
   marked or otherwise designated in writing by You as "Not a
   Contribution."

2. Grant of Copyright License.

   Subject to the terms and conditions of this Agreement, You hereby grant
   to the Maintainer and to recipients of software distributed by the
   Maintainer a perpetual, worldwide, non-exclusive, no-charge,
   royalty-free, irrevocable copyright license to reproduce, prepare
   derivative works of, publicly display, publicly perform, sublicense,
   and distribute Your Contributions and such derivative works.

   You further grant the Maintainer the right to license Your Contribution
   under ANY license terms, including without limitation copyleft licenses
   (such as the GNU Affero General Public License), permissive licenses,
   and proprietary or commercial licenses. This includes the right to
   distribute Your Contribution as part of a dual-licensed offering (for
   example, an open-source Community edition and a commercially licensed
   Enterprise edition). You retain all right, title, and interest in and
   to Your Contributions; this grant is a license, not an assignment.

3. Grant of Patent License.

   Subject to the terms and conditions of this Agreement, You hereby grant
   to the Maintainer and to recipients of software distributed by the
   Maintainer a perpetual, worldwide, non-exclusive, no-charge,
   royalty-free, irrevocable (except as stated in this section) patent
   license to make, have made, use, offer to sell, sell, import, and
   otherwise transfer the Work, where such license applies only to those
   patent claims licensable by You that are necessarily infringed by Your
   Contribution alone or by combination of Your Contribution with the Work
   to which such Contribution was submitted. If any entity institutes
   patent litigation against You or any other entity (including a
   cross-claim or counterclaim in a lawsuit) alleging that Your
   Contribution, or the Work to which You have contributed, constitutes
   direct or contributory patent infringement, then any patent licenses
   granted to that entity under this Agreement for that Contribution or
   Work shall terminate as of the date such litigation is filed.

4. You represent that You are legally entitled to grant the above license.
   If Your employer(s) has rights to intellectual property that You create
   that includes Your Contributions, You represent that You have received
   permission to make Contributions on behalf of that employer, that Your
   employer has waived such rights for Your Contributions to the
   Maintainer, or that Your employer has executed a separate Corporate CLA
   with the Maintainer.

5. You represent that each of Your Contributions is Your original creation
   (see section 7 for submissions on behalf of others). You represent that
   Your Contribution submissions include complete details of any
   third-party license or other restriction (including, but not limited
   to, related patents and trademarks) of which You are personally aware
   and which are associated with any part of Your Contributions.

6. You are not expected to provide support for Your Contributions, except
   to the extent You desire to provide support. You may provide support
   for free, for a fee, or not at all. Unless required by applicable law
   or agreed to in writing, You provide Your Contributions on an "AS IS"
   BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
   implied, including, without limitation, any warranties or conditions of
   TITLE, NON-INFRINGEMENT, MERCHANTABILITY, or FITNESS FOR A PARTICULAR
   PURPOSE.

7. Should You wish to submit work that is not Your original creation, You
   may submit it to the Maintainer separately from any Contribution,
   identifying the complete details of its source and of any license or
   other restriction (including, but not limited to, related patents,
   trademarks, and license agreements) of which You are personally aware,
   and conspicuously marking the work as "Submitted on behalf of a
   third-party: [named here]".

8. You agree to notify the Maintainer of any facts or circumstances of
   which You become aware that would make these representations
   inaccurate in any respect.

9. Governing Law. This Agreement shall be governed by and construed in
   accordance with the laws of [the Federative Republic of Brazil], without
   regard to its conflict-of-law provisions, and the parties submit to the
   [courts of the Maintainer's domicile] for any dispute arising from this
   Agreement. [Placeholder — confirm jurisdiction and venue with counsel
   before adoption.]

Please sign: _______________________   Date: _______________

Name (printed): _____________________

GitHub username: ____________________

Email: ______________________________

---

Electronic acceptance. You may accept this Agreement electronically. Where
the Maintainer provides an automated mechanism for recording assent — such
as a CLA management bot integrated with the pull request workflow (for
example, CLA Assistant or EasyCLA) — Your affirmative action through that
mechanism (including a comment, checkbox, or authenticated confirmation
associated with Your submitted Contribution) constitutes Your signature and
has the same force and effect as a handwritten signature. The record kept
by that mechanism, associating Your identity with the accepted version of
this Agreement, shall be sufficient evidence of Your acceptance.
```

> **Nota (não faz parte do CLA):** a cláusula-chave para o dual-license é a **§2** — o direito de relicenciar sob quaisquer termos, incl. comercial. É ela que preserva a capacidade de manter uma Enterprise Edition fechada. A nota de aceite eletrônico acima permite usar CLA Assistant / EasyCLA sem papel físico.

---

## 10. Conclusão

Não há **bloqueador jurídico ou técnico** para a migração:

- Titularidade integral → o autor pode relicenciar (§1–2).
- Dependências compatíveis (§5) e identificador SPDX resolvido (§6).
- Exceção de output redigida, incl. a cláusula de runtime para o grafo HTML (§3).
- O modelo dual-license é **suportado** pela AGPL (§7) — a migração é, na verdade, seu pré-requisito.

As pendências reais são de **execução e decisão**, não impedimentos:

1. Aplicar a AGPL de fato (substituir `LICENSE`, editar `pyproject.toml`) nos 4 repos — §8 — **incluindo o aviso de aplicabilidade da exceção** (condição de eficácia, §3).
2. Adotar o CLA (§9) *antes* do primeiro PR externo, **independentemente da decisão dual** (§7.4) — este é o elemento mais sensível a tempo, porque abrir mão dele é irreversível na prática.
3. Revisão jurídica dos textos (exceção + CLA, incl. cláusula de lei aplicável) antes de publicar.
4. **Se o dual-license avançar:** registrar a marca "Synesis" e avaliar a constituição de entidade (§7.5) — a AGPL protege o código, não o nome.
5. Decisão de timing e de impacto de adoção (AGPL pode afastar alguns usos corporativos — trade-off menor para público acadêmico).
