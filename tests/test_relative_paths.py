"""C-3: every path in the exports is relative to the project folder.

Before, `traceability.file`, the template and ontology locations (and, depending
on the invocation, the project and include locations) carried the author's
absolute paths, and two copies of a project produced different JSON.
"""

import csv
import json
import re
import shutil
from pathlib import Path

import openpyxl

from synesis.compiler import SynesisCompiler
from synesis.exporters.csv_export import export_csv
from synesis.exporters.json_export import build_json_payload
from synesis.exporters.xls_export import export_xls

ABS = re.compile(r"[A-Za-z]:[\\/]|^/")
TEMPLATE = (
    "ITEM FIELDS\n    REQUIRED code\nEND ITEM FIELDS\n"
    "FIELD code TYPE CODE\n    SCOPE ITEM\nEND FIELD\n"
    "ONTOLOGY FIELDS\n    OPTIONAL definition\nEND ONTOLOGY FIELDS\n"
    "FIELD definition TYPE TEXT\n    SCOPE ONTOLOGY\nEND FIELD\n"
)


def _project(root: Path, shared: bool = False) -> Path:
    proj = root / "proj"
    (proj / "anotacoes").mkdir(parents=True)
    (proj / "t.synt").write_text(TEMPLATE, encoding="utf-8")
    (proj / "r.bib").write_text("@misc{a1,\n  title = {T}\n}\n", encoding="utf-8")
    (proj / "anotacoes" / "a.syn").write_text(
        "SOURCE @a1\nEND SOURCE\n\nITEM @a1\n    code: water\nEND ITEM\n", encoding="utf-8")
    if shared:
        (root / "comum").mkdir()
        (root / "comum" / "o.syno").write_text("ONTOLOGY water\nEND ONTOLOGY\n", encoding="utf-8")
        onto = 'INCLUDE SHARED ONTOLOGY "../comum/o.syno"\n'
    else:
        (proj / "o.syno").write_text("ONTOLOGY water\nEND ONTOLOGY\n", encoding="utf-8")
        onto = 'INCLUDE ONTOLOGY "o.syno"\n'
    synp = proj / "p.synp"
    synp.write_text('PROJECT p\nTEMPLATE "t.synt"\nINCLUDE BIBLIOGRAPHY "r.bib"\n'
                    'INCLUDE ANNOTATIONS "anotacoes"\n' + onto + "END PROJECT\n", encoding="utf-8")
    return synp


def _payload(synp: Path) -> dict:
    r = SynesisCompiler(synp.resolve()).compile()
    assert not r.has_errors(), r.get_diagnostics()
    return build_json_payload(r.linked_project, r.template, r.bibliography, r.dataset, generated_at="X")


def _all_files(obj, acc):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "file" and isinstance(v, str):
                acc.append(v)
            else:
                _all_files(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            _all_files(v, acc)
    return acc


def test_json_paths_are_project_relative(tmp_path):
    payload = _payload(_project(tmp_path))
    files = _all_files(payload, [])
    assert files and not [f for f in files if ABS.search(f)]
    assert payload["corpus"][0]["traceability"]["file"] == "anotacoes/a.syn"
    assert payload["project"]["location"]["file"] == "p.synp"
    assert payload["export_metadata"]["paths_relative_to"] == "project_folder"


def test_shared_file_outside_the_folder_uses_parent_reference(tmp_path):
    payload = _payload(_project(tmp_path, shared=True))
    assert payload["ontology"]["water"]["location"]["file"] == "../comum/o.syno"


def test_two_copies_produce_the_same_json(tmp_path):
    a = _project(tmp_path / "a")
    b_root = tmp_path / "somewhere" / "else"
    shutil.copytree(a.parent, b_root / "proj")
    pa = json.dumps(_payload(a), sort_keys=True)
    pb = json.dumps(_payload(b_root / "proj" / "p.synp"), sort_keys=True)
    assert pa == pb


def test_csv_and_xls_paths_are_project_relative(tmp_path):
    synp = _project(tmp_path)
    r = SynesisCompiler(synp.resolve()).compile()
    out = tmp_path / "csv"
    export_csv(r.linked_project, r.template, out, r.bibliography, r.dataset)
    values = [cell for f in out.glob("*.csv")
              for row in csv.reader(f.open(encoding="utf-8")) for cell in row]
    assert "anotacoes/a.syn" in values
    assert not [v for v in values if ABS.search(v) and v.endswith((".syn", ".syno", ".synp"))]
    xls = tmp_path / "out.xlsx"
    export_xls(r.linked_project, r.template, xls, r.bibliography, r.dataset)
    cells = [c for ws in openpyxl.load_workbook(xls) for row in ws.iter_rows(values_only=True)
             for c in row if isinstance(c, str)]
    assert "anotacoes/a.syn" in cells
    assert not [c for c in cells if ABS.search(c) and c.endswith((".syn", ".syno", ".synp"))]
