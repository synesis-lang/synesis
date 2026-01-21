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
from pathlib import Path
from typing import Iterable

try:
    import click
except ImportError:
    raise ImportError(
        "click nao encontrado. CLI requer instalacao com: pip install synesis[cli]"
    )

from synesis.compiler import SynesisCompiler
from synesis.exporters.csv_export import export_csv
from synesis.exporters.json_export import export_json
from synesis.exporters.xls_export import export_xls
from synesis.parser.lexer import SynesisSyntaxError, parse_file
from synesis.parser.template_loader import TemplateLoadError, load_template

VERSION = "0.2.0"


HELP_EPILOG = (
    "Examples:\n"
    "  python -m synesis.cli compile projeto.synp --json saida.json\n"
    "  python -m synesis.cli compile projeto.synp --csv saida_csv/\n"
    "  python -m synesis.cli compile projeto.synp --xls resultado.xlsx\n"
    "  python -m synesis.cli compile projeto.synp --json saida.json --csv saida_csv/ --xls saida.xlsx\n"
)


@click.group(invoke_without_command=True, epilog=HELP_EPILOG)
@click.option("--version", is_flag=True, help="Show version and exit")
@click.pass_context
def main(ctx, version: bool) -> None:
    """Synesis - Compiler for qualitative research corpora"""
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
    try:
        compiler = SynesisCompiler(Path(project))
        result = compiler.compile()

        _print_diagnostics(result.validation_result.errors, "ERROR")
        _print_diagnostics(result.validation_result.warnings, "WARNING")

        if stats:
            _print_stats(result.stats)

        has_errors = result.has_errors()
        has_warnings = result.has_warnings()
        exit_code = 1 if has_errors or (strict and has_warnings) else 0

        if (force or exit_code == 0) and result.linked_project:
            if json_path:
                export_json(
                    result.linked_project,
                    Path(json_path),
                    result.template,
                    result.bibliography,
                )
            if csv_dir:
                export_csv(result.linked_project, result.template, Path(csv_dir))
            if xls_path:
                export_xls(result.linked_project, result.template, Path(xls_path))

        raise SystemExit(exit_code)

    except SynesisSyntaxError as exc:
        # Erro de sintaxe já formatado pedagogicamente
        click.echo(click.style(str(exc), fg="red"), err=True)
        raise SystemExit(1)

    except Exception as exc:
        # Qualquer outro erro inesperado
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
    annotations_dir = cwd / "annotations"
    ontology_dir = cwd / "ontologies"
    bibliography_path = cwd / "references.bib"

    annotations_dir.mkdir(exist_ok=True)
    ontology_dir.mkdir(exist_ok=True)

    if not project_path.exists():
        project_path.write_text(
            "PROJECT demo\n"
            '    TEMPLATE "template.synt"\n'
            '    INCLUDE BIBLIOGRAPHY "references.bib"\n'
            '    INCLUDE ANNOTATIONS "annotations/*.syn"\n'
            '    INCLUDE ONTOLOGY "ontologies/*.syno"\n'
            "END PROJECT\n",
            encoding="utf-8",
        )

    if not template_path.exists():
        template_path.write_text(
            "TEMPLATE demo\n"
            "ITEM FIELDS\n"
            "    REQUIRED quote\n"
            "END ITEM FIELDS\n"
            "FIELD quote TYPE QUOTATION SCOPE ITEM\n"
            "END FIELD\n",
            encoding="utf-8",
        )

    if not bibliography_path.exists():
        bibliography_path.write_text("", encoding="utf-8")

    click.echo(click.style("Project initialized.", fg="green"))


def _print_diagnostics(errors: Iterable, severity_label: str) -> None:
    color = "red" if severity_label == "ERROR" else "yellow"
    for err in errors:
        location = err.location
        full_message = err.to_diagnostic().strip()

        # Primeira linha com localização e severidade
        lines = full_message.split("\n")
        first_line = f"{location}: [{severity_label}] {lines[0]}"
        click.echo(click.style(first_line, fg=color), err=True)

        # Linhas adicionais com indentação
        for line in lines[1:]:
            click.echo(click.style(f"  {line}", fg=color), err=True)


def _print_stats(stats) -> None:
    click.echo("Stats:")
    click.echo(f"  sources: {stats.source_count}")
    click.echo(f"  items: {stats.item_count}")
    click.echo(f"  ontologies: {stats.ontology_count}")
    click.echo(f"  codes: {stats.code_count}")
    click.echo(f"  chains: {stats.chain_count}")
    click.echo(f"  triples: {stats.triple_count}")


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
