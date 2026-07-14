"""
cli.py - Interface de linha de comando do compilador Synesis

Proposito:
    Expor comandos de compilacao, validacao e inicializacao de projetos.
    Gerencia saida de diagnosticos e codigos de retorno.

Componentes principais:
    - main: grupo principal Click
    - compile/check/validate_template/init: comandos CLI

Dependencias criticas:
    - click: CLI
    - synesis.compiler: pipeline principal
    - synesis.parser/template_loader: validacao isolada

Exemplo de uso:
    synesis compile projeto.synp --json out.json --csv out_dir

Notas de implementacao:
    - Saidas usam formato arquivo:linha:coluna: [SEVERITY] mensagem.
    - --force permite exportacao mesmo com erros.

Gerado conforme: Especificacao Synesis v1.1
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from pathlib import Path
from typing import Iterable

try:
    import click
except ImportError:
    raise ImportError(
        "click nao encontrado. CLI requer instalacao com: pip install synesis[cli]"
    )

from synesis import __version__ as VERSION
from synesis.compiler import SynesisCompiler
from synesis.exporters.alpaca_export import export_alpaca
from synesis.exporters.csv_export import export_csv
from synesis.exporters.json_export import export_json
from synesis.exporters.xls_export import export_xls
from synesis.parser.lexer import SynesisSyntaxError, parse_file
from synesis.parser.template_loader import TemplateLoadError, load_template

# ---------------------------------------------------------------------------
# Helpers de estilo
# ---------------------------------------------------------------------------

def _tty() -> bool:
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _c(text: str, **kwargs) -> str:
    return click.style(text, **kwargs) if _tty() else text


def _configure_logging(verbose: int, quiet: int) -> None:
    """Set root log level: -q → WARNING/ERROR, default → INFO, -v → DEBUG."""
    if quiet >= 2:
        level = logging.ERROR
    elif quiet == 1:
        level = logging.WARNING
    elif verbose >= 1:
        level = logging.DEBUG
    else:
        level = logging.INFO
    logging.basicConfig(level=level, format="[%(levelname)s] %(message)s")


_COPYRIGHT = "Copyright (c) 2011-2026 Christian Maciel de Britto"
_LICENSE   = "MIT (AGPL-3.0-only WITH Synesis-data-output-exception pending)"
_URL       = "https://github.com/synesis-lang/synesis"

_CREDITS_TEXT = f"""\
SYNESIS — Intellectual Genealogy
=================================
{_COPYRIGHT}
https://orcid.org/0000-0003-1431-3924

The Synesis compiler is the formal culmination of a research and
development trajectory spanning more than a decade. The following
prior works contributed to its architecture:

  BDM — Banco de Dados Multimodal (2011-2013)
  Master's dissertation, UFPR. DOI:10.13140/RG.2.2.10686.10563
  First definition of: sources, items, factors, relations,
  ontology, and knowledge graph as an integrated structure.

  SocioAtlas (2016-2018)
  Doctoral thesis, UFPR. DOI:10.13140/RG.2.2.26449.17760
  Integration of annotations, audit trails, Zotero,
  georeferenced data, and knowledge graphs.

  DSAP annotation pipeline (2019-2020)
  Professional consultancy, environmental sector.
  First professional validation of the audit trail:
  corpus → item → summary → theme → score.

  SocioAtlas para Google Sheets (2022)
  Independent development, Google Workspace Marketplace.
  Collaboration and portability; first attempt at systematic
  theological study within the same framework.

  DGT.7 pipeline (2024)
  Independent development.
  Text-file knowledge representation; exposed the need
  for formal, readable, validatable syntax.

Full history:
  https://synesis-lang.github.io/synesis-docs/pt/explanation/sobre.html
  https://synesis-lang.github.io/synesis-docs/en/explanation/about.html
"""


def _build_main_help() -> str:
    title = _c("SYNESIS COMPILER", fg="green", bold=True) + f" (v{VERSION})"
    copyright_line = _c(_COPYRIGHT, fg="bright_black")
    url_line       = _c(_URL, fg="bright_black")
    desc = "Semantic compiler for knowledge engineering."
    license_line = _c(f"Licensed under {_LICENSE}.", fg="bright_black")
    usage = _c("Usage:", fg="yellow", bold=True) + " synesis [COMMAND] [OPTIONS]"

    groups = [
        ("Project Management", [
            ("init",              "Creates the minimal structure for a new project"),
        ]),
        ("Compilation & Export", [
            ("compile",           "Compiles the project and generates artifacts (JSON, CSV, XLS, Alpaca)"),
        ]),
        ("Validation & Debugging", [
            ("check",             "Validates the syntax and integrity of a single file"),
            ("validate-template", "Verifies the structure and consistency of a template file"),
        ]),
    ]

    opt_rows = [
        ("-v, --verbose",  "Increase log verbosity (DEBUG). Repeatable."),
        ("-q, --quiet",    "Decrease log verbosity (-q WARNING, -qq ERROR). Repeatable."),
        ("--version",      "Show version and exit"),
        ("--credits",      "Show intellectual genealogy and prior works"),
        ("--help",         "Show this message and exit"),
    ]

    cmd_names_len = max(len(name) for _, rows in groups for name, _ in rows)
    opt_names_len = max(len(name) for name, _ in opt_rows)
    col = max(cmd_names_len, opt_names_len) + 2

    options = _c("Global Options:", fg="yellow", bold=True) + "\n" + "\n".join(
        f"  {_c(name.ljust(col), fg='cyan')}  {desc_}"
        for name, desc_ in opt_rows
    )

    def _render_group(label, rows):
        lines = [_c("  " + label, fg="yellow", bold=True)]
        for name, desc_ in rows:
            lines.append(f"    {_c(name.ljust(col), fg='green', bold=True)}  {desc_}")
        return "\n".join(lines)

    commands = _c("Commands:", fg="yellow", bold=True) + "\n\n" + "\n\n".join(
        _render_group(label, rows) for label, rows in groups
    )

    hint = _c(
        "Run 'synesis COMMAND --help' for specific parameters, output formats, and examples.",
        fg="bright_black",
    )

    return "\n\n".join([title, copyright_line, url_line, desc, license_line, usage, options, commands, hint]) + "\n"


class _SynesisCommand(click.Command):
    def format_epilog(self, ctx, formatter):
        if self.epilog:
            formatter.write("\n")
            for line in self.epilog.splitlines():
                formatter.write(line + "\n")


class _SynesisGroup(click.Group):
    command_class = _SynesisCommand

    def format_help(self, ctx, formatter):
        pass

    def get_help(self, ctx):
        out = _build_main_help()
        if hasattr(sys.stdout, "buffer"):
            sys.stdout.buffer.write(out.encode("utf-8"))
            sys.stdout.buffer.flush()
            raise SystemExit(0)
        return out


def _ex(*lines: str) -> str:
    import re
    out = [_c("Examples:", fg="yellow", bold=True)]
    for line in lines:
        stripped = line.lstrip()
        indent = line[: len(line) - len(stripped)]
        if stripped.startswith("#"):
            out.append(indent + _c(stripped, fg="bright_black"))
        else:
            tokens = re.split(r"(\s+)", stripped)
            result = []
            for tok in tokens:
                if tok == "synesis":
                    result.append(_c(tok, fg="green", bold=True))
                elif re.match(r"^--[\w-]+=?", tok):
                    result.append(_c(tok, fg="cyan"))
                elif tok in ("compile", "check", "validate-template", "init"):
                    result.append(_c(tok, fg="green"))
                else:
                    result.append(tok)
            out.append(indent + "".join(result))
    return "\n".join(out)


_EPILOG_COMPILE = _ex(
    "  # Compile and export to JSON",
    "  synesis compile project.synp --json output.json",
    "",
    "  # Compile and export to CSV directory",
    "  synesis compile project.synp --csv output_csv/",
    "",
    "  # Compile and export to Excel",
    "  synesis compile project.synp --xls output.xlsx",
    "",
    "  # Export Alpaca JSONL for LLM fine-tuning",
    "  synesis compile project.synp --alpaca dataset.jsonl",
    "",
    "  # Combine multiple export formats",
    "  synesis compile project.synp --json out.json --csv out_csv/ --alpaca dataset.jsonl",
    "",
    "  # Show compilation statistics",
    "  synesis compile project.synp --stats",
)

_EPILOG_CHECK = _ex(
    "  # Validate a single annotations file",
    "  synesis check annotations.syn",
    "",
    "  # Validate a template file syntax",
    "  synesis check template.synt",
)

_EPILOG_VALIDATE_TEMPLATE = _ex(
    "  # Verify a template before running compile",
    "  synesis validate-template template.synt",
)

_EPILOG_INIT = _ex(
    "  # Initialize a new project in the current directory",
    "  synesis init",
)


# ---------------------------------------------------------------------------
# Spinner
# ---------------------------------------------------------------------------

class _Spinner:
    """Spinner animado para etapas do pipeline. Desativa-se se stdout nao for TTY."""

    _FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")

    def __init__(self) -> None:
        self._active = False
        self._thread: threading.Thread | None = None
        self._label = ""
        self._is_tty = sys.stderr.isatty()

    def start(self, label: str) -> None:
        self._label = label
        if not self._is_tty:
            sys.stderr.write(f"  {label}...\n")
            sys.stderr.flush()
            return
        self._active = True
        self._t0 = time.monotonic()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def _spin(self) -> None:
        i = 0
        while self._active:
            frame = self._FRAMES[i % len(self._FRAMES)]
            sys.stderr.write(f"\r  {frame} {self._label}...")
            sys.stderr.flush()
            time.sleep(0.08)
            i += 1

    def done(self, suffix: str = "") -> None:
        if not self._is_tty:
            return
        self._active = False
        if self._thread:
            self._thread.join()
        elapsed = time.monotonic() - self._t0
        elapsed_str = click.style(f"({elapsed:.1f}s)", fg="bright_black")
        check = click.style("✔", fg="green", bold=True)
        suffix_str = f"  {suffix}" if suffix else ""
        sys.stderr.write(f"\r  {check} {self._label}{suffix_str}  {elapsed_str}\n")
        sys.stderr.flush()

    def fail(self) -> None:
        if not self._is_tty:
            return
        self._active = False
        if self._thread:
            self._thread.join()
        cross = click.style("✖", fg="red", bold=True)
        sys.stderr.write(f"\r  {cross} {self._label}\n")
        sys.stderr.flush()




def _version_callback(ctx: click.Context, _param: click.Parameter, value: bool) -> None:
    if not value or ctx.resilient_parsing:
        return
    lines = [
        f"synesis {VERSION}",
        _COPYRIGHT,
        f"License: {_LICENSE}",
        _URL,
    ]
    click.echo("\n".join(lines))
    ctx.exit()


def _credits_callback(ctx: click.Context, _param: click.Parameter, value: bool) -> None:
    if not value or ctx.resilient_parsing:
        return
    click.echo(_CREDITS_TEXT, nl=False)
    ctx.exit()


@click.group(cls=_SynesisGroup, invoke_without_command=True)
@click.option("--version", is_flag=True, is_eager=True, expose_value=False,
              callback=_version_callback, help="Show version and exit.")
@click.option("--credits", is_flag=True, is_eager=True, expose_value=False,
              callback=_credits_callback, help="Show intellectual genealogy and prior works.")
@click.option("-v", "--verbose", count=True, default=0,
              help="Increase log verbosity (-v for DEBUG). Repeatable.")
@click.option("-q", "--quiet", count=True, default=0,
              help="Decrease log verbosity (-q for WARNING, -qq for ERROR). Repeatable.")
@click.pass_context
def main(ctx: click.Context, verbose: int, quiet: int) -> None:
    """Compilador semântico para validação e consolidação de conhecimento."""
    _configure_logging(verbose, quiet)
    if ctx.invoked_subcommand is None:
        out = _build_main_help()
        if hasattr(sys.stdout, "buffer"):
            sys.stdout.buffer.write(out.encode("utf-8"))
            sys.stdout.buffer.flush()
        else:
            click.echo(out)


@main.command(cls=_SynesisCommand, epilog=_EPILOG_COMPILE)
@click.argument("project", type=click.Path(exists=True))
@click.option("--json", "json_path", type=click.Path(), help="Export canonical JSON v3.0")
@click.option("--csv", "csv_dir", type=click.Path(), help="Export CSV tables to directory")
@click.option("--xls", "xls_path", type=click.Path(), help="Export Excel workbook (.xlsx)")
@click.option("--alpaca", "alpaca_path", type=click.Path(), help="Export Alpaca JSONL for LLM fine-tuning")
@click.option("--strict", is_flag=True, help="Treat warnings as errors")
@click.option("--stats", is_flag=True, help="Show compilation statistics")
@click.option("--force", is_flag=True, help="Generate artifacts even with errors")
def compile(project: str, json_path: str | None, csv_dir: str | None, xls_path: str | None, alpaca_path: str | None, strict: bool, stats: bool, force: bool) -> None:
    """Compile a Synesis project."""
    click.echo(click.style(f"SYNESIS v{VERSION}", bold=True) + "  Compile seu pensamento.")

    spinner = _Spinner()
    project_path = Path(project)
    project_dir = project_path.parent

    try:
        from synesis.ast.results import MalformedBibliographyEntry, ValidationResult
        from synesis.parser.template_loader import validate_template

        compiler = SynesisCompiler(project_path)

        # Etapa 1: projeto + template + bibliografia
        spinner.start("Lendo projeto e template")
        project_node, project_validation = compiler.parse_project()
        project_validation_structure = compiler.validate_project_structure(project_node)
        bib_validation = compiler._check_bibliography_file(project_node)
        bib_format_validation = compiler._check_bibliography_format(project_node)
        template, template_load_result = compiler._safe_load_template(project_node)
        if template is None:
            spinner.fail()
            result_early = ValidationResult()
            compiler._merge(result_early, project_validation)
            compiler._merge(result_early, project_validation_structure)
            compiler._merge(result_early, template_load_result)
            compiler._merge(result_early, bib_validation)
            compiler._merge(result_early, bib_format_validation)
            _print_diagnostics(result_early.errors, "ERROR", project_dir)
            raise SystemExit(1)
        template_validation = validate_template(template)
        bibliography = compiler.load_bibliography(project_node)
        spinner.done()

        # Etapa 2: ontologia
        spinner.start("Carregando ontologia")
        ontologies, ontology_load_result = compiler.parse_ontologies(project_node)
        spinner.done(f"{len(ontologies):,}".replace(",", ".") + " conceitos")

        # Etapa 3: anotacoes (etapa mais lenta — paralela)
        spinner.start("Lendo anotacoes")
        sources, items, annotations_load_result = compiler.parse_annotations(project_node)
        spinner.done(
            f"{len(sources):,}".replace(",", ".") + " sources, "
            f"{len(items):,}".replace(",", ".") + " items"
        )

        # Etapa 4: validacao semantica
        spinner.start("Validando")
        norm_cache: dict = {}
        malformed_keys = {
            e.entry_key.lower() for e in bib_format_validation.errors
            if isinstance(e, MalformedBibliographyEntry)
        }
        validation_result = compiler.validate_all(
            project=project_node,
            template=template,
            bibliography=bibliography,
            sources=sources,
            items=items,
            ontologies=ontologies,
            norm_cache=norm_cache,
            malformed_bib_keys=malformed_keys,
        )
        compiler._merge(validation_result, project_validation)
        compiler._merge(validation_result, project_validation_structure)
        compiler._merge(validation_result, template_validation)
        compiler._merge(validation_result, bib_validation)
        compiler._merge(validation_result, bib_format_validation)
        compiler._merge(validation_result, ontology_load_result)
        compiler._merge(validation_result, annotations_load_result)
        n_errors = len(validation_result.errors)
        n_warnings = len(validation_result.warnings)
        if n_errors:
            spinner.done(click.style(f"{n_errors} erro(s)", fg="red"))
        elif n_warnings:
            spinner.done(click.style(f"{n_warnings} aviso(s)", fg="yellow"))
        else:
            spinner.done("sem erros")

        # Etapa 5: vinculacao
        spinner.start("Vinculando")
        linked_project = compiler.link_all(
            project=project_node,
            template=template,
            sources=sources,
            items=items,
            ontologies=ontologies,
            validation_result=validation_result,
            norm_cache=norm_cache,
        )
        spinner.done()

        result_stats = compiler._compute_stats(linked_project, sources, items, ontologies)

        click.echo("")
        _print_diagnostics(validation_result.errors, "ERROR", project_dir)
        _print_diagnostics(validation_result.warnings, "WARNING", project_dir)

        if stats:
            click.echo("")
            _print_stats(result_stats)

        has_errors = validation_result.has_errors()
        has_warnings = validation_result.has_warnings()
        exit_code = 1 if has_errors or (strict and has_warnings) else 0

        if (force or exit_code == 0) and linked_project:
            if json_path:
                export_json(linked_project, Path(json_path), template, bibliography)
            if csv_dir:
                export_csv(linked_project, template, Path(csv_dir))
            if xls_path:
                export_xls(linked_project, template, Path(xls_path))
            if alpaca_path:
                export_alpaca(linked_project, Path(alpaca_path), template, bibliography)

        raise SystemExit(exit_code)

    except SystemExit:
        raise
    except SynesisSyntaxError as exc:
        spinner.fail()
        click.echo(click.style(str(exc), fg="red"), err=True)
        raise SystemExit(1)
    except Exception as exc:
        spinner.fail()
        click.echo(click.style(f"erro: Falha inesperada durante compilacao: {exc}", fg="red"), err=True)
        if click.get_current_context().obj and click.get_current_context().obj.get("debug"):
            raise
        raise SystemExit(1)


@main.command(cls=_SynesisCommand, epilog=_EPILOG_CHECK)
@click.argument("file", type=click.Path(exists=True))
def check(file: str) -> None:
    """Validate the syntax and integrity of a single Synesis file."""
    try:
        parse_file(Path(file))
        click.echo(click.style("OK", fg="green"))
        raise SystemExit(0)
    except SynesisSyntaxError as exc:
        click.echo(_format_syntax_error(exc), err=True)
        raise SystemExit(1)


@main.command(cls=_SynesisCommand, epilog=_EPILOG_VALIDATE_TEMPLATE)
@click.argument("template", type=click.Path(exists=True))
def validate_template(template: str) -> None:
    """Verify the structure and consistency of a template file."""
    try:
        load_template(Path(template))
        click.echo(click.style("OK", fg="green"))
        raise SystemExit(0)
    except (SynesisSyntaxError, TemplateLoadError) as exc:
        click.echo(str(exc), err=True)
        raise SystemExit(1)


@main.command(cls=_SynesisCommand, epilog=_EPILOG_INIT)
def init() -> None:
    """Create the minimal structure for a new project in the current directory."""
    cwd = Path.cwd()
    project_path = cwd / "project.synp"
    template_path = cwd / "template.synt"
    bibliography_path = cwd / "references.bib"
    annotations_path = cwd / "annotations.syn"
    ontology_path = cwd / "ontology.syno"

    if not project_path.exists():
        project_path.write_text(
            "PROJECT demo\n"
            '    TEMPLATE "template.synt"\n'
            '    INCLUDE BIBLIOGRAPHY "references.bib"\n'
            '    INCLUDE ANNOTATIONS "annotations.syn"\n'
            '    INCLUDE ONTOLOGY "ontology.syno"\n'
            "END PROJECT\n",
            encoding="utf-8",
        )

    if not template_path.exists():
        template_path.write_text(
            "# =================================================================\n"
            "# DATA SOURCES (Interviews, Articles, Field Notes, etc.)\n"
            "# =================================================================\n"
            "\n"
            "SOURCE FIELDS\n"
            "    OPTIONAL description\n"
            "END SOURCE FIELDS\n"
            "\n"
            "FIELD description TYPE TEXT\n"
            "    SCOPE SOURCE\n"
            "    DESCRIPTION General context, summary, or bibliographic details of the data source\n"
            "    GUIDELINES\n"
            "        Summarize the source purpose and context in 1-2 sentences.\n"
            "        Use only information supported by the source.\n"
            "        Do not add analytical interpretation.\n"
            "    END GUIDELINES\n"
            "END FIELD\n"
            "\n"
            "\n"
            "# =================================================================\n"
            "# DATA EXCERPTS & ANALYSIS (Quotes, Memos, and Codes)\n"
            "# =================================================================\n"
            "\n"
            "ITEM FIELDS\n"
            "    REQUIRED citation, note, code\n"
            "END ITEM FIELDS\n"
            "\n"
            "FIELD citation TYPE QUOTATION\n"
            "    SCOPE ITEM\n"
            "    DESCRIPTION Direct quote or selected excerpt from the data source\n"
            "    GUIDELINES\n"
            "        Extract a complete, self-contained excerpt of 1-3 sentences.\n"
            "        Preserve the original wording and punctuation.\n"
            "        Provide enough context for the excerpt to be understood independently.\n"
            "        Do not paraphrase.\n"
            "    END GUIDELINES\n"
            "END FIELD\n"
            "\n"
            "FIELD note TYPE MEMO\n"
            "    SCOPE ITEM\n"
            "    DESCRIPTION Analytical memo recording interpretations, emerging patterns, or causal reasoning\n"
            "    GUIDELINES\n"
            "        Explain the analytical significance of the excerpt in 1-3 sentences.\n"
            "        Identify patterns, mechanisms, or relevant interpretations.\n"
            "        Do not merely restate the citation.\n"
            "        Distinguish textual evidence from your interpretation.\n"
            "    END GUIDELINES\n"
            "END FIELD\n"
            "\n"
            "FIELD code TYPE CODE\n"
            "    SCOPE ITEM\n"
            "    DESCRIPTION Codes or descriptors applied to this specific excerpt (tags)\n"
            "    GUIDELINES\n"
            "        Apply one or more ontology codes directly supported by the excerpt.\n"
            "        Prefer existing codes and avoid redundant synonyms.\n"
            "        Add a new code only for a distinct and analytically relevant concept.\n"
            "        Every code must have a corresponding ONTOLOGY entry.\n"
            "    END GUIDELINES\n"
            "END FIELD\n"
            "\n"
            "\n"
            "# =================================================================\n"
            "# CODEBOOK & THEMES (Coding Framework and Thematic Categories)\n"
            "# =================================================================\n"
            "\n"
            "ONTOLOGY FIELDS\n"
            "    REQUIRED definition, group\n"
            "END ONTOLOGY FIELDS\n"
            "\n"
            "FIELD definition TYPE TEXT\n"
            "    SCOPE ONTOLOGY\n"
            "    DESCRIPTION Clear definition of the code, indicating inclusion/exclusion criteria for when to apply it\n"
            "    GUIDELINES\n"
            "        Define the code in 1-3 sentences.\n"
            "        State when the code should be applied and, when useful, when it should not.\n"
            "        Distinguish it from closely related codes.\n"
            "    END GUIDELINES\n"
            "END FIELD\n"
            "\n"
            "FIELD group TYPE TOPIC\n"
            "    SCOPE ONTOLOGY\n"
            "    DESCRIPTION Broader theme, category, or thematic domain that groups these codes together\n"
            "    GUIDELINES\n"
            "        Assign one broad parent-level thematic category.\n"
            "        Reuse an existing group whenever possible.\n"
            "        Avoid creating a group that applies to only one narrowly defined code.\n"
            "    END GUIDELINES\n"
            "END FIELD\n",
            encoding="utf-8",
        )

    if not bibliography_path.exists():
        bibliography_path.write_text(
            "@article{smith2024,\n"
            "    author = {Smith, Jane},\n"
            "    title = {Understanding Community Resilience},\n"
            "    journal = {Journal of Social Research},\n"
            "    year = {2024},\n"
            "    volume = {12},\n"
            "    pages = {45--67}\n"
            "}\n",
            encoding="utf-8",
        )

    if not annotations_path.exists():
        annotations_path.write_text(
            "SOURCE @smith2024\n"
            "    description: Qualitative study on community resilience strategies in urban contexts.\n"
            "END SOURCE\n"
            "\n"
            "ITEM @smith2024\n"
            "    citation: \"People here look out for each other. When the flood came, nobody waited\n"
            "        for official help — neighbors just organized themselves.\"\n"
            "\n"
            "    note: Participant describes spontaneous collective action as a primary resilience\n"
            "        mechanism, bypassing formal institutions. Suggests strong bonding social capital.\n"
            "\n"
            "    code: Social_Cohesion, Collective_Action\n"
            "END ITEM\n",
            encoding="utf-8",
        )

    if not ontology_path.exists():
        ontology_path.write_text(
            "ONTOLOGY Social_Cohesion\n"
            "    definition: The degree to which community members trust, support, and cooperate\n"
            "        with one another. Applies when participants describe solidarity, mutual aid,\n"
            "        or a shared sense of belonging.\n"
            "    group: Community_Resilience\n"
            "END ONTOLOGY\n"
            "\n"
            "ONTOLOGY Collective_Action\n"
            "    definition: Coordinated efforts by community members to address shared challenges\n"
            "        without formal institutional direction. Applies when groups self-organize in\n"
            "        response to a problem or crisis.\n"
            "    group: Community_Resilience\n"
            "END ONTOLOGY\n",
            encoding="utf-8",
        )

    click.echo(click.style("Basic project initialized.", fg="green"))


def _print_diagnostics(errors: Iterable, severity_label: str, base_dir: Path | None = None) -> None:
    label_color = "red" if severity_label == "ERROR" else "yellow"

    def _fmt_location(loc) -> str:
        try:
            rel = Path(loc.file).relative_to(base_dir) if base_dir else Path(loc.file)
        except ValueError:
            rel = Path(loc.file).name
        return f"{rel}:{loc.line}:{loc.column}"

    formatted = [
        (_fmt_location(err.location), err.to_cli_line())
        for err in errors
    ]
    if not formatted:
        return

    col_width = max(len(loc) for loc, _ in formatted) + 2

    for loc_str, msg in formatted:
        loc_part = click.style(loc_str.ljust(col_width), fg="cyan")
        label_part = click.style(f"[{severity_label}]", fg=label_color, bold=True)
        click.echo(f"{loc_part}{label_part}  {msg}", err=True)


def _print_stats(stats) -> None:
    rows = [
        ("Sources",    stats.source_count),
        ("Items",      stats.item_count),
        ("Ontologies", stats.ontology_count),
        ("Codes",      stats.code_count),
        ("Chains",     stats.chain_count),
    ]
    label_width = max(len(label) for label, _ in rows)
    num_width   = max(len(f"{n:,}".replace(",", ".")) for _, n in rows)

    click.echo(click.style("Estatisticas da Compilacao:", bold=True))
    for label, n in rows:
        formatted_n = f"{n:,}".replace(",", ".")
        click.echo(f"  {label:<{label_width}}  {formatted_n:>{num_width}}")


def _format_syntax_error(error: SynesisSyntaxError) -> str:
    return f"{error.location}: [ERROR] {error.message}"


if __name__ == "__main__":
    main()
