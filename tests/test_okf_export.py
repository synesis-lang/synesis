"""Exportador OKF v0.2 (experimental) — critérios de aceitação do estudo (§11.3).

Um só projeto de fixture exercita o que o template permite e o corpus real
quase não usa: `quote` repetido, `note` e `memo` no mesmo ITEM, BUNDLE
MEMO+CODE com vários códigos numa ocorrência, CHAIN qualificada e simples no
mesmo template, CHAIN de ONTOLOGY (`is_a`), TOPIC, um conceito chamado `Log`
(nome reservado do OKF) e valores com Markdown/HTML e caractere de controle.
"""

import re

import yaml
from click.testing import CliRunner
from markdown_it import MarkdownIt

import synesis
from synesis.cli import main
from synesis.exporters.okf_export import build_okf_bundle, md_literal
from tests.conftest import BIBLIOGRAPHY_BASIC, PROJECT_CONTENT

TEMPLATE = """\
TEMPLATE okf

ITEM FIELDS
    REQUIRED quote
    OPTIONAL note, memo, chain, cadeia
    OPTIONAL BUNDLE justificativa, rotulos
END ITEM FIELDS

FIELD quote TYPE QUOTATION
    SCOPE ITEM
END FIELD

FIELD note TYPE MEMO
    SCOPE ITEM
END FIELD

FIELD memo TYPE MEMO
    SCOPE ITEM
END FIELD

FIELD justificativa TYPE MEMO
    SCOPE ITEM
END FIELD

FIELD rotulos TYPE CODE
    SCOPE ITEM
END FIELD

FIELD chain TYPE CHAIN
    SCOPE ITEM
    ARITY >= 2
    RELATIONS
        GERA: A produz B
    END RELATIONS
END FIELD

FIELD cadeia TYPE CHAIN
    SCOPE ITEM
    ARITY >= 2
END FIELD

ONTOLOGY FIELDS
    REQUIRED definicao
    OPTIONAL grupo, is_a
END ONTOLOGY FIELDS

FIELD definicao TYPE TEXT
    SCOPE ONTOLOGY
END FIELD

FIELD grupo TYPE TOPIC
    SCOPE ONTOLOGY
END FIELD

FIELD is_a TYPE CHAIN
    SCOPE ONTOLOGY
    ARITY >= 2
END FIELD
"""

ANNOTATIONS = """\
SOURCE @smith2024
END SOURCE

ITEM @smith2024
    quote: PRIMEIRO trecho
    quote: SEGUNDO trecho
    note: NOTA-DO-NOTE
    memo: ### Falso cabecalho <a id="falsa"></a> - item [link](https://x.y)
    justificativa: m1
    rotulos: X, Y
    justificativa: m2
    rotulos: Z
    chain: Alfa -> GERA -> Beta
    cadeia: Gama -> Delta -> Log
END ITEM
"""

ONTOLOGY = """\
ONTOLOGY Log
    definicao: Conceito chamado Log\u0085 com controle C1.
    grupo: Temas
    is_a: Log -> Alfa
END ONTOLOGY

ONTOLOGY Alfa
    definicao: Primeiro conceito.
    grupo: Temas
END ONTOLOGY
"""

MD = MarkdownIt("commonmark")


def _result():
    r = synesis.load(
        project_content=PROJECT_CONTENT,
        template_content=TEMPLATE,
        annotation_contents={"annotations.syn": ANNOTATIONS},
        ontology_contents={"ontology.syno": ONTOLOGY},
        bibliography_content=BIBLIOGRAPHY_BASIC,
    )
    assert not r.has_errors(), r.get_diagnostics(verbose=False)
    return r


def _front(text: str) -> dict:
    match = re.match(r"---\n(.*?)\n---\n", text, re.S)
    assert match, text[:200]
    return yaml.safe_load(match.group(1))


def _segments(text: str) -> dict:
    """{campo: [trecho de cada ocorrência rotulada **campo:**]} de um documento."""
    out: dict = {}
    current = None
    for line in text.splitlines():
        label = re.fullmatch(r"\*\*(.+?):\*\*", line)
        if label:
            current = label.group(1).replace("\\", "")
            out.setdefault(current, []).append("")
        elif line.startswith(("#", "*Origem:*", "<a id=")):
            current = None
        elif current and line.strip():
            out[current][-1] += re.sub(r"\\(.)", r"\1", line) + "\n"  # desfaz md_literal
    return out


def test_bundle_is_conformant_linked_and_deterministic():
    r = _result()
    files = build_okf_bundle(r.linked_project, r.template, r.bibliography)
    assert files == build_okf_bundle(r.linked_project, r.template, r.bibliography)
    assert _front(files["index.md"]) == {"okf_version": "0.2"}
    for path, text in files.items():
        if path.split("/")[-1] == "index.md":
            assert path == "index.md" or not text.startswith("---"), path
            continue
        front = _front(text)
        assert str(front["type"]).strip(), path
        assert "at" not in front.get("generated", {}), path  # sem data, sem relógio
        assert "verified" not in front, path
        for target in re.findall(r"\]\((/[^)#]+)", text):
            assert target.lstrip("/") in files, (path, target)
    # `log` é nome reservado do OKF: o conceito Log ganha outro nome de arquivo.
    assert "concepts/log.md" not in files and "concepts/log-concept.md" in files
    # Controle C1 no valor: escapado no YAML e lido de volta igual (o valor integral).
    fields = _front(files["concepts/log-concept.md"])["synesis"]["fields"]
    assert fields["definicao"] == ["Conceito chamado Log\u0085 com controle C1."]


def test_item_keeps_every_occurrence_and_bundle_pairs():
    r = _result()
    doc = build_okf_bundle(r.linked_project, r.template, r.bibliography)["sources/smith2024.md"]
    segs = _segments(doc)
    quotes = "".join(segs["quote"])
    assert quotes.index("PRIMEIRO") < quotes.index("SEGUNDO")
    assert "NOTA-DO-NOTE" in "".join(segs["note"]) and "NOTA-DO-NOTE" not in "".join(segs["memo"])
    pairs = list(zip(segs["justificativa"], segs["rotulos"]))
    assert len(pairs) == 2
    assert "m1" in pairs[0][0] and "[X]" in pairs[0][1] and "[Y]" in pairs[0][1]
    assert "m2" in pairs[1][0] and "[Z]" in pairs[1][1] and "[X]" not in pairs[1][1]


def test_chain_triples_follow_each_field_without_hierarchy():
    r = _result()
    files = build_okf_bundle(r.linked_project, r.template, r.bibliography)
    alfa = _front(files["concepts/alfa.md"])["synesis"]["relations"]
    assert [(x["field"], x["relation"], x["target"]) for x in alfa] == [("chain", "GERA", "Beta")]
    log = _front(files["concepts/log-concept.md"])["synesis"]["relations"]
    assert {(x["field"], x["relation"], x["target"]) for x in log} == {("is_a", "", "Alfa")}
    assert "Gama" in files["codes/gama.md"] and "**→**" in files["sources/smith2024.md"]
    assert "hierarchy" not in str(files)  # nenhuma relação é marcada como IS_A


def test_values_never_become_markdown_structure():
    cases = [
        "### Technical Skills",
        "- item",
        "1. item",
        'texto <a id="falsa"></a> no meio',
        "veja [link](https://x.y)",
        "**negrito** e `codigo`",
        "rodapé [^id]",
        "linha\n===",
        "    recuo",
        "| a | b |\n|---|---|",
        "> citação",
        "&amp; e \\* já presentes",
        "__dunder__",
        "1986. ano no início",
        "* * *",
    ]
    for value in cases:
        tokens = MD.parse(md_literal(value))
        kinds = {t.type for t in tokens} | {c.type for t in tokens for c in (t.children or [])}
        assert kinds <= {"paragraph_open", "paragraph_close", "inline", "text", "softbreak"}, (
            value,
            kinds,
        )
        visible = "\n".join(
            c.content for t in tokens for c in (t.children or []) if c.type == "text"
        )
        assert " ".join(visible.replace(" ", " ").split()) == " ".join(value.split()), value
    r = _result()
    doc = build_okf_bundle(r.linked_project, r.template, r.bibliography)["sources/smith2024.md"]
    # No documento real: o valor chega escapado — texto, não cabeçalho nem âncora.
    assert '\\### Falso cabecalho \\<a id="falsa">\\</a>' in doc
    tokens = MD.parse(doc.split("---\n", 2)[2])
    assert not [
        t
        for t in tokens
        if t.type == "heading_open" and t.map and "Falso" in doc.splitlines()[t.map[0]]
    ]


def test_generated_at_is_optional_and_needs_time_zone():
    r = _result()
    files = build_okf_bundle(
        r.linked_project, r.template, r.bibliography, generated_at="2026-10-23T10:00:00-03:00"
    )
    assert _front(files["codebook.md"])["generated"]["at"] == "2026-10-23T10:00:00-03:00"
    try:
        build_okf_bundle(
            r.linked_project, r.template, r.bibliography, generated_at="2026-10-23T10:00:00"
        )
    except ValueError:
        pass
    else:
        raise AssertionError("data sem fuso deveria ser recusada")


def test_cli_writes_bundle_and_refuses_non_empty_directory(tmp_path):
    (tmp_path / "template.synt").write_text(TEMPLATE, encoding="utf-8")
    (tmp_path / "references.bib").write_text(BIBLIOGRAPHY_BASIC, encoding="utf-8")
    (tmp_path / "annotations.syn").write_text(ANNOTATIONS, encoding="utf-8")
    (tmp_path / "ontology.syno").write_text(ONTOLOGY, encoding="utf-8")
    (tmp_path / "project.synp").write_text(PROJECT_CONTENT, encoding="utf-8")
    bundle = tmp_path / "bundle"
    runner = CliRunner()
    first = runner.invoke(main, ["compile", str(tmp_path / "project.synp"), "--okf", str(bundle)])
    assert first.exit_code == 0, first.output
    assert (bundle / "index.md").is_file() and (bundle / "sources" / "smith2024.md").is_file()
    again = runner.invoke(main, ["compile", str(tmp_path / "project.synp"), "--okf", str(bundle)])
    assert again.exit_code == 1 and "não está vazia" in again.output
