"""
test_bibtexparser_compat.py - O mesmo resultado com bibtexparser 1.x e 2.x

A 2.0 trocou a API (parse_string/Library no lugar de loads/BibDatabase) e, com a
pilha padrão, entrega valores diferentes da 1.x. parse_bibtex() isola a
diferença. Estes testes fixam o comportamento da 1.x — medido — e devem passar
com QUALQUER das duas versões instaladas. O CI roda o arquivo com cada uma.

Diferenças medidas (bibtexparser 1.4.4 x 2.0.1, pilha padrão):
  - indentação das linhas de continuação: a 1.x remove, a 2.x mantém;
  - `\\r\\n`: a 1.x converte em `\\n`;
  - macros de mês (`month = jan`): a 1.x expande, a 2.x não;
  - concatenação (`pub # " Ltda"`): a 1.x resolve, a 2.x deixa cru;
  - chave repetida no mesmo arquivo: a 1.x fica com a última;
  - nome de campo: a 1.x põe em minúsculas;
  - ordem das chaves do dict: a 1.x inverte a ordem do arquivo.
E um defeito da 1.x corrigido nos dois lados: tipos não padrão (`@online`,
`@dataset`) eram descartados em silêncio pelo parser padrão.
"""

from __future__ import annotations

import bibtexparser

from synesis.parser.bib_loader import (
    detect_malformed_entries,
    load_bibliography_from_string,
    parse_bibtex,
)


def _entry(src: str, key: str) -> dict:
    return load_bibliography_from_string(src)[key]


def test_versao_instalada_e_suportada():
    assert int(bibtexparser.__version__.split(".")[0]) in (1, 2)


def test_indentacao_de_continuacao_removida():
    src = "@article{k,\n  title = {linha um\n     linha dois\n\t\tlinha tres}\n}\n"
    assert _entry(src, "k")["title"] == "linha um\nlinha dois\nlinha tres"


def test_espaco_no_fim_e_linha_em_branco_preservados():
    src = "@article{k,\n  title = {um   \n\n   dois}\n}\n"
    assert _entry(src, "k")["title"] == "um   \n\ndois"


def test_crlf_vira_lf():
    src = "@article{k,\r\n  title = {um\r\n   dois}\r\n}\r\n"
    assert _entry(src, "k")["title"] == "um\ndois"


def test_valor_entre_aspas():
    src = '@article{k,\n  title = "com {chaves} dentro"\n}\n'
    assert _entry(src, "k")["title"] == "com {chaves} dentro"


def test_macro_de_mes_expandida_e_mes_entre_chaves_literal():
    src = "@article{k,\n  month = jan,\n  m2 = {jan},\n  m3 = Mar\n}\n"
    e = _entry(src, "k")
    assert (e["month"], e["m2"], e["m3"]) == ("January", "jan", "March")


def test_concatenacao_e_string_encadeada():
    src = (
        '@string{pub = "Editora"}\n'
        '@String{Loja = {Casa} # " do " # pub}\n'
        '@article{k,\n  publisher = pub # " Ltda",\n  x = Loja,\n  y = LOJA\n}\n'
    )
    e = _entry(src, "k")
    assert e["publisher"] == "Editora Ltda"
    assert e["x"] == e["y"] == "Casa do Editora"


def test_chaves_vazias_viram_texto_vazio():
    assert _entry("@article{k,\n  note = {}\n}\n", "k")["note"] == ""


def test_numero_sem_delimitador():
    assert _entry("@article{k,\n  year = 2024\n}\n", "k")["year"] == "2024"


def test_nome_de_campo_em_minusculas():
    e = _entry("@Article{k,\n  Author = {Silva, Ana}\n}\n", "k")
    assert e["author"] == "Silva, Ana"
    assert e["ENTRYTYPE"] == "article"


def test_chave_repetida_no_mesmo_arquivo_fica_a_ultima():
    src = "@article{d,\n  title = {Primeira}\n}\n@article{d,\n  title = {Segunda}\n}\n"
    assert _entry(src, "d")["title"] == "Segunda"
    assert [e["title"] for e in parse_bibtex(src).entries] == ["Primeira", "Segunda"]


def test_tipos_nao_padrao_sao_aceitos():
    src = "@online{s,\n  title = {Web}\n}\n@dataset{d,\n  title = {Dados}\n}\n"
    bib = load_bibliography_from_string(src)
    assert bib["s"]["ENTRYTYPE"] == "online" and bib["d"]["title"] == "Dados"


def test_ordem_das_chaves_igual_a_1x():
    src = "@article{k,\n  title = {T},\n  year = {2024},\n  author = {A}\n}\n"
    entry = parse_bibtex(src).entries[0]
    assert list(entry) == ["author", "year", "title", "ENTRYTYPE", "ID"]


def test_entrada_malformada_detectada():
    src = (
        "@article{ok2020,\n  title = {Boa}\n}\n\n"
        "@misc sem-chaves\n  title: x\n\n"
        "@book{@BibliaNVT,\n  title = {Chave com arroba}\n}\n"
    )
    malformadas = dict(detect_malformed_entries(src))
    assert malformadas["misc"] == 5
    assert malformadas["BibliaNVT"] == 8
