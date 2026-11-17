"""
okf_export.py - Exportador OKF (Open Knowledge Format v0.2) do projeto Synesis

Propósito:
    Gerar um bundle OKF — uma pasta de arquivos Markdown com frontmatter YAML —
    que um agente lê navegando, sem servidor. EXPERIMENTAL: a especificação
    OKF (GoogleCloudPlatform/open-knowledge-format) ainda está em v0.2.

Componentes principais:
    - build_okf_bundle: bundle em memória ({caminho: texto}), função pura
    - export_okf: grava o bundle numa pasta vazia
    - md_literal: valor do pesquisador como texto literal em Markdown

Estrutura do bundle (tudo guiado pelo template):
    index.md                     raiz, com okf_version
    codebook.md                  o próprio template (FIELD por escopo)
    concepts/<conceito>.md       um por bloco ONTOLOGY (status: stable)
    codes/<código>.md            código usado sem conceito (status: draft)
    topics/<campo>/<valor>.md    um por valor de campo TOPIC, de qualquer escopo
    sources/<bibref>.md          um por SOURCE; cada ITEM é uma seção com âncora

Regras:
    - Campo, ordem, rótulo, BUNDLE, VALUES e RELATIONS vêm do template; o
      valor vem POR OCORRÊNCIA (occurrences.field_occurrences): duas
      ocorrências de um campo são duas, e o k-ésimo par de um BUNDLE junta a
      k-ésima ocorrência de cada membro.
    - CHAIN: triplas no modo do PRÓPRIO campo. Nenhuma relação é marcada como
      hierarquia (IS_A é decisão de linguagem em aberto).
    - Todo valor é texto literal (md_literal): não cria cabeçalho, lista, link,
      âncora ou HTML no documento. A formatação visível é só do gerador.
    - Sem I/O e sem relógio: mesma entrada, mesmos bytes. `generated.at` só
      entra quando o chamador fornece a data.
    - `verified` nunca é escrito: o Synesis não registra quem revisou.

Dependências críticas:
    - synesis.semantic.occurrences: valor por ocorrência
    - synesis.exporters.json_export: id do ITEM e frequência (mesma regra do JSON)

Gerado conforme: OKF v0.2 (SPEC.md), Especificacao Synesis v3.0
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from synesis.ast.nodes import ChainNode, FieldSpec, FieldType, Scope, TemplateNode
from synesis.ast.normalize import normalize_bibref, normalize_code
from synesis.exporters._helpers import _get_source_field_value
from synesis.exporters.json_export import (
    _build_chain_usage,
    _build_code_frequency_index,
    _format_item_id,
)
from synesis.parser.bib_loader import find_bibref
from synesis.semantic.linker import LinkedProject
from synesis.semantic.occurrences import field_occurrences

OKF_VERSION = "0.2"
_RESERVED = {"index", "log"}  # OKF v0.2: nomes reservados em qualquer nível da árvore
_MAX_SLUG = 80
_MAX_EVIDENCE = 50

# ---------------------------------------------------------------------------
# Texto literal e YAML
# ---------------------------------------------------------------------------

# Estrutura em qualquer posição: escape, código, ênfase (*), link/rodapé ([ ]),
# HTML/autolink (<), entidade (&), tabela (|), tachado/cerca (~).
_ANYWHERE = re.compile(r"[\\`*\[\]<&|~]")
# `_` só abre/fecha ênfase fora de palavra (CommonMark: `a_b` é literal). A
# sequência inteira de `_` é que conta: em `__x__` o 2º `_` também abre ênfase.
_UNDERSCORES = re.compile(r"_+")


def _escape_underscores(body: str) -> str:
    def repl(match: re.Match[str]) -> str:
        before = body[match.start() - 1] if match.start() > 0 else ""
        after = body[match.end()] if match.end() < len(body) else ""
        if before.isalnum() and after.isalnum():
            return match.group()
        return "\\_" * len(match.group())

    return _UNDERSCORES.sub(repl, body)


# Estrutura só no início da linha: cabeçalho, citação, listas, setext.
_LINE_START = re.compile(r"^([#>+\-=])")
_ORDERED = re.compile(r"^(\d+)([.)])")


def md_literal(text: Any) -> str:
    """Valor como texto literal em Markdown (CommonMark).

    Escapa com barra invertida só o que cria estrutura, onde cria: o texto
    visível fica igual ao valor, nenhum trecho vira cabeçalho, lista, ênfase,
    link, rodapé, HTML ou tabela, e a prosa continua legível para quem lê o
    arquivo cru (vírgula, ponto, parênteses e `a_b` ficam como estão). O recuo
    inicial vira &nbsp;: quatro espaços abririam um bloco de código.
    """
    out = []
    for line in str(text).splitlines():
        body = line.lstrip(" \t")
        lead = len(line) - len(body)
        body = _escape_underscores(_ANYWHERE.sub(r"\\\g<0>", body))
        body = _ORDERED.sub(r"\1\\\2", _LINE_START.sub(r"\\\1", body))
        out.append("&nbsp;" * lead + body)
    return "\n".join(out)


_YAML_UNSAFE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f  ﻿￾￿]")


def _yaml_scalar(value: Any) -> str:
    """Escalar YAML seguro sem PyYAML: JSON é YAML válido entre aspas duplas.

    Controles C0/C1 e separadores de linha Unicode viram \\uXXXX — o YAML os
    proíbe ou os dobraria como quebra de linha.
    """
    return _YAML_UNSAFE.sub(
        lambda m: "\\u%04x" % ord(m.group()), json.dumps(value, ensure_ascii=False)
    )


def _front_matter(data: Dict[str, Any]) -> str:
    lines = ["---"]

    def emit(key: str, value: Any, indent: int) -> None:
        pad = "  " * indent
        if isinstance(value, dict) and value:
            lines.append(f"{pad}{key}:")
            for k, v in value.items():
                emit(_yaml_scalar(k), v, indent + 1)
        elif isinstance(value, list) and value:
            lines.append(f"{pad}{key}:")
            for item in value:
                if isinstance(item, dict) and item:
                    first = True
                    for k, v in item.items():
                        prefix = f"{pad}  - " if first else f"{pad}    "
                        lines.append(f"{prefix}{_yaml_scalar(k)}: {_yaml_scalar(v)}")
                        first = False
                else:
                    lines.append(f"{pad}  - {_yaml_scalar(item)}")
        else:
            lines.append(f"{pad}{key}: {_yaml_scalar(value)}")

    for k, v in data.items():
        emit(k, v, 0)
    lines.append("---")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Nomes de arquivo
# ---------------------------------------------------------------------------


def _slug(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return (slug or "x")[:_MAX_SLUG].strip("-") or "x"


class _Slugs:
    """Nome de arquivo único por pasta, sem colisão de caixa/acento (FS do Windows/macOS)."""

    def __init__(self, keys: Iterable[str]) -> None:
        self._by_key: Dict[str, str] = {}
        used: set = set()
        for key in keys:
            if key in self._by_key:
                continue
            base = _slug(key)
            if base in _RESERVED:
                base = f"{base}-concept"
            slug, n = base, 2
            while slug in used:
                slug, n = f"{base}-{n}", n + 1
            used.add(slug)
            self._by_key[key] = slug

    def __getitem__(self, key: str) -> str:
        return self._by_key[key]

    def items(self) -> List[Tuple[str, str]]:
        return list(self._by_key.items())


# ---------------------------------------------------------------------------
# Construção
# ---------------------------------------------------------------------------


def _first_sentence(text: str) -> str:
    flat = " ".join(str(text).split())
    match = re.match(r"(.+?[.!?])(\s|$)", flat)
    return (match.group(1) if match else flat)[:300]


def _clean_bib(value: Any) -> Any:
    return re.sub(r"[{}]", "", value).strip() if isinstance(value, str) else value


def _check_generated_at(generated_at: Optional[str]) -> None:
    if generated_at is None:
        return
    try:
        parsed = datetime.fromisoformat(generated_at)
    except ValueError as exc:
        raise ValueError(f"generated_at não é ISO 8601: {generated_at!r}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"generated_at precisa de fuso horário (OKF v0.2): {generated_at!r}")


class _Builder:
    def __init__(
        self,
        linked: LinkedProject,
        template: TemplateNode,
        bibliography: Optional[Dict[str, Any]],
        dataset: Optional[Dict[str, Any]],
        producer: str,
        generated_at: Optional[str],
    ) -> None:
        self.linked = linked
        self.t = template
        self.bib = bibliography or {}
        self.dataset = dataset
        self.generated: Dict[str, Any] = {"by": producer}
        if generated_at is not None:
            self.generated["at"] = generated_at
        self.specs = template.field_specs
        self.files: Dict[str, str] = {}

        # Uso dos códigos (CODE e CHAIN do ITEM, pelo tipo) e relações por conceito.
        self.usage: Dict[str, List[Tuple[str, str]]] = {}
        self.relations: Dict[str, List[Dict[str, Any]]] = {}
        self.code_label: Dict[str, str] = {}
        # Todo código citado (CODE/CHAIN de qualquer escopo) tem documento — o link nunca quebra;
        # a evidência (`usage`) vem só dos ITEMs.
        self.mentioned: set = set()
        self.topic_values: Dict[Tuple[str, str], set] = {}
        self._collect()

        onto = linked.ontology_index
        self.concept_slugs = _Slugs(sorted(onto))
        self.code_slugs = _Slugs(
            sorted(k for k in set(self.usage) | self.mentioned if k not in onto)
        )
        self.source_slugs = _Slugs(sorted(normalize_bibref(b) for b in linked.sources))
        self.topic_slugs = {
            field: _Slugs(sorted(v for f, v in self.topic_values if f == field))
            for field in sorted({f for f, _ in self.topic_values})
        }
        self.frequency = _build_code_frequency_index(linked, _build_chain_usage(linked, template))

    # --- template e valores -------------------------------------------------

    def _fields(self, scope: Scope) -> List[Tuple[str, FieldSpec]]:
        return [(n, s) for n, s in self.specs.items() if s.scope == scope]

    def _bundles(self, scope: Scope) -> List[Tuple[str, ...]]:
        bundles = list(self.t.bundled_fields.get(scope, []))
        bundles += list((self.t.optional_bundles or {}).get(scope, []))
        return [tuple(b) for b in bundles]

    def _occurrences(self, scope: Scope, node: Any, name: str, spec: FieldSpec) -> List[Any]:
        values = field_occurrences(node, name, self.t)
        if values or scope != Scope.SOURCE or spec.value_origin == "document":
            return values
        # ON BIBLIOGRAPHY / ON DATASET: o valor mora fora do bloco SOURCE.
        external = _get_source_field_value(node, name, self.t, self.bib, self.dataset)
        return [external] if external not in (None, "", []) else []

    def _triples(self, spec: FieldSpec, chain: ChainNode) -> List[Tuple[str, str, str]]:
        return chain.to_triples(has_relations=bool(spec.relations))

    def _bib_entry(self, bibref: str) -> Dict[str, Any]:
        entry = find_bibref(self.bib, bibref.lstrip("@")) if self.bib else None
        return dict(entry) if entry else {}

    def _collect(self) -> None:
        for bibref in sorted(self.linked.sources, key=normalize_bibref):
            source = self.linked.sources[bibref]
            for name, spec in self._fields(Scope.SOURCE):
                if spec.type == FieldType.TOPIC:
                    for value in self._occurrences(Scope.SOURCE, source, name, spec):
                        self.topic_values.setdefault((name, str(value)), set())
            for index, item in enumerate(source.items, start=1):
                item_id = _format_item_id(source.bibref, index)
                for name, spec in self._fields(Scope.ITEM):
                    for value in field_occurrences(item, name, self.t):
                        if spec.type == FieldType.CODE:
                            for code in value:
                                self._use(code, source.bibref, item_id)
                        elif spec.type == FieldType.CHAIN and isinstance(value, ChainNode):
                            for a, rel, b in self._triples(spec, value):
                                self._use(a, source.bibref, item_id)
                                self._use(b, source.bibref, item_id)
                                self.relations.setdefault(normalize_code(a), []).append(
                                    {
                                        "field": name,
                                        "relation": rel if spec.relations else "",
                                        "target": b,
                                        "bibref": source.bibref,
                                        "item": item_id,
                                    }
                                )
                        elif spec.type == FieldType.TOPIC:
                            self.topic_values.setdefault((name, str(value)), set())
        for key in sorted(self.linked.ontology_index):
            ontology = self.linked.ontology_index[key]
            for name, spec in self._fields(Scope.ONTOLOGY):
                for value in field_occurrences(ontology, name, self.t):
                    if spec.type == FieldType.TOPIC:
                        self.topic_values.setdefault((name, str(value)), set()).add(key)
                    else:
                        self._mention(spec, value)
        for source in self.linked.sources.values():
            for name, spec in self._fields(Scope.SOURCE):
                for value in field_occurrences(source, name, self.t):
                    self._mention(spec, value)

    def _mention(self, spec: FieldSpec, value: Any) -> None:
        codes: List[str] = []
        if spec.type == FieldType.CODE:
            codes = [str(code) for code in value]
        elif spec.type == FieldType.CHAIN and isinstance(value, ChainNode):
            codes = [c for a, _r, b in self._triples(spec, value) for c in (a, b)]
        for code in codes:
            key = normalize_code(code)
            self.code_label.setdefault(key, code)
            self.mentioned.add(key)

    def _use(self, code: str, bibref: str, item_id: str) -> None:
        key = normalize_code(str(code))
        self.code_label.setdefault(key, str(code))
        self.mentioned.add(key)
        hits = self.usage.setdefault(key, [])
        if (bibref, item_id) not in hits:
            hits.append((bibref, item_id))

    # --- links ---------------------------------------------------------------

    def _code_link(self, code: str) -> str:
        key = normalize_code(str(code))
        if key in self.linked.ontology_index:
            return f"[{md_literal(code)}](/concepts/{self.concept_slugs[key]}.md)"
        return f"[{md_literal(code)}](/codes/{self.code_slugs[key]}.md)"

    def _source_path(self, bibref: str) -> str:
        return f"/sources/{self.source_slugs[normalize_bibref(bibref)]}.md"

    def _topic_link(self, field: str, value: str) -> str:
        return f"[{md_literal(value)}](/topics/{_slug(field)}/{self.topic_slugs[field][str(value)]}.md)"

    def _footnote_id(self, bibref: str) -> str:
        return self.source_slugs[normalize_bibref(bibref)]

    # --- renderização por tipo -------------------------------------------------

    def _label(self, spec: FieldSpec, value: Any) -> str:
        """ENUMERATED/ORDERED: rótulo e descrição vêm de VALUES do template."""
        raw = value
        if isinstance(value, str) and value.strip().lstrip("-").isdigit():
            raw = int(value.strip())
        for option in spec.values or []:
            if (isinstance(raw, int) and option.index == raw) or str(value) == option.label:
                index = f" [{option.index}]" if spec.type == FieldType.ORDERED else ""
                text = f"{option.label}{index}" + (
                    f" — {option.description}" if option.description else ""
                )
                return md_literal(text)
        return md_literal(value)

    def _render_value(self, spec: FieldSpec, value: Any) -> List[str]:
        kind = spec.type
        if kind == FieldType.CHAIN:
            if not isinstance(value, ChainNode):
                return [md_literal(value)]
            return [
                f"- {self._code_link(a)} **{md_literal(r) if spec.relations else '→'}** {self._code_link(b)}"
                for a, r, b in self._triples(spec, value)
            ]
        if kind == FieldType.CODE:
            return [", ".join(self._code_link(code) for code in value)]
        if kind == FieldType.TOPIC:
            return [self._topic_link(spec.name, str(value))]
        if kind in (FieldType.ENUMERATED, FieldType.ORDERED):
            return [self._label(spec, value)]
        if kind == FieldType.QUOTATION:
            return ["> " + line if line else ">" for line in md_literal(value).split("\n")]
        return [md_literal(value)]

    def _render_field(self, spec: FieldSpec, values: List[Any]) -> List[str]:
        out = [f"**{md_literal(spec.name)}:**", ""]
        for value in values:
            out += self._render_value(spec, value) + [""]
        return out

    def _plain(self, spec: FieldSpec, value: Any) -> Any:
        """Valor de UMA ocorrência para a extensão `synesis` do frontmatter."""
        if isinstance(value, ChainNode):
            return [{"from": a, "relation": r, "to": b} for a, r, b in self._triples(spec, value)]
        if isinstance(value, list):
            return [str(v) for v in value]
        if isinstance(value, (int, float)):
            return value
        return str(value)

    def _render_block(self, scope: Scope, node: Any) -> Tuple[List[str], Dict[str, Any]]:
        """Corpo e extensão de um nó: campos na ordem do template, BUNDLE por ocorrência."""
        fields = dict(self._fields(scope))
        occurrences = {n: self._occurrences(scope, node, n, s) for n, s in fields.items()}
        ext = {
            n: [self._plain(fields[n], v) for v in vals] for n, vals in occurrences.items() if vals
        }
        body: List[str] = []
        done: set = set()
        for name in fields:
            if name in done:
                continue
            bundle = next((b for b in self._bundles(scope) if name in b), None)
            if bundle:
                members = [m for m in bundle if m in fields]
                done.update(members)
                width = max((len(occurrences[m]) for m in members), default=0)
                for k in range(width):
                    body += [f"### {md_literal(' + '.join(members))} ({k + 1})", ""]
                    for member in members:
                        if k < len(occurrences[member]):
                            body += self._render_field(fields[member], [occurrences[member][k]])
                continue
            done.add(name)
            if occurrences[name]:
                body += self._render_field(fields[name], occurrences[name])
        return body, ext

    # --- documentos -----------------------------------------------------------

    def _write(self, path: str, front: Optional[Dict[str, Any]], body: List[str]) -> None:
        head = _front_matter(front) + "\n\n" if front is not None else ""
        self.files[path] = head + "\n".join(body).rstrip() + "\n"

    def _sources_entries(self, hits: List[Tuple[str, str]]) -> List[Dict[str, str]]:
        entries = []
        for bibref in sorted({b for b, _ in hits}, key=normalize_bibref):
            entry = {"id": self._footnote_id(bibref), "resource": self._source_path(bibref)}
            title = self._bib_entry(bibref).get("title")
            if title:
                entry["title"] = _clean_bib(title)
            entries.append(entry)
        return entries

    def _evidence(self, hits: List[Tuple[str, str]]) -> List[str]:
        lines = ["## Evidências", ""]
        for bibref, item_id in hits[:_MAX_EVIDENCE]:
            lines.append(
                f"- [{item_id}]({self._source_path(bibref)}#{item_id})[^{self._footnote_id(bibref)}]"
            )
        if len(hits) > _MAX_EVIDENCE:
            lines.append(f"- … e mais {len(hits) - _MAX_EVIDENCE} ocorrência(s), nas fontes")
        lines.append("")
        for bibref in sorted({b for b, _ in hits}, key=normalize_bibref):
            title = _clean_bib(self._bib_entry(bibref).get("title") or bibref)
            lines.append(f"[^{self._footnote_id(bibref)}]: {md_literal(title)}")
        return lines

    def build(self) -> Dict[str, str]:
        self._concepts()
        self._codes()
        self._sources()
        self._topics()
        self._codebook()
        self._indexes()
        return dict(sorted(self.files.items()))

    def _concepts(self) -> None:
        onto = self.linked.ontology_index
        text_fields = [n for n, s in self._fields(Scope.ONTOLOGY) if s.type == FieldType.TEXT]
        topic_fields = [n for n, s in self._fields(Scope.ONTOLOGY) if s.type == FieldType.TOPIC]
        chain_fields = [
            (n, s) for n, s in self._fields(Scope.ONTOLOGY) if s.type == FieldType.CHAIN
        ]
        for key in sorted(onto):
            ontology = onto[key]
            body, ext = self._render_block(Scope.ONTOLOGY, ontology)
            description = next(
                (vals[0] for n in text_fields if (vals := field_occurrences(ontology, n, self.t))),
                "",
            )
            tags = [str(v) for n in topic_fields for v in field_occurrences(ontology, n, self.t)]
            relations = [
                {
                    "field": r["field"],
                    "relation": r["relation"],
                    "target": r["target"],
                    "item": r["item"],
                }
                for r in self.relations.get(key, [])
            ]
            # CHAIN da própria ONTOLOGY: relação entre conceitos, com o nome do campo (sem IS_A).
            for name, spec in chain_fields:
                for value in field_occurrences(ontology, name, self.t):
                    if isinstance(value, ChainNode):
                        for a, relation, b in self._triples(spec, value):
                            relations.append(
                                {
                                    "field": name,
                                    "relation": relation if spec.relations else "",
                                    "from": a,
                                    "target": b,
                                }
                            )
            hits = self.usage.get(key, [])
            front: Dict[str, Any] = {"type": "Concept", "title": ontology.concept}
            if description:
                front["description"] = _first_sentence(description)
            if tags:
                front["tags"] = tags
            front["status"] = "stable"
            front["generated"] = self.generated
            if hits:
                front["sources"] = self._sources_entries(hits)
            synesis_ext: Dict[str, Any] = {"fields": ext, "frequency": self.frequency.get(key, 0)}
            if relations:
                synesis_ext["relations"] = relations
            front["synesis"] = synesis_ext
            doc = [f"# {md_literal(ontology.concept)}", ""] + body
            if self.relations.get(key):
                doc += ["## Relações", ""]
                for rel_info in self.relations[key]:
                    rel = md_literal(rel_info["relation"]) if rel_info["relation"] else "→"
                    doc.append(
                        f"- {md_literal(ontology.concept)} **{rel}** {self._code_link(rel_info['target'])} — "
                        f"{md_literal(rel_info['field'])}, [{rel_info['item']}]({self._source_path(rel_info['bibref'])}#{rel_info['item']})"
                        f"[^{self._footnote_id(rel_info['bibref'])}]"
                    )
                doc.append("")
            if hits:
                doc += self._evidence(hits)
            self._write(f"concepts/{self.concept_slugs[key]}.md", front, doc)

    def _codes(self) -> None:
        for key, slug in self.code_slugs.items():
            hits = self.usage.get(key, [])
            label = self.code_label.get(key, key)
            front: Dict[str, Any] = {
                "type": "Code",
                "title": label,
                "description": f"Código sem conceito na ontologia ({len(hits)} ITEM(s)).",
                "status": "draft",
                "generated": self.generated,
            }
            if hits:
                front["sources"] = self._sources_entries(hits)
            front["synesis"] = {"frequency": self.frequency.get(key, 0)}
            body = [f"# {md_literal(label)}", ""] + (self._evidence(hits) if hits else [])
            self._write(f"codes/{slug}.md", front, body)

    def _sources(self) -> None:
        for bibref in sorted(self.linked.sources, key=normalize_bibref):
            source = self.linked.sources[bibref]
            entry = self._bib_entry(source.bibref)
            body, ext = self._render_block(Scope.SOURCE, source)
            title = _clean_bib(entry.get("title")) or source.bibref
            front: Dict[str, Any] = {"type": "Source", "title": title}
            if entry.get("doi"):
                front["resource"] = "https://doi.org/" + _clean_bib(entry["doi"])
            elif entry.get("url"):
                front["resource"] = _clean_bib(entry["url"])
            front["generated"] = self.generated
            front["synesis"] = {
                "bibref": source.bibref,
                "fields": ext,
                "bibliography": {
                    k: _clean_bib(v)
                    for k, v in entry.items()
                    if k != "ID" and not k.startswith("_")
                },
            }
            doc = [f"# {md_literal(title)}", ""] + body
            for index, item in enumerate(source.items, start=1):
                item_id = _format_item_id(source.bibref, index)
                item_body, _ = self._render_block(Scope.ITEM, item)
                origin = f"{item.location.file.name}:{item.location.line}" if item.location else "?"
                doc += [f'<a id="{item_id}"></a>', f"## ITEM {index}", ""] + item_body
                doc += [f"*Origem:* {md_literal(origin)}", ""]
            self._write(f"sources/{self.source_slugs[normalize_bibref(bibref)]}.md", front, doc)

    def _topics(self) -> None:
        onto = self.linked.ontology_index
        for field, slugs in self.topic_slugs.items():
            for value, slug in slugs.items():
                members = sorted(self.topic_values.get((field, value), set()))
                body = [f"# {md_literal(value)}", ""]
                if members:
                    body += ["## Conceitos", ""] + [
                        f"- {self._code_link(onto[m].concept)}" for m in members
                    ]
                self._write(
                    f"topics/{_slug(field)}/{slug}.md",
                    {"type": field, "title": value, "generated": self.generated},
                    body,
                )

    def _codebook(self) -> None:
        body = [f"# {md_literal(self.t.name or 'Template')}", ""]
        for scope in Scope:
            fields = self._fields(scope)
            if not fields:
                continue
            body += [f"## {scope.value}", ""]
            for name, spec in fields:
                body += [f"### {md_literal(name)}", "", f"- tipo: {spec.type.value}"]
                for attr in ("description", "format", "arity", "identifies", "refers_to"):
                    if getattr(spec, attr):
                        body.append(f"- {attr}: {md_literal(getattr(spec, attr))}")
                if spec.value_origin != "document":
                    body.append(f"- origem do valor: {spec.value_origin}")
                for option in spec.values or []:
                    body.append(
                        f"- valor \\[{option.index}\\] {md_literal(option.label)}: {md_literal(option.description)}"
                    )
                for rel, meaning in (spec.relations or {}).items():
                    body.append(f"- relação {md_literal(rel)}: {md_literal(meaning)}")
                if spec.guidelines:
                    body += ["", md_literal(spec.guidelines)]
                body.append("")
        self._write(
            "codebook.md",
            {"type": "Codebook", "title": self.t.name or "Template", "generated": self.generated},
            body,
        )

    def _indexes(self) -> None:
        folders = sorted({path.split("/")[0] for path in self.files if "/" in path})
        for folder in folders:
            docs = sorted(p for p in self.files if p.startswith(folder + "/") and p.count("/") == 1)
            subdirs = sorted(
                {
                    p.split("/")[1]
                    for p in self.files
                    if p.startswith(folder + "/") and p.count("/") == 2
                }
            )
            lines = [f"# {folder}", ""]
            lines += [f"- [{sub}](/{folder}/{sub}/index.md)" for sub in subdirs]
            lines += [f"- [{_title_of(self.files[d])}](/{d})" for d in docs]
            self.files[f"{folder}/index.md"] = "\n".join(lines) + "\n"
            for sub in subdirs:
                inner = sorted(
                    p
                    for p in self.files
                    if p.startswith(f"{folder}/{sub}/") and not p.endswith("index.md")
                )
                sub_lines = [f"# {sub}", ""] + [
                    f"- [{_title_of(self.files[d])}](/{d})" for d in inner
                ]
                self.files[f"{folder}/{sub}/index.md"] = "\n".join(sub_lines) + "\n"
        project = self.linked.project
        root = [
            "---",
            f"okf_version: {_yaml_scalar(OKF_VERSION)}",
            "---",
            "",
            f"# {md_literal(project.name)}",
            "",
        ]
        if project.description:
            root += [md_literal(project.description.strip()), ""]
        root += ["- [Livro de códigos](/codebook.md)"] + [
            f"- [{folder}](/{folder}/index.md)" for folder in folders
        ]
        root += [
            "",
            "*Gerado pelo Synesis. Nenhum documento registra revisão humana (`verified`).*",
        ]
        self.files["index.md"] = "\n".join(root) + "\n"


def _title_of(text: str) -> str:
    """Título já escapado do documento: a primeira linha `# ` do corpo."""
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:]
    return ""


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


def build_okf_bundle(
    linked: LinkedProject,
    template: TemplateNode,
    bibliography: Optional[Dict[str, Any]] = None,
    dataset: Optional[Dict[str, Any]] = None,
    *,
    producer: Optional[str] = None,
    generated_at: Optional[str] = None,
) -> Dict[str, str]:
    """Bundle OKF v0.2 em memória: {caminho no bundle: texto do arquivo}.

    Função pura: sem I/O e sem relógio. `generated_at` (ISO 8601 com fuso) só
    entra no frontmatter quando fornecido; `producer` padrão é
    "synesis/<versão>".

    Raises:
        ValueError: sem template, ou `generated_at` inválido/sem fuso.
    """
    if template is None:
        raise ValueError("OKF exige template: a estrutura do bundle vem dele")
    _check_generated_at(generated_at)
    if producer is None:
        from synesis import __version__

        producer = f"synesis/{__version__}"
    return _Builder(linked, template, bibliography, dataset, producer, generated_at).build()


def export_okf(
    linked: LinkedProject,
    path: Path,
    template: TemplateNode,
    bibliography: Optional[Dict[str, Any]] = None,
    dataset: Optional[Dict[str, Any]] = None,
    *,
    generated_at: Optional[str] = None,
) -> int:
    """Grava o bundle numa pasta nova ou vazia. Devolve o número de arquivos.

    Pasta com conteúdo é recusada: misturar rodadas deixaria documentos de
    conceitos que não existem mais.

    Raises:
        FileExistsError: a pasta existe e não está vazia.
    """
    path = Path(path)
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise FileExistsError(f"pasta de destino não está vazia: {path}")
    files = build_okf_bundle(linked, template, bibliography, dataset, generated_at=generated_at)
    for relative, text in files.items():
        target = path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
    return len(files)
