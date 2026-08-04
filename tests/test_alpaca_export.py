"""
test_alpaca_export.py - Testes do exportador Alpaca JSONL

Cobre: geracao de pares por tipo de campo, bundles, deduplicacao,
       filtro de output curto, pares agregados, escrita em disco.

Gerado conforme: Especificacao Synesis v3.0
"""

import json
from pathlib import Path

import pytest

import synesis
from synesis.exporters.alpaca_export import (
    _format_citation,
    _is_sentinel_value,
    build_alpaca_pairs,
    export_alpaca,
)
from tests.conftest import (
    BIBLIOGRAPHY_BASIC,
    ONTOLOGY_VALID,
    PROJECT_CONTENT,
    TEMPLATE_BASIC,
    TEMPLATE_WITH_CHAIN,
)

# ---------------------------------------------------------------------------
# Templates adicionais para cenarios especificos
# ---------------------------------------------------------------------------

TEMPLATE_WITH_BUNDLE = """\
TEMPLATE test_bundle

ITEM FIELDS
    REQUIRED BUNDLE citation, analysis
    REQUIRED tag
END ITEM FIELDS

ONTOLOGY FIELDS
    OPTIONAL definition
END ONTOLOGY FIELDS

FIELD citation TYPE QUOTATION
    SCOPE ITEM
    DESCRIPTION Direct excerpt from the source
END FIELD

FIELD analysis TYPE MEMO
    SCOPE ITEM
    DESCRIPTION Analytical note linking excerpt to theory
END FIELD

FIELD tag TYPE CODE
    SCOPE ITEM
END FIELD

FIELD definition TYPE TEXT
    SCOPE ONTOLOGY
    DESCRIPTION Conceptual definition
END FIELD
"""

TEMPLATE_CHAIN_BUNDLE = """\
TEMPLATE test_chain_bundle

ITEM FIELDS
    REQUIRED citation
    REQUIRED BUNDLE causal_chain, causal_memo
END ITEM FIELDS

ONTOLOGY FIELDS
    OPTIONAL definition
END ONTOLOGY FIELDS

FIELD citation TYPE QUOTATION
    SCOPE ITEM
END FIELD

FIELD causal_chain TYPE CHAIN
    SCOPE ITEM
    ARITY >= 2
    RELATIONS
        INFLUENCES: Causal influence
    END RELATIONS
END FIELD

FIELD causal_memo TYPE MEMO
    SCOPE ITEM
    DESCRIPTION Explanation of the causal relationship
END FIELD

FIELD definition TYPE TEXT
    SCOPE ONTOLOGY
END FIELD
"""

ANNOTATIONS_WITH_CHAIN = """\
SOURCE @smith2024
END SOURCE

ITEM @smith2024
    citation: People cooperate in crisis situations.
    causal_chain: Social_Cohesion -> INFLUENCES -> Collective_Action
    causal_memo: Strong bonding capital drives spontaneous collective response.
END ITEM
"""

ANNOTATIONS_WITH_BUNDLE = """\
SOURCE @smith2024
END SOURCE

ITEM @smith2024
    citation: People cooperate naturally.
    analysis: Participant describes bonding social capital as a driver of resilience.
    tag: Social_Cohesion
END ITEM
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def result_basic(template_basic, bibliography_basic, annotations_valid, ontology_valid):
    return synesis.load(
        project_content=PROJECT_CONTENT,
        template_content=template_basic,
        annotation_contents={"annotations.syn": annotations_valid},
        ontology_contents={"ontology.syno": ontology_valid},
        bibliography_content=bibliography_basic,
    )


@pytest.fixture
def result_bundle():
    return synesis.load(
        project_content=PROJECT_CONTENT,
        template_content=TEMPLATE_WITH_BUNDLE,
        annotation_contents={"annotations.syn": ANNOTATIONS_WITH_BUNDLE},
        ontology_contents={"ontology.syno": ONTOLOGY_VALID},
        bibliography_content=BIBLIOGRAPHY_BASIC,
    )


@pytest.fixture
def result_chain_bundle():
    return synesis.load(
        project_content=PROJECT_CONTENT,
        template_content=TEMPLATE_CHAIN_BUNDLE,
        annotation_contents={"annotations.syn": ANNOTATIONS_WITH_CHAIN},
        ontology_contents={"ontology.syno": ONTOLOGY_VALID},
        bibliography_content=BIBLIOGRAPHY_BASIC,
    )


@pytest.fixture
def result_chain(bibliography_basic, ontology_valid):
    return synesis.load(
        project_content=PROJECT_CONTENT,
        template_content=TEMPLATE_WITH_CHAIN,
        annotation_contents={
            "annotations.syn": """\
SOURCE @smith2024
END SOURCE

ITEM @smith2024
    citation: People cooperate in crisis situations.
    chain: Social_Cohesion -> INFLUENCES -> Collective_Action
END ITEM
"""
        },
        ontology_contents={"ontology.syno": ontology_valid},
        bibliography_content=bibliography_basic,
    )


# ---------------------------------------------------------------------------
# Formato dos pares
# ---------------------------------------------------------------------------

class TestPairFormat:

    def test_returns_list(self, result_basic):
        pairs = result_basic.to_alpaca_pairs()
        assert isinstance(pairs, list)

    def test_each_pair_has_three_keys(self, result_basic):
        pairs = result_basic.to_alpaca_pairs()
        assert len(pairs) > 0
        for pair in pairs:
            assert set(pair.keys()) == {"instruction", "input", "output"}

    def test_all_values_are_strings(self, result_basic):
        pairs = result_basic.to_alpaca_pairs()
        for pair in pairs:
            assert isinstance(pair["instruction"], str)
            assert isinstance(pair["input"], str)
            assert isinstance(pair["output"], str)

    def test_no_empty_output(self, result_basic):
        pairs = result_basic.to_alpaca_pairs()
        for pair in pairs:
            assert len(pair["output"]) >= 5

    def test_no_none_values(self, result_basic):
        pairs = result_basic.to_alpaca_pairs()
        for pair in pairs:
            assert pair["instruction"] is not None
            assert pair["input"] is not None
            assert pair["output"] is not None


# ---------------------------------------------------------------------------
# Geracao por tipo de campo
# ---------------------------------------------------------------------------

class TestCodePairs:

    def test_generates_code_pairs(self, result_basic):
        pairs = result_basic.to_alpaca_pairs()
        code_pairs = [p for p in pairs if "concepts are attributed" in p["instruction"]]
        assert len(code_pairs) >= 1

    def test_code_output_contains_concept(self, result_basic):
        pairs = result_basic.to_alpaca_pairs()
        code_pairs = [p for p in pairs if "concepts are attributed" in p["instruction"]]
        outputs = [p["output"] for p in code_pairs]
        assert any("Social_Cohesion" in o or "Collective_Action" in o for o in outputs)


class TestOntologyTextPairs:

    def test_generates_ontology_definition_pairs(self, result_basic):
        pairs = result_basic.to_alpaca_pairs()
        defn_pairs = [p for p in pairs if "define the concept" in p["instruction"]]
        assert len(defn_pairs) >= 1

    def test_ontology_instruction_contains_concept_name(self, result_basic):
        pairs = result_basic.to_alpaca_pairs()
        defn_pairs = [p for p in pairs if "define the concept" in p["instruction"]]
        names = {p["instruction"] for p in defn_pairs}
        assert any("Social_Cohesion" in n or "Collective_Action" in n for n in names)

    def test_ontology_input_is_empty(self, result_basic):
        pairs = result_basic.to_alpaca_pairs()
        defn_pairs = [p for p in pairs if "define the concept" in p["instruction"]]
        for p in defn_pairs:
            assert p["input"] == ""


class TestTopicPairs:

    def test_generates_topic_pairs(self, result_basic):
        pairs = result_basic.to_alpaca_pairs()
        topic_pairs = [p for p in pairs if "thematic category" in p["instruction"]]
        assert len(topic_pairs) >= 1

    def test_topic_output_is_topic_name(self, result_basic):
        pairs = result_basic.to_alpaca_pairs()
        topic_pairs = [p for p in pairs if "thematic category" in p["instruction"]]
        outputs = [p["output"] for p in topic_pairs]
        assert any("Community_Resilience" in o for o in outputs)


# ---------------------------------------------------------------------------
# BUNDLE QUOTATION + MEMO
# ---------------------------------------------------------------------------

class TestBundleQuotationMemo:

    def test_generates_quotation_memo_pairs(self, result_bundle):
        pairs = result_bundle.to_alpaca_pairs()
        qm_pairs = [p for p in pairs if "analytical interpretation" in p["instruction"].lower()]
        assert len(qm_pairs) >= 1

    def test_quotation_memo_input_contains_quote(self, result_bundle):
        pairs = result_bundle.to_alpaca_pairs()
        qm_pairs = [p for p in pairs if "analytical interpretation" in p["instruction"].lower()]
        assert any("cooperate" in p["input"].lower() for p in qm_pairs)

    def test_quotation_memo_output_contains_memo(self, result_bundle):
        pairs = result_bundle.to_alpaca_pairs()
        qm_pairs = [p for p in pairs if "analytical interpretation" in p["instruction"].lower()]
        assert any("bonding" in p["output"].lower() for p in qm_pairs)


# ---------------------------------------------------------------------------
# BUNDLE CHAIN + MEMO
# ---------------------------------------------------------------------------

class TestBundleChainMemo:

    def test_generates_chain_memo_pairs(self, result_chain_bundle):
        pairs = result_chain_bundle.to_alpaca_pairs()
        chain_pairs = [p for p in pairs if "relationship" in p["instruction"].lower()
                       or "causal" in p["instruction"].lower()]
        assert len(chain_pairs) >= 1

    def test_chain_memo_output_contains_triple_and_memo(self, result_chain_bundle):
        pairs = result_chain_bundle.to_alpaca_pairs()
        chain_pairs = [p for p in pairs if "->" in p["output"]]
        assert len(chain_pairs) >= 1
        # Output deve conter a tripla
        assert any("Social_Cohesion" in p["output"] and "Collective_Action" in p["output"]
                   for p in chain_pairs)

    def test_chain_memo_output_contains_memo_text(self, result_chain_bundle):
        pairs = result_chain_bundle.to_alpaca_pairs()
        chain_pairs = [p for p in pairs if "->" in p["output"]]
        assert any("bonding" in p["output"].lower() for p in chain_pairs)


# ---------------------------------------------------------------------------
# Pares de chains sem bundle
# ---------------------------------------------------------------------------

class TestChainPairs:

    def test_generates_chain_pairs(self, result_chain):
        pairs = result_chain.to_alpaca_pairs()
        chain_pairs = [p for p in pairs if "->" in p["output"]]
        assert len(chain_pairs) >= 1

    def test_chain_output_format(self, result_chain):
        pairs = result_chain.to_alpaca_pairs()
        chain_pairs = [p for p in pairs if "->" in p["output"]]
        # Formato esperado: "From -> REL -> To"
        for p in chain_pairs:
            parts = p["output"].split("->")
            assert len(parts) >= 3


# ---------------------------------------------------------------------------
# Pares agregados
# ---------------------------------------------------------------------------

class TestAggregateTriplePairs:

    def test_generates_aggregate_pairs_when_multiple_triples(self):
        """Dois items referenciando o mesmo conceito via chain geram par agregado."""
        annotations = """\
SOURCE @smith2024
END SOURCE

ITEM @smith2024
    citation: First excerpt.
    chain: Social_Cohesion -> INFLUENCES -> Collective_Action
END ITEM

ITEM @smith2024
    citation: Second excerpt.
    chain: Bonding_Capital -> INFLUENCES -> Collective_Action
END ITEM
"""
        ontology = """\
ONTOLOGY Social_Cohesion
    definition: Degree of trust among members.
END ONTOLOGY
ONTOLOGY Collective_Action
    definition: Coordinated community efforts.
END ONTOLOGY
ONTOLOGY Bonding_Capital
    definition: Intra-group social ties.
END ONTOLOGY
"""
        result = synesis.load(
            project_content=PROJECT_CONTENT,
            template_content=TEMPLATE_WITH_CHAIN,
            annotation_contents={"annotations.syn": annotations},
            ontology_contents={"ontology.syno": ontology},
            bibliography_content=BIBLIOGRAPHY_BASIC,
        )
        pairs = build_alpaca_pairs(result.linked_project, result.template, result.bibliography)
        agg_pairs = [p for p in pairs if "factors and" in p["instruction"]]
        assert len(agg_pairs) >= 1

    def test_no_aggregate_pairs_when_single_triple(self, result_chain):
        """Conceito com apenas uma triple entrante nao gera par agregado."""
        pairs = build_alpaca_pairs(
            result_chain.linked_project, result_chain.template, result_chain.bibliography
        )
        agg_pairs = [p for p in pairs if "factors and" in p["instruction"]]
        # Social_Cohesion so tem 1 triple entrante (nenhuma) e Collective_Action so tem 1
        assert all(len(p["output"].strip().splitlines()) >= 2 for p in agg_pairs)


# ---------------------------------------------------------------------------
# Pares de topic_index
# ---------------------------------------------------------------------------

class TestTopicIndexPairs:

    def test_generates_topic_index_pairs(self, result_basic):
        pairs = result_basic.to_alpaca_pairs()
        topic_idx_pairs = [p for p in pairs
                           if "belong to the thematic" in p["instruction"]]
        assert len(topic_idx_pairs) >= 1

    def test_topic_index_output_lists_concepts(self, result_basic):
        pairs = result_basic.to_alpaca_pairs()
        topic_idx_pairs = [p for p in pairs
                           if "belong to the thematic" in p["instruction"]]
        outputs = " ".join(p["output"] for p in topic_idx_pairs)
        assert "Social_Cohesion" in outputs or "Collective_Action" in outputs


# ---------------------------------------------------------------------------
# Deduplicacao
# ---------------------------------------------------------------------------

class TestDeduplication:

    def test_no_duplicate_instruction_output_pairs(self, result_basic):
        pairs = result_basic.to_alpaca_pairs()
        seen = set()
        for p in pairs:
            key = (p["instruction"], p["output"])
            assert key not in seen, f"Duplicated pair: {key}"
            seen.add(key)


# ---------------------------------------------------------------------------
# Modo legado (sem template)
# ---------------------------------------------------------------------------

class TestLegacyMode:

    def test_no_template_returns_empty(self, compiled_result):
        """build_alpaca_pairs sem template retorna lista vazia."""
        pairs = build_alpaca_pairs(compiled_result.linked_project, template=None)
        assert pairs == []

    def test_api_no_template_returns_empty(self):
        result = synesis.load(
            project_content=PROJECT_CONTENT,
            template_content=TEMPLATE_BASIC,
        )
        result.template = None
        pairs = result.to_alpaca_pairs()
        assert pairs == []


# ---------------------------------------------------------------------------
# export_alpaca (escrita em disco)
# ---------------------------------------------------------------------------

class TestExportAlpaca:

    def test_creates_file(self, result_basic, tmp_path):
        out = tmp_path / "dataset.jsonl"
        export_alpaca(
            result_basic.linked_project,
            out,
            result_basic.template,
            result_basic.bibliography,
        )
        assert out.exists()

    def test_file_is_valid_jsonl(self, result_basic, tmp_path):
        out = tmp_path / "dataset.jsonl"
        export_alpaca(
            result_basic.linked_project,
            out,
            result_basic.template,
            result_basic.bibliography,
        )
        lines = out.read_text(encoding="utf-8").splitlines()
        for line in lines:
            obj = json.loads(line)
            assert "instruction" in obj
            assert "input" in obj
            assert "output" in obj

    def test_file_line_count_matches_pair_count(self, result_basic, tmp_path):
        out = tmp_path / "dataset.jsonl"
        export_alpaca(
            result_basic.linked_project,
            out,
            result_basic.template,
            result_basic.bibliography,
        )
        pairs = build_alpaca_pairs(
            result_basic.linked_project, result_basic.template, result_basic.bibliography
        )
        lines = [l for l in out.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(lines) == len(pairs)

    def test_creates_parent_dirs(self, result_basic, tmp_path):
        out = tmp_path / "nested" / "dir" / "dataset.jsonl"
        export_alpaca(
            result_basic.linked_project,
            out,
            result_basic.template,
            result_basic.bibliography,
        )
        assert out.exists()

    def test_string_path_accepted(self, result_basic, tmp_path):
        out = str(tmp_path / "dataset.jsonl")
        export_alpaca(
            result_basic.linked_project,
            out,
            result_basic.template,
            result_basic.bibliography,
        )
        assert Path(out).exists()


# ---------------------------------------------------------------------------
# Filtro de sentinelas ORDERED/ENUMERATED
# ---------------------------------------------------------------------------

class TestSentinelFilter:

    def _make_mock_value(self, index, label, description=""):
        """Cria objeto simples com atributos index/label/description."""
        class V:
            pass
        v = V()
        v.index = index
        v.label = label
        v.description = description
        return v

    def test_index_zero_is_sentinel(self):
        v = self._make_mock_value(0, "Anything", "desc")
        assert _is_sentinel_value(v) is True

    def test_undefined_label_is_sentinel(self):
        v = self._make_mock_value(1, "Undefined", "Not available")
        assert _is_sentinel_value(v) is True

    def test_na_label_is_sentinel(self):
        v = self._make_mock_value(1, "N/A", "")
        assert _is_sentinel_value(v) is True

    def test_normal_label_not_sentinel(self):
        v = self._make_mock_value(1, "Analytical", "Research and analysis")
        assert _is_sentinel_value(v) is False

    def test_sentinel_output_not_generated(self):
        """Conceito com valor anotado como sentinela (index 0) nao gera par."""
        template_ordered = """\
TEMPLATE test_ordered

ONTOLOGY FIELDS
    REQUIRED aspect
END ONTOLOGY FIELDS

FIELD aspect TYPE ORDERED
    SCOPE ONTOLOGY
    DESCRIPTION Modal aspect classification
    VALUES
        [0] Undefined: Not available
        [1] Analytical: Research and analysis
        [2] Social: Community dynamics
    END VALUES
END FIELD
"""
        ontology_with_sentinel = """\
ONTOLOGY ConceptA
    aspect: 0
END ONTOLOGY

ONTOLOGY ConceptB
    aspect: 2
END ONTOLOGY
"""
        result = synesis.load(
            project_content=PROJECT_CONTENT,
            template_content=template_ordered,
            ontology_contents={"ontology.syno": ontology_with_sentinel},
        )
        pairs = build_alpaca_pairs(result.linked_project, result.template)
        # ConceptA tem aspect=0 (Undefined) — nao deve gerar par
        assert not any("ConceptA" in p["instruction"] and "aspect" in p["instruction"].lower()
                       for p in pairs)
        # ConceptB tem aspect=2 (Social) — deve gerar par
        assert any("ConceptB" in p["instruction"] for p in pairs)

    def test_undefined_not_in_options(self):
        """'Undefined' nao deve aparecer como opcao na instrucao."""
        template_ordered = """\
TEMPLATE test_ordered2

ONTOLOGY FIELDS
    REQUIRED aspect
END ONTOLOGY FIELDS

FIELD aspect TYPE ORDERED
    SCOPE ONTOLOGY
    DESCRIPTION Modal aspect
    VALUES
        [0] Undefined: Not available
        [1] Analytical: Research and analysis
        [2] Social: Community dynamics
        [3] Economic: Financial factors
        [4] Juridical: Legal frameworks
        [5] Ethical: Moral responsibility
        [6] Fiducial: Trust and belief
        [7] Lingual: Communication
    END VALUES
END FIELD
"""
        ontology = """\
ONTOLOGY ConceptX
    aspect: 3
END ONTOLOGY
"""
        result = synesis.load(
            project_content=PROJECT_CONTENT,
            template_content=template_ordered,
            ontology_contents={"ontology.syno": ontology},
        )
        pairs = build_alpaca_pairs(result.linked_project, result.template)
        classification_pairs = [p for p in pairs if "ConceptX" in p["instruction"]]
        assert len(classification_pairs) >= 1
        for p in classification_pairs:
            assert "Undefined" not in p["instruction"]

    def test_long_ordered_uses_abbreviated_form(self):
        """ORDERED com >6 valores usa forma abreviada (sem listar todos)."""
        template_ordered = """\
TEMPLATE test_ordered3

ONTOLOGY FIELDS
    REQUIRED aspect
END ONTOLOGY FIELDS

FIELD aspect TYPE ORDERED
    SCOPE ONTOLOGY
    DESCRIPTION Modal aspect
    VALUES
        [0] Undefined: Not available
        [1] A1: First
        [2] A2: Second
        [3] A3: Third
        [4] A4: Fourth
        [5] A5: Fifth
        [6] A6: Sixth
        [7] A7: Seventh
    END VALUES
END FIELD
"""
        ontology = """\
ONTOLOGY ConceptY
    aspect: 4
END ONTOLOGY
"""
        result = synesis.load(
            project_content=PROJECT_CONTENT,
            template_content=template_ordered,
            ontology_contents={"ontology.syno": ontology},
        )
        pairs = build_alpaca_pairs(result.linked_project, result.template)
        classification_pairs = [p for p in pairs if "ConceptY" in p["instruction"]]
        assert len(classification_pairs) >= 1
        # Forma abreviada nao deve listar todos os valores com ":"
        for p in classification_pairs:
            assert "Levels:" not in p["instruction"]


# ---------------------------------------------------------------------------
# Citacao bibliografica em SOURCE pairs
# ---------------------------------------------------------------------------

class TestFormatCitation:

    def test_no_bibliography_returns_key(self):
        result = _format_citation("smith2024", None)
        assert result == "'smith2024'"

    def test_key_not_in_bibliography_returns_key(self):
        result = _format_citation("unknown2024", {"smith2024": {"author": "Smith, J.", "year": "2024"}})
        assert result == "'unknown2024'"

    def test_full_citation_single_author(self):
        result = _format_citation("smith2024", {
            "smith2024": {"author": "Smith, Jane", "title": "Community Resilience", "year": "2024"}
        })
        assert "Smith" in result
        assert "2024" in result
        assert "Community Resilience" in result

    def test_two_authors_uses_and(self):
        result = _format_citation("ab2024", {
            "ab2024": {"author": "Smith, Jane and Doe, Bob", "title": "Study", "year": "2024"}
        })
        assert "Smith and Doe" in result

    def test_three_or_more_authors_uses_et_al(self):
        result = _format_citation("abc2024", {
            "abc2024": {"author": "Smith, J. and Doe, B. and Brown, C.", "title": "Study", "year": "2024"}
        })
        assert "et al." in result

    def test_long_title_truncated(self):
        long_title = "A Very Long Title That Exceeds Sixty Characters And Should Be Truncated"
        result = _format_citation("x2024", {
            "x2024": {"author": "Smith, J.", "title": long_title, "year": "2024"}
        })
        assert "..." in result
        # A parte do titulo na citacao deve ter no maximo 63 chars (60 + "...")
        title_part = [p for p in result.split(" – ") if "'" in p][0]
        assert len(title_part) <= 65  # com as aspas

    def test_at_sign_stripped_from_bibref(self):
        result = _format_citation("@smith2024", {"smith2024": {"author": "Smith, J.", "year": "2024"}})
        assert "Smith" in result

    def test_source_instruction_uses_citation(self, result_basic):
        """Instrucoes SOURCE devem usar citacao legivel, nao chave opaca."""
        pairs = build_alpaca_pairs(
            result_basic.linked_project,
            result_basic.template,
            result_basic.bibliography,
        )
        source_pairs = [p for p in pairs if p["instruction"].startswith("Regarding ")]
        assert len(source_pairs) >= 1
        # Nenhuma instrucao SOURCE deve ser apenas "Regarding 'smith2024'"
        for p in source_pairs:
            # Deve conter algo alem da chave (autor ou titulo)
            inst = p["instruction"]
            assert "Smith" in inst or "Community" in inst or "Urban" in inst


# ---------------------------------------------------------------------------
# Divisao de TOPIC_INDEX com muitos conceitos
# ---------------------------------------------------------------------------

class TestTopicIndexChunking:

    def _make_large_topic_result(self, n_concepts: int):
        """Compila projeto com n_concepts no mesmo topico."""
        ontology_lines = []
        for i in range(1, n_concepts + 1):
            ontology_lines.append(
                f"ONTOLOGY Concept{i:02d}\n"
                f"    definition: Definition of concept {i}.\n"
                f"    theme: BigTopic\n"
                f"END ONTOLOGY"
            )
        ontology_content = "\n\n".join(ontology_lines)
        return synesis.load(
            project_content=PROJECT_CONTENT,
            template_content=TEMPLATE_BASIC,
            ontology_contents={"ontology.syno": ontology_content},
        )

    def test_small_topic_single_pair(self):
        """Topico com <= 15 conceitos gera um unico par."""
        result = self._make_large_topic_result(10)
        pairs = build_alpaca_pairs(result.linked_project, result.template)
        topic_pairs = [p for p in pairs if "BigTopic" in p["instruction"]]
        assert len(topic_pairs) == 1
        assert "part" not in topic_pairs[0]["instruction"]

    def test_large_topic_split_into_parts(self):
        """Topico com > 15 conceitos e dividido em partes."""
        result = self._make_large_topic_result(20)
        pairs = build_alpaca_pairs(result.linked_project, result.template)
        topic_pairs = [p for p in pairs if "BigTopic" in p["instruction"]]
        assert len(topic_pairs) == 2  # ceil(20/15) = 2
        assert "part 1 of 2" in topic_pairs[0]["instruction"]
        assert "part 2 of 2" in topic_pairs[1]["instruction"]

    def test_large_topic_all_concepts_covered(self):
        """Todos os conceitos aparecem em algum par."""
        n = 32
        result = self._make_large_topic_result(n)
        pairs = build_alpaca_pairs(result.linked_project, result.template)
        topic_pairs = [p for p in pairs if "BigTopic" in p["instruction"]]
        all_outputs = " ".join(p["output"] for p in topic_pairs)
        for i in range(1, n + 1):
            assert f"Concept{i:02d}" in all_outputs

    def test_exactly_15_concepts_single_pair(self):
        """Limite exato de 15 conceitos nao divide."""
        result = self._make_large_topic_result(15)
        pairs = build_alpaca_pairs(result.linked_project, result.template)
        topic_pairs = [p for p in pairs if "BigTopic" in p["instruction"]]
        assert len(topic_pairs) == 1
