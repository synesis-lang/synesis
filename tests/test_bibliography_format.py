"""
test_bibliography_format.py - Testes para deteccao de .bib malformado (erro 72)

Cobre: detect_malformed_entries(), integracao no compilador e na API in-memory.

Gerado conforme: Especificacao Synesis v1.1
"""

import synesis
from synesis.compiler import SynesisCompiler
from synesis.parser.bib_loader import detect_malformed_entries
from tests.conftest import (
    ANNOTATIONS_VALID,
    BIBLIOGRAPHY_BASIC,
    ONTOLOGY_VALID,
    PROJECT_CONTENT,
    TEMPLATE_BASIC,
)


# Formato invalido: sem tipo de entrada, chave fora de chaves, campos com ":"
MALFORMED_BIB = """\
@smith2024
    title: {Community Resilience}
    year: {2024}
"""

# Chave com @ no inicio (ex: @book{@BibliaNVT,...})
AT_KEY_BIB = """\
@book{@smith2024,
    title = {Community Resilience},
    year = {2024}
}
"""

# Uma entrada valida seguida de uma malformada
MIXED_BIB = """\
@article{jones2023,
    title = {Urban Studies},
    year = {2023}
}

@smith2024
    title: {Community Resilience}
    year: {2024}
"""


def _ecodes(result):
    return [e.CODE for e in result.errors]


# ===========================================================================
# detect_malformed_entries()
# ===========================================================================

class TestDetectMalformedEntries:

    def test_detects_malformed_entry(self):
        malformed = detect_malformed_entries(MALFORMED_BIB)
        assert len(malformed) == 1
        key, line = malformed[0]
        assert key == "smith2024"
        assert line == 1

    def test_valid_bib_returns_empty(self):
        assert detect_malformed_entries(BIBLIOGRAPHY_BASIC) == []

    def test_empty_content_returns_empty(self):
        assert detect_malformed_entries("") == []

    def test_mixed_bib_flags_only_malformed(self):
        malformed = detect_malformed_entries(MIXED_BIB)
        assert len(malformed) == 1
        key, line = malformed[0]
        assert key == "smith2024"
        assert line == 6

    def test_detects_at_prefix_in_key(self):
        malformed = detect_malformed_entries(AT_KEY_BIB)
        assert len(malformed) == 1
        key, line = malformed[0]
        assert key == "smith2024"
        assert line == 1


# ===========================================================================
# Integracao com o compilador (SYNESIS_E072)
# ===========================================================================

def _write_project(tmp_path, bib_content):
    (tmp_path / "template.synt").write_text(TEMPLATE_BASIC, encoding="utf-8")
    (tmp_path / "references.bib").write_text(bib_content, encoding="utf-8")
    (tmp_path / "annotations.syn").write_text(ANNOTATIONS_VALID, encoding="utf-8")
    (tmp_path / "ontology.syno").write_text(ONTOLOGY_VALID, encoding="utf-8")
    synp = tmp_path / "project.synp"
    synp.write_text(PROJECT_CONTENT, encoding="utf-8")
    return synp


class TestCompilerIntegration:

    def test_malformed_bib_reports_e072(self, tmp_path):
        synp = _write_project(tmp_path, MALFORMED_BIB)
        result = SynesisCompiler(synp).compile().validation_result
        assert "SYNESIS_E072" in _ecodes(result)

    def test_e072_points_to_bib_file_and_key(self, tmp_path):
        synp = _write_project(tmp_path, MALFORMED_BIB)
        result = SynesisCompiler(synp).compile().validation_result
        errors = [e for e in result.errors if e.CODE == "SYNESIS_E072"]
        assert len(errors) == 1
        assert errors[0].entry_key == "smith2024"
        assert str(errors[0].location.file).endswith("references.bib")
        assert errors[0].location.line == 1

    def test_valid_bib_has_no_e072(self, tmp_path):
        synp = _write_project(tmp_path, BIBLIOGRAPHY_BASIC)
        result = SynesisCompiler(synp).compile().validation_result
        assert "SYNESIS_E072" not in _ecodes(result)

    def test_malformed_bib_suppresses_e001_for_malformed_key(self, tmp_path):
        synp = _write_project(tmp_path, MALFORMED_BIB)
        result = SynesisCompiler(synp).compile().validation_result
        assert "SYNESIS_E072" in _ecodes(result)
        assert "SYNESIS_E001" not in _ecodes(result)

    def test_at_prefix_key_reports_e072(self, tmp_path):
        synp = _write_project(tmp_path, AT_KEY_BIB)
        result = SynesisCompiler(synp).compile().validation_result
        assert "SYNESIS_E072" in _ecodes(result)
        errors = [e for e in result.errors if e.CODE == "SYNESIS_E072"]
        assert errors[0].entry_key == "smith2024"

    def test_at_prefix_key_suppresses_e001(self, tmp_path):
        synp = _write_project(tmp_path, AT_KEY_BIB)
        result = SynesisCompiler(synp).compile().validation_result
        assert "SYNESIS_E001" not in _ecodes(result)


# ===========================================================================
# Integracao com a API in-memory synesis.load()
# ===========================================================================

class TestApiIntegration:

    def test_malformed_bibliography_content_reports_e072(self):
        result = synesis.load(
            project_content=PROJECT_CONTENT,
            template_content=TEMPLATE_BASIC,
            annotation_contents={"annotations.syn": ANNOTATIONS_VALID},
            ontology_contents={"ontology.syno": ONTOLOGY_VALID},
            bibliography_content=MALFORMED_BIB,
        )
        assert "SYNESIS_E072" in _ecodes(result.validation_result)

    def test_valid_bibliography_content_has_no_e072(self):
        result = synesis.load(
            project_content=PROJECT_CONTENT,
            template_content=TEMPLATE_BASIC,
            annotation_contents={"annotations.syn": ANNOTATIONS_VALID},
            ontology_contents={"ontology.syno": ONTOLOGY_VALID},
            bibliography_content=BIBLIOGRAPHY_BASIC,
        )
        assert "SYNESIS_E072" not in _ecodes(result.validation_result)

    def test_malformed_bibliography_suppresses_e001_for_malformed_key(self):
        result = synesis.load(
            project_content=PROJECT_CONTENT,
            template_content=TEMPLATE_BASIC,
            annotation_contents={"annotations.syn": ANNOTATIONS_VALID},
            ontology_contents={"ontology.syno": ONTOLOGY_VALID},
            bibliography_content=MALFORMED_BIB,
        )
        assert "SYNESIS_E072" in _ecodes(result.validation_result)
        assert "SYNESIS_E001" not in _ecodes(result.validation_result)
