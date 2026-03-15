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
from synesis.exporters.csv_export import export_csv
from synesis.exporters.json_export import export_json
from synesis.exporters.xls_export import export_xls
from synesis.parser.lexer import SynesisSyntaxError, parse_file
from synesis.parser.template_loader import TemplateLoadError, load_template

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


HELP_EPILOG = (
    "Examples:\n"
    "\n"
    "  synesis compile projeto.synp --json saida.json\n"
    "  synesis compile projeto.synp --csv saida_csv/\n"
    "  synesis compile projeto.synp --xls resultado.xlsx\n"
    "  synesis compile projeto.synp --json saida.json --csv saida_csv/ --xls saida.xlsx\n"
)


@click.group(invoke_without_command=True, epilog=HELP_EPILOG)
@click.option("--version", is_flag=True, help="Show version and exit")
@click.pass_context
def main(ctx, version: bool) -> None:
    """Synesis - Compile yout thinking"""
    if version:
        click.echo(f"Synesis Compiler v{VERSION}")
        raise SystemExit(0)
    if ctx.invoked_subcommand is None:
        _print_help()


@main.command()
@click.argument("project", type=click.Path(exists=True))
@click.option("--json", "json_path", type=click.Path())
@click.option("--csv", "csv_dir", type=click.Path())
@click.option("--xls", "xls_path", type=click.Path())
@click.option("--strict", is_flag=True, help="Treat warnings as errors")
@click.option("--stats", is_flag=True, help="Show compilation statistics")
@click.option("--force", is_flag=True, help="Generate artifacts even with errors")
def compile(project: str, json_path: str | None, csv_dir: str | None, xls_path: str | None, strict: bool, stats: bool, force: bool) -> None:
    """Compile a Synesis project."""
    click.echo(click.style(f"SYNESIS v{VERSION}", bold=True) + "  Compile seu pensamento.")

    spinner = _Spinner()
    project_path = Path(project)
    project_dir = project_path.parent

    try:
        from synesis.ast.results import ValidationResult
        from synesis.parser.template_loader import validate_template

        compiler = SynesisCompiler(project_path)

        # Etapa 1: projeto + template + bibliografia
        spinner.start("Lendo projeto e template")
        project_node, project_validation = compiler.parse_project()
        project_validation_structure = compiler.validate_project_structure(project_node)
        bib_validation = compiler._check_bibliography_file(project_node)
        template, template_load_result = compiler._safe_load_template(project_node)
        if template is None:
            spinner.fail()
            result_early = ValidationResult()
            compiler._merge(result_early, project_validation)
            compiler._merge(result_early, project_validation_structure)
            compiler._merge(result_early, template_load_result)
            compiler._merge(result_early, bib_validation)
            _print_diagnostics(result_early.errors, "ERROR", project_dir)
            raise SystemExit(1)
        template_validation = validate_template(template)
        bibliography = compiler.load_bibliography(project_node)
        spinner.done()

        # Etapa 2: ontologia
        spinner.start("Carregando ontologia")
        ontologies = compiler.parse_ontologies(project_node)
        spinner.done(f"{len(ontologies):,}".replace(",", ".") + " conceitos")

        # Etapa 3: anotacoes (etapa mais lenta — paralela)
        spinner.start("Lendo anotacoes")
        sources, items = compiler.parse_annotations(project_node)
        spinner.done(
            f"{len(sources):,}".replace(",", ".") + " sources, "
            f"{len(items):,}".replace(",", ".") + " items"
        )

        # Etapa 4: validacao semantica
        spinner.start("Validando")
        norm_cache: dict = {}
        validation_result = compiler.validate_all(
            project=project_node,
            template=template,
            bibliography=bibliography,
            sources=sources,
            items=items,
            ontologies=ontologies,
            norm_cache=norm_cache,
        )
        compiler._merge(validation_result, project_validation)
        compiler._merge(validation_result, project_validation_structure)
        compiler._merge(validation_result, template_validation)
        compiler._merge(validation_result, bib_validation)
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


@main.command()
@click.argument("file", type=click.Path(exists=True))
def check(file: str) -> None:
    """Validate a single Synesis file without full compilation."""
    try:
        parse_file(Path(file))
        click.echo(click.style("OK", fg="green"))
        raise SystemExit(0)
    except SynesisSyntaxError as exc:
        click.echo(_format_syntax_error(exc), err=True)
        raise SystemExit(1)


@main.command()
@click.argument("template", type=click.Path(exists=True))
def validate_template(template: str) -> None:
    """Validate a template file."""
    try:
        load_template(Path(template))
        click.echo(click.style("OK", fg="green"))
        raise SystemExit(0)
    except (SynesisSyntaxError, TemplateLoadError) as exc:
        click.echo(str(exc), err=True)
        raise SystemExit(1)


@main.command()
def init() -> None:
    """Create a minimal project structure in current directory."""
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
            "END FIELD\n"
            "\n"
            "FIELD note TYPE MEMO\n"
            "    SCOPE ITEM\n"
            "    DESCRIPTION Analytical memo recording interpretations, emerging patterns, or causal reasoning\n"
            "END FIELD\n"
            "\n"
            "FIELD code TYPE CODE\n"
            "    SCOPE ITEM\n"
            "    DESCRIPTION Codes or descriptors applied to this specific excerpt (tags)\n"
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
            "END FIELD\n"
            "\n"
            "FIELD group TYPE TOPIC\n"
            "    SCOPE ONTOLOGY\n"
            "    DESCRIPTION Broader theme, category, or thematic domain that groups these codes together\n"
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
    color = "red" if severity_label == "ERROR" else "yellow"
    label_color = "red" if severity_label == "ERROR" else "yellow"

    # Formata location com caminho relativo
    def _fmt_location(loc) -> str:
        try:
            rel = Path(loc.file).relative_to(base_dir) if base_dir else Path(loc.file)
        except ValueError:
            rel = Path(loc.file).name
        return f"{rel}:{loc.line}:{loc.column}"

    # Pre-formata para calcular alinhamento
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


def _print_help() -> None:
    """Print help message with examples when no command is provided."""
    click.echo(click.style(f"Synesis Compiler v{VERSION}", fg="cyan", bold=True))
    click.echo(click.style("Compiler for qualitative research corpora", fg="cyan"))
    click.echo()
    click.echo(click.style("Usage:", fg="yellow", bold=True))
    click.echo("  synesis [COMMAND] [OPTIONS]")
    click.echo()
    click.echo(click.style("Commands:", fg="yellow", bold=True))
    click.echo("  compile           Compile a Synesis project")
    click.echo("  check             Validate a single Synesis file")
    click.echo("  validate-template Validate a template file")
    click.echo("  init              Create a minimal project structure")
    click.echo()
    click.echo(click.style("Examples:", fg="yellow", bold=True))
    click.echo("  # Compile project and export to JSON")
    click.echo("  synesis compile projeto.synp --json saida.json")
    click.echo()
    click.echo("  # Compile and export to CSV directory")
    click.echo("  synesis compile projeto.synp --csv saida_csv/")
    click.echo()
    click.echo("  # Compile and export to XLS (Excel)")
    click.echo("  synesis compile projeto.synp --xls resultado.xlsx")
    click.echo()
    click.echo("  # Combine multiple export formats")
    click.echo("  synesis compile projeto.synp --json saida.json --csv saida_csv/ --xls saida.xlsx")
    click.echo()
    click.echo("  # Initialize a new project")
    click.echo("  synesis init")
    click.echo()
    click.echo("  # Show compilation statistics")
    click.echo("  synesis compile projeto.synp --stats")
    click.echo()
    click.echo(click.style("For more information on a command:", fg="yellow", bold=True))
    click.echo("  synesis [COMMAND] --help")
    click.echo()


if __name__ == "__main__":
    main()
