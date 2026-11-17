"""
test_roles_catalog.py - Etapa A2c do plano ROLE/EXPORT (Spec v7, §5-§8)

Catalogo de papeis e validacoes de template (E104-E112), coerencia de rotulos
e hierarquia (E113-E119), fundamentacao (E120), rota depreciada (E121),
definicao pelo papel, LABEL como lista, sugestao do E004 por rotulo e o JSON 3.1
(`indices.relations` e `indices.subtree` com uniao de ITEMs).
"""

from __future__ import annotations

import synesis

BIB = "@article{a1, title={T}, author={A}, year={2024}}\n"

BASE_TEMPLATE = """\
SOURCE FIELDS
    OPTIONAL resumo
END SOURCE FIELDS

FIELD resumo TYPE TEXT
    SCOPE SOURCE
END FIELD

ITEM FIELDS
    REQUIRED trecho, codigo
END ITEM FIELDS

FIELD trecho TYPE QUOTATION
    SCOPE ITEM
END FIELD

FIELD codigo TYPE CODE
    SCOPE ITEM
END FIELD

ONTOLOGY FIELDS
    REQUIRED definicao
    OPTIONAL tipo_de, parte_de, usado_por, oculto, rotulo
END ONTOLOGY FIELDS

FIELD definicao TYPE TEXT
    SCOPE ONTOLOGY
    ROLE NOTE DEFINITION
END FIELD

FIELD tipo_de TYPE CODE
    SCOPE ONTOLOGY
    ROLE HIERARCHY KIND
END FIELD

FIELD parte_de TYPE CODE
    SCOPE ONTOLOGY
    ROLE HIERARCHY PART
END FIELD

FIELD usado_por TYPE TEXT
    SCOPE ONTOLOGY
    ROLE LABEL ALTERNATIVE
END FIELD

FIELD oculto TYPE TEXT
    SCOPE ONTOLOGY
    ROLE LABEL HIDDEN
END FIELD

FIELD rotulo TYPE TEXT
    SCOPE ONTOLOGY
    ROLE LABEL PREFERRED
END FIELD
"""

ANNOTATIONS = """\
SOURCE @a1
END SOURCE

ITEM @a1
    trecho: Mensagens com link falso.
    codigo: smishing, vishing
END ITEM
"""

ONTOLOGY = """\
ONTOLOGY phishing
    definicao: Fraude por comunicacao enganosa.
    usado_por: golpe da isca
END ONTOLOGY

ONTOLOGY smishing
    definicao: Phishing por SMS.
    tipo_de: phishing
    usado_por: phishing por SMS, SMS phishing
END ONTOLOGY

ONTOLOGY vishing
    definicao: Phishing por voz.
    tipo_de: phishing
END ONTOLOGY
"""

PROJECT = (
    'PROJECT p\nTEMPLATE "t.synt"\nINCLUDE BIBLIOGRAPHY "r.bib"\n'
    'INCLUDE ANNOTATIONS "a.syn"\nINCLUDE ONTOLOGY "o.syno"\nEND PROJECT\n'
)


def load(template=BASE_TEMPLATE, ontology=ONTOLOGY, annotations=ANNOTATIONS, check_codes=False):
    kwargs = {}
    if check_codes:
        kwargs["check_codes"] = True
    return synesis.load(
        project_content=PROJECT,
        template_content=template,
        annotation_contents={"a.syn": annotations},
        ontology_contents={"o.syno": ontology},
        bibliography_content=BIB,
        **kwargs,
    )


def codes(result) -> list[str]:
    vr = result.validation_result
    return [e.CODE for e in vr.errors + vr.warnings]


def role(field: str, new_role: str, template: str = BASE_TEMPLATE) -> str:
    """Troca o ROLE de um campo no template base."""
    start = template.index(f"FIELD {field} TYPE")
    end = template.index("END FIELD", start)
    block = template[start:end]
    lines = [ln for ln in block.splitlines() if not ln.strip().startswith("ROLE")]
    if new_role:
        lines.append(f"    ROLE {new_role}")
    return template[:start] + "\n".join(lines) + "\n" + template[end:]


# ---------------------------------------------------------------- base valida

def test_base_project_is_clean():
    result = load()
    assert not result.validation_result.has_errors(), result.get_diagnostics()


# ------------------------------------------------------------ template (E104+)

def test_e104_unknown_role():
    assert "SYNESIS_E104" in codes(load(role("usado_por", "LABEL SYNONYM")))


def test_e104_removed_role_points_to_chain():
    result = load(role("usado_por", "ASSOCIATION RELATED"))
    err = next(e for e in result.validation_result.errors if e.CODE == "SYNESIS_E104")
    assert "MAP RELATIONS" in err.to_diagnostic()


def test_e105_reserved_role():
    assert "SYNESIS_E105" in codes(load(role("tipo_de", "DIVISION EXCLUSIVE")))


def test_e106_family_without_species():
    assert "SYNESIS_E106" in codes(load(role("tipo_de", "HIERARCHY")))


def test_e107_type_mismatch():
    assert "SYNESIS_E107" in codes(load(role("usado_por", "HIERARCHY KIND")))


def test_e108_role_outside_ontology():
    assert "SYNESIS_E108" in codes(load(role("resumo", "NOTE DEFINITION")))


def test_e109_repeated_role_in_one_field():
    t = BASE_TEMPLATE.replace("    ROLE HIERARCHY KIND\n", "    ROLE HIERARCHY KIND\n    ROLE HIERARCHY PART\n")
    assert "SYNESIS_E109" in codes(load(t))


def test_e110_two_definition_fields():
    assert "SYNESIS_E110" in codes(load(role("oculto", "NOTE DEFINITION")))


def test_e111_required_hierarchy():
    t = BASE_TEMPLATE.replace("REQUIRED definicao\n    OPTIONAL tipo_de,", "REQUIRED definicao, tipo_de\n    OPTIONAL")
    assert "SYNESIS_E111" in codes(load(t))


def test_e112_reserved_field_name():
    t = BASE_TEMPLATE.replace(
        "OPTIONAL tipo_de, parte_de, usado_por, oculto, rotulo",
        "OPTIONAL tipo_de, parte_de, usado_por, oculto, rotulo, frequency",
    ) + "\nFIELD frequency TYPE TEXT\n    SCOPE ONTOLOGY\nEND FIELD\n"
    assert "SYNESIS_E112" in codes(load(t))


# ------------------------------------------------------------ rotulos (E113+)

def test_e113_two_preferred_labels():
    o = ONTOLOGY.replace("    usado_por: golpe da isca\n", "    rotulo: Phishing, Pescaria\n")
    assert "SYNESIS_E113" in codes(load(ontology=o))


def test_e114_same_term_in_two_label_species():
    o = ONTOLOGY.replace("    usado_por: golpe da isca\n", "    usado_por: golpe da isca\n    oculto: golpe da isca\n")
    assert "SYNESIS_E114" in codes(load(ontology=o))


def test_e115_same_label_in_two_concepts():
    o = ONTOLOGY.replace("    definicao: Phishing por voz.\n", "    definicao: Phishing por voz.\n    usado_por: golpe da isca\n")
    assert "SYNESIS_E115" in codes(load(ontology=o))


def test_e116_label_equal_to_another_concept():
    o = ONTOLOGY.replace("    usado_por: golpe da isca\n", "    usado_por: vishing\n")
    assert "SYNESIS_E116" in codes(load(ontology=o))


# ---------------------------------------------------------- hierarquia (E117+)

def test_e117_self_reference():
    o = ONTOLOGY.replace("ONTOLOGY phishing\n", "ONTOLOGY phishing\n    tipo_de: phishing\n")
    assert "SYNESIS_E117" in codes(load(ontology=o))


def test_e118_cycle_across_species():
    o = ONTOLOGY.replace("ONTOLOGY phishing\n", "ONTOLOGY phishing\n    parte_de: smishing\n")
    result = load(ontology=o)
    err = next(e for e in result.validation_result.errors if e.CODE == "SYNESIS_E118")
    assert "phishing" in err.to_cli_line() and "smishing" in err.to_cli_line()


def test_e119_same_pair_in_two_species():
    o = ONTOLOGY.replace("    tipo_de: phishing\n    usado_por: phishing por SMS", "    tipo_de: phishing\n    parte_de: phishing\n    usado_por: phishing por SMS")
    assert "SYNESIS_E119" in codes(load(ontology=o))


def test_e120_ungrounded_only_without_mentioned_descendants():
    # phishing nao e mencionado, mas tem filhos mencionados: fundamentado.
    assert "SYNESIS_E120" not in codes(load())
    o = ONTOLOGY + "\nONTOLOGY solto\n    definicao: Sem uso.\nEND ONTOLOGY\n"
    result = load(ontology=o)
    warning = next(w for w in result.validation_result.warnings if w.CODE == "SYNESIS_E120")
    assert "solto" in warning.to_cli_line()


def test_e120_counts_chain_mentions_too():
    t = BASE_TEMPLATE.replace("REQUIRED trecho, codigo", "REQUIRED trecho\n    OPTIONAL codigo, cadeia") + (
        "\nFIELD cadeia TYPE CHAIN\n    SCOPE ITEM\nEND FIELD\n"
    )
    ann = ANNOTATIONS.replace("    codigo: smishing, vishing\n", "    cadeia: smishing -> vishing\n")
    assert "SYNESIS_E120" not in codes(load(template=t, annotations=ann))


def test_e121_name_based_hierarchy_is_deprecated():
    t = BASE_TEMPLATE.replace(
        "OPTIONAL tipo_de, parte_de, usado_por, oculto, rotulo",
        "OPTIONAL tipo_de, parte_de, usado_por, oculto, rotulo, is_a",
    ) + "\nFIELD is_a TYPE TEXT\n    SCOPE ONTOLOGY\nEND FIELD\n"
    o = ONTOLOGY.replace("ONTOLOGY vishing\n", "ONTOLOGY vishing\n    is_a: phishing\n")
    assert "SYNESIS_E121" in codes(load(template=t, ontology=o))


# ------------------------------------------------------- valores e exportacao

def test_label_is_a_list_and_definition_comes_from_the_role():
    result = load()
    smishing = result.to_json_dict()["ontology"]["smishing"]
    assert smishing["usado_por"] == ["phishing por SMS", "SMS phishing"]
    assert smishing["description"] == "Phishing por SMS."


def test_e004_suggests_the_concept_whose_label_matches():
    ann = ANNOTATIONS.replace("codigo: smishing, vishing", "codigo: smishing, SMS phishing")
    result = load(annotations=ann, check_codes=True)
    e004 = next(w for w in result.validation_result.warnings if w.CODE == "SYNESIS_E004")
    assert e004.suggestions == ["smishing"]


def test_json_31_relations_and_subtree_union():
    # Um ITEM que menciona dois filhos conta uma vez na subarvore do pai.
    data = load().to_json_dict()
    assert data["version"] == "3.1"
    assert data["indices"]["relations"]["KIND"] == [["smishing", "phishing"], ["vishing", "phishing"]]
    sub = data["indices"]["subtree"]["phishing"]
    assert sub == {"children": 2, "descendants": 2, "items": 0, "items_subtree": 1, "grounded": True}


def test_template_without_roles_has_no_new_indices():
    plain = "\n".join(ln for ln in BASE_TEMPLATE.splitlines() if not ln.strip().startswith("ROLE")) + "\n"
    data = load(template=plain).to_json_dict()
    assert "relations" not in data["indices"] and "subtree" not in data["indices"]


def test_structural_profile_lines():
    from synesis.semantic.hierarchy import structural_profile

    result = load()
    lines = structural_profile(result.linked_project, result.template, result.validation_result)
    assert "Concepts: 3" in lines
    assert "With KIND parent: 2" in lines
    assert "Top concepts: 1" in lines
    assert "Organizing model: Terminological: With synonyms  |  Conceptual: Taxonomy" in lines


def test_profile_without_ontology_blocks_says_so():
    from synesis.semantic.hierarchy import structural_profile

    result = synesis.load(project_content='PROJECT p\nTEMPLATE "t.synt"\nEND PROJECT\n',
                          template_content=BASE_TEMPLATE)
    lines = structural_profile(result.linked_project, result.template, result.validation_result)
    assert "Organizing model: none (no ONTOLOGY blocks)" in lines
