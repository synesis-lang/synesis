"""
test_phase_blocks.py - Bloco PHASE no .synp (etapa B1; Estudo ROLE/EXPORT §6.2, §9)

O compilador so valida o plano de producao; nunca executa uma fase.
"""

from __future__ import annotations

import synesis

TEMPLATE = """\
SOURCE FIELDS
    REQUIRED resumo
    OPTIONAL autor ON BIBLIOGRAPHY
END SOURCE FIELDS

FIELD resumo TYPE TEXT
    SCOPE SOURCE
END FIELD

FIELD autor TYPE TEXT
    SCOPE SOURCE
END FIELD

ITEM FIELDS
    REQUIRED trecho, codigo
    OPTIONAL BUNDLE cadeia, estatuto
END ITEM FIELDS

FIELD trecho TYPE QUOTATION
    SCOPE ITEM
END FIELD

FIELD codigo TYPE CODE
    SCOPE ITEM
END FIELD

FIELD cadeia TYPE CHAIN
    SCOPE ITEM
END FIELD

FIELD estatuto TYPE TEXT
    SCOPE ITEM
END FIELD

ONTOLOGY FIELDS
    REQUIRED definicao
    OPTIONAL tipo_de
END ONTOLOGY FIELDS

FIELD definicao TYPE TEXT
    SCOPE ONTOLOGY
    ROLE NOTE DEFINITION
END FIELD

FIELD tipo_de TYPE CODE
    SCOPE ONTOLOGY
    ROLE HIERARCHY KIND
END FIELD
"""

GOOD_PLAN = """
PHASE ANNOTATIONS extracao
    FIELDS resumo, trecho, codigo, cadeia, estatuto
END PHASE

PHASE ONTOLOGY definicoes
    FIELDS definicao
    INPUT trecho, cadeia
END PHASE

PHASE ONTOLOGY taxonomia
    FIELDS tipo_de
    INPUT definicao, cadeia
END PHASE
"""


def load(plan: str, includes: str = 'INCLUDE ONTOLOGY "o.syno"\n'):
    project = 'PROJECT p\nTEMPLATE "t.synt"\n' + includes + plan + "END PROJECT\n"
    return synesis.load(
        project_content=project, template_content=TEMPLATE,
        ontology_contents={"o.syno": "ONTOLOGY x\n    definicao: X.\nEND ONTOLOGY\n"},
    )


def codes(result) -> list[str]:
    vr = result.validation_result
    return [e.CODE for e in vr.errors + vr.warnings]


def phase_codes(result) -> list[str]:
    return [c for c in codes(result) if c >= "SYNESIS_E133" and c <= "SYNESIS_E144"]


def test_good_plan_parses_and_has_no_phase_diagnostics():
    result = load(GOOD_PLAN)
    phases = result.linked_project.project.phases
    assert [(p.scope, p.name) for p in phases] == [
        ("ANNOTATIONS", "extracao"), ("ONTOLOGY", "definicoes"), ("ONTOLOGY", "taxonomia")]
    assert phases[1].fields("INPUT") == ["trecho", "cadeia"]
    assert phases[2].env_key == "TAXONOMIA"
    assert phase_codes(result) == []


def test_phases_are_not_in_the_json():
    assert "phases" not in load(GOOD_PLAN).to_json_dict()["project"]


def test_e133_unknown_property_and_output_outside_ontology():
    plan = GOOD_PLAN.replace("    FIELDS resumo,", '    ENGINE LLM grande\n    OUTPUT "o.syno"\n    FIELDS resumo,')
    assert phase_codes(load(plan)).count("SYNESIS_E133") == 2


def test_e134_duplicate_property():
    plan = GOOD_PLAN.replace("    FIELDS tipo_de\n", "    FIELDS tipo_de\n    FIELDS tipo_de\n")
    assert "SYNESIS_E134" in phase_codes(load(plan))


def test_e135_phase_without_fields():
    plan = GOOD_PLAN + "\nPHASE ONTOLOGY vazia\n    INPUT definicao\nEND PHASE\n"
    assert "SYNESIS_E135" in phase_codes(load(plan))


def test_e136_field_not_in_template():
    plan = GOOD_PLAN.replace("INPUT definicao, cadeia", "INPUT definicao, inexistente")
    assert "SYNESIS_E136" in phase_codes(load(plan))


def test_e137_field_in_two_phases():
    plan = GOOD_PLAN.replace("    FIELDS tipo_de\n", "    FIELDS tipo_de, definicao\n")
    assert "SYNESIS_E137" in phase_codes(load(plan))


def test_e138_scope_mismatch():
    plan = GOOD_PLAN.replace("    FIELDS definicao\n", "    FIELDS definicao, trecho\n")
    assert "SYNESIS_E138" in phase_codes(load(plan))


def test_e139_input_not_produced_before_is_a_warning():
    plan = GOOD_PLAN.replace("INPUT definicao, cadeia", "INPUT definicao, cadeia").replace(
        "    FIELDS definicao\n    INPUT trecho, cadeia\n", "    FIELDS definicao\n    INPUT tipo_de\n")
    result = load(plan)
    assert "SYNESIS_E139" in [w.CODE for w in result.validation_result.warnings]


def test_e140_bundle_split_across_phases():
    plan = GOOD_PLAN.replace("FIELDS resumo, trecho, codigo, cadeia, estatuto", "FIELDS resumo, trecho, codigo, cadeia") + (
        "\nPHASE ANNOTATIONS relacoes\n    FIELDS estatuto\nEND PHASE\n")
    assert "SYNESIS_E140" in phase_codes(load(plan))


def test_e141_required_field_without_phase_skips_on_bibliography():
    plan = GOOD_PLAN.replace("FIELDS resumo, trecho,", "FIELDS trecho,")
    result = load(plan)
    warnings = [w for w in result.validation_result.warnings if w.CODE == "SYNESIS_E141"]
    assert [w.field_name for w in warnings] == ["resumo"]  # `autor` vem do .bib


def test_e142_ambiguous_output_with_two_local_syno():
    two = 'INCLUDE ONTOLOGY "o.syno"\nINCLUDE ONTOLOGY "p.syno"\n'
    result = synesis.load(
        project_content='PROJECT p\nTEMPLATE "t.synt"\n' + two + GOOD_PLAN + "END PROJECT\n",
        template_content=TEMPLATE,
        ontology_contents={"o.syno": "ONTOLOGY x\n    definicao: X.\nEND ONTOLOGY\n",
                           "p.syno": "ONTOLOGY y\n    definicao: Y.\nEND ONTOLOGY\n"},
    )
    assert phase_codes(result).count("SYNESIS_E142") == 2


def test_e143_output_must_be_a_local_project_file():
    plan = GOOD_PLAN.replace("    FIELDS tipo_de\n", '    FIELDS tipo_de\n    OUTPUT "outro.syno"\n')
    assert "SYNESIS_E143" in phase_codes(load(plan))
    ok = GOOD_PLAN.replace("    FIELDS tipo_de\n", '    FIELDS tipo_de\n    OUTPUT "./o.syno"\n')
    assert "SYNESIS_E143" not in phase_codes(load(ok))


def test_e144_names_that_collide_in_the_environment():
    plan = GOOD_PLAN + "\nPHASE ONTOLOGY Taxonomia\n    FIELDS tipo_de\nEND PHASE\n"
    assert "SYNESIS_E144" in phase_codes(load(plan))


def test_project_without_phases_is_unchanged():
    assert phase_codes(load("")) == []


def test_ontology_only_plan_does_not_warn_about_annotation_fields():
    """Sem PHASE ANNOTATIONS, SOURCE/ITEM vêm das anotações existentes (sem E141)."""
    plan = "\nPHASE ONTOLOGY taxonomia\n    FIELDS tipo_de\n    INPUT definicao, cadeia\nEND PHASE\n"
    result = load(plan)
    e141 = [w.field_name for w in result.validation_result.warnings if w.CODE == "SYNESIS_E141"]
    assert e141 == ["definicao"]  # REQUIRED do ONTOLOGY, escopo coberto, sem fase


def test_input_from_existing_data_is_not_a_warning():
    """INPUT que nenhuma fase produz vem dos dados (.syn/.syno): sem E139."""
    plan = "\nPHASE ONTOLOGY taxonomia\n    FIELDS tipo_de\n    INPUT definicao, cadeia\nEND PHASE\n"
    assert "SYNESIS_E139" not in phase_codes(load(plan))
