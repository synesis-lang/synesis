"""
conftest.py - Fixtures compartilhadas para testes do compilador Synesis

Gerado conforme: Especificacao Synesis v1.1
"""

import pytest

# Usa nomes de campos sem colisao com keywords do parser (ex: 'code_description'
# começa com 'code' que é KW_CODE — usamos 'definition' e 'theme' nos fixtures)

TEMPLATE_BASIC = """\
TEMPLATE test

SOURCE FIELDS
    OPTIONAL summary
END SOURCE FIELDS

ITEM FIELDS
    REQUIRED citation, memo, tag
END ITEM FIELDS

ONTOLOGY FIELDS
    REQUIRED definition, theme
END ONTOLOGY FIELDS

FIELD summary TYPE TEXT
    SCOPE SOURCE
END FIELD

FIELD citation TYPE QUOTATION
    SCOPE ITEM
END FIELD

FIELD memo TYPE MEMO
    SCOPE ITEM
END FIELD

FIELD tag TYPE CODE
    SCOPE ITEM
END FIELD

FIELD definition TYPE TEXT
    SCOPE ONTOLOGY
END FIELD

FIELD theme TYPE TOPIC
    SCOPE ONTOLOGY
END FIELD
"""

TEMPLATE_WITH_CHAIN = """\
TEMPLATE test_chain

ITEM FIELDS
    REQUIRED citation
    OPTIONAL chain
END ITEM FIELDS

ONTOLOGY FIELDS
    REQUIRED definition
END ONTOLOGY FIELDS

FIELD citation TYPE QUOTATION
    SCOPE ITEM
END FIELD

FIELD chain TYPE CHAIN
    SCOPE ITEM
    ARITY >= 2
    RELATIONS
        INFLUENCES: Causal influence
        ENABLES: Enabling condition
    END RELATIONS
END FIELD

FIELD definition TYPE TEXT
    SCOPE ONTOLOGY
END FIELD
"""

BIBLIOGRAPHY_BASIC = """\
@article{smith2024,
    author = {Smith, Jane},
    title = {Community Resilience},
    journal = {Journal of Research},
    year = {2024}
}

@article{jones2023,
    author = {Jones, Bob},
    title = {Urban Studies},
    year = {2023}
}
"""

ANNOTATIONS_VALID = """\
SOURCE @smith2024
    summary: Study on community resilience in urban areas.
END SOURCE

ITEM @smith2024
    citation: People cooperate naturally in crisis situations.
    memo: Spontaneous collective action bypasses formal institutions.
    tag: Social_Cohesion, Collective_Action
END ITEM
"""

ONTOLOGY_VALID = """\
ONTOLOGY Social_Cohesion
    definition: Degree of trust and cooperation among community members.
    theme: Community_Resilience
END ONTOLOGY

ONTOLOGY Collective_Action
    definition: Coordinated efforts without formal institutional direction.
    theme: Community_Resilience
END ONTOLOGY
"""

PROJECT_CONTENT = """\
PROJECT test
    TEMPLATE "template.synt"
    INCLUDE BIBLIOGRAPHY "references.bib"
    INCLUDE ANNOTATIONS "annotations.syn"
    INCLUDE ONTOLOGY "ontology.syno"
END PROJECT
"""


@pytest.fixture
def template_basic():
    return TEMPLATE_BASIC


@pytest.fixture
def template_with_chain():
    return TEMPLATE_WITH_CHAIN


@pytest.fixture
def bibliography_basic():
    return BIBLIOGRAPHY_BASIC


@pytest.fixture
def annotations_valid():
    return ANNOTATIONS_VALID


@pytest.fixture
def ontology_valid():
    return ONTOLOGY_VALID


@pytest.fixture
def project_content():
    return PROJECT_CONTENT


@pytest.fixture
def compiled_result(template_basic, bibliography_basic, annotations_valid, ontology_valid):
    """Resultado de compilacao completa e valida."""
    import synesis
    return synesis.load(
        project_content=PROJECT_CONTENT,
        template_content=template_basic,
        annotation_contents={"annotations.syn": annotations_valid},
        ontology_contents={"ontology.syno": ontology_valid},
        bibliography_content=bibliography_basic,
    )
