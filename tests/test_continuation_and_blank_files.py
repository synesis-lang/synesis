"""C-1: continuation lines of field values; C-2: empty or comment-only .syn/.syno.

C-1 (synesis 0.13.4-0.15.0): `field: value` followed by a more indented line
compiled without the continuation, silently. C-2: an empty or comment-only file
raised "Unexpected token <EOF>", so a project could not include an empty .syno
and synesis-coder could not create a first ontology.
"""

from pathlib import Path

import pytest

from synesis import api
from synesis.compiler import SynesisCompiler
from synesis.parser.lexer import SynesisSyntaxError, is_blank_source


def _item(body: str):
    nodes = api.compile_string(f"ITEM @a\n{body}END ITEM\n", "t.syn")
    return nodes[0]


# --- C-1 -------------------------------------------------------------------

def test_text_continuation_is_kept():
    item = _item("    note: first line\n        second line\n    code: x\n")
    assert item.notes == ["first line\nsecond line"]
    assert item.codes == ["x"]


def test_text_continuation_with_crlf():
    nodes = api.compile_string(
        "ITEM @a\r\n    note: first line\r\n        second line\r\n    code: x\r\nEND ITEM\r\n", "t.syn")
    assert nodes[0].notes == ["first line\nsecond line"]


def test_continuation_equals_block_form():
    continued = _item("    note: first line\n        second line\n    code: x\n")
    block = _item("    note:\n        first line\n        second line\n    code: x\n")
    assert continued.notes == block.notes


def test_code_list_continuation():
    item = _item("    code: x,\n        y\n")
    assert item.codes == ["x", "y"]


def test_chain_continuation():
    item = _item("    cadeia: a -> b\n        -> c\n")
    assert item.extra_fields["cadeia"].nodes == ["a", "b", "c"]


def test_continuation_in_source_and_ontology():
    nodes = api.compile_string(
        "SOURCE @a\n    descricao: one\n        two\nEND SOURCE\n"
        "ONTOLOGY conceito\n    definicao: um\n        dois\nEND ONTOLOGY\n", "t.syno")
    source = next(n for n in nodes if type(n).__name__ == "SourceNode")
    onto = next(n for n in nodes if type(n).__name__ == "OntologyNode")
    assert "two" in str(source.fields.get("descricao") or source.extra_fields.get("descricao"))
    assert "dois" in str(onto.fields.get("definicao") or onto.description)


def test_multiline_continuation_more_than_two_lines():
    item = _item("    note: a\n        b\n        c\n    code: x\n")
    assert item.notes == ["a\nb\nc"]


# --- C-2 -------------------------------------------------------------------

@pytest.mark.parametrize("content", ["", "\n\n", "# only a comment\n", "﻿# bom\n  \n"])
def test_blank_content_has_no_blocks(content):
    assert is_blank_source(content)
    assert api.compile_string(content, "empty.syno") == []


def test_real_syntax_error_still_raises():
    assert not is_blank_source("ITEM @a\n    note: x\n")
    with pytest.raises(SynesisSyntaxError):
        api.compile_string("ITEM @a\n    note: x\n", "broken.syn")


def test_load_with_empty_ontology():
    """synesis.load is what synesis-coder `ontology` uses to read the previous state."""
    template = (
        "ITEM FIELDS\n    REQUIRED code\nEND ITEM FIELDS\n"
        "FIELD code TYPE CODE\n    SCOPE ITEM\nEND FIELD\n"
        "ONTOLOGY FIELDS\n    REQUIRED description\nEND ONTOLOGY FIELDS\n"
        "FIELD description TYPE TEXT\n    SCOPE ONTOLOGY\nEND FIELD\n"
    )
    project = 'PROJECT p\nTEMPLATE "t.synt"\nINCLUDE ONTOLOGY "o.syno"\nEND PROJECT\n'
    api.load(project_content=project, template_content=template,
             annotation_contents={}, ontology_contents={"o.syno": ""})


def test_project_with_empty_and_comment_only_files(tmp_path: Path):
    (tmp_path / "t.synt").write_text(
        "ITEM FIELDS\n    REQUIRED code\nEND ITEM FIELDS\n"
        "FIELD code TYPE CODE\n    SCOPE ITEM\nEND FIELD\n"
        "ONTOLOGY FIELDS\n    REQUIRED description\nEND ONTOLOGY FIELDS\n"
        "FIELD description TYPE TEXT\n    SCOPE ONTOLOGY\nEND FIELD\n", encoding="utf-8")
    (tmp_path / "o.syno").write_text("", encoding="utf-8")
    (tmp_path / "a.syn").write_text("# nothing coded yet\n", encoding="utf-8")
    (tmp_path / "p.synp").write_text(
        'PROJECT p\nTEMPLATE "t.synt"\nINCLUDE ANNOTATIONS "a.syn"\n'
        'INCLUDE ONTOLOGY "o.syno"\nEND PROJECT\n', encoding="utf-8")
    result = SynesisCompiler(tmp_path / "p.synp").compile()
    unreadable = [e for e in result.validation_result.errors
                  if type(e).__name__ == "UnreadableIncludedFile"]
    assert unreadable == []


def test_empty_template_is_still_an_error(tmp_path: Path):
    (tmp_path / "t.synt").write_text("", encoding="utf-8")
    (tmp_path / "p.synp").write_text('PROJECT p\nTEMPLATE "t.synt"\nEND PROJECT\n', encoding="utf-8")
    result = SynesisCompiler(tmp_path / "p.synp").compile()
    assert result.has_errors()
