"""
test_role_value_by_type.py - Etapa A2a do plano ROLE/EXPORT (Spec v7, §1-§3)

    - `ROLE <FAMILIA> [<ESPECIE>]` no FIELD, na forma canonica;
    - valor do ONTOLOGY lido pelo TIPO declarado, com ou sem ROLE: TEXT com `->`
      e texto, CODE e lista de conceitos declarados;
    - a mesma leitura nos tres caminhos que validam ONTOLOGY (disco,
      `synesis.load`, adaptador do LSP) e em compilacoes sucessivas;
    - E101 (conceito sem bloco), E102 (item vazio), W031 (item repetido).
"""

from __future__ import annotations

from pathlib import Path

import synesis
from synesis.compiler import SynesisCompiler
from synesis.lsp_adapter import ValidationContext, validate_single_file
from synesis.parser.template_loader import load_template_from_string

TEMPLATE = """\
ONTOLOGY FIELDS
    REQUIRED definicao
    OPTIONAL tipo_de
END ONTOLOGY FIELDS

FIELD definicao TYPE TEXT
    SCOPE ONTOLOGY
    ROLE note definition
END FIELD

FIELD tipo_de TYPE CODE
    SCOPE ONTOLOGY
    ROLE HIERARCHY KIND
END FIELD
"""

ONTOLOGY = """\
ONTOLOGY smishing
    definicao: Phishing por SMS -> leva ao golpe
    tipo_de: phishing
END ONTOLOGY

ONTOLOGY phishing
    definicao: Fraude por comunicacao enganosa.
END ONTOLOGY
"""

PROJECT = 'PROJECT p\nTEMPLATE "t.synt"\nINCLUDE ONTOLOGY "o.syno"\nEND PROJECT\n'


def _load(ontology: str = ONTOLOGY, template: str = TEMPLATE):
    return synesis.load(
        project_content=PROJECT, template_content=template, ontology_contents={"o.syno": ontology}
    )


def _codes(result) -> list[str]:
    vr = result.validation_result if hasattr(result, "validation_result") else result
    return [e.CODE for e in vr.errors + vr.warnings]


class TestRole:
    def test_role_is_canonical_and_reaches_json(self):
        template = _load().template
        assert template.field_specs["definicao"].role == "NOTE DEFINITION"
        assert template.field_specs["tipo_de"].to_dict()["role"] == "HIERARCHY KIND"

    def test_field_without_role_has_no_role_key(self):
        template = load_template_from_string(TEMPLATE.replace("    ROLE HIERARCHY KIND\n", ""), "t.synt")
        assert "role" not in template.field_specs["tipo_de"].to_dict()

    def test_repeated_role_is_kept_for_the_diagnostic(self):
        t = TEMPLATE.replace("    ROLE HIERARCHY KIND\n", "    ROLE HIERARCHY KIND\n    ROLE HIERARCHY PART\n")
        spec = load_template_from_string(t, "t.synt").field_specs["tipo_de"]
        assert spec.role == "HIERARCHY KIND"
        assert spec.role_repeats == ["HIERARCHY PART"]


class TestValueByType:
    def test_text_with_arrow_is_text(self):
        result = _load()
        assert not result.validation_result.has_errors(), result.get_diagnostics()
        node = result.linked_project.ontology_index["smishing"]
        assert node.fields["definicao"] == "Phishing por SMS -> leva ao golpe"
        assert result.to_json_dict()["ontology"]["smishing"]["definicao"] == "Phishing por SMS -> leva ao golpe"

    def test_code_is_a_list_with_or_without_role(self):
        template = TEMPLATE.replace("    ROLE HIERARCHY KIND\n", "")
        ontology = ONTOLOGY.replace("tipo_de: phishing", "tipo_de: phishing, smishing")
        result = _load(ontology, template)
        assert result.to_json_dict()["ontology"]["smishing"]["tipo_de"] == ["phishing", "smishing"]

    def test_e101_undeclared_concept_even_without_role(self):
        template = TEMPLATE.replace("    ROLE HIERARCHY KIND\n", "")
        result = _load(ONTOLOGY.replace("tipo_de: phishing", "tipo_de: phishing, fraude"), template)
        assert "SYNESIS_E101" in _codes(result)
        assert result.validation_result.has_errors()

    def test_e102_empty_item(self):
        result = _load(ONTOLOGY.replace("tipo_de: phishing", "tipo_de: phishing, , phishing"))
        assert "SYNESIS_E102" in _codes(result)

    def test_w031_repeated_item(self):
        result = _load(ONTOLOGY.replace("tipo_de: phishing", "tipo_de: phishing, phishing"))
        assert "SYNESIS_W031" in _codes(result)

    def test_parsed_node_is_not_mutated(self):
        """A projecao devolve uma copia; o no parseado (parse_cache) nao muda."""
        from synesis.ast.nodes import ChainNode
        from synesis.semantic.ontology_values import project_ontology

        template = _load().template
        node = next(n for n in synesis.compile_string(ONTOLOGY, "o.syno") if getattr(n, "concept", "") == "smishing")
        assert isinstance(node.fields["definicao"], ChainNode)  # o transformer decide pelo conteudo
        projected = project_ontology(node, template)
        assert projected is not node
        assert projected.fields["definicao"] == "Phishing por SMS -> leva ao golpe"
        assert isinstance(node.fields["definicao"], ChainNode)  # intocado


class TestThreePaths:
    def _write(self, root: Path) -> Path:
        (root / "t.synt").write_text(TEMPLATE, encoding="utf-8")
        (root / "o.syno").write_text(ONTOLOGY, encoding="utf-8")
        synp = root / "p.synp"
        synp.write_text(PROJECT, encoding="utf-8")
        return synp

    def test_disk_compile_twice_gives_same_result(self, tmp_path):
        synp = self._write(tmp_path)
        first = SynesisCompiler(synp).compile()
        second = SynesisCompiler(synp).compile()
        assert not first.has_errors(), first.get_diagnostics()
        assert first.get_diagnostics() == second.get_diagnostics()
        a = first.linked_project.ontology_index["smishing"].fields
        b = second.linked_project.ontology_index["smishing"].fields
        assert a == b == {"definicao": "Phishing por SMS -> leva ao golpe", "tipo_de": ["phishing"]}

    def test_lsp_path_accepts_text_with_arrow(self, tmp_path):
        synp = self._write(tmp_path)
        compiled = SynesisCompiler(synp).compile()
        context = ValidationContext(
            template=compiled.template,
            ontology_index=dict(compiled.linked_project.ontology_index),
        )
        for _ in range(2):
            result = validate_single_file(ONTOLOGY, (tmp_path / "o.syno").as_uri(), context)
            assert "SYNESIS_E028" not in _codes(result)
            assert not result.errors, [e.to_cli_line() for e in result.errors]


class TestIdentityNFC:
    """Etapa A2b: normalizador unico com NFC (Spec §4)."""

    def test_composed_and_decomposed_names_are_one_identity(self):
        import unicodedata

        from synesis.ast.normalize import normalize_code

        assert normalize_code(unicodedata.normalize("NFD", "Inovação")) == normalize_code("inovação")

    def test_e103_identity_collision(self):
        import unicodedata

        nfd = unicodedata.normalize("NFD", "ação")
        nfc = unicodedata.normalize("NFC", "ação")
        ontology = (
            f"ONTOLOGY {nfc}\n    definicao: Uma.\nEND ONTOLOGY\n\n"
            f"ONTOLOGY {nfd}\n    definicao: Outra.\nEND ONTOLOGY\n"
        )
        result = _load(ontology)
        assert "SYNESIS_E103" in _codes(result)
