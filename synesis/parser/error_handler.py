"""
error_handler.py - Mensagens de erro pedagogicas para o parser Synesis

Proposito:
    Gerar mensagens de erro claras e educativas para falhas de parsing.
    Detecta padroes comuns de uso incorreto e sugere correcoes.

Componentes principais:
    - SynesisErrorHandler: detector de padroes e formatador de erros
    - Helpers para inspecao de contexto e extracao de linhas

Dependencias criticas:
    - lark.exceptions: tipos de erro de parsing
    - synesis.ast.nodes: SourceLocation para localizacao precisa

Exemplo de uso:
    handler = SynesisErrorHandler("arquivo.syn")
    msg = handler.handle_unexpected_token(error, source)

Notas de implementacao:
    - Foca em clareza pedagogica e exemplos diretos.
    - Nao tenta corrigir; apenas sugere.

Gerado conforme: Especificacao Synesis v1.1
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from lark.exceptions import UnexpectedCharacters, UnexpectedToken

from synesis.ast.nodes import SourceLocation


@dataclass(frozen=True)
class SynesisErrorHandler:
    filename: str | Path

    def handle_unexpected_token(self, error: UnexpectedToken, source: str) -> str:
        location = SourceLocation(file=Path(self.filename), line=error.line, column=error.column)
        line_text = self._get_line(source, error.line)
        pointer = self._pointer_line(error.column, span=len(str(error.token)))
        message = self._generic_unexpected_token(error)

        if self._is_list_field_context(error.token):
            if self._has_space_separated_identifiers(source, error.pos_in_stream):
                message = (
                    "Parece que voce listou varios codigos usando apenas espacos. "
                    "Use virgulas: code: A, B, C"
                )

        if self._is_strict_identifier_context(error.token):
            message = (
                "Nome contem espacos. Use hifen (Climate-Belief) "
                "ou defina na ONTOLOGY"
            )

        if self._is_chain_context(source, error.pos_in_stream):
            message = "Use -> entre elementos: A -> B -> C"

        return self._format_error_message(location, line_text, pointer, message)

    def handle_unexpected_characters(self, error: UnexpectedCharacters, source: str) -> str:
        location = SourceLocation(file=Path(self.filename), line=error.line, column=error.column)
        line_text = self._get_line(source, error.line)
        pointer = self._pointer_line(error.column, span=1)
        message = f"Caractere invalido '{error.char}'"

        if self._is_chain_context(source, error.pos_in_stream):
            message = "Use -> entre elementos: A -> B -> C"

        return self._format_error_message(location, line_text, pointer, message)

    def format_error_location(self, location: SourceLocation, source: str) -> str:
        line_text = self._get_line(source, location.line)
        pointer = self._pointer_line(location.column, span=1)
        return self._format_error_message(location, line_text, pointer, "Erro de sintaxe")

    def _is_list_field_context(self, token) -> bool:
        return getattr(token, "type", "") == "IDENTIFIER"

    def _is_strict_identifier_context(self, token) -> bool:
        value = str(getattr(token, "value", ""))
        return " " in value.strip()

    def _is_chain_context(self, source: str, pos: int) -> bool:
        prefix = source[max(0, pos - 40):pos].lower()
        return "chain" in prefix and "->" not in prefix

    def _has_space_separated_identifiers(self, source: str, pos: int) -> bool:
        line = self._get_line(source, self._line_number(source, pos))
        if "code" not in line.lower():
            return False
        return bool(re.search(r"code\\s*:\\s*\\w+\\s+\\w+", line))

    def _get_line(self, source: str, line_number: int) -> str:
        lines = source.splitlines()
        if 1 <= line_number <= len(lines):
            return lines[line_number - 1]
        return ""

    def _line_number(self, source: str, pos: int) -> int:
        return source.count("\\n", 0, pos) + 1

    def _pointer_line(self, column: int, span: int = 1) -> str:
        if span <= 1:
            return " " * (max(column, 1) - 1) + "^"
        return " " * (max(column, 1) - 1) + "~" * span

    def _format_error_message(
        self,
        location: SourceLocation,
        line_text: str,
        pointer: str,
        message: str,
    ) -> str:
        header = f"erro: {location}: {message}"
        if line_text:
            return f"{header}\\n    {line_text}\\n    {pointer}\\n\\n{self._format_suggestion(message)}"
        return f"{header}\\n\\n{self._format_suggestion(message)}"

    def _format_suggestion(self, message: str) -> str:
        if "virgulas" in message:
            return "Sugestao: use virgulas para separar codigos.\\n    code: A, B, C"
        if "hifen" in message:
            return "Sugestao: evite espacos em identificadores.\\n    concept: Climate-Belief"
        if "->" in message:
            return "Sugestao: use o operador de cadeia.\\n    chain: A -> B -> C"
        return "Sugestao: revise a sintaxe do bloco."

    def _generic_unexpected_token(self, error: UnexpectedToken) -> str:
        expected = ", ".join(sorted(error.expected)) if error.expected else "simbolo valido"
        return f"Token inesperado '{error.token}'. Esperado: {expected}"
