# Synesis Error Inventory

## Propósito deste documento

Este arquivo é a **especificação de referência** para todas as mensagens de erro e aviso que o compilador Synesis deve produzir. Para cada situação problemática, ele registra:

- **A descrição técnica** do que causou o problema
- **A mensagem pedagógica** — redigida para pesquisadores sem formação técnica, seguindo o princípio de que *o usuário nunca deve ficar sem saber o que fazer*
- **O status de implementação** — se a mensagem já existe no compilador ou ainda precisa ser implementada

Toda mensagem de erro segue a mesma estrutura interna:
1. **O que aconteceu** — descrição direta e específica do problema
2. **Por que é um problema** — contexto mínimo que explica a regra violada
3. **O que fazer** — instrução concreta de correção

---

## Convenções

`{variável}` — partes dinâmicas preenchidas com dados reais em tempo de execução

**(ERRO)** — impede a compilação ou invalida os dados; bloqueia a exportação

**(AVISO)** — algo incompleto ou incomum; não bloqueia, mas deve ser investigado

**[implementado]** — mensagem já existe no compilador (classe indicada entre parênteses)

**[pendente]** — ainda não implementada

---

## Estrutura de apresentação das mensagens

Toda mensagem deve ser apresentada com **contexto espacial completo**, independentemente do canal (terminal ou extensão VSCode):

```
ERRO  arquivo.syn  linha 42, coluna 7
  O código `Acietacao_Social` não está definido na ontologia.
  Você quis dizer `Aceitacao_Social`?
  Para criar o conceito, adicione em um arquivo .syno:
      ONTOLOGY Aceitacao_Social
          description: ...
      END ONTOLOGY
```

Os campos obrigatórios do envelope são: **nível** (ERRO/AVISO), **arquivo**, **linha** e **coluna**. O trecho do código com marcador visual (`^^^`) deve ser exibido quando tecnicamente viável.

### Integração com o Language Server Protocol (LSP)

Na extensão VSCode, as mensagens se dividem em duas camadas:

- **Diagnóstico inline** (a "cobrinha" vermelha/amarela): exibe a **descrição curta** do problema — primeira frase da mensagem, sem a instrução de correção.
- **Hover** (ao passar o mouse): exibe a **mensagem completa**, incluindo a explicação do porquê e a instrução de correção.
- **Code Actions** (lâmpada amarela): quando aplicável, oferece uma **correção automática** sugerida — por exemplo, aplicar a grafia correta identificada por similaridade, ou inserir o campo obrigatório ausente.

Erros de declaração de template (erros 37–55) devem incluir no hover a nota: *"Este problema está na definição do template, não nas anotações. Se você não é o autor do template, avise o coordenador do projeto."*

### Sugestões por similaridade ("Você quis dizer...?")

Para qualquer erro que envolva um identificador escrito pelo usuário — `@bibref`, nome de conceito, nome de relação, nome de campo — o compilador deve tentar encontrar a alternativa mais próxima usando distância de edição (algoritmo de Levenshtein). Se a similaridade ultrapassar o limiar mínimo, a mensagem inclui a sugestão antes da instrução de correção.

### Normalização silenciosa com aviso informativo

Alguns problemas de forma não impedem a compilação e podem ser corrigidos automaticamente pelo compilador (ex: diferença de maiúsculas/minúsculas em `@bibref`). Nesses casos, a abordagem correta **não é gerar um erro** — é normalizar internamente e emitir um **aviso informativo**, explicando o que foi feito. Isso evita que o usuário se pergunte "por que funcionou se eu escrevi diferente?".

Modelo de aviso informativo:
```
AVISO  arquivo.syn  linha 12
  A referência `@Smith2024` foi resolvida como `@smith2024` (normalização de maiúsculas).
  O arquivo compilou corretamente, mas considere padronizar a grafia para evitar ambiguidade.
```

Esse padrão se aplica a qualquer normalização que o compilador faça implicitamente: caixa de identificadores, espaços extras, codificação de caracteres, etc.

---

## Erros de Vínculo Bibliográfico

**1.** `@bibref` em SOURCE inexistente no arquivo `.bib`

> A referência `@{bibref}` não foi encontrada no arquivo de referências (`.bib`). Verifique se o identificador está escrito corretamente — ele deve corresponder exatamente ao campo `ID` da entrada BibTeX.
> *(Se houver entrada similar)* Você quis dizer `@{sugestao}`?
> Consulte o arquivo `.bib` para ver as referências disponíveis.
>
> **(AVISO)** [implementado — `UnregisteredSource`]

**2.** ITEM sem SOURCE correspondente no mesmo arquivo

> Este ITEM referencia `@{bibref}`, mas não há nenhum bloco SOURCE com essa referência neste arquivo. Todo ITEM precisa de um SOURCE correspondente no mesmo arquivo.
> Crie um bloco `SOURCE @{bibref}` antes deste ITEM, ou verifique se a referência está correta.
>
> **(ERRO)** [implementado — `OrphanItem`]

---

## Erros de Vínculo Ontológico

**3.** `code:` referenciando conceito ausente na ontologia

> O código `{code}` não está definido na ontologia do projeto. Todos os códigos usados nas anotações precisam ter um conceito correspondente declarado em um bloco ONTOLOGY.
> *(Se houver conceito similar)* Você quis dizer `{sugestao}`?
> Para criar o conceito, adicione em um arquivo `.syno`:
> ```
> ONTOLOGY {code}
>     description: ...
> END ONTOLOGY
> ```
>
> **(AVISO)** [implementado — `UndefinedCode`]

**4.** Nó de conceito em `chain:` (posição ímpar) referenciando conceito ausente na ontologia

> O conceito `{code}` usado nesta cadeia não está definido na ontologia do projeto. Todos os nós conceituais de uma cadeia precisam ter entradas ONTOLOGY correspondentes.
> *(Se houver conceito similar)* Você quis dizer `{sugestao}`?
> Verifique a grafia ou crie o conceito no arquivo de ontologia do projeto.
>
> **(AVISO)** [implementado — `UndefinedCode`]

**5.** ONTOLOGY definido mas nenhum campo configurado em ONTOLOGY FIELDS no template

> O projeto contém blocos ONTOLOGY, mas o template não declara nenhum campo em `ONTOLOGY FIELDS`. Sem essa configuração, os campos dos conceitos não podem ser validados.
> Este problema está na definição do template. Se você não é o autor do template, avise o coordenador do projeto.
> Para corrigir, adicione ao template:
> ```
> ONTOLOGY FIELDS
>     REQUIRED nome_do_campo
> END ONTOLOGY FIELDS
> ```
>
> **(ERRO)** [pendente]

**6.** Campo declarado em ONTOLOGY FIELDS sem FIELD correspondente com SCOPE ONTOLOGY

> O campo `{field_name}` está listado em `ONTOLOGY FIELDS`, mas não há uma definição `FIELD` correspondente com `SCOPE ONTOLOGY` no template. Cada campo listado precisa ter sua própria definição completa.
> Este problema está na definição do template. Se você não é o autor do template, avise o coordenador do projeto.
> Adicione ao template:
> ```
> FIELD {field_name} TYPE TEXT
>     SCOPE ONTOLOGY
> END FIELD
> ```
>
> **(ERRO)** [pendente]

---

## Erros de Vínculo de Relações

**7.** RELATION usada em `chain:` qualificada não declarada em RELATIONS do template

> A relação `{relation}` usada nesta cadeia não está declarada no template para este campo.
> *(Se houver relação similar)* Você quis dizer `{sugestao}`?
> As relações disponíveis são: `{valid_relations}`. Use uma das relações listadas ou peça ao coordenador do projeto que inclua a nova relação no template.
>
> **(ERRO)** [implementado — `InvalidChainRelation`]

**8.** `chain:` qualificada usada sem bloco RELATIONS definido no template

> Esta cadeia usa relações nomeadas (ex: `Conceito -> RELACAO -> Conceito`), mas o template não define nenhum bloco `RELATIONS` para este campo de cadeia.
> Se o template usa cadeias simples, reescreva a cadeia sem relações: `Conceito -> Conceito`. Se deseja usar relações nomeadas, peça ao coordenador do projeto que adicione um bloco `RELATIONS` à definição do campo no template.
>
> **(ERRO)** [pendente]

**9.** `chain:` simples (sem RELATIONS) usada quando template define RELATIONS

> O template exige que as cadeias usem relações nomeadas, mas esta cadeia foi escrita sem relações. As relações disponíveis são: `{valid_relations}`.
> Reescreva a cadeia no formato: `Conceito -> RELACAO -> Conceito`. Consulte a documentação do projeto para saber quais relações usar.
>
> **(ERRO)** [pendente]

---

## Erros de Estrutura de CHAIN

**10.** Conceito em posição par (posição de relação) em chain qualificada

> A estrutura desta cadeia está incorreta: há um conceito onde deveria haver uma relação.
> Encontrado: `{elemento_anterior} -> {elemento_problematico} -> ...`
> Esperado:  `[Conceito] -> [RELAÇÃO] -> [Conceito]`
> Em cadeias qualificadas, posições pares (após cada `->`) são sempre tipos de relação, não conceitos. Revise a ordem dos elementos.
>
> **(ERRO)** [implementado — `MalformedQualifiedChain`]

**11.** RELATION em posição ímpar (posição de conceito) em chain qualificada

> A estrutura desta cadeia está incorreta: há uma relação onde deveria haver um conceito.
> Encontrado: `... -> {elemento_anterior} -> {elemento_problematico} -> ...`
> Esperado:  `[Conceito] -> [RELAÇÃO] -> [Conceito]`
> Em cadeias qualificadas, posições ímpares são sempre conceitos, não tipos de relação. Revise a ordem dos elementos.
>
> **(ERRO)** [implementado — `MalformedQualifiedChain`]

**12.** `chain:` com apenas 1 elemento quando ARITY >= 2

> Esta cadeia tem poucos elementos. O template exige `{expected}` conceitos, mas foram encontrados apenas `{found}`.
> Uma cadeia precisa conectar pelo menos dois conceitos com `->`. Acrescente os elementos faltantes até satisfazer o requisito mínimo.
>
> **(ERRO)** [implementado — `ChainArityViolation`]

**13.** `chain:` sem operador `->` entre elementos

> Os elementos desta cadeia não estão separados pelo operador `->`. Sem a seta, o compilador não consegue identificar onde um elemento termina e o próximo começa.
> Reescreva a cadeia conectando os elementos com `->`, por exemplo:
> `ConceitoA -> ConceitoB` ou `ConceitoA -> RELACAO -> ConceitoB`
>
> **(ERRO)** [pendente]

**14.** Nome de conceito em `chain:` idêntico ao nome de uma relação do mesmo campo

> O elemento `{name}` aparece nesta cadeia em posição de conceito, mas também está declarado como relação no template para este campo. Essa ambiguidade impede o compilador de determinar o papel do elemento na cadeia.
> Renomeie o conceito na ontologia para que seja distinto dos nomes de relação, ou renomeie a relação no template.
>
> **(ERRO)** [pendente]

**15.** Conceito em `chain:` contendo espaços (sem underscore)

> O elemento `{concept}` contém espaços, o que não é permitido em nomes de conceitos. O compilador interpreta cada espaço como separador entre elementos distintos da cadeia.
> Substitua os espaços por underscore. Por exemplo: `Aceitacao_Social` em vez de `Aceitacao Social`.
>
> **(ERRO)** [pendente]

---

## Erros de BUNDLE

**16.** Campo de BUNDLE presente sem o(s) campo(s) parceiro(s) do mesmo bundle

> Os campos `{bundle_str}` formam um pacote indivisível (bundle) neste bloco — eles representam informação composta e devem sempre aparecer juntos. Um ou mais campos do pacote estão ausentes: `{missing_fields}`.
> Adicione os campos faltantes ou remova todos os campos do pacote. Um bundle parcial não é válido.
>
> **(ERRO)** [implementado — `MissingBundleField`]

**17.** Contagem de ocorrências de campo1 do bundle diferente de campo2

> Os campos `{bundle_str}` formam um pacote indivisível (bundle) e devem aparecer o mesmo número de vezes neste bloco. Contagem atual: `{count_str}`.
> Acrescente ou remova entradas até que todos os campos do pacote tenham a mesma quantidade de ocorrências. Cada ocorrência de um campo deve ter uma ocorrência correspondente dos demais.
>
> **(ERRO)** [implementado — `BundleCountMismatch`]

**18.** BUNDLE declarado no template com apenas um campo

> O bundle `{bundle_name}` no template foi declarado com apenas um campo. Um bundle precisa de pelo menos dois campos — ele existe para garantir que informações relacionadas apareçam sempre juntas.
> Este problema está na definição do template. Se você não é o autor do template, avise o coordenador do projeto.
> Adicione os demais campos ao bundle ou remova a declaração BUNDLE, tornando o campo simplesmente REQUIRED ou OPTIONAL.
>
> **(ERRO)** [pendente]

**19.** ITEM sem nenhuma ocorrência de BUNDLE obrigatório

> Este bloco ITEM não contém nenhuma ocorrência do pacote de campos obrigatório `{bundle_name}`. O template exige que este pacote apareça pelo menos uma vez.
> Adicione ao bloco os campos `{bundle_fields}`, sempre juntos e na mesma quantidade.
>
> **(ERRO)** [implementado — `MissingRequiredField`]

---

## Erros de Campos Obrigatórios

**20.** Campo declarado REQUIRED ausente no bloco ITEM

> O campo `{field_name}` é obrigatório neste bloco ITEM, mas não foi encontrado.
> Adicione a linha `{field_name}: <valor>` ao bloco antes de `END ITEM`.
>
> **(ERRO)** [implementado — `MissingRequiredField`]

**21.** Campo declarado REQUIRED ausente no bloco SOURCE

> O campo `{field_name}` é obrigatório neste bloco SOURCE, mas não foi encontrado.
> Adicione a linha `{field_name}: <valor>` ao bloco antes de `END SOURCE`.
>
> **(ERRO)** [implementado — `MissingRequiredField`]

**22.** Campo declarado REQUIRED ausente no bloco ONTOLOGY

> O campo `{field_name}` é obrigatório neste bloco ONTOLOGY, mas não foi encontrado.
> Adicione a linha `{field_name}: <valor>` ao bloco antes de `END ONTOLOGY`.
>
> **(ERRO)** [implementado — `MissingRequiredField`]

**23.** ITEM sem nenhum campo (bloco vazio)

> Este bloco ITEM está vazio — não contém nenhum campo com conteúdo. Um ITEM sem campos não representa nenhuma unidade de análise.
> Adicione os campos exigidos pelo template ou remova o bloco se ele foi criado por engano.
>
> **(ERRO)** [pendente]

**24.** SOURCE sem nenhum ITEM associado

> O bloco `SOURCE @{bibref}` não possui nenhum ITEM associado. Um SOURCE existe para contextualizar unidades de análise — sem ITEMs, a fonte foi registrada mas nunca analisada.
> Verifique se há ITEMs com essa referência em outro arquivo do projeto, ou adicione pelo menos um ITEM a este SOURCE.
>
> **(AVISO)** [implementado — `SourceWithoutItems`]

---

## Erros de Tipo de Campo

**25.** Valor fora do intervalo FORMAT em campo SCALE

> O valor `{value}` está fora do intervalo permitido para o campo `{field_name}`. Este campo aceita apenas valores entre `{min}` e `{max}`.
> Corrija o valor para que fique dentro desse intervalo.
>
> **(ERRO)** [implementado — `ScaleOutOfRange`]

**26.** Valor decimal em campo SCALE com intervalo inteiro

> O valor `{value}` tem casas decimais, mas o campo `{field_name}` foi declarado com um intervalo de inteiros (`FORMAT [{min}..{max}]`). Este campo aceita apenas números inteiros.
> Use um valor inteiro dentro do intervalo, ou peça ao coordenador do projeto que ajuste o FORMAT para aceitar decimais (ex: `FORMAT [0.0..5.0]`).
>
> **(ERRO)** [pendente]

**27.** Valor não declarado em VALUES de campo ENUMERATED

> O valor `{value}` não é reconhecido para o campo `{field_name}`. Este campo aceita apenas valores de uma lista fechada.
> *(Se houver valor similar)* Você quis dizer `{sugestao}`?
> Valores disponíveis: `{valid_values_truncated}`.*(Se a lista for longa)* — e outros `{n}` valores. Consulte o template para a lista completa.
> Se o valor que você precisa não está na lista, peça ao coordenador do projeto que o inclua no template.
>
> **(ERRO)** [implementado — `InvalidEnumeratedValue`]

**28.** Valor não declarado em VALUES de campo ORDERED

> O valor `{value}` não é válido para o campo `{field_name}`. Este campo usa uma escala ordenada com opções específicas.
> *(Se houver valor similar)* Você quis dizer `{sugestao}`?
> Opções disponíveis: `{valid_options_truncated}`.*(Se a lista for longa)* — e outras `{n}`. Consulte o template para a lista completa.
> Você pode usar o rótulo textual ou o número de posição na escala.
>
> **(ERRO)** [implementado — `InvalidOrderedValue`]

**29.** Data em formato inválido em campo DATE

> A data informada no campo `{field_name}` não está em um formato reconhecido. O formato aceito é `AAAA-MM-DD`.
> Por exemplo: `2024-03-15` para 15 de março de 2024.
>
> **(ERRO)** [implementado — `InvalidFieldType`]

**30.** Valor numérico em campo TEXT ou QUOTATION

> O campo `{field_name}` espera texto, mas recebeu um valor que parece ser apenas um número. Campos de texto e citação precisam de conteúdo textual.
> Se o número faz parte de uma citação ou nota, escreva-o como parte de uma frase. Se for um dado numérico, verifique se o campo correto não seria do tipo SCALE ou ORDERED.
>
> **(ERRO)** [implementado — `InvalidFieldType`]

**31.** Campo CODE com o mesmo código repetido na mesma ocorrência

> O código `{code}` aparece mais de uma vez no campo `{field_name}` neste bloco. Códigos repetidos não acrescentam informação e podem distorcer a contagem nas exportações.
> Remova a ocorrência duplicada e mantenha o código apenas uma vez.
>
> **(AVISO)** [pendente]

**32.** Campo TOPIC recebendo valor com espaços

> O valor do campo `{field_name}` contém espaços, o que não é permitido para campos do tipo TOPIC. Espaços são interpretados como separadores e causariam ambiguidade na hierarquia ontológica.
> Use underscore no lugar de espaços. Por exemplo: `Tecnologia_Renovavel` em vez de `Tecnologia Renovavel`.
>
> **(ERRO)** [pendente]

**33.** Nome de código ou conceito com caracteres inválidos

> O nome `{name}` contém o caractere inválido `{invalid_char}`, que não é permitido em identificadores Synesis. Identificadores aceitam apenas letras, números e underscore, e devem começar com uma letra.
> *(Se houver forma corrigida óbvia)* Você quis dizer `{sugestao}`?
> Por exemplo: use `custo_alto` em vez de `custo-alto`; `dado_2024` em vez de `2024_dado`.
>
> **(ERRO)** [pendente]

---

## Erros de Escopo

**34.** Campo com SCOPE ITEM usado em bloco SOURCE

> O campo `{field_name}` só pode ser usado em blocos ITEM, mas foi encontrado em um bloco SOURCE.
> Mova este campo para o ITEM correspondente. Se você acredita que o campo deveria pertencer ao SOURCE, avise o coordenador do projeto para revisar o template.
>
> **(ERRO)** [implementado — `ForbiddenFieldPresent`]

**35.** Campo com SCOPE SOURCE usado em bloco ITEM

> O campo `{field_name}` só pode ser usado em blocos SOURCE, mas foi encontrado em um bloco ITEM.
> Mova este campo para o SOURCE correspondente. Se você acredita que o campo deveria pertencer ao ITEM, avise o coordenador do projeto para revisar o template.
>
> **(ERRO)** [implementado — `ForbiddenFieldPresent`]

**36.** Campo com SCOPE ONTOLOGY usado em bloco ITEM ou SOURCE

> O campo `{field_name}` só pode ser usado em blocos ONTOLOGY, mas foi encontrado em um bloco `{block_type}`. Este campo pertence à definição de conceitos da ontologia, não às anotações.
> Se você está anotando uma fonte, este campo não se aplica aqui. Se quiser registrar uma característica de um conceito, faça-o no arquivo de ontologia (`.syno`).
>
> **(ERRO)** [implementado — `ForbiddenFieldPresent`]

**37.** Campo TOPIC (SCOPE ONTOLOGY) usado fora de bloco ONTOLOGY

> O campo `{field_name}` é exclusivo de blocos ONTOLOGY e não pode ser usado em `{block_type}`. Campos do tipo TOPIC organizam a ontologia em categorias temáticas e não têm sentido fora de um bloco ONTOLOGY.
> Se você precisa categorizar uma anotação, verifique com o coordenador do projeto qual campo de classificação usar nos blocos ITEM ou SOURCE.
>
> **(ERRO)** [implementado — `ForbiddenFieldPresent`]

**38.** Campo CHAIN (SCOPE ITEM) usado em bloco ONTOLOGY

> O campo `{field_name}` é exclusivo de blocos ITEM e não pode ser usado em um bloco ONTOLOGY. Cadeias causais são instrumentos de análise das anotações — elas registram relações observadas nas fontes, não características dos conceitos.
> Se você quer documentar relações entre conceitos na ontologia, use campos do tipo TEXT ou MEMO para isso.
>
> **(ERRO)** [implementado — `ForbiddenFieldPresent`]

---

## Erros de Declaração de Template

> **Nota para todos os erros desta seção:** os problemas abaixo estão na definição das regras do projeto (arquivo `.synt`), não nas anotações. Se você é pesquisador e não o autor do template, avise o coordenador do projeto.

**39.** Campo listado em SOURCE FIELDS sem FIELD correspondente definido

> O campo `{field_name}` está listado em `SOURCE FIELDS`, mas não há uma definição `FIELD` correspondente no template. Sem a definição, o compilador não sabe que tipo de dado o campo aceita nem como validá-lo.
> Adicione ao template:
> ```
> FIELD {field_name} TYPE TEXT
>     SCOPE SOURCE
> END FIELD
> ```
>
> **(ERRO)** [pendente]

**40.** Campo listado em ITEM FIELDS sem FIELD correspondente definido

> O campo `{field_name}` está listado em `ITEM FIELDS`, mas não há uma definição `FIELD` correspondente no template.
> Adicione ao template:
> ```
> FIELD {field_name} TYPE TEXT
>     SCOPE ITEM
> END FIELD
> ```
>
> **(ERRO)** [pendente]

**41.** Campo listado em ONTOLOGY FIELDS sem FIELD correspondente definido

> O campo `{field_name}` está listado em `ONTOLOGY FIELDS`, mas não há uma definição `FIELD` correspondente no template.
> Adicione ao template:
> ```
> FIELD {field_name} TYPE TEXT
>     SCOPE ONTOLOGY
> END FIELD
> ```
>
> **(ERRO)** [pendente]

**42.** FIELD definido sem estar listado em SOURCE/ITEM/ONTOLOGY FIELDS

> O campo `{field_name}` está definido no template, mas não aparece em nenhum bloco `SOURCE FIELDS`, `ITEM FIELDS` ou `ONTOLOGY FIELDS`. Um campo definido mas não listado nunca será reconhecido nas anotações — a definição existe, mas está inacessível.
> Inclua `{field_name}` no bloco de campos correspondente ao seu escopo (`{scope} FIELDS`), ou remova a definição se ela não for necessária.
>
> **(AVISO)** [pendente]

**43.** FIELD sem declaração de SCOPE

> O campo `{field_name}` não declara em qual tipo de bloco ele pode ser usado. Sem o escopo, o compilador não sabe onde aceitar ou rejeitar este campo.
> Adicione ao campo uma das declarações: `SCOPE SOURCE`, `SCOPE ITEM` ou `SCOPE ONTOLOGY`.
>
> **(ERRO)** [pendente]

**44.** FIELD sem declaração de TYPE

> O campo `{field_name}` não declara o tipo de dado que aceita. Sem o tipo, não é possível validar os valores inseridos pelos pesquisadores.
> Adicione ao campo uma declaração como `TYPE TEXT`, `TYPE QUOTATION`, `TYPE CODE`, `TYPE CHAIN`, `TYPE DATE`, etc.
>
> **(ERRO)** [pendente]

**45.** FIELD com valor inválido para SCOPE

> O campo `{field_name}` tem um valor de escopo desconhecido: `{value}`. O compilador não sabe a qual tipo de bloco este campo pertence.
> Os únicos valores válidos são `SOURCE`, `ITEM` e `ONTOLOGY`. Corrija a declaração de escopo.
>
> **(ERRO)** [pendente]

**46.** FIELD com múltiplas declarações de TYPE

> O campo `{field_name}` tem mais de uma declaração `TYPE`. Cada campo pode ter apenas um tipo de dado.
> Mantenha somente a declaração de tipo desejada e remova as demais.
>
> **(ERRO)** [pendente]

**47.** TYPE CHAIN sem ARITY quando semântica exige mínimo de nós

> O campo `{field_name}` é do tipo CHAIN, mas não declara `ARITY`. Sem ARITY, o compilador não pode verificar se as cadeias escritas pelos pesquisadores têm o número mínimo de conceitos exigidos pela metodologia.
> Adicione uma declaração como `ARITY >= 2` para garantir que toda cadeia tenha ao menos dois conceitos conectados.
>
> **(ERRO)** [pendente]

**48.** ARITY incompatível com o número de RELATIONS declaradas

> O campo `{field_name}` declara `ARITY >= {arity}`, o que exige pelo menos `{arity}` conceitos por cadeia — mas apenas `{n_relations}` relação(ões) está(ão) definida(s) em `RELATIONS`. Para conectar `{arity}` conceitos em sequência, são necessárias pelo menos `{arity_minus_1}` relações.
> Adicione as relações faltantes ao bloco `RELATIONS` ou reduza o valor de `ARITY`.
>
> **(ERRO)** [pendente]

**49.** TYPE ORDERED sem bloco VALUES

> O campo `{field_name}` é do tipo ORDERED, mas não define um bloco `VALUES` com as opções válidas e sua ordem. Sem isso, não há como validar os valores inseridos nem apresentar a escala aos pesquisadores.
> Adicione um bloco `VALUES` listando as opções em ordem crescente, por exemplo:
> ```
> VALUES
>     baixo
>     medio
>     alto
> END VALUES
> ```
>
> **(ERRO)** [pendente]

**50.** TYPE ENUMERATED sem bloco VALUES

> O campo `{field_name}` é do tipo ENUMERATED, mas não define um bloco `VALUES` com as opções válidas. Sem isso, qualquer valor seria aceito, perdendo o controle sobre o vocabulário.
> Adicione um bloco `VALUES` listando todas as opções aceitas para este campo.
>
> **(ERRO)** [pendente]

**51.** TYPE SCALE sem declaração FORMAT

> O campo `{field_name}` é do tipo SCALE, mas não declara o intervalo numérico permitido. Sem o intervalo, o compilador não pode verificar se os valores estão dentro da faixa esperada.
> Adicione uma declaração como `FORMAT [0..10]` para definir o valor mínimo e máximo aceitos.
>
> **(ERRO)** [pendente]

**52.** Sintaxe inválida na declaração FORMAT de campo SCALE

> O intervalo declarado em `FORMAT` para o campo `{field_name}` não está no formato esperado. O formato correto usa colchetes e dois pontos como separador: `[mínimo..máximo]`.
> Exemplos válidos: `[1..5]`, `[0..100]`, `[0.0..1.0]`. Verifique se os colchetes estão presentes e se o separador é `..` (dois pontos seguidos).
>
> **(ERRO)** [pendente]

**53.** Operador inválido na declaração ARITY

> A declaração `ARITY` do campo `{field_name}` usa um operador não reconhecido: `{operator}`.
> Os operadores válidos são: `>=`, `>`, `<=`, `<`, `=`. Por exemplo: `ARITY >= 2` significa "ao menos dois conceitos por cadeia".
>
> **(ERRO)** [pendente]

**54.** `FORMAT` declarado em campo que não é TYPE SCALE

> O campo `{field_name}` declara `FORMAT`, mas seu tipo é `{type}`. A declaração `FORMAT [min..max]` é exclusiva de campos do tipo SCALE — ela não tem efeito nem significado em outros tipos.
> Este problema está na definição do template. Remova a declaração `FORMAT` ou altere o tipo do campo para `SCALE`.
>
> **(ERRO)** [pendente]

**55.** `ARITY` declarado em campo que não é TYPE CHAIN

> O campo `{field_name}` declara `ARITY`, mas seu tipo é `{type}`. A declaração `ARITY` é exclusiva de campos do tipo CHAIN — ela define o número mínimo de conceitos em uma cadeia e não se aplica a outros tipos de campo.
> Este problema está na definição do template. Remova a declaração `ARITY` ou altere o tipo do campo para `CHAIN`.
>
> **(ERRO)** [pendente]

**56.** RELATIONS definido em campo que não é TYPE CHAIN

> O campo `{field_name}` define um bloco `RELATIONS`, mas seu tipo é `{type}`, não `CHAIN`. Blocos `RELATIONS` descrevem os tipos de vínculo possíveis entre conceitos — eles só fazem sentido em campos do tipo CHAIN.
> Remova o bloco `RELATIONS` ou altere o tipo do campo para `CHAIN`.
>
> **(ERRO)** [pendente]

**57.** Dois ou mais blocos ONTOLOGY FIELDS no mesmo template

> O template contém mais de um bloco `ONTOLOGY FIELDS`. Apenas um bloco desse tipo é permitido por template — ter dois causaria ambiguidade sobre quais campos são válidos nos conceitos.
> Unifique todas as declarações em um único bloco `ONTOLOGY FIELDS`.
>
> **(ERRO)** [pendente]

**58.** Valor em bloco VALUES com espaço no início ou no fim

> O valor `"{value}"` declarado no campo `{field_name}` contém espaço em branco no início ou no final. Esses espaços invisíveis fariam com que o valor não fosse reconhecido quando usado nas anotações — o compilador compararia `"alto "` com `"alto"` e não encontraria correspondência.
> Remova os espaços extras ao redor do valor na declaração do template.
>
> **(ERRO)** [pendente]

**59.** Valores duplicados dentro de um mesmo bloco VALUES

> O campo `{field_name}` tem o valor `{value}` declarado mais de uma vez no bloco `VALUES`. Valores duplicados causam ambiguidade e podem gerar resultados inconsistentes na exportação.
> Remova a entrada duplicada.
>
> **(ERRO)** [pendente]

**60.** Bloco GUIDELINES sem END GUIDELINES correspondente

> O bloco `GUIDELINES` do campo `{field_name}` foi aberto, mas não foi fechado com `END GUIDELINES`. O compilador não consegue determinar onde o bloco termina e o que vem depois.
> Adicione `END GUIDELINES` ao final do bloco de instruções.
>
> **(ERRO)** [pendente]

---

## Erros de Estrutura do Projeto

**61.** Arquivo `.syn` incluído sem bloco INCLUDE ANNOTATIONS no `.synp`

> O arquivo `{filename}` (extensão `.syn`) está sendo referenciado, mas o arquivo de projeto não possui um bloco `INCLUDE ANNOTATIONS`. Sem essa declaração, o compilador não sabe que deve carregar arquivos de anotação.
> Adicione ao arquivo de projeto (`.synp`):
> ```
> INCLUDE ANNOTATIONS "{filename}"
> ```
>
> **(ERRO)** [pendente]

**62.** Arquivo `.syno` incluído sem bloco INCLUDE ONTOLOGY no `.synp`

> O arquivo `{filename}` (extensão `.syno`) está sendo referenciado, mas o arquivo de projeto não possui um bloco `INCLUDE ONTOLOGY`. Sem essa declaração, a ontologia não será carregada e os códigos não poderão ser validados.
> Adicione ao arquivo de projeto (`.synp`):
> ```
> INCLUDE ONTOLOGY "{filename}"
> ```
>
> **(ERRO)** [pendente]

**63.** Arquivo `.bib` ausente ou não encontrado no caminho declarado

> O arquivo de referências bibliográficas `{filename}` declarado no projeto não foi encontrado no caminho indicado. Sem ele, nenhuma referência `@bibref` pode ser validada.
> Verifique se o arquivo existe e se o caminho está correto. O caminho deve ser relativo à pasta onde está o arquivo de projeto (`.synp`).
>
> **(ERRO)** [pendente]

**64.** Arquivo `.synt` ausente ou não encontrado no caminho declarado

> O arquivo de template `{template_path}` declarado no projeto não foi encontrado. Sem o template, nenhuma validação semântica pode ser realizada.
> Verifique se o arquivo existe no caminho `{template_path}` (relativo à pasta do projeto). Se o arquivo foi renomeado ou movido, atualize o caminho no arquivo de projeto.
>
> **(ERRO)** [implementado — `MissingTemplateFile`]

**65.** PROJECT sem TEMPLATE declarado

> O arquivo de projeto não declara nenhum template. O template é obrigatório — ele define as regras de validação para todas as anotações do projeto. Sem ele, o compilador não tem como verificar se as anotações estão corretas.
> Adicione ao bloco PROJECT:
> ```
> TEMPLATE "nome_do_arquivo.synt"
> ```
>
> **(ERRO)** [pendente]

**66.** Dois blocos PROJECT no mesmo arquivo `.synp`

> Este arquivo de projeto contém dois blocos `PROJECT`. Apenas um bloco PROJECT é permitido por arquivo — o compilador não saberia qual dos dois usar como ponto de entrada.
> Remova o bloco duplicado ou separe os projetos em arquivos `.synp` distintos.
>
> **(ERRO)** [pendente]

**67.** Data `MODIFIED` anterior à data `CREATED` no bloco METADATA

> A data de modificação `{modified}` é anterior à data de criação `{created}` declarada no bloco METADATA do projeto. Um projeto não pode ter sido modificado antes de existir.
> Verifique as datas e corrija a que estiver incorreta. O formato esperado é `AAAA-MM-DD`.
>
> **(AVISO)** [pendente]

---

## Erros de Unicidade e Duplicidade

**68.** Dois blocos ONTOLOGY com o mesmo nome de conceito

> O conceito `{concept_name}` está definido mais de uma vez na ontologia do projeto (em `{file_a}` e `{file_b}`). Cada conceito deve ter um nome único em todo o projeto — duplicatas causariam ambiguidade sobre qual definição usar.
> Verifique se os dois blocos representam o mesmo conceito. Se sim, unifique-os em um único bloco ONTOLOGY. Se não, renomeie um deles para que os nomes sejam distintos.
>
> **(ERRO)** [pendente]

**69.** Dois campos FIELD com o mesmo nome no template

> O campo `{field_name}` está definido mais de uma vez no template. Nomes de campos devem ser únicos — a duplicata impediria o compilador de determinar qual definição aplicar.
> Remova a definição duplicada ou renomeie um dos campos se eles representam informações diferentes.
>
> **(ERRO)** [pendente]

**70.** Mesmo `@bibref` declarado em dois blocos SOURCE distintos no mesmo arquivo

> A referência `@{bibref}` aparece em dois blocos SOURCE diferentes neste arquivo. Cada referência bibliográfica pode ter apenas um bloco SOURCE por arquivo — ter dois tornaria ambíguo a qual bloco os ITEMs pertencem.
> Unifique os dois blocos SOURCE em um único, ou distribua as anotações em arquivos `.syn` separados.
>
> **(ERRO)** [pendente]

**71.** Dois blocos ONTOLOGY com `description` idêntica

> Os conceitos `{concept_a}` e `{concept_b}` têm exatamente a mesma descrição. Isso geralmente indica um erro de cópia — dois conceitos distintos não devem ter definições idênticas.
> Revise as definições e diferencie as descrições, ou verifique se os dois conceitos deveriam ser um único.
>
> **(AVISO)** [pendente]
