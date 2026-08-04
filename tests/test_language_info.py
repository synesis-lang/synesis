"""test_language_info.py - Descricao executavel da linguagem (Etapa 1).

Cobre:
  - classificacao obrigatoria/permitida/proibida por sondagem;
  - regras de escopo para IDENTIFIES/REFERS TO (E078);
  - reaproveitamento do texto didatico de to_diagnostic();
  - o contrato central: a matriz e DERIVADA do validador, nao copiada dele;
  - o comando `synesis help-field`.
"""
from synesis.ast.nodes import FieldType, Scope
from synesis.language_info import (
    Requirement,
    field_type_names,
    get_field_type_info,
    get_language_info,
    get_linkage_info,
)


def _names(props):
    return {p.name for p in props}


# --------------------------------------------------------------------------
# Classificacao por tipo
# --------------------------------------------------------------------------

def test_chain_requires_arity_and_allows_relations():
    info = get_field_type_info("CHAIN")
    assert _names(info.required) == {"ARITY"}
    assert "RELATIONS" in _names(info.allowed)
    assert "FORMAT" in _names(info.forbidden)


def test_scale_requires_format_and_forbids_arity():
    info = get_field_type_info("SCALE")
    assert _names(info.required) == {"FORMAT"}
    assert {"ARITY", "RELATIONS"} <= _names(info.forbidden)


def test_ordered_and_enumerated_require_values():
    for type_name in ("ORDERED", "ENUMERATED"):
        assert _names(get_field_type_info(type_name).required) == {"VALUES"}


def test_plain_type_requires_nothing():
    info = get_field_type_info("TEXT")
    assert info.required == []
    assert {"ARITY", "FORMAT", "RELATIONS"} <= _names(info.forbidden)


def test_every_field_type_is_describable():
    """Tipo novo no enum passa a ser descrito sem tocar neste modulo."""
    for field_type in FieldType:
        assert get_field_type_info(field_type.value) is not None


def test_lookup_is_case_insensitive():
    assert get_field_type_info("chain").name == "CHAIN"
    assert get_field_type_info(" Chain ").name == "CHAIN"


def test_unknown_type_returns_none():
    assert get_field_type_info("NAO_EXISTE") is None


# --------------------------------------------------------------------------
# O contrato central: derivado, nao copiado
# --------------------------------------------------------------------------

def test_classification_matches_the_validator():
    """A matriz tem de ser CONSEQUENCIA do validador, nao uma segunda verdade.

    Reproduz a sondagem de forma independente e confere: se alguem trocar a
    derivacao por uma tabela escrita a mao, este teste comeca a divergir
    assim que uma regra do compilador mudar.
    """
    from synesis.parser.template_loader import (
        load_template_from_string,
        validate_template,
    )

    snippets = {
        "ARITY": "    ARITY >= 2\n",
        "FORMAT": "    FORMAT [0..3]\n",
    }

    for field_type in FieldType:
        info = get_field_type_info(field_type.value)
        by_name = {p.name: p for p in info.properties}
        for prop_name, body in snippets.items():
            src = (
                f"TEMPLATE t\nITEM FIELDS\n    REQUIRED f\nEND ITEM FIELDS\n"
                f"FIELD f TYPE {field_type.value}\n    SCOPE ITEM\n{body}END FIELD\n"
            )
            errors = validate_template(load_template_from_string(src)).errors
            codes = {e.CODE for e in errors}
            forbidden_here = by_name[prop_name].requirement is Requirement.FORBIDDEN
            # Se o modulo diz "proibida", o validador tem de reclamar — e
            # vice-versa (descontado o erro de propriedade obrigatoria ausente).
            complained = bool(codes - {"SYNESIS_E047", "SYNESIS_E049",
                                       "SYNESIS_E050", "SYNESIS_E051"})
            assert forbidden_here == complained, (
                f"{field_type.value} + {prop_name}: modulo diz "
                f"forbidden={forbidden_here}, validador diz {codes}"
            )


def test_error_codes_come_from_the_compiler():
    info = get_field_type_info("CHAIN")
    arity = next(p for p in info.required if p.name == "ARITY")
    assert arity.error_code == "SYNESIS_E047"


def test_explanation_reuses_compiler_diagnostic():
    """A ajuda e a mensagem de erro tem de ser a MESMA prosa."""
    info = get_field_type_info("CHAIN")
    arity = next(p for p in info.required if p.name == "ARITY")
    assert arity.explanation
    assert "ARITY" in arity.explanation
    # Placeholder legivel, nao um identificador tecnico vazando para o usuario.
    assert "nome_do_campo" in arity.explanation


def test_allowed_property_has_no_error_code():
    info = get_field_type_info("CHAIN")
    relations = next(p for p in info.allowed if p.name == "RELATIONS")
    assert relations.error_code is None


# --------------------------------------------------------------------------
# Escopo — IDENTIFIES / REFERS TO
# --------------------------------------------------------------------------

def test_linkage_only_in_source_scope():
    linkage = get_linkage_info()
    assert set(linkage) == {s.value for s in Scope}

    for prop in linkage["SOURCE"]:
        assert prop.requirement is Requirement.ALLOWED

    for scope in ("ITEM", "ONTOLOGY"):
        for prop in linkage[scope]:
            assert prop.requirement is Requirement.FORBIDDEN
            assert prop.error_code == "SYNESIS_E078"


# --------------------------------------------------------------------------
# Agregado
# --------------------------------------------------------------------------

def test_language_info_covers_all_types_and_scopes():
    info = get_language_info()
    assert {f.name for f in info.field_types} == {t.value for t in FieldType}
    assert info.scopes == [s.value for s in Scope]
    assert info.field_type("CHAIN") is not None


def test_field_type_names_come_from_enum():
    assert field_type_names() == [t.value for t in FieldType]


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def test_cli_help_field_shows_requirements():
    from click.testing import CliRunner

    from synesis.cli import main

    result = CliRunner().invoke(main, ["help-field", "CHAIN"])
    assert result.exit_code == 0, result.output
    assert "TYPE CHAIN" in result.output
    assert "OBRIGATORIAS" in result.output
    assert "ARITY" in result.output
    assert "RELATIONS" in result.output
    assert "FORMAT" in result.output  # listado como nao aplicavel
    assert "SCOPE SOURCE" in result.output


def test_cli_help_field_without_argument_lists_types():
    from click.testing import CliRunner

    from synesis.cli import main

    result = CliRunner().invoke(main, ["help-field"])
    assert result.exit_code == 0, result.output
    for field_type in FieldType:
        assert field_type.value in result.output


def test_cli_help_field_rejects_unknown_type():
    from click.testing import CliRunner

    from synesis.cli import main

    result = CliRunner().invoke(main, ["help-field", "NAO_EXISTE"])
    assert result.exit_code == 1
    assert "desconhecido" in result.output


def test_cli_help_field_contextualizes_error_codes():
    """O codigo de erro sai contextualizado, nao solto numa coluna: o publico
    e o pesquisador qualitativo, que precisa saber QUANDO o erro ocorre."""
    from click.testing import CliRunner

    from synesis.cli import main

    result = CliRunner().invoke(main, ["help-field", "CHAIN"])
    assert result.exit_code == 0, result.output
    assert "(erro E047 se ausente)" in result.output
    assert "(erro E054 se declarada)" in result.output


def test_cli_help_field_has_no_trailing_padding():
    """Propriedades sem codigo de erro nao carregam padding a direita."""
    from click.testing import CliRunner

    from synesis.cli import main

    result = CliRunner().invoke(main, ["help-field", "CHAIN"])
    optional_lines = [
        line for line in result.output.splitlines()
        if line.lstrip().startswith("+")
    ]
    assert optional_lines
    for line in optional_lines:
        assert line == line.rstrip(), f"padding sobrando: {line!r}"


# --------------------------------------------------------------------------
# E086 — VALUES fora de ORDERED/ENUMERATED (fase 1b)
# --------------------------------------------------------------------------

def test_values_is_forbidden_outside_enumerable_types():
    """A regra nova (E086) e refletida automaticamente pela sondagem: o modulo
    nao precisou mudar quando o validador ganhou a guarda."""
    for type_name in ("CHAIN", "TEXT", "MEMO", "CODE", "QUOTATION",
                      "DATE", "SCALE", "TOPIC"):
        info = get_field_type_info(type_name)
        values = next(p for p in info.properties if p.name == "VALUES")
        assert values.requirement is Requirement.FORBIDDEN, type_name
        assert values.error_code == "SYNESIS_E086"


def test_values_remains_required_for_ordered_and_enumerated():
    for type_name in ("ORDERED", "ENUMERATED"):
        info = get_field_type_info(type_name)
        values = next(p for p in info.properties if p.name == "VALUES")
        assert values.requirement is Requirement.REQUIRED, type_name


# --------------------------------------------------------------------------
# Snippets para editores
# --------------------------------------------------------------------------

def _expand(body):
    """Expande tab-stops como o editor faria, deixando os defaults."""
    import re

    text = "\n".join(body)
    text = re.sub(r"\$\{\d+\|([^,|]+)[^|]*\|\}", r"\1", text)  # choice -> 1a opcao
    text = re.sub(r"\$\{\d+:([^}]*)\}", r"\1", text)           # placeholder -> default
    return text.replace("$0", "").strip()


def test_every_snippet_compiles_clean():
    """Contrato central: snippet que o pesquisador expande tem de compilar."""
    import re

    from synesis.language_info import build_editor_snippets
    from synesis.parser.template_loader import (
        load_template_from_string,
        validate_template,
    )

    snippets = build_editor_snippets()
    assert len(snippets) == len(field_type_names())

    for name, snippet in snippets.items():
        code = _expand(snippet["body"])
        field = re.search(r"FIELD (\w+)", code).group(1)
        scope = re.search(r"SCOPE (\w+)", code).group(1)
        src = (
            f"TEMPLATE t\n{scope} FIELDS\n    REQUIRED {field}\n"
            f"END {scope} FIELDS\n{code}\n"
        )
        errors = validate_template(load_template_from_string(src)).errors
        assert not errors, f"{name} nao compila: {[e.CODE for e in errors]}"


def test_snippet_bodies_follow_the_derived_matrix():
    """O corpo reflete a matriz derivada — nao uma lista escrita a mao.

    Se a regra do compilador mudar (como quando VALUES deixou de valer em
    CHAIN), o snippet acompanha sem edicao manual.
    """
    from synesis.language_info import build_editor_snippets

    snippets = build_editor_snippets()
    for type_name in field_type_names():
        info = get_field_type_info(type_name)
        body = "\n".join(snippets[f"FIELD {type_name}"]["body"])
        for prop in info.required:
            assert prop.name in body, f"{type_name}: falta obrigatoria {prop.name}"
        for prop in info.forbidden:
            assert prop.name not in body, f"{type_name}: contem proibida {prop.name}"


def test_values_absent_from_chain_snippet_after_e086():
    """Regressao da fase 1b: VALUES nao pode voltar ao snippet de CHAIN."""
    from synesis.language_info import build_editor_snippets

    body = "\n".join(build_editor_snippets()["FIELD CHAIN"]["body"])
    assert "ARITY" in body
    assert "VALUES" not in body


def test_snippet_prefixes_are_unique_and_scoped():
    """Prefixo `field-` evita ruido: o language id cobre .syn/.syno tambem."""
    from synesis.language_info import build_editor_snippets

    prefixes = [s["prefix"] for s in build_editor_snippets().values()]
    assert len(prefixes) == len(set(prefixes))
    assert all(p.startswith("field-") for p in prefixes)


def test_snippet_tabstops_are_sequential():
    """Tab-stops numerados em ordem, sem repetir — senao o cursor pula errado."""
    import re

    from synesis.language_info import build_editor_snippets

    for name, snippet in build_editor_snippets().items():
        text = "\n".join(snippet["body"])
        stops = [int(n) for n in re.findall(r"\$\{(\d+)[:|]", text)]
        assert stops == sorted(stops), f"{name}: fora de ordem {stops}"
        assert len(stops) == len(set(stops)), f"{name}: repetidos {stops}"


def test_cli_export_snippets_writes_file(tmp_path):
    import json
    import re

    from click.testing import CliRunner

    from synesis.cli import main

    out = tmp_path / "nested" / "synesis.code-snippets"
    result = CliRunner().invoke(main, ["export-snippets", "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert out.exists()

    content = out.read_text(encoding="utf-8")
    assert "NAO EDITAR A MAO" in content
    payload = json.loads(re.sub(r"^//.*$", "", content, flags=re.M))
    assert len(payload) == len(field_type_names())


def test_cli_export_snippets_to_stdout():
    from click.testing import CliRunner

    from synesis.cli import main

    result = CliRunner().invoke(main, ["export-snippets"])
    assert result.exit_code == 0, result.output
    assert "field-chain" in result.output
