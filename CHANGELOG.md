# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [0.9.0] - 2026-07-18

### Fixed

- **`DedentError` do Lark vazava cru pela API publica** (`synesis/parser/lexer.py`)
  - `parse_string()` capturava `UnexpectedToken` e `UnexpectedCharacters`, mas
    nao `DedentError`. Indentacao inconsistente — fechar um bloco numa coluna
    que nao alinha com nenhum nivel aberto — e erro comum de usuario e escapava
    sem passar pelo `error_handler` pedagogico: a CLI mostrava traceback de
    biblioteca e nenhum consumidor do ecossistema tratava o tipo.
  - Agora vira `SynesisSyntaxError` com mensagem explicativa e localizacao. O
    `DedentError` nao carrega linha/coluna, entao a posicao e recuperada
    re-tokenizando com `lex_tokens()` (que trunca no ponto da falha).
  - Encontrado por fuzzing de mutacao, nao por revisao — ver
    `tests/test_fuzz_robustness.py`.

### Added

- `synesis.lex_tokens(source)` — tokenizacao posicional tolerante a erro, com
  `LexToken` (type, value, line, column, end_line, end_column). Expoe o fluxo de
  tokens da gramatica para consumidores que precisam saber ONDE cada construto
  aparece: colorizacao semantica (LSP), navegacao, ferramentas de analise.

  Diferencas em relacao a `parse_string()`:
  - Nunca levanta excecao; retorna tokens parciais ate o ponto de falha e
    registra o truncamento em nivel `debug`.
  - Nao normaliza TABs (normalizar deslocaria as colunas: o editor conta um
    TAB como 1 caractere).

  Motivacao: substituir listas de keywords em regex reimplementadas nos
  consumidores, que divergiam da gramatica a cada construto novo. Ver
  `Planning/syntax_semantic_highlight.md`.

- **Ampliacao do protocolo de testes** — tres tecnicas complementares as
  fixtures curadas, que testam o que ninguem pensou em testar:

  - `tests/test_fuzz_robustness.py` (11 testes) — fuzzing de mutacao sobre
    fixtures reais, com seeds fixas. Trava o contrato: para qualquer entrada,
    `compile_string()` compila ou levanta `SynesisSyntaxError`, nunca excecao de
    biblioteca. Achou o vazamento de `DedentError` acima.
  - `tests/test_grammar_differential.py` (78 testes) — differential testing
    entre `synesis.lark` (fonte) e `synesis_standalone.py` (gerado). Previne o
    modo de falha de editar a gramatica sem regenerar o standalone, em que a
    suite fica verde e a mudanca simplesmente nao tem efeito. Compara assinatura
    de terminais (nome **e** padrao), conjunto de regras e tokenizacao de todas
    as fixtures.
  - `tests/test_error_coverage.py` (7 testes) — inventario do catalogo de
    erros. Uma auditoria encontrou 22 dos 69 codigos sem nenhum teste; quatro
    foram cobertos e o restante ficou travado por um teste-catraca que falha se
    a divida crescer. Documenta tambem o compartilhamento de `SYNESIS_E064` por
    tres classes distintas (ambiguidade de diagnostico conhecida).

## [0.8.1] - 2026-07-15

### Fixed

- **`--stats`, `--xls` e `--alpaca` eram ignorados em silêncio no passo de linkagem** (`synesis/cli.py`)
  - Reportado pelo usuário: `synesis compile p1.synp p2.synp --xls output.xls` terminava com exit 0 e nenhum arquivo `.xlsx` gerado, sem qualquer aviso. `_link_projects` recebia os três parâmetros mas nunca os usava — só `--json` e `--csv` estavam de fato implementados no link step.
  - `--stats` agora funciona: imprime as estatísticas de cada membro (`Sources`, `Items`, `Ontologies`, `Codes`, `Chains`) e o agregado da linkagem. Reaproveita `CompilationStats`, já calculado por membro durante a compilação isolada.
  - **Deduplicação da ontologia compartilhada no agregado:** `Sources`/`Items`/`Chains` são próprios de cada membro e agregam por soma; mas a ontologia é compartilhada (`INCLUDE SHARED ONTOLOGY`), então somar os contadores daria valor duplicado (ex.: `74 + 74 = 148` para uma única ontologia de 74 conceitos). O agregado agora deduplica pela união dos conjuntos de conceitos e rotula as linhas como `Shared ontology`/`Shared codes` quando há sobreposição entre membros. Sem sobreposição, mantém os rótulos comuns `Ontologies`/`Codes`.
  - `--xls` e `--alpaca` continuam **sem exportador** no link step (§6 do design: `SOURCE FIELDS` diverge entre membros, não há tabela/dataset único coerente), mas agora emitem um aviso explícito em vez de falhar silenciosamente — a lacuna vira comportamento visível, não uma armadilha.

### Documentation

- **Help da CLI documenta a compilação multiprojeto** (`synesis/cli.py`)
  - `synesis compile --help` (`_EPILOG_COMPILE`) ganhou exemplos do passo de linkagem (`synesis compile lattes.synp abstracts.synp`, com e sem exportação do agregado v3.1/`links.csv`, e com `--stats`) e notas explicando que o caminho de linkagem só ativa com 2+ projetos, que a compilação isolada de um projeto com `REFERS TO` emite apenas um aviso informativo (nunca erro/warning), e que `--xls`/`--alpaca` ainda não têm exportador no link step. O help geral (`synesis --help`) também passou a citar "one project (or links several)" na linha do comando `compile`.

## [0.8.0] - 2026-07-15

### Added

- **Modificador de campo `IDENTIFIES <entidade>`** (Etapa 1 da ligação multiprojeto — `synesis/grammar/synesis.lark`, `synesis/parser/transformer.py`, `synesis/ast/nodes.py`)
  - Novo modificador em `FIELD` que declara o campo como **chave primária** de uma entidade nomeada (ex.: `IDENTIFIES researcher`). Análogo a *candidate key* relacional: cada valor deve identificar um único SOURCE. Propriedade local do corpus — zero acoplamento a outros projetos.
  - Token `KW_IDENTIFIES` com lookahead de fronteira (como `KW_TOPIC`) para não casar como prefixo de nome de campo maior; nova alternativa em `field_props` e regra `entity_label`. O parser standalone (`synesis/grammar/synesis_standalone.py`) foi regenerado a partir da gramática.
  - `FieldSpec` ganha o campo `identifies: Optional[str] = None`, serializado em `to_dict()`. Aditivo: um campo sem o modificador mantém `identifies=None` e compila idêntico ao comportamento anterior.
- **Validação de unicidade de identidade — erro `SYNESIS_E077` (`DuplicateIdentityValue`)** (`synesis/semantic/validator.py`, `synesis/ast/results.py`)
  - Dois SOURCEs do mesmo corpus com o mesmo valor num campo `IDENTIFIES` agora produzem erro na compilação do próprio membro, antes de qualquer linkagem — um defeito de dados antes silencioso vira erro explícito. Comparação por igualdade exata pós-`trim` (sem *case-folding*, sem normalização), coerente com a regra anti-fuzzy planejada para o link step. Mensagem dual (`to_diagnostic`/`to_cli_line`) apontando entidade, valor e os dois bibrefs.
  - Ligado nos dois orquestradores de validação (`synesis/compiler.py` e `synesis/api.py`) via `validate_identity_uniqueness(sources)`.
- **Modificador de campo `REFERS TO <entidade>` + origem de valor `ON BIBLIOGRAPHY`** (Etapa 2a — `synesis/grammar/synesis.lark`, `synesis/parser/transformer.py`, `synesis/parser/template_loader.py`, `synesis/ast/nodes.py`)
  - `REFERS TO` declara o campo como **chave estrangeira** para uma entidade (aponta, pode repetir, não cria nó). Tokens `KW_REFERS`/`KW_TO`/`KW_ON` com lookahead de fronteira (palavras curtas — evita casar `to_do`, `on_hold`); nova alternativa em `field_props`.
  - `REQUIRED <campo> ON BIBLIOGRAPHY` (no `SOURCE FIELDS`) marca a **origem do valor** como a entrada `.bib` do SOURCE, não o texto do documento. Restrito a **cláusula de campo único** — `REQUIRED a, b ON BIBLIOGRAPHY` (lista) é erro de sintaxe, evitando ambiguidade de a qual campo o sufixo se aplica. `FieldSpec` ganha `refers_to` e `value_origin` (`"document"`/`"bibliography"`, default `"document"`), serializados em `to_dict()`.
- **Validações de ligação — erros `SYNESIS_E078`, `SYNESIS_E079` e INFO `SYNESIS_I080`** (`synesis/semantic/validator.py`, `synesis/parser/template_loader.py`, `synesis/ast/results.py`)
  - `E078` (`LinkageModifierOutsideSource`): `IDENTIFIES`/`REFERS TO` em campo que não é `SCOPE SOURCE` — a ligação opera sobre SOURCEs.
  - `E079` (`MissingBibliographyValue`): campo `REQUIRED ... ON BIBLIOGRAPHY` cujo valor não está na entrada `.bib` do SOURCE. Resolvido via `find_bibref`; o campo `ON BIBLIOGRAPHY` é **excluído** da verificação de campo obrigatório do bloco SOURCE (`MissingRequiredField`/E020), que passaria a disparar falso-positivo já que o valor não vive no bloco.
  - `I080` (`ExternalReferenceDeclared`, severidade **INFO**): projeto declara `REFERS TO` para uma entidade externa não resolvida isoladamente — informativo, emitido uma vez por entidade, nunca *warning* recorrente. As ligações só se materializam num link step (etapa seguinte).
- **Passo de linkagem multiprojeto na CLI — `synesis compile p1.synp p2.synp …`** (Etapa 2b — `synesis/cli.py`, `synesis/semantic/link_step.py`)
  - O comando `compile` passa a aceitar **N projetos** (`nargs=-1`) e despacha internamente: **1 projeto** segue o caminho legado `_compile_single` (inalterado); **≥2 projetos** dispara `_link_projects`, que compila cada membro isolado e resolve as ligações `IDENTIFIES`/`REFERS TO` entre eles — modelo do *linker* C/C++, exclusivo da CLI (o LSP nunca carrega o agregado).
  - Resolução por **rótulo de entidade + igualdade exata de valor** (pós-`trim`, sem normalização): cada `REFERS TO` casado com o `IDENTIFIES` dono vira uma aresta (suporta n:1 e n:n — campo multi-valorado gera uma aresta por valor). Valor de campo `ON BIBLIOGRAPHY` é resolvido da entrada `.bib` do SOURCE. Bibrefs são **qualificados por alias de membro** (`abstracts:@artigo_a`) — dissolve a colisão de bibref entre corpora.
  - Diagnósticos do link step: `SYNESIS_E081` (`DuplicateEntityOwner`, dois membros declaram `IDENTIFIES` do mesmo rótulo), `SYNESIS_E082` (`TypeMismatchInLinkage`, `TYPE` divergente entre campos da mesma entidade — erro duro), `SYNESIS_W083` (`OrphanReference`, `REFERS TO` sem `IDENTIFIES` correspondente). O órfão que **casaria só sob normalização de caixa** vira *warning* enriquecido de **quase-casamento** — o link step detecta e sugere canonizar na origem, mas **nunca funde** (evita unir entidades que a fonte considera distintas).
  - **Pacote de saída §6:** `--json` gera o agregado **schema v3.1 aditivo** (`kind: "link"`, `entity_owners`, seção `links` com arestas resolvidas + órfãos, bibrefs qualificados); `--csv` gera `links.csv`. Consumidores v3.0 ignoram as chaves novas.
- **CLI exibe diagnósticos INFO** (`synesis/cli.py`)
  - `_compile_single` agora imprime a seção INFO da validação (antes computada mas nunca exibida) — em particular o `I080` de referência externa na compilação isolada, conforme §5 do design. Aditivo: apenas exibe dado já presente no resultado.
- **`INCLUDE SHARED ONTOLOGY` — ontologia externa autorizada por declaração** (Etapa 3 — `synesis/grammar/synesis.lark`, `synesis/parser/paths.py`, `synesis/parser/transformer.py`, `synesis/ast/nodes.py`, `synesis/compiler.py`, `synesis/lsp_adapter.py`)
  - Nova keyword `SHARED` em `INCLUDE`: `INCLUDE SHARED ONTOLOGY "../shared/vocabulario.syno"` autoriza um alvo **fora** da pasta do projeto, permitindo que vários projetos do mesmo estudo compartilhem um único vocabulário conceitual sem duplicá-lo. A autorização mora na **declaração** (keyword versionada e auditável no `.synp`), não na geometria do path — por isso aceita caminho de rede (`\\servidor\...`), outro drive (`Z:/...`) e `..`, casos que nenhuma âncora de pasta conseguiria autorizar.
  - `resolve_include` ganha o parâmetro *keyword-only* `shared: bool = False`; quando `True`, pula a checagem de contenção `is_within`. O **default preserva o comportamento atual** em todos os call sites — só os dois de ontologia (`compiler._collect_include_paths`, `lsp_adapter._load_context_from_project`) propagam a keyword. `INCLUDE ONTOLOGY` sem `SHARED` continua produzindo `ESCAPES_PROJECT` (E075) byte-idêntico, inclusive no LSP.
  - `IncludeNode` ganha `shared: bool = False`, serializado em `to_dict()`. `include_type` na gramática passa a aceitar `KW_SHARED?` antes de **qualquer** tipo; a restrição "só ONTOLOGY" (D13) é **semântica**, para dar mensagem pedagógica em vez de erro de sintaxe cru.
  - `SYNESIS_E084` (`SharedOnlyForOntology`): `INCLUDE SHARED` com tipo diferente de `ONTOLOGY` (`BIBLIOGRAPHY`/`ANNOTATIONS`) — o escape autorizado não vaza para tipos que a motivação (compartilhar vocabulário) não pediu.

### Documentation

- Plano de design da ligação multiprojeto revisado até a **Rev. 7** (`Planning/multiproject_key_ref.md`): reenquadramento `IDENTIFIES`/`REFERS TO` como PK/FK, remoção da âncora `.synstudy` em favor de `INCLUDE SHARED ONTOLOGY`, e correções de verificação contra o código (encaixe gramatical de `ON BIBLIOGRAPHY`, wiring de `resolve_include`, baseline de testes dinâmico).


## [0.7.0] - 2026-07-13

### Security

- **Path traversal via glob em `INCLUDE ANNOTATIONS`** (`synesis/compiler.py`, `synesis/parser/paths.py`)
  - O guard de contenção fechava caminhos literais (`"../x.syn"` → E075), mas o ramo de glob não passava por ele: `Path.glob` segue `..`, então `INCLUDE ANNOTATIONS "../../*.syn"` lia e parseava arquivos fora da pasta do projeto, cujo conteúdo entrava no projeto compilado e podia ser exfiltrado por qualquer exportador. Como arquivos `.synp` circulam entre pesquisadores e são gerados por LLM, é leitura arbitrária de arquivos a partir de dado não-confiável.
  - Correção: nova função `resolve_glob()` expande o padrão e filtra pelo mesmo invariante de contenção (`is_within`); matches que escapam viram E075 e não são lidos.
- **Leitura de arquivo sem limite de tamanho (DoS de memória)** (`synesis/parser/lexer.py` e demais loaders)
  - Os loaders liam o arquivo inteiro com `read_text()` sem checar tamanho. O LSP é processo de longa duração; um `.syn`/`.bib` de vários GB (por engano ou gerado por LLM) travava o editor. Correção: `read_source_file()` recusa arquivos acima de `MAX_SOURCE_BYTES` (32 MB) com `SourceFileTooLarge` (subclasse de `OSError`), reportado como `UnreadableIncludedFile` (E076). Ponto único de leitura para `.syn`/`.syno`/`.synp`/`.synt`/`.bib`.
- **CSV/formula injection nos exportadores** (`synesis/exporters/csv_export.py`)
  - Células cujo texto (não-confiável) começa com `= + - @ \t \r` eram executadas como fórmula/DDE ao abrir o CSV no Excel/LibreOffice. Correção: `_sanitize_cell()` prefixa essas células com aspa simples antes da escrita, sem alterar o valor exibido.
- **Higiene de supply chain** (`.github/`, `.pre-commit-config.yaml`)
  - GitHub Actions pinadas por SHA de commit (antes usavam tags móveis `@v4`/`@release/v1`, sujeitas a comprometimento upstream — o job `publish` tem `id-token: write`).
  - `dependabot.yml` (pip + github-actions) e `SECURITY.md` (política de reporte privado, modelo de ameaça de arquivos não-confiáveis) adicionados.
  - Novo job `security` no CI: `pip-audit` sobre as dependências de runtime declaradas (isolado dos extras `[dev]`, para ser determinístico) + Gitleaks (varredura de segredos no histórico). Gitleaks também adicionado ao `pre-commit`.

### Changed

- **CI honesto: removido o mascaramento do smoke test de compilação** (`.github/workflows/ci.yml`)
  - O passo de integração usava `synesis compile ... || true` sobre uma fixture (`tests/fixtures/valid_project`) que não existe, então nunca testava nada de fato. Agora compila a fixture real `tests/fixtures/Basic/project.synp`, sem `|| true`, e verifica que o JSON foi gerado — uma regressão na compilação de ponta a ponta passa a falhar o CI visivelmente.

### Added

- **Módulo `synesis/parser/paths.py`** — ponto único de resolução de caminhos declarados no `.synp`
  - `uri_to_path` / `path_to_uri`: conversão URI ↔ Path. Substitui três implementações divergentes que existiam em `lsp_adapter.py` (uma delas incorreta — ver Fixed).
  - `resolve_include(project_dir, raw)`: resolve o literal de `TEMPLATE`/`INCLUDE` contra o diretório do projeto e devolve `IncludeResolution` (caminho canônico + motivo da falha). Nunca levanta exceção.
  - `normalize_include_path`: canoniza `\` → `/` no literal do `.synp`, tornando portável um projeto escrito no Windows.
  - `canonical_path`: caminho na caixa real do disco. Necessário porque `Path.resolve()` não normaliza caixa — em FS case-insensitive `NOTES.SYN` e `notes.syn` são o mesmo arquivo mas comparam como paths distintos.
  - Novos erros pedagógicos em `synesis/ast/results.py`: `MissingAnnotationsFile` (E073), `MissingOntologyFile` (E074), `IncludePathEscapesProject` (E075), `UnreadableIncludedFile` (E076).
  - Suíte de regressão `tests/test_include_paths.py` (22 testes). Detecta o tipo de FS em runtime e afirma o comportamento correto tanto em case-sensitive quanto case-insensitive — os defeitos de caixa e de separador passariam despercebidos se testados apenas no Windows.

### Fixed

- **Arquivo declarado em `INCLUDE ANNOTATIONS`/`INCLUDE ONTOLOGY` mas inexistente derrubava a compilação** (`synesis/compiler.py`)
  - `_parse_nodes()` chamava `parse_file(path)` sem checar existência, e `_collect_include_paths()` devolvia o caminho mesmo quando o arquivo não estava no disco. O resultado era `FileNotFoundError` escapando de `SynesisCompiler.compile()`. `TEMPLATE` (`_safe_load_template`) e `INCLUDE BIBLIOGRAPHY` (`_check_bibliography_file`) já tinham a checagem defensiva; `ANNOTATIONS` e `ONTOLOGY` nunca a receberam.
  - Correção: `_collect_include_paths()` passa a resolver via `resolve_include()` e emite E073/E074 para os arquivos ausentes, devolvendo apenas os caminhos legíveis. Um `INCLUDE` quebrado não impede mais o parsing dos demais arquivos do projeto.
  - Efeito no LSP: o `FileNotFoundError` chegava à extensão como notificação genérica ("LSP Error", mensagem técnica sem localização). Agora chega como diagnóstico posicionado no `.synp`, sem alteração em `synesis-lsp` nem em `synesis-vscode` — o compilador voltou a ser a fonte de verdade.

- **Erro de sintaxe ou encoding inválido em arquivo incluído escapava como exceção** (`synesis/compiler.py`)
  - `SynesisSyntaxError` e `UnicodeDecodeError` levantados ao parsear um `.syn`/`.syno` incluído atravessavam `compile()` inteiro. O caso do erro de sintaxe é o mais frequente no uso real, e era o que menos informação dava ao usuário: nenhuma indicação de qual arquivo continha o problema.
  - Correção: `_parse_nodes()` e `_parse_single_annotation()` (worker de `ProcessPoolExecutor`) capturam ambos e emitem `UnreadableIncludedFile` (E076). O worker devolve a falha como string, pois exceções não são garantidamente picklable entre processos.

- **`INCLUDE` podia ler arquivos fora da pasta do projeto** (`synesis/compiler.py`, `synesis/parser/paths.py`)
  - Caminhos como `INCLUDE ANNOTATIONS "../../etc/passwd"` eram resolvidos sem validação de contenção — o compilador lia e parseava qualquer arquivo do sistema apontado pelo `.synp`. Relevante porque arquivos `.synp`/`.syn` circulam entre pesquisadores e são gerados automaticamente pelo `synesis-coder`.
  - Correção: `resolve_include()` recusa caminhos que escapem do diretório do projeto (E075). Subpastas (`entrevistas/e01.syn`) continuam válidas.

- **Conversão URI→Path quebrada no Windows** (`synesis/lsp_adapter.py`)
  - `_parse_with_error_handling()` usava `Path(file_uri.replace("file://", ""))`, que deixava a barra inicial antes da letra do drive (`/C:/x` → `\C:\x`, caminho inexistente) e não decodificava percent-encoding — um projeto em `Meus Documentos` ou com acentos no nome virava `meu%20projeto/anota%C3%A7%C3%B5es.syn`. O `file_path` resultante era passado ao `SynesisTransformer`, contaminando o `SourceLocation` de todos os nós daquele arquivo.
  - A conversão correta já existia duplicada em outros dois pontos do mesmo arquivo (`discover_context` e `find_workspace_root`), inline. Correção: as três cópias foram substituídas por `uri_to_path()`.

- **Divergência de caixa entre o `.synp` e o disco produzia erro falso-positivo** (`synesis/compiler.py`)
  - `validate_project_structure()` comparava `set()` de paths via `Path.resolve()`, que não normaliza caixa. Um `.synp` com `INCLUDE ANNOTATIONS "NOTES.SYN"` para o arquivo `notes.syn` no disco: em FS case-insensitive (Windows/macOS) o arquivo abria normalmente mas gerava `MissingAnnotationsInclude` (E061) espúrio — e, com dois `INCLUDE` de caixas diferentes para o mesmo arquivo, também `DuplicateSourceBibref` (E070) espúrio, pois o arquivo era parseado duas vezes. Em FS case-sensitive (Linux) o mesmo `.synp` simplesmente crashava. O mesmo projeto se comportava de três formas distintas nos três sistemas.
  - Correção: comparações passam a usar `canonical_path()` (caixa real do disco). `SourceLocation.file` também passa a carregar a caixa do disco em vez da escrita no `.synp` — sem isso o LSP publicava diagnósticos numa URI (`.../ANNOTATIONS.SYN`) que o editor não reconhece, e o usuário não via o squiggle.

- **Separador `\` em `INCLUDE` não resolvia fora do Windows** (`synesis/compiler.py`, `synesis/parser/paths.py`)
  - `INCLUDE ANNOTATIONS "entrevistas\e01.syn"` — natural para quem escreve o `.synp` no Windows — funcionava lá e falhava no Linux/macOS, onde `\` é caractere válido de nome de arquivo e o caminho era interpretado literalmente. Correção: `normalize_include_path()` canoniza o separador antes da resolução.

### Changed

- **Assinatura de `SynesisCompiler.parse_annotations()` e `parse_ontologies()`** (`synesis/compiler.py`, `synesis/cli.py`)
  - Passam a devolver um `ValidationResult` adicional com os erros de carregamento (E073–E076), agregado em `compile()` e na CLI: `parse_ontologies()` → `(ontologies, result)`; `parse_annotations()` → `(sources, items, result)`. `_collect_include_paths()` e `_parse_nodes()` seguem o mesmo padrão. Métodos internos ao compilador; a API pública (`synesis.load()`, `CompilationResult`) não muda.
- **`SynesisCompiler.load_bibliography()` e `load_template()`** resolvem o caminho via `resolve_include()`, ganhando normalização de separador e contenção. A distinção semântica de `load_bibliography()` (`None` = sem `INCLUDE BIBLIOGRAPHY`, `{}` = declarada mas ilegível) é preservada.

## [0.6.0] - 2026-06-22

### Added

- **`OPTIONAL BUNDLE` em templates** (`synesis/grammar/synesis.lark`, `synesis/parser/transformer.py`, `synesis/ast/nodes.py`, `synesis/parser/template_loader.py`, `synesis/semantic/validator.py`, `synesis/exporters/csv_export.py`, `synesis/exporters/xls_export.py`, `synesis/exporters/alpaca_export.py`)
  - Nova cláusula `OPTIONAL BUNDLE field1, field2` em blocos `SCOPE FIELDS`. Semântica: ausência total do bundle é válida; presença parcial gera `MissingBundleField` (E016); contagens divergentes geram `BundleCountMismatch` (E017). O `REQUIRED BUNDLE` existente não foi alterado.
  - `TemplateNode` ganha o campo `optional_bundles: Dict[Scope, List[Tuple[str, ...]]]` com `default_factory=dict`; `to_dict()` o serializa. Retrocompatível: templates sem `OPTIONAL BUNDLE` produzem dicionário vazio.
  - `validate_optional_bundle` é uma função separada de `validate_bundle` (classificada CRITICAL pelo GitNexus) — sem alteração na lógica de REQUIRED BUNDLE.
  - Exporters CSV, XLS e Alpaca incluem campos de `optional_bundles` nas funções de expansão de linhas e mapeamento de bundle (`_collect_item_bundle_fields`, `_build_bundle_map`).
  - `synesis_standalone.py` regenerado com `compress=True` a partir da gramática atualizada.
  - Fixture `tests/fixtures/T09-OptionalBundle/` com 4 cenários: ausência total (válido), presença parcial (E016), contagem divergente (E017), bundle completo (válido).

### Fixed

- **E001 (`UnregisteredSource`) espúrio em projetos sem `INCLUDE BIBLIOGRAPHY`** (`synesis/compiler.py`, `synesis/api.py`)
  - `compiler.load_bibliography()` retornava `{}` quando não havia declaração `INCLUDE BIBLIOGRAPHY`. O validador, com guarda `if self.bibliography is None`, interpretava `{}` como "bib declarada mas vazia" e validava todos os `@bibref` contra um dicionário vazio, gerando E001 em cascata.
  - Correção: `load_bibliography()` retorna `None` quando não há `INCLUDE BIBLIOGRAPHY`. A distinção semântica é preservada: `None` → sem declaração, validação desativada; `{}` → bib declarada mas vazia, validação ativa e reporta E001. A guarda `is None` no validador permanece intocada.
  - O check E070 (`DuplicateSourceBibref`) é ortogonal à bibliografia e sobrevive à correção: projetos sem bib com `@silva2026` + `@SILVA2026` produzem 0× E001 e 1× E070, conforme verificado empiricamente.

- **`_has_chain_relations` ignorava campos `TYPE CHAIN` com nome customizado** (`synesis/exporters/json_export.py`)
  - `_has_chain_relations()` buscava `template.field_specs.get("chain")` — nome literal. Campos `TYPE CHAIN` renomeados (ex.: `causal_chain`) eram invisíveis à função, fazendo com que os triples do JSON saíssem com `relation='IMPLICIT'` em vez das relações nomeadas declaradas.
  - Correção: a função agora itera `template.field_specs.values()` verificando `spec.type == FieldType.CHAIN and spec.relations`, espelhando o padrão já adotado em `semantic/linker.py`.

- **`ARITY = 2.0` desativava silenciosamente a validação de aridade** (`synesis/parser/template_loader.py`, `synesis/ast/results.py`)
  - `_validate_chain_arity` chamava `int("2.0")`, que lançava `ValueError` capturado com `return None`, desativando toda a validação de arity para aquele campo sem nenhum aviso ao usuário.
  - Correção: `_check_invalid_arity_operator` em `template_loader.py` detecta operador válido com valor não-inteiro e emite `NonIntegerArityValue` (novo erro E060) antes que a execução chegue ao `int()`. O erro é explícito e pedagógico.

- **Bibrefs puramente numéricos (`@2026`, `@001`) eram rejeitados pelo parser** (`synesis/grammar/synesis.lark`, `synesis/grammar/synesis_standalone.py`)
  - `BIBREF: "@" /[a-zA-Z][a-zA-Z0-9_-]*/` exigia letra como primeiro caractere, herança da convenção BibTeX. Com SOURCE como unidade de evidência genérica, identificadores numéricos são casos de uso legítimos (entrevistas numeradas, anos, IDs institucionais).
  - Correção: primeiro caractere relaxado para `[a-zA-Z0-9]`. O `@` inicial é desambiguador suficiente — sem colisão com `NUMBER` nem `TEXT_LINE`. Projetos com bib e chaves numéricas passam a funcionar de ponta a ponta.

- **Nomes de campo que começam com keyword de tipo causavam `UnexpectedToken`** (`synesis/grammar/synesis.lark`, `synesis/grammar/synesis_standalone.py`)
  - Tokens como `KW_CODE.5: /code/i` venciam `FIELD_NAME.1` no lexer contextual, casando apenas o prefixo (`code` em `code_quality`) e deixando `_quality: x` como `TEXT_LINE` órfão.
  - Correção: cada keyword-type ganhou lookahead negativo `(?![\p{L}\p{N}_-])` na própria declaração do terminal, bloqueando o match apenas quando a keyword forma o nome inteiro do campo. `code_quality`, `chain_length`, `date_created`, `topic_area` etc. passam a parsear corretamente; keywords exatas (`code`, `chain`) continuam roteadas pelas alternativas explícitas de `field_key`.

## [0.5.7] - 2026-06-15

### Changed

- **`ValidationResult.to_diagnostics(verbose=False)`** — novo modo compacto para exibição ao usuário pesquisador (`synesis/ast/results.py`)
  - `verbose=True` (padrão): comportamento inalterado — mensagens pedagógicas completas para o LSP e para o LLM de auto-correção.
  - `verbose=False`: usa `to_cli_line()` por erro; agrupa todos os avisos `UndefinedCode` em um bloco único com contagem de ocorrências por código, ordenados por frequência; acrescenta dica `synesis-coder ontology` quando há códigos sem definição. Reduz saída de centenas de linhas repetidas para ~10 linhas no caso típico.
- **`MemoryCompilationResult.get_diagnostics(verbose=True)`** e **`CompilationResult.get_diagnostics(verbose=True)`** — repassa o kwarg `verbose` para `to_diagnostics()`. Default retrocompatível; nenhum chamador existente quebra.

## [0.5.6] - 2026-06-12

### Added

- **Verbosity flags `-v`/`-q` on `synesis` CLI** (`synesis/cli.py`)
  - `-v` / `--verbose` (count): raises log level to DEBUG. Repeatable.
  - `-q` / `--quiet` (count): lowers to WARNING (`-q`) or ERROR (`-qq`). Repeatable.
  - Implemented via `_configure_logging(verbose, quiet)` helper using `logging.basicConfig`.
  - `Global Options:` section added to `_build_main_help()` output — consistent with synesis-coder style.
  - No impact on compilation output; only controls Python logging channel.

## [0.5.5] - 2026-06-11

### Added

- **Quality toolchain and CI** (`pyproject.toml`, `.pre-commit-config.yaml`, `.github/workflows/ci.yml`)
  - `ruff==0.15.17` and `mypy==1.15.0` added to `dev` extras (pinned, shared across ecosystem).
  - `[tool.ruff]`: `line-length=100`, `target-version="py310"`; lint rules `["E","F","I","UP","B","SIM","C4"]`.
  - `[tool.mypy]`: `ignore_missing_imports=true`, `disallow_untyped_defs=false` (lenient baseline).
  - `.pre-commit-config.yaml`: `ruff` (lint + `--fix`), `ruff-format`, `mypy`, `end-of-file-fixer`, `trailing-whitespace`, `check-yaml`, `check-toml`, `check-merge-conflict`.
  - CI workflow (3 OS × 3 Python versions): `test` (pytest + coverage), `lint` (ruff + mypy), `build` (wheel + twine check), `integration` (`synesis --help/--version`).

- **CLI snapshot tests** (`tests/test_cli.py`)
  - Subprocess-based tests asserting structural anchors in `--help` output (title, `Usage:`, `Commands:`, subcommand names) and `--version` correctness — serve as regression guard for CLI refactors.

### Changed

- **CLI rewritten with Unix-style output, colors, and English-only interface** (`synesis/cli.py`)
  - Replaced the ad-hoc `_print_help()` function with a `_SynesisGroup` / `_SynesisCommand` architecture identical to the synesis-coder CLI pattern.
  - `_build_main_help()`: fully custom help rendered via `sys.stdout.buffer` with explicit UTF-8 encoding, bypassing Click's codec path to prevent character corruption on Windows terminals.
  - Commands grouped into three semantic sections: "Project Management", "Compilation & Export", "Validation & Debugging".
  - ANSI colors applied consistently: section headers in yellow/bold, command names in green/bold, option flags in cyan — colors suppressed automatically when stdout is not a TTY.
  - Global column alignment computed once across all groups (`col = max(cmd_names_len) + 2`), ensuring all command names align at the same column regardless of group.
  - `_SynesisCommand` subclass overrides `format_epilog` to write epilog lines verbatim (no Click reflowing), enabling structured `Examples:` blocks per subcommand.
  - `_ex(*lines)` helper colorizes example blocks: `synesis` in green/bold, subcommand names in green, `--flags` in cyan, `# comments` in bright_black.
  - All four subcommands (`compile`, `check`, `validate-template`, `init`) now carry colored `Examples:` epilogs.
  - `--version` handled via `@click.version_option`; `--help` via `get_help()` override — both paths write UTF-8 directly.
  - All user-facing strings translated to English; internal variable names and comments unchanged.

## [0.5.4] - 2026-06-10

### Changed

- **Campos `TYPE CHAIN` e `TYPE CODE` aceitam qualquer nome de campo** (`synesis/parser/transformer.py`, `synesis/semantic/validator.py`, `synesis/semantic/linker.py`)
  - Até v0.5.3.3, o compilador exigia que campos `TYPE CHAIN` se chamassem literalmente `chain`/`chains` e campos `TYPE CODE` se chamassem `code`/`codes`. Qualquer outro nome produzia `InvalidFieldType: expected chain, actual str` em todos os ITEMs que usavam o campo.
  - **Causa raiz:** `transformer.py:field_entry` convertia o valor para `ChainNode` apenas se `_is_chain_field_name(name)` fosse verdadeiro — qualquer outro nome despejava o valor como `str` em `extra_fields`. O validador (passo 6) lia a string e emitia `InvalidFieldType`; o linker (passo 7), que já suportava campos CHAIN genéricos por `spec.type`, rodava tarde demais.
  - **`transformer.py`**: `field_entry` passa a converter para `ChainNode` por **estrutura** (presença de `->` no valor), não por nome. Nova helper `_lines_contain_chain()` detecta `->` em valores multi-linha. `item_block` roteia `ChainNode` com nome não-canônico para `extra_fields` preservando o tipo.
  - **`validator.py`**: `__post_init__` pré-indexa `_chain_field_specs` (todos os campos `TYPE CHAIN` do template, análogo ao `_code_field_names` existente). `_validate_codes_defined` e `_validate_chains` iteram sobre `_chain_field_specs` em vez de fixar o literal `field_specs.get("chain")` — validação de arity, relações e `UndefinedCode` funciona para qualquer nome de campo CHAIN.
  - **`linker.py`**: `_has_chain_relations` itera por tipo (`spec.type == FieldType.CHAIN`) em vez de buscar pelo literal `"chain"`.
  - **Compatibilidade retroativa total:** campos nomeados `chain`/`code` continuam com comportamento idêntico — as condições novas são superconjuntos das anteriores. Projetos existentes não precisam de nenhuma alteração.
  - **Validação verificada:** `InvalidChainRelation`, `ChainArityViolation`, `SimpleChainWithRelationsRequired`, `UndefinedCode` em contexto CHAIN — todos funcionam corretamente para campos com nome descritivo (ex: `FIELD causal_chain TYPE CHAIN ... RELATIONS`).

## [0.5.3.3] - 2026-06-01

### Changed

- **Projeto basico e scaffold `synesis init` agora incluem `GUIDELINES`** (`synesis/cli.py`, `README.md`, `case-studies/Basic/template.synt`)
  - Os seis campos do template introdutorio (`description`, `citation`, `note`, `code`, `definition`, `group`) agora incorporam instrucoes curtas para anotadores humanos e agentes de IA.
  - As orientacoes cobrem resumo de fontes, extracao literal de excertos, elaboracao de memos analiticos, reutilizacao de codigos da ontologia, definicao de criterios de aplicacao e agrupamento tematico em categorias amplas.
  - O exemplo completo do `README.md`, o projeto `case-studies/Basic` e novos projetos criados por `synesis init` permanecem sincronizados.
  - Mudanca aditiva: a estrutura de dados do exemplo nao foi alterada; os blocos sao exportados como `field_specs.<campo>.guidelines` no JSON compilado.

## [0.5.3.2] - 2026-05-21

### Fixed

- **Deteccao de chaves BibTeX com `@` no inicio** (`synesis/parser/bib_loader.py`)
  - Entradas no formato `@book{@BibliaNVT,...}` — onde o `@` faz parte da chave — eram parseadas com sucesso pelo bibtexparser mas armazenadas com chave inválida (`@biblianvt`). Isso impedia a correspondência com o `@bibref` da anotação, gerando E001 (`UnregisteredSource`) com sugestão incorreta (`@@biblianvt`).
  - `detect_malformed_entries()` estendida com um segundo caso de detecção: inspeciona `bib_database.entries` em busca de entradas cujo `ID` começa com `@`. O `@` inicial é removido antes de reportar (`clean_key = entry_id.lstrip("@")`), evitando duplo `@` na mensagem E072 e garantindo que `malformed_bib_keys` suprima corretamente o E001 correspondente.

- **Sugestoes de bibref sem `@` duplicado e com ate 3 alternativas** (`synesis/semantic/validator.py`, `synesis/ast/results.py`)
  - `_validate_bibref()`: chaves passadas ao `suggest_bibref` agora passam por `lstrip("@")`, eliminando sugestoes com `@@` independente do conteúdo do dicionário `.bib`.
  - `UnregisteredSource.to_cli_line()` e `to_diagnostic()`: exibem todas as sugestoes retornadas (ate 3), separadas por vírgula, no lugar de apenas a primeira.

## [0.5.3.1] - 2026-05-21

### Fixed

- **Supressao de erros `SYNESIS_E001` em cascata quando o `.bib` e malformado** (`synesis/semantic/validator.py`, `synesis/compiler.py`, `synesis/cli.py`, `synesis/api.py`)
  - Quando uma entrada do `.bib` era malformada (E072), o compilador tambem emitia um `UnregisteredSource` (E001) para cada `@bibref` que apontava para essa entrada — com uma "sugestao de correcao" incorreta apontando para outra chave de referencia. O comportamento gerava erros em cascata que escondiam a causa raiz (E072) e induziam o usuario a renomear corretamente um `@bibref` para uma referencia errada.
  - Fix: `SemanticValidator` agora recebe o conjunto de chaves malformadas (`malformed_bib_keys`) detectadas na etapa de validacao de formato do `.bib`. Em `_validate_bibref()`, bibrefs que correspondem a uma entrada malformada sao silenciados — o diagnostico E072 ja aponta o problema correto no `.bib`. A mudanca e puramente defensiva e nao afeta a validacao de bibrefs para entradas `.bib` validas.
  - Impacto zero no `synesis-lsp`: o caminho de validacao de arquivo unico (`validate_document`) ja era marcado como fora de escopo para deteccao de formato de `.bib`. O caminho de workspace (`validateWorkspace` → `SynesisCompiler.compile()`) beneficia-se automaticamente.

## [0.5.3] - 2026-05-21

### Added

- **Deteccao de entradas BibTeX malformadas no arquivo `.bib`** (`synesis/parser/bib_loader.py`, `synesis/ast/results.py`, `synesis/compiler.py`, `synesis/api.py`)
  - Novo erro `MalformedBibliographyEntry` (`SYNESIS_E072`): quando uma entrada do `.bib` nao esta em formato BibTeX valido — sem tipo de entrada, chave fora de chaves, ou campos com `:` no lugar de `=` — o compilador emite um diagnostico educativo apontando o proprio `.bib` e a linha da entrada, com exemplo do formato correto.
  - Causa do problema corrigido: o `bibtexparser` v1.4.4 nao lanca excecao com entradas malformadas — trata o bloco invalido como "comentario implicito" (armazenado em `BibDatabase.comments`, nunca em `entries`). O resultado era `load_bibliography()` retornar vazio e cada `@bibref` falhar depois como "referencia nao encontrada", apontando o arquivo `.syn` errado e escondendo a causa raiz no `.bib`.
  - `detect_malformed_entries(content)` em `bib_loader.py`: inspeciona `BibDatabase.comments` em busca de blocos iniciados por `@` (entradas que o parser nao reconheceu), extrai a chave suspeita e localiza a linha no conteudo original. Nao altera as assinaturas de `load_bibliography` / `load_bibliography_from_string` — mudanca puramente aditiva.
  - `SynesisCompiler._check_bibliography_format()`: nova etapa do pipeline, espelhando `_check_bibliography_file()` (erro 63), executada antes do carregamento da bibliografia.
  - Integrado tambem na API in-memory (`synesis.load()`), que passa a reportar o erro em `validation_result`.
  - Cobertura no VSCode sem alterar o `synesis-lsp`: a validacao de workspace do LSP ja roteia cada erro para o URI do seu `location.file` via `group_diagnostics_by_file()` — o diagnostico aparece no painel Problems atribuido ao arquivo `.bib`.

## [0.5.2.1] - 2026-05-21

### Fixed

- **Identificadores Unicode aceitos em nomes de conceitos e códigos** (`synesis/semantic/validator.py`)
  - A regex de validação de identificadores (erro 33) usava `[^a-zA-Z0-9_\-]`, rejeitando qualquer caractere fora do ASCII — incluindo letras acentuadas como `ç`, `ã`, `é`, `ü`. Isso causava `InvalidIdentifierCharacter` em conceitos de ontologia com nomes em português, espanhol ou qualquer idioma com diacríticos (ex.: `Perseguições`, `Conflitos`).
  - Contraste com a gramática: os tokens `IDENTIFIER`, `CONCEPT_NAME`, `CODE_ELEMENT` e `CHAIN_ELEMENT` em `synesis.lark` já usam `\p{L}` com flag Unicode, aceitando qualquer letra Unicode desde o parser. O validador semântico era o único ponto que bloqueava esses caracteres.
  - Fix: regex substituída por `[^\w\-]` com `re.UNICODE`. `\w` em modo Unicode cobre `[a-zA-Z0-9_]` mais qualquer letra ou dígito Unicode, alinhando o validador ao que o parser já aceita. Nomes ASCII não são afetados.

## [0.5.2] - 2026-05-15

### Changed

- **Paralelização de `parse_annotations` migrada para multiprocessing** (`synesis/compiler.py`)
  - `ThreadPoolExecutor` substituído por `ProcessPoolExecutor` no caminho paralelo de `parse_annotations()`. O parser Lark (incluindo o standalone gerado e o `SynesisIndenter`) é puramente Python; com a GIL, 4 worker threads serializavam o trabalho CPU-bound e ainda adicionavam overhead de coordenação. A paralelização introduzida na v0.4.0 era, na prática, uma regressão para projetos grandes: medido contra `Nave_Topical_Concordance` (26 arquivos `.syn`, 82.826 items, 8.6 MB), `ThreadPoolExecutor(4)` levava 39.2s — pior que rodar sequencial (12.0s).
  - Com `ProcessPoolExecutor(4)`, cada worker tem sua própria GIL e o parsing escala de fato: o mesmo projeto cai para ~4.0s (≈10× mais rápido que a versão anterior, ≈3× mais rápido que sequencial). Tempo total de compilação no Nave: ~42s → ~7s.
  - Threshold ajustado de `len(paths) <= 2` para `len(paths) <= 3`: o custo de spawn de processos no Windows (~50-100 ms por worker) só é amortizado a partir de 4 arquivos `.syn`. Projetos pequenos seguem no caminho sequencial sem overhead.
  - Remoção do pre-warm `create_parser()` na main thread antes do spawn: era específico ao modelo thread-local; com processos, cada worker importa `synesis_standalone` no seu próprio startup.
  - `_parse_single_annotation` já era function module-level (introduzida em 0.4.0 justamente para ser picklable) — nenhuma adaptação adicional foi necessária. Os nós AST (`SourceNode`, `ItemNode`, `ChainNode`, `SourceLocation`, enums) são `@dataclass` com tipos primitivos, picklados automaticamente pelo IPC do `multiprocessing`.

## [0.5.1] - 2026-04-09

### Fixed

- **Filtro de sentinelas em ORDERED/ENUMERATED** (`synesis/exporters/alpaca_export.py`)
  - Valores com `index=0` ou label `Undefined/None/N/A` eram incluídos na lista de opções das instruções ORDERED/ENUMERATED, treinando o LLM a reconhecer "Undefined" como resposta válida. Esses são marcadores estruturais de dados faltantes no compilador, não alvos de classificação.
  - Fix: `_is_sentinel_value()` detecta sentinelas por `index == 0` ou label em `{"undefined", "none", "n/a", "not available"}` e os remove das opções e dos outputs gerados.

- **Instrução abreviada para ORDERED com muitos valores** (`synesis/exporters/alpaca_export.py`)
  - Campos ORDERED com > 6 valores (ex: escala Dooyeweerd com 15 aspectos) listavam todas as opções na instrução, tornando-a excessivamente densa e desperdiçando tokens no fine-tuning.
  - Fix: quando `len(meaningful_values) > 6`, a instrução usa forma abreviada com exemplos representativos: `"Classify the concept 'X' into the most appropriate level of '...' (e.g., Quantitative, Spatial, ..., Fiducial)."` — o modelo já possui conhecimento latente dessas categorias e só precisa do vínculo conceito→nível.
  - Fix colateral: corrigido bug de `{{concept}}` (double brace) na forma abreviada que gerava `'{Cost}'` em vez de `'Cost'` nas instruções.

- **Citação bibliográfica legível em pares SOURCE** (`synesis/exporters/alpaca_export.py`)
  - Instruções SOURCE usavam apenas a chave BibTeX (`"Describe the source 'jenal2021' regarding: ..."`) — chave opaca que força o LLM a memorizar IDs arbitrários sem generalização.
  - Fix: `_format_citation()` extrai `author`, `title` e `year` da `BibEntry` e formata como `"Regarding Jenal et al. (2021) – 'Technological Transformation Processes...'", describe: ..."` — grounding real na referência bibliográfica.
  - `_format_authors()` normaliza strings BibTeX: 1 autor → `"Smith"`, 2 → `"Smith and Doe"`, 3+ → `"Smith et al."`.
  - Fallback gracioso para bibrefs sem entrada na bibliografia (mantém a chave).

- **Divisão de TOPIC_INDEX com muitos conceitos** (`synesis/exporters/alpaca_export.py`)
  - Tópicos com muitos conceitos (ex: "Behavior" com 40+ itens) geravam um único par com output excessivamente longo, de difícil aprendizado.
  - Fix: tópicos com > 15 conceitos são divididos em partes de 15 com instrução numerada `"(part 1 of 2)"`, garantindo que todos os conceitos sejam cobertos sem sobrecarregar nenhum par.

## [0.5.0] - 2026-04-09

### Added

- **Exportador Alpaca JSONL** (`synesis/exporters/alpaca_export.py`)
  - Novo módulo `alpaca_export` gera pares `{"instruction", "input", "output"}` para fine-tuning de LLMs diretamente a partir de qualquer projeto Synesis compilado — sem dependência de IA (Camada 1 estática, determinística).
  - `build_alpaca_pairs(linked, template, bibliography)` — retorna lista de pares em memória.
  - `export_alpaca(linked, output_path, template, bibliography)` — serializa como JSONL em disco.
  - Geração template-driven por tipo de campo:
    - **QUOTATION + MEMO (bundle)**: pares de interpretação analítica com trecho como `input` e memo como `output`.
    - **CHAIN + MEMO (bundle)**: pares causais com tripla + memo concatenados no `output` (`"A -> REL -> B. {memo}"`).
    - **CHAIN (sem bundle)**: pares de triplas causais com a QUOTATION do item como `input`.
    - **MEMO autônomo**: pares de interpretação analítica usando a QUOTATION como `input`.
    - **CODE**: pares de codificação conceitual com todos os códigos do item no `output`.
    - **ONTOLOGY TEXT**: pares de definição conceitual por conceito (`input` vazio).
    - **ONTOLOGY TOPIC**: pares de categorização temática por conceito.
    - **ONTOLOGY ENUMERATED/ORDERED**: pares de classificação com opções no enunciado.
    - **ONTOLOGY SCALE**: pares de escala numérica com intervalo no enunciado.
    - **SOURCE TEXT/MEMO/QUOTATION**: pares de descrição de fontes bibliográficas.
    - **Pares agregados** de `all_triples`: conceitos com ≥ 2 triples distintas entrantes.
    - **Pares de topic_index**: tópicos com ≥ 2 conceitos listam todos os membros.
  - Deduplicação exata por `(instruction, output)` — sem colisões entre geradores.
  - Descarte automático de `output` com menos de 5 caracteres.
  - BUNDLE-aware: detecta `(CHAIN, MEMO)` e `(QUOTATION, MEMO)` via `template.bundled_fields` — MEMOs bundled com CHAIN não são processados como MEMO autônomos.
  - Integrado em `CompilationResult.to_alpaca(path)` (`compiler.py`), `MemoryCompilationResult.to_alpaca_pairs()` (`api.py`) e opção `--alpaca` na CLI.
  - Validado em `social_acceptance` (452 sources, 1.505 items, 2.211 chains): **13.699 pares** gerados.

- **Opção `--alpaca` na CLI** (`synesis/cli.py`)
  - `synesis compile projeto.synp --alpaca dataset.jsonl` exporta JSONL de fine-tuning junto com os demais artefatos.
  - Compatível com `--force` e com qualquer combinação de `--json`, `--csv`, `--xls`.

- **Módulo `_helpers.py`** (`synesis/exporters/_helpers.py`)
  - Funções compartilhadas entre `csv_export`, `xls_export` e `alpaca_export`:
    - `_get_field_names_for_scope(template, scope)` — lista de nomes de campo para um dado scope.
    - `_get_field_names_for_scope_and_types(template, scope, types)` — filtrado por tipo.
    - `_get_item_field_value(item, name)` — acesso unificado a campos de ItemNode (extra_fields + campos canônicos).
    - `_get_ontology_field_value(ontology, name)` — acesso unificado a campos de OntologyNode.

### Changed

- **JSON v3.0** (`synesis/exporters/json_export.py`)
  - Campos de ontologia agora são planos no objeto (`"topic": "Theme"` em vez de `"fields": {"topic": "Theme"}`).
  - Chains exportadas como lista de objetos `{"from", "relation", "to"}` em vez de lista de nodes.
  - Seção `bibliography` enriquecida com os campos SOURCE do template (ex: `epistemic_model`, `method`).
  - Corrigido **bug de `frequency`/`source_count` sempre zero** em projetos cujos conceitos aparecem exclusivamente em campos CHAIN: `_build_chain_usage()` itera todos os chains do corpus para mapear conceitos → items, complementando o `code_usage` do linker que só registra referências diretas via CODE/ITEM.
  - `synesis2neo4j` e `synesis2graph` atualizados para consumir o formato v3.0 flat.

### Fixed

- **`frequency` e `source_count` sempre 0 em projetos CHAIN-only** (`synesis/exporters/json_export.py`)
  - Projetos que atribuem conceitos exclusivamente via campos CHAIN (sem campos CODE) tinham `item.codes = []`, portanto `linked.code_usage = {}`. Todos os conceitos da ontologia apareciam com `frequency: 0` e `source_count: 0` no JSON exportado.
  - Fix: `_build_chain_usage()` extrai ocorrências de conceitos dos chains de todos os items, e `_build_ontology_schema()` combina `code_usage` (direto) + `chain_usage` (via chains) para calcular `frequency` e `source_count` corretos.

## [0.4.7] - 2026-03-19

### Fixed
- **Race condition no parser paralelo** (`synesis/parser/lexer.py`)
  - O `SynesisIndenter` era singleton via `@lru_cache`, compartilhado entre todas as threads do `ThreadPoolExecutor` usado em `parse_annotations`. O estado mutável do Indenter (`indent_level`, `paren_level`) era corrompido quando múltiplas threads chamavam `parser.parse()` simultaneamente, produzindo erros espúrios de indentação (`_INDENT` inesperado) em projetos com mais de 2 arquivos `.syn`.
  - Fix: `create_parser()` migrado de `@lru_cache` para `threading.local` — cada thread recebe sua própria instância do parser (incluindo `SynesisIndenter`), criada uma vez na primeira chamada por thread.
  - Custo: ~4ms na primeira chamada por thread; zero nas subsequentes. Compilação sequencial (≤2 arquivos) não é afetada.

- **TAB misturado com espaços causa falha de parse** (`synesis/parser/lexer.py`)
  - O parser standalone Lark trata TAB e espaços como tokens distintos no terminal `NEWLINE`. Arquivos `.syn` com TAB em uma linha e espaços nas demais (comportamento comum de editores com `insertSpaces=false`) causavam `UnexpectedToken(_INDENT)` mesmo que a indentação numérica fosse equivalente (1 TAB = 4 espaços).
  - Fix: normalização `\t → "    "` em `parse_string()` antes do parse, com guard `if "\t" in content` para custo zero em arquivos sem TAB.

## [0.4.6] - 2026-03-19

### Fixed
- **`DuplicateSourceBibref` (E070) não reportado pelo LSP** (`synesis/lsp_adapter.py`)
  - `validate_single_file` validava cada `SourceNode` isoladamente via `SemanticValidator` — nunca acumulava o conjunto completo para checar bibrefs duplicados entre blocos SOURCE.
  - O erro era detectado apenas pelo CLI (fase de linking no `Linker._check_duplicate_source_bibrefs`), invisível no VSCode.
  - Fix: adicionada checagem cross-node em `_validate_semantics` após coleta dos sources — replica exatamente a lógica do Linker usando `normalize_bibref` para consistência (case-insensitive).
  - Fix: `filename` na mensagem de diagnóstico decodificado via `urllib.parse.unquote` — evita exibição de `%3A` em vez de `:` em paths Windows.

## [0.4.5] - 2026-03-18

### Fixed
- **API pública do `lsp_adapter.py`** — 3 funções privadas promovidas a nomes públicos com aliases backward-compat:
  - `_find_workspace_root` → `find_workspace_root`
  - `_discover_context` → `discover_context`
  - `_invalidate_cache` → `invalidate_cache`
  - Aliases `_find_workspace_root = find_workspace_root` etc. garantem que imports existentes não quebram.
  - Chamadas internas (`validate_single_file`, `discover_context`) atualizadas para usar os nomes públicos.

### Removed
- **`synesis/parser/error_handler.py`** — arquivo de código morto deletado.
  - Continha `SynesisErrorHandler` como `@dataclass(frozen=True)` com API incompatível com o handler ativo (`synesis/error_handler.py`).
  - Zero imports em qualquer repositório do ecossistema. Nunca exportado por `synesis/parser/__init__.py`.

## [0.4.4] - 2026-03-17

### Fixed
- **Ontologia não carregada no contexto LSP** (`synesis/lsp_adapter.py`)
  - `_load_context_from_project` carregava template e bibliografia mas retornava sempre `ontology_index={}` — o campo `INCLUDE ONTOLOGY` do `.synp` era ignorado. Resultado: `validate_single_file` via LSP reportava todos os códigos como "não definidos na ontologia", mesmo com a ontologia corretamente declarada.
  - Fix: adicionado bloco "3. CARREGAR ONTOLOGIAS" em `_load_context_from_project` — itera `project.includes`, filtra `include_type == "ONTOLOGY"`, parseia cada `.syno` via `parse_file` + `SynesisTransformer` e popula `ontology_index` com os `OntologyNode` encontrados. Mesmo padrão já usado pelo compilador (`compiler.py:parse_ontologies`).
  - Verificado: `validate_single_file` no projeto Basic agora encontra `['Social_Cohesion', 'Collective_Action']` na ontologia e retorna 0 erros.

## [0.4.3] - 2026-03-17

### Fixed
- **`_find_workspace_root` e `_discover_context` falham silenciosamente no Windows** (`synesis/lsp_adapter.py`)
  - `Path(file_uri.replace("file://", ""))` transformava `file:///C:/...` em `/C:/...` — caminho inválido no Windows — fazendo `_find_workspace_root` retornar `None`. `_discover_context` então retornava contexto vazio e `validate_single_file` validava arquivos sem template, gerando **zero diagnósticos** mesmo com erros reais presentes.
  - Fix: substituído por `urlparse` + `unquote` com normalização de drive Windows (`/C:/...` → `C:/...`) — mesmo padrão já usado em `server.py:_normalize_workspace_path`. Aplicado em dois locais: `_find_workspace_root` (linha 484) e `_discover_context` (linha 355).
  - Verificado: `validate_single_file` com URI `file:///` passou de 0 para 10 diagnósticos no case-study T01.

## [0.4.2] - 2026-03-15

### Fixed
- **Bloco `GUIDELINES` aceita qualquer conteúdo de texto** (`grammar/synesis.lark`, `parser/transformer.py`, `grammar/synesis_standalone.py`)
  - O lexer tokenizava keywords (`CODE`, `CHAIN`, `DESCRIPTION`, etc.) com prioridade `.5` antes do terminal `TEXT_LINE` (.3), causando falha de parse quando linhas do GUIDELINES continham nomes de campos ou commands (ex: `CODE: Use taxonomy codes`).
  - Solução: regra `guideline_line` + `guideline_token` que aceita explicitamente qualquer keyword, `IDENTIFIER`, `FIELD_NAME`, `NUMBER`, `BIBREF`, `COLON`, `","`, `"->"` como texto. O transformer `guideline_line` reconstrói a linha sem espaço desnecessário antes de `:`.
  - `synesis_standalone.py` regenerado com a nova gramática.

## [0.4.1] - 2026-03-15

### Added

- `ast/results.py`: 38 novas subclasses `ValidationError` cobrindo erros de template (Fase 1),
  anotações (Fase 2), entidades cruzadas (Fase 3) e estrutura de projeto (Fase 4) — elevando de
  19 para 57 subclasses tipadas no total:
  - **Fase 1 — Validação estrutural de template:** `DuplicateFieldName`, `UndefinedFieldInScopeFields`,
    `OrphanFieldDefinition`, `SingleFieldBundle`, `FieldScopeListMismatch`, `ChainWithoutArity`,
    `ArityRelationsMismatch`, `OrderedWithoutValues`, `EnumeratedWithoutValues`, `ScaleWithoutFormat`,
    `InvalidFormatSyntax`, `InvalidArityOperator`, `FormatOnNonScale`, `ArityOnNonChain`,
    `RelationsOnNonChain`, `DuplicateScopeBlock`, `ValueWithWhitespace`, `DuplicateValue`
    (erros 18, 39–59, 69 do inventory).
  - **Fase 2 — Validação semântica de anotações:** `OntologyWithoutTemplateFields`,
    `QualifiedChainWithoutRelations`, `SimpleChainWithRelationsRequired`, `EmptyItemBlock`,
    `DecimalInIntegerScale`, `DuplicateCodeInField`, `TopicWithSpaces`, `InvalidIdentifierCharacter`
    (erros 5, 8, 9, 23, 26, 31–33).
  - **Fase 3 — Validação cross-entity:** `ChainWithoutArrowOperator`, `ConceptNameMatchesRelation`,
    `ConceptWithSpaces`, `DuplicateOntologyConcept`, `DuplicateSourceBibref`,
    `DuplicateOntologyDescription` (erros 6, 13–15, 68, 70, 71).
  - **Fase 4 — Estrutura de projeto:** `MissingAnnotationsInclude`, `MissingOntologyInclude`,
    `MissingBibliographyFile`, `MissingTemplateDeclaration`, `DuplicateProjectBlock`,
    `ModifiedBeforeCreated` (erros 61–63, 65–67).
- `parser/template_loader.py`: função `validate_template()` com 16 funções auxiliares que realiza
  validação estrutural completa do `TemplateNode` após parsing — substituindo os `TemplateLoadError`
  pontuais por `ValidationResult` acumulável compatível com o pipeline LSP/diagnósticos.
- `semantic/validator.py`: validações para erros 5, 8, 9, 23, 26, 31 integradas ao
  `SemanticValidator`; novo método `_validate_code_fields_duplicates` e helper `_validate_identifier`.
- `semantic/linker.py`: detecção de `DuplicateOntologyConcept` (erro 68), `DuplicateSourceBibref`
  (erro 70) e `DuplicateOntologyDescription` (erro 71) integradas ao `Linker`.
- `compiler.py`: chamada a `validate_template()` inserida no pipeline entre `load_template()` e
  `validate_all()`; verificações de estrutura de projeto (erros 61–67) integradas a `compile()`.
- `ast/nodes.py`: campo `parse_errors` adicionado a `TemplateNode` para propagar erros de parsing
  de template pelo pipeline `ValidationResult`.

### Changed

- `cli.py`: saída do comando `compile` reformulada para eliminar "ansiedade de tela preta" em
  projetos grandes. O pipeline agora é executado etapa a etapa com feedback visual em tempo real:
  spinner animado por etapa (`⠋ Lendo anotacoes...`), substituído por linha de conclusão com
  checkmark verde, tempo decorrido e contagem relevante (`✔ Lendo anotacoes  484 sources, 1.614 items  (1.2s)`).
  Em terminais não-TTY (pipe, redirect, CI) o spinner é desativado e as etapas são impressas como
  linhas simples sem animação.
- `cli.py`: mensagens de erro e aviso migradas para formato compacto de uma linha via novo método
  `to_cli_line()` na hierarquia de `ValidationError`. A mensagem pedagógica completa permanece em
  `to_diagnostic()` para uso no LSP/hover do VSCode.
- `cli.py`: localização nos diagnósticos exibe caminho relativo ao diretório do projeto em vez do
  caminho absoluto. Colunas de localização e label `[ERROR]`/`[WARNING]` alinhadas tabulariamente.
- `cli.py`: estatísticas (`--stats`) removem `Triples` (métrica técnica interna sem significado
  direto para o usuário) e exibem separador de milhar com ponto (`1.614`), alinhamento à direita
  dos números e título `Estatisticas da Compilacao:` em negrito.
- `cli.py`: cabeçalho `SYNESIS v{VERSION}  Compile seu pensamento.` exibido no início de cada
  compilação.
- `ast/results.py`: `ValidationError` recebe método `to_cli_line()` com implementação padrão
  (extrai primeira linha de `to_diagnostic()`). Todas as 57 subclasses implementam a versão
  especializada com mensagem de uma linha contendo dado principal + sugestão de correção quando
  disponível. Sugestões usam padrão uniforme `"Sugestao de correcao -> \`valor\`"`.

## [0.4.0] - 2026-03-13

### Added
- `ast/normalize.py`: módulo centralizado com `normalize_code()` e `normalize_bibref()`,
  substituindo 9 cópias independentes de `_norm_code` dispersas entre `validator.py`,
  `linker.py` e os 7 módulos do `synesis-lsp`. Cache opcional por compilação via `dict`
  passado explicitamente (`norm_cache`).
- `parser/parse_cache.py`: cache por arquivo `(path, mtime) → list[nodes]` para compilação
  incremental. Evita re-parsing de arquivos não modificados entre compilações no mesmo
  processo. API: `get_cached_nodes`, `put_cached_nodes`, `invalidate_cache`.
- `grammar/synesis_standalone.py`: parser LALR precompilado gerado via
  `lark.tools.standalone`, eliminando custo de cold-start (~52ms → ~8ms, redução ~84%).
  Ativado automaticamente em `create_parser()`; fallback para compilação da gramática se
  ausente.

### Changed
- `compiler.py`: `compile()` cria `norm_cache: dict` compartilhado entre `validate_all()`
  e `link_all()`, eliminando normalizações redundantes entre as duas fases.
- `compiler.py`: `parse_annotations()` paraleliza o parsing de >2 arquivos `.syn` via
  `ThreadPoolExecutor(max_workers=min(4, N))`. Projetos com 1-2 arquivos usam path
  sequencial sem overhead. Extrai `_parse_single_annotation()` como função de módulo
  (thread-safe).
- `compiler.py`: `_parse_nodes()` consulta `parse_cache` antes de parsear; armazena
  resultado no cache após parse+transform.
- `semantic/validator.py`: `SemanticValidator.__post_init__` pré-indexa `_code_field_names`
  (fields `CODE` no scope `ITEM`) — elimina iteração O(total_specs × total_items) em
  `_collect_item_codes()`. Remove `_norm_code()`; usa `normalize_code()` centralizado.
- `semantic/linker.py`: `Linker.link()` computa `has_relations` uma única vez antes do
  loop de items (era recalculado por chain). Remove `_norm_code()` e `_norm_bibref()`;
  usa `normalize_code()` e `normalize_bibref()` centralizados.
- `parser/lexer.py`: `create_parser()` tenta importar o parser standalone primeiro,
  patcheando `Tree`, `Token`, `UnexpectedToken` e `UnexpectedCharacters` para as classes
  oficiais do Lark antes de instanciar `Lark_StandAlone`.

### Fixed
- `semantic/validator.py`, `semantic/linker.py`: fields do tipo `CODE` com múltiplos valores
  separados por vírgula (ex: `topic: CREATOR, EARTH, HEAVENS_THE_NATURAL`) eram tratados como
  um único código, gerando falsos warnings de "código não definido na ontologia". Causa raiz:
  o token `TEXT_LINE` (prioridade 3) prevalece sobre `CODE_ELEMENT` (prioridade 2) no lexer
  contextual do Lark, tornando a regra `code_list` da gramática inacessível nesse contexto.
  Fix: `_extract_code_values()` faz split por vírgula quando o valor é uma `str` com vírgulas.

### Performance (medido em projetos reais)
| Otimização | Ganho estimado |
|---|---|
| Normalização com cache compartilhado | ~96% menos chamadas `split+join+lower` |
| Pre-indexação de field specs | ~88% menos iterações em `_collect_item_codes` |
| Parser standalone (cold-start) | ~84% (52ms → 8ms) |
| Parsing paralelo (>2 arquivos .syn) | ~70% no tempo de parse (4 workers) |
| Cache por arquivo (recompilação) | ~95% (só re-parseia arquivos modificados) |

## [0.3.0] - 2026-03-06

### Added
- `grammar/synesis.lark`: keyword `KW_GUIDELINES` e regras `guidelines_block` / `guidelines_lines`
  para suporte ao bloco `GUIDELINES...END GUIDELINES` dentro de `FIELD...END FIELD`.
- `ast/nodes.py`: campo `guidelines: Optional[str] = None` em `FieldSpec`; serializado
  automaticamente via `to_dict()` como `"guidelines"` no JSON exportado.
- `parser/transformer.py`: handler `KW_GUIDELINES`, transformers `guidelines_lines` e
  `guidelines_block`, detecção em `field_props()`, extração em `field_def_block()`.

### Notes
- Adição aditiva: templates sem `GUIDELINES` continuam compilando sem alteração.
- Semântica pass-through: o compilador armazena e exporta o conteúdo sem interpretá-lo.
- Consumidores (MCP Server, agentes de IA) lêem `guidelines` via `synesis.load()` → JSON.

## [0.2.11] - 2026-03-06

### Fixed
- `transformer.py`: replaced `@v_args(meta=True)` with `@v_args(tree=True)` in all 10
  Transformer methods to fix cross-platform incompatibility. Different Lark builds (e.g.
  Homebrew on macOS vs pip on Windows) pass arguments to `_vargs_meta` in opposite orders
  (`f(children, meta)` vs `f(meta, children)`). `@v_args(tree=True)` passes a single
  `Tree` object whose `.meta` and `.children` attributes are always stable, eliminating the
  build-dependent argument-order ambiguity that caused `'Meta' object is not subscriptable`
  on macOS.

## [0.2.10] - 2026-02-24

### Fixed
- Grammar now accepts empty SOURCE, ITEM, and ONTOLOGY blocks (no fields required for parsing).
  Previously, blocks with no fields caused a syntax error because the `_INDENT`/`_DEDENT` tokens
  were not emitted by the indentation lexer, failing before semantic validation.
  Empty blocks are now valid syntax; required-field enforcement is delegated to the semantic validator.

### Changed
- `synesis init`: renamed generated field `code_description` to `definition` in template and ontology
  files to avoid collision with the `KW_CODE` keyword token in the Lark lexer.

## [0.2.9] - 2026-02-04 - Consolidates changes since version 0.2.2

### Fixed
- Deduplication of `code_locations` in the linker to prevent duplicate CODE/CHAIN locations (transformer + linker)
- VSCode Explorer tree views now show only 1 occurrence per CODE/CHAIN (no more ITEM + CODE duplicates)
- Definitive fix for the duplication bug in CODE/CHAIN fields in the Explorer

## [0.2.8] - 2026-02-04

### Changed
- Consolidation release for CODE/CHAIN location fixes

## [0.2.7] - 2026-02-04

### Fixed
- `code_locations` now accumulates locations from multiple CODE lines instead of overwriting
- `value()` function preserves Token (subclass of str) to keep location metadata (fixes navigation in Code Explorer)

## [0.2.6] - 2026-02-04

### Added
- Post-processing with template to generate exact locations in TYPE CODE/CHAIN fields with a custom name.

### Changed
- Preservation of line tokens for single-line fields, enabling exact column calculation after parsing.

## [0.2.5] - 2026-02-04

### Added
- Exact location for TYPE CODE/CHAIN fields with a custom name, using the template after parsing.

### Changed
- Items now carry multiline line tokens to allow position calculation for CODE/CHAIN defined in the template.

## [0.2.4] - 2026-02-04

### Added
- AST now stores `code_locations` (ItemNode) and `node_locations` (ChainNode) for exact CODE/CHAIN positions, including multiline values.

### Changed
- Transformer preserves `TEXT_LINE` tokens to calculate exact columns in multiline CODE/CHAIN fields.
- Package version centralized in `pyproject.toml` (fallback via metadata/pyproject).

## [0.2.3] - 2026-02-03

### Added
- LinkedProject now includes `relation_index` with chain location/type provenance to support LSP relation navigation.

## [0.2.2] - 2026-01-23

### Fixed
- Dependencies `click` and `openpyxl` moved to required (were optional extras causing installation failures with `pipx install synesis`)
- Removed `[cli]`, `[excel]`, `[full]` extras - all compiler features now available in base installation

## [0.2.1] - 2026-01-22

### Fixed
- CI: correct Codecov v4 inputs and add optional token support
- Add regex dependency required by Lark when regex=True

## [0.2.0] - 2026-01-21

### Added
- `synesis.load()` in-memory compilation API (no disk I/O)
- `synesis.compile_string()` for single file parsing
- `MemoryCompilationResult` with `to_json_dict()`, `to_csv_tables()`, `to_dataframe()` methods
- `load_template_from_string()` in template_loader.py
- `load_bibliography_from_string()` in bib_loader.py
- `build_json_payload()` in json_export.py for in-memory JSON construction
- `build_csv_tables()` in csv_export.py for in-memory table construction
- `build_xls_workbook()` in xls_export.py for in-memory Workbook construction
- Pandas integration via `to_dataframe()` and `to_dataframes()`
- Tests for new API in tests/test_api.py
- In-memory API documentation

### Changed
- Dependencies `click` and `openpyxl` are now optional
- Reorganized dependencies in pyproject.toml: `[cli]`, `[excel]`, `[full]`, `[dev]`
- Exporters refactored to separate data construction from disk writing

  

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
---

[0.4.6]: https://github.com/synesis-lang/synesis/releases/tag/v0.4.6
[0.4.5]: https://github.com/synesis-lang/synesis/releases/tag/v0.4.5
[0.4.4]: https://github.com/synesis-lang/synesis/releases/tag/v0.4.4
[0.4.3]: https://github.com/synesis-lang/synesis/releases/tag/v0.4.3
[0.4.2]: https://github.com/synesis-lang/synesis/releases/tag/v0.4.2
[0.4.1]: https://github.com/synesis-lang/synesis/releases/tag/v0.4.1
[0.4.0]: https://github.com/synesis-lang/synesis/releases/tag/v0.4.0
[0.3.0]: https://github.com/synesis-lang/synesis/releases/tag/v0.3.0
[0.2.2]: https://github.com/synesis-lang/synesis/releases/tag/v0.2.2
[0.2.1]: https://github.com/synesis-lang/synesis/releases/tag/v0.2.1
[0.2.0]: https://github.com/synesis-lang/synesis/releases/tag/v0.2.0
[0.1.0]: https://github.com/synesis-lang/synesis/releases/tag/v0.1.0
