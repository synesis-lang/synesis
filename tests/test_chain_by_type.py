"""CHAIN coletado pelo TIPO, não pelo nome (linker).

Antes: o parser só punha em `item.chains` os campos chamados `chain`/`chains`,
e o linker montava `all_triples`/`relation_index` só a partir deles. Um CHAIN
com outro nome ficava fora — e, por consequência, fora do LSP (relações, grafo)
e da lista de conceitos do synesis-coder. Além disso, `has_relations` era
GLOBAL: com dois CHAIN de configurações diferentes, a cadeia simples seria lida
como qualificada.
"""

import synesis
from tests.conftest import BIBLIOGRAPHY_BASIC, PROJECT_CONTENT


def _template(campos: str) -> str:
    return f"""\
TEMPLATE t

SOURCE FIELDS
    OPTIONAL summary
END SOURCE FIELDS

ITEM FIELDS
    REQUIRED citation
    OPTIONAL chain
    OPTIONAL relacoes
    OPTIONAL ligacoes
END ITEM FIELDS

FIELD summary TYPE TEXT
    SCOPE SOURCE
END FIELD

FIELD citation TYPE QUOTATION
    SCOPE ITEM
END FIELD
{campos}"""


QUALIFICADO = """
FIELD {nome} TYPE CHAIN
    SCOPE ITEM
    ARITY >= 2
    RELATIONS
        INFLUENCES: A muda B
        ENABLES: A permite B
    END RELATIONS
END FIELD
"""

SIMPLES = """
FIELD {nome} TYPE CHAIN
    SCOPE ITEM
    ARITY >= 2
END FIELD
"""


def _load(campos: str, item_lines: str):
    ann = f"""\
SOURCE @smith2024
    summary: A source.
END SOURCE
ITEM @smith2024
    citation: A quote.
{item_lines}
END ITEM
"""
    return synesis.load(
        project_content=PROJECT_CONTENT,
        template_content=_template(campos),
        annotation_contents={"annotations.syn": ann},
        bibliography_content=BIBLIOGRAPHY_BASIC,
    )


def _ok(r):
    assert not r.has_errors(), r.get_diagnostics(verbose=False)
    return r.linked_project


def test_nome_tradicional_inalterado():
    lp = _ok(_load(QUALIFICADO.format(nome="chain"), "    chain: trust -> INFLUENCES -> acceptance"))
    assert lp.all_triples == [("trust", "INFLUENCES", "acceptance")]
    assert lp.relation_index[("trust", "INFLUENCES", "acceptance")]["type"] == "qualified"


def test_nome_arbitrario_entra_nas_triplas():
    lp = _ok(_load(QUALIFICADO.format(nome="relacoes"), "    relacoes: trust -> ENABLES -> acceptance"))
    assert lp.all_triples == [("trust", "ENABLES", "acceptance")]
    assert ("trust", "ENABLES", "acceptance") in lp.relation_index


def test_dois_campos_tradicional_e_arbitrario_coexistem():
    campos = QUALIFICADO.format(nome="chain") + QUALIFICADO.format(nome="relacoes")
    lp = _ok(_load(campos, "    chain: a -> INFLUENCES -> b\n    relacoes: c -> ENABLES -> d"))
    assert sorted(lp.all_triples) == [("a", "INFLUENCES", "b"), ("c", "ENABLES", "d")]


def test_simples_e_qualificado_cada_um_no_seu_modo():
    campos = QUALIFICADO.format(nome="relacoes") + SIMPLES.format(nome="ligacoes")
    lp = _ok(_load(campos, "    relacoes: a -> INFLUENCES -> b\n    ligacoes: x -> y -> z"))
    assert ("a", "INFLUENCES", "b") in lp.all_triples
    # cadeia simples: todos os elementos são conceitos (relação IMPLICIT), não x→y como relação
    assert ("x", "IMPLICIT", "y") in lp.all_triples and ("y", "IMPLICIT", "z") in lp.all_triples
    assert lp.relation_index[("x", "IMPLICIT", "y")]["type"] == "simple"
    assert lp.relation_index[("a", "INFLUENCES", "b")]["type"] == "qualified"


def test_sem_duplicacao():
    lp = _ok(_load(QUALIFICADO.format(nome="chain"),
                   "    chain: a -> INFLUENCES -> b\n    chain: b -> ENABLES -> c"))
    assert sorted(lp.all_triples) == [("a", "INFLUENCES", "b"), ("b", "ENABLES", "c")]


def test_localizacao_preservada():
    lp = _ok(_load(QUALIFICADO.format(nome="relacoes"), "    relacoes: a -> INFLUENCES -> b"))
    loc = lp.relation_index[("a", "INFLUENCES", "b")]["location"]
    assert str(loc.file).endswith("annotations.syn") and loc.line > 0
