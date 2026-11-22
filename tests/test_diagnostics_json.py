"""C-4: `synesis compile --diagnostics-json PATH` writes every diagnostic on every exit path."""

import json
from pathlib import Path

from click.testing import CliRunner

from synesis.cli import main

TEMPLATE = (
    "SOURCE FIELDS\n    OPTIONAL description\nEND SOURCE FIELDS\n"
    "FIELD description TYPE TEXT\n    SCOPE SOURCE\nEND FIELD\n"
    "ITEM FIELDS\n    REQUIRED code\nEND ITEM FIELDS\n"
    "FIELD code TYPE CODE\n    SCOPE ITEM\nEND FIELD\n"
    "ONTOLOGY FIELDS\n    REQUIRED definition\nEND ONTOLOGY FIELDS\n"
    "FIELD definition TYPE TEXT\n    SCOPE ONTOLOGY\nEND FIELD\n"
)


def _project(tmp_path: Path, annotations: str, template: str | None = TEMPLATE) -> Path:
    if template is not None:
        (tmp_path / "t.synt").write_text(template, encoding="utf-8")
    (tmp_path / "r.bib").write_text("@misc{a1,\n  title = {T}\n}\n", encoding="utf-8")
    (tmp_path / "a.syn").write_text(annotations, encoding="utf-8")
    (tmp_path / "o.syno").write_text("ONTOLOGY water\n    definition: Access to water.\nEND ONTOLOGY\n",
                                     encoding="utf-8")
    synp = tmp_path / "p.synp"
    synp.write_text('PROJECT p\nTEMPLATE "t.synt"\nINCLUDE BIBLIOGRAPHY "r.bib"\n'
                    'INCLUDE ANNOTATIONS "a.syn"\nINCLUDE ONTOLOGY "o.syno"\nEND PROJECT\n',
                    encoding="utf-8")
    return synp


def _run(synp: Path, *extra: str):
    out = synp.parent / "diag" / "report.json"
    result = CliRunner().invoke(main, ["compile", str(synp), "--diagnostics-json", str(out), *extra])
    report = json.loads(out.read_text(encoding="utf-8")) if out.exists() else None
    return result, report


GOOD = "SOURCE @a1\nEND SOURCE\n\nITEM @a1\n    code: water\nEND ITEM\n"


def test_clean_project(tmp_path):
    result, report = _run(_project(tmp_path, GOOD))
    assert result.exit_code == 0
    assert report["format"] == "synesis-diagnostics" and report["exit_code"] == 0
    assert report["errors"] == 0 and report["warnings"] == 0 and report["diagnostics"] == []


def test_report_written_when_project_has_errors(tmp_path):
    result, report = _run(_project(tmp_path, "ITEM @nope\n    code: water\nEND ITEM\n"))
    assert result.exit_code == 1
    assert report["exit_code"] == 1 and report["errors"] >= 1
    first = report["diagnostics"][0]
    assert first["severity"] == "error" and first["file"] == "a.syn" and first["line"] == 1
    assert ":\\" not in json.dumps(report)  # no absolute Windows paths


def test_report_written_when_strict_blocks_on_warnings(tmp_path):
    synp = _project(tmp_path, "SOURCE @a1\nEND SOURCE\n\nITEM @a1\n    code: unknown_code\nEND ITEM\n")
    result, report = _run(synp, "--strict")
    assert result.exit_code == 1
    assert report["errors"] == 0 and report["warnings"] >= 1 and report["exit_code"] == 1


def test_report_written_when_template_is_missing(tmp_path):
    result, report = _run(_project(tmp_path, GOOD, template=None))
    assert result.exit_code == 1
    assert report["errors"] >= 1


def test_report_written_on_project_syntax_error(tmp_path):
    synp = _project(tmp_path, GOOD)
    synp.write_text("PROJECT p\nTEMPLATE\n", encoding="utf-8")
    result, report = _run(synp)
    assert result.exit_code == 1
    assert report["errors"] == 1 and report["diagnostics"][0]["code"] == "SynesisSyntaxError"


def test_linking_mode_warns_instead_of_ignoring(tmp_path):
    a = _project(tmp_path / "a" if (tmp_path / "a").mkdir() is None else tmp_path, GOOD)
    b_dir = tmp_path / "b"
    b_dir.mkdir()
    b = _project(b_dir, GOOD)
    result = CliRunner().invoke(main, ["compile", str(a), str(b), "--diagnostics-json",
                                       str(tmp_path / "x.json")])
    assert "--diagnostics-json is not yet supported in the linking step" in result.output
