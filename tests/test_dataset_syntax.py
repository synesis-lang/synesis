"""
test_dataset_syntax.py - Fase 2: gramática/AST/transformer de ON DATASET

Cobre o parse das três formas novas e a reconciliação em FieldSpec:
  - INCLUDE DATASET no .synp;
  - REQUIRED/OPTIONAL <campo> ON DATASET "caminho" -> value_origin/dataset_path;
  - CONTEXT FROM DATASET "s1", "s2" (propriedade de FIELD) -> context_from_dataset.

`ON DATASET` espelha ON BIBLIOGRAPHY: cláusula no bloco FIELDS (origem-de-valor),
reconciliada no template_loader. `CONTEXT FROM DATASET` é propriedade do bloco
FIELD (irmã de GUIDELINES): descreve como o campo é processado, não requisito de
presença — lida direto em field_def_block, sem reconciliação.
"""

from __future__ import annotations

from synesis.parser.template_loader import load_template_from_string

_TEMPLATE = """
TEMPLATE lattes

SOURCE FIELDS
    REQUIRED lattes_id ON DATASET "informacoes_pessoais.id_lattes"
    OPTIONAL bolsa ON DATASET "informacoes_pessoais.bolsa_produtividade"
END SOURCE FIELDS

ITEM FIELDS
    REQUIRED trecho, zona
END ITEM FIELDS

FIELD lattes_id TYPE TEXT
    SCOPE SOURCE
    IDENTIFIES researcher
END FIELD

FIELD bolsa TYPE TEXT
    SCOPE SOURCE
END FIELD

FIELD trecho TYPE QUOTATION
    SCOPE ITEM
END FIELD

FIELD zona TYPE TEXT
    SCOPE ITEM
END FIELD

FIELD chain TYPE CHAIN
    SCOPE ITEM
    ARITY >= 2
    CONTEXT FROM DATASET "linhas_de_pesquisa", "projetos_pesquisa[ano_conclusao=Atual]"
END FIELD
"""


def _load():
    return load_template_from_string(_TEMPLATE, "lattes.synt")


def test_on_dataset_sets_value_origin_and_path():
    tpl = _load()
    spec = tpl.field_specs["lattes_id"]
    assert spec.value_origin == "dataset"
    assert spec.dataset_path == "informacoes_pessoais.id_lattes"


def test_on_dataset_optional_field():
    tpl = _load()
    spec = tpl.field_specs["bolsa"]
    assert spec.value_origin == "dataset"
    assert spec.dataset_path == "informacoes_pessoais.bolsa_produtividade"


def test_on_dataset_coexists_with_identifies():
    """ON DATASET (origem) e IDENTIFIES (papel de chave) são ortogonais."""
    tpl = _load()
    spec = tpl.field_specs["lattes_id"]
    assert spec.value_origin == "dataset"
    assert spec.identifies == "researcher"


def test_context_from_dataset_collected():
    tpl = _load()
    spec = tpl.field_specs["chain"]
    assert spec.context_from_dataset == [
        "linhas_de_pesquisa",
        "projetos_pesquisa[ano_conclusao=Atual]",
    ]
    # CONTEXT não é origem-de-valor
    assert spec.value_origin == "document"


def test_context_from_dataset_antes_de_guidelines():
    """CONTEXT é propriedade de FIELD e conviver com GUIDELINES no mesmo bloco.

    Posição livre na gramática (field_props*), mas o uso canônico é logo antes
    de GUIDELINES — o contexto declara o insumo que as GUIDELINES interpretam.
    """
    tpl = load_template_from_string(
        """
TEMPLATE t

SOURCE FIELDS
    REQUIRED cargo
END SOURCE FIELDS

FIELD cargo TYPE TEXT
    SCOPE SOURCE
    DESCRIPTION Cargo atual
    CONTEXT FROM DATASET "atuacao_profissional[ano_fim=Atual]"
    GUIDELINES
        Os vinculos chegam filtrados por ano_fim=Atual.
        Passo 1: use o campo enquadramento.
    END GUIDELINES
END FIELD
""",
        "t.synt",
    )
    spec = tpl.field_specs["cargo"]
    assert spec.context_from_dataset == ["atuacao_profissional[ano_fim=Atual]"]
    assert spec.guidelines is not None
    assert "enquadramento" in spec.guidelines
    assert spec.value_origin == "document"


def test_context_no_bloco_fields_e_rejeitado():
    """A forma antiga (CONTEXT <campo> FROM DATASET em SOURCE/ITEM FIELDS) saiu.

    Sem compatibilidade retroativa: CONTEXT só é aceito dentro do bloco FIELD.
    """
    import pytest

    from synesis.parser.lexer import SynesisSyntaxError

    with pytest.raises(SynesisSyntaxError):
        load_template_from_string(
            """
TEMPLATE t

ITEM FIELDS
    REQUIRED trecho
    CONTEXT trecho FROM DATASET "linhas_de_pesquisa"
END ITEM FIELDS

FIELD trecho TYPE TEXT
    SCOPE ITEM
END FIELD
""",
            "t.synt",
        )


def test_field_without_dataset_unchanged():
    tpl = _load()
    assert tpl.field_specs["trecho"].value_origin == "document"
    assert tpl.field_specs["trecho"].dataset_path is None
    assert tpl.field_specs["trecho"].context_from_dataset is None


def test_include_dataset_parses():
    project = """
PROJECT lattes
TEMPLATE "lattes.synt"
INCLUDE DATASET "curriculos/*.toml"
END PROJECT
"""
    from synesis.parser.lexer import parse_string
    from synesis.parser.transformer import SynesisTransformer

    tree = parse_string(project, "lattes.synp")
    result = SynesisTransformer("lattes.synp").transform(tree)
    includes = list(_walk_includes(result))
    assert any(
        inc.include_type.upper() == "DATASET" and "curriculos" in inc.path
        for inc in includes
    )


def _walk_includes(node):
    """Coleta IncludeNode(s) do resultado transformado (lista de itens de topo)."""
    from synesis.ast.nodes import IncludeNode

    if isinstance(node, IncludeNode):
        yield node
    elif isinstance(node, (list, tuple)):
        for item in node:
            yield from _walk_includes(item)
    else:
        for attr in ("includes", "project", "body", "items", "children"):
            value = getattr(node, attr, None)
            if value is not None and not callable(value):
                yield from _walk_includes(value)
