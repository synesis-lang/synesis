# case-studies-Tests

Projetos de teste para o compilador Synesis. Cada projeto isola um grupo de erros do inventário
`synesis/synesis-error-inventory.md`. Os arquivos contêm comentários `#` explicando o objetivo
de cada teste e o resultado esperado.

## Estrutura

| Projeto | Erros cobertos | Descrição |
|---------|---------------|-----------|
| [T01-Bibliographic-Ontology-Links](T01-Bibliographic-Ontology-Links/) | 1, 2, 3, 4, 24, 68, 70, 71 | Vínculos bibliográficos e ontológicos |
| [T02-Chain-Relations](T02-Chain-Relations/) | 7, 8, 9, 10, 11, 12, 13, 14, 15 | Estrutura de CHAIN e relações |
| [T03-Bundle](T03-Bundle/) | 16, 17, 18, 19 | Erros de BUNDLE |
| [T04-Fields-Types-Scope](T04-Fields-Types-Scope/) | 20, 21, 22, 23, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38 | Campos obrigatórios, tipos e escopo |
| [T05-Template-Declaration](T05-Template-Declaration/) | 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 69 | Erros de declaração de template |
| [T06-Project-Structure](T06-Project-Structure/) | 5, 6, 61, 62, 63, 64, 65, 66, 67 | Estrutura de projeto e configuração |

## Convenções

- Cada erro tem um comentário `# ERRO N` imediatamente acima do trecho que o provoca.
- O comentário indica a **classe do compilador** (se já implementada) ou `[pendente]`.
- O comentário inclui o **resultado esperado** — a mensagem que o compilador deve emitir.
- Arquivos com múltiplos projetos `.synp` na mesma pasta (T06) cobrem variantes da mesma categoria.

## Erros não cobertos diretamente por arquivos

| Erro | Motivo |
|------|--------|
| 13 (chain sem `->`) | Provável erro de sintaxe no parser antes de chegar ao validador semântico |
| 15 (conceito com espaço em chain) | Idem — o parser pode capturar antes |
| 32 (TOPIC com espaço) | Testado via t04.syno |
| 38 (CHAIN em ONTOLOGY) | O parser rejeita sintaxe de cadeia em ONTOLOGY; testado via campo QUOTATION com SCOPE ITEM |

## Erros sem arquivo dedicado (cobertos dentro de outros projetos)

| Erro | Projeto | Localização |
|------|---------|-------------|
| 69 (dois FIELDs com mesmo nome) | T05 | t05.synt — segundo bloco `FIELD memo` |
