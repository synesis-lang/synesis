"""
error_handler.py - Gerador de mensagens de erro pedagogicas para Synesis

Proposito:
    Transformar erros brutos do Lark em mensagens educativas que ensinam
    a sintaxe correta sem exigir leitura do manual. Detecta padroes comuns
    de erro e fornece exemplos de correcao.

Componentes principais:
    - SynesisErrorHandler: gerador principal de mensagens pedagogicas
    - Detectores de padroes: _is_missing_comma, _is_missing_arrow, etc.
    - Formatadores de mensagens: _format_error_with_context

Dependencias criticas:
    - lark.exceptions: UnexpectedToken, UnexpectedCharacters
    - synesis.ast.nodes: SourceLocation
    - re: deteccao de padroes

Exemplo de uso:
    from synesis.error_handler import SynesisErrorHandler
    handler = SynesisErrorHandler()
    message = handler.handle_unexpected_token(exc, source_code)

Notas de implementacao:
    - Usa heuristicas baseadas em contexto para detectar erros comuns
    - Prioriza mensagens com exemplos praticos de correcao
    - Detecta ate 3 linhas de contexto antes e depois do erro

Gerado conforme: Especificacao Synesis v1.1
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Tuple

from lark.exceptions import UnexpectedCharacters, UnexpectedToken

from synesis.ast.nodes import SourceLocation


class SynesisErrorHandler:
    """
    Gerador de mensagens de erro pedagogicas.

    Detecta padroes comuns de erro e fornece mensagens educativas
    com exemplos de sintaxe correta.

    Example:
        handler = SynesisErrorHandler()
        try:
            tree = parser.parse(content)
        except UnexpectedToken as e:
            print(handler.handle_unexpected_token(e, content))
    """

    def __init__(self) -> None:
        """Inicializa o error handler com padroes de deteccao."""
        # Padroes para detectar contextos especificos
        self.code_field_pattern = re.compile(r'\b(code|codes)\s*:\s*', re.IGNORECASE)
        self.chain_field_pattern = re.compile(r'\b(chain|chains)\s*:\s*', re.IGNORECASE)

        # Nomes de campos conhecidos para detecção de typos
        self.known_field_names = {
            'quote', 'quotation', 'code', 'codes', 'chain', 'chains',
            'note', 'notes', 'memo', 'memos', 'description', 'topic',
            'aspect', 'dimension', 'confidence', 'parent', 'parents',
            'is_a', 'isa'
        }

    def handle_unexpected_token(
        self,
        error: UnexpectedToken,
        source: str,
        filename: str | Path = "<unknown>",
    ) -> str:
        """
        Processa erro UnexpectedToken e gera mensagem pedagogica.

        Args:
            error: Excecao do Lark
            source: Codigo fonte completo
            filename: Nome do arquivo

        Returns:
            Mensagem formatada com diagnostico e sugestao
        """
        location = SourceLocation(
            file=Path(filename),
            line=error.line,
            column=error.column,
        )

        # Extrai contexto ao redor do erro
        context_lines = self._get_context_lines(source, error.line)
        current_line = context_lines[1] if len(context_lines) > 1 else ""

        # Detecta typo em nome de campo
        field_typo = self._detect_field_typo(current_line)
        if field_typo:
            return self._format_field_typo_error(
                location, current_line, field_typo
            )

        # Detecta padroes comuns
        if self._is_code_field_context(current_line):
            if self._is_missing_comma_in_code_list(current_line, error.column):
                return self._format_missing_comma_error(
                    location, current_line, error.column
                )

        if self._is_chain_field_context(current_line):
            if self._is_missing_arrow_in_chain(current_line, error.column):
                return self._format_missing_arrow_error(
                    location, current_line, error.column
                )

        # Se nao detectou padrao especifico, retorna mensagem generica melhorada
        return self._format_generic_unexpected_token(
            location, error, current_line, context_lines
        )

    def handle_unexpected_characters(
        self,
        error: UnexpectedCharacters,
        source: str,
        filename: str | Path = "<unknown>",
    ) -> str:
        """
        Processa erro UnexpectedCharacters e gera mensagem pedagogica.

        Args:
            error: Excecao do Lark
            source: Codigo fonte completo
            filename: Nome do arquivo

        Returns:
            Mensagem formatada com diagnostico e sugestao
        """
        location = SourceLocation(
            file=Path(filename),
            line=error.line,
            column=error.column,
        )

        context_lines = self._get_context_lines(source, error.line)
        current_line = context_lines[1] if len(context_lines) > 1 else ""

        return self._format_generic_unexpected_char(
            location, error, current_line
        )

    # =========================================================================
    # DETECTORES DE PADROES
    # =========================================================================

    def _is_code_field_context(self, line: str) -> bool:
        """Verifica se linha contem campo 'code:' ou 'codes:'."""
        return bool(self.code_field_pattern.search(line))

    def _is_chain_field_context(self, line: str) -> bool:
        """Verifica se linha contem campo 'chain:' ou 'chains:'."""
        return bool(self.chain_field_pattern.search(line))

    def _is_missing_comma_in_code_list(self, line: str, column: int) -> bool:
        """
        Detecta se erro e causado por virgula ausente entre codigos.

        Heuristica: Se apos 'code:', ha multiplas palavras sem virgula.

        Example:
            code: Climate Belief Risk Perception  # ERRO: falta virgula
        """
        match = self.code_field_pattern.search(line)
        if not match:
            return False

        # Extrai parte apos "code:"
        value_start = match.end()
        value_part = line[value_start:].strip()

        # Se tem espaco mas nao tem virgula, provavelmente falta virgula
        has_space = ' ' in value_part
        has_comma = ',' in value_part
        has_arrow = '->' in value_part

        return has_space and not has_comma and not has_arrow

    def _is_missing_arrow_in_chain(self, line: str, column: int) -> bool:
        """
        Detecta se erro e causado por seta ausente em cadeia.

        Heuristica: Se apos 'chain:', ha multiplas palavras sem '->'.

        Example:
            chain: Climate Belief INFLUENCES Support  # ERRO: falta ->
        """
        match = self.chain_field_pattern.search(line)
        if not match:
            return False

        value_start = match.end()
        value_part = line[value_start:].strip()

        # Se tem espacos mas nao tem ->, provavelmente falta seta
        has_multiple_words = len(value_part.split()) > 1
        has_arrow = '->' in value_part

        return has_multiple_words and not has_arrow

    def _detect_field_typo(self, line: str) -> Optional[Tuple[str, str]]:
        """
        Detecta typos em nomes de campos.

        Procura padroes como "chaino:" em vez de "chain:".

        Returns:
            Tupla (typo, sugestao) ou None se nao houver typo detectado

        Example:
            "    chaino: A -> B" -> ("chaino", "chain")
        """
        # Padrão: palavra seguida de dois-pontos
        field_pattern = re.compile(r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', re.IGNORECASE)
        match = field_pattern.match(line)

        if not match:
            return None

        field_name = match.group(1).lower()

        # Se já é um campo conhecido, não há typo
        if field_name in self.known_field_names:
            return None

        # Busca campo mais similar usando distância de Levenshtein
        best_match = self._find_closest_field(field_name)

        if best_match and self._levenshtein_distance(field_name, best_match) <= 2:
            return (field_name, best_match)

        return None

    def _find_closest_field(self, typo: str) -> Optional[str]:
        """
        Encontra o campo conhecido mais próximo do typo.

        Args:
            typo: Nome do campo com possível erro

        Returns:
            Nome do campo correto mais próximo
        """
        min_distance = float('inf')
        closest = None

        for known in self.known_field_names:
            distance = self._levenshtein_distance(typo, known)
            if distance < min_distance:
                min_distance = distance
                closest = known

        return closest

    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """
        Calcula distância de Levenshtein entre duas strings.

        Args:
            s1, s2: Strings a comparar

        Returns:
            Número de edições necessárias para transformar s1 em s2
        """
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)

        if len(s2) == 0:
            return len(s1)

        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                # j+1 em vez de j pois previous_row e current_row tem len(s2)+1
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        return previous_row[-1]

    # =========================================================================
    # FORMATADORES DE MENSAGENS
    # =========================================================================

    def _format_field_typo_error(
        self,
        location: SourceLocation,
        line: str,
        typo_info: Tuple[str, str],
    ) -> str:
        """
        Formata mensagem pedagógica para typo em nome de campo.

        Args:
            location: Localização do erro
            line: Linha com o erro
            typo_info: Tupla (typo, sugestão)

        Returns:
            Mensagem formatada
        """
        typo, suggestion = typo_info
        corrected_line = re.sub(
            rf'\b{re.escape(typo)}\b',
            suggestion,
            line,
            flags=re.IGNORECASE
        )

        msg = f"""erro: {location}: Nome de campo desconhecido '{typo}'.
    {line.strip()}

Voce quis dizer '{suggestion}'?
    {corrected_line.strip()}

Campos comuns:
    quote, quotation - Excerto textual
    code, codes - Rótulos conceituais
    chain, chains - Cadeias causais
    note, notes, memo - Anotações analíticas
    description - Descrição do conceito"""

        return msg

    def _format_missing_comma_error(
        self,
        location: SourceLocation,
        line: str,
        column: int,
    ) -> str:
        """
        Formata mensagem pedagogica para virgula ausente em lista de codigos.

        Conforme especificacao index.md:698-711.
        """
        # Encontra onde começa o valor do campo code
        match = self.code_field_pattern.search(line)
        if not match:
            return self._format_generic_message(location, line)

        value_start = match.end()
        value_part = line[value_start:].strip()

        # Cria visualizacao do erro
        marker = " " * (column - 1) + "^" + "~" * 3

        msg = f"""erro: {location}: Multiplos codigos devem ser separados por virgula.
    {line}
    {marker} falta virgula aqui

Use virgula para separar codigos:
    code: {', '.join(value_part.split())}

OU especifique cada codigo em linha separada:
    code: {value_part.split()[0]}
    code: {value_part.split()[1] if len(value_part.split()) > 1 else '...'}"""

        return msg

    def _format_missing_arrow_error(
        self,
        location: SourceLocation,
        line: str,
        column: int,
    ) -> str:
        """
        Formata mensagem pedagogica para seta ausente em cadeia causal.

        Conforme especificacao index.md:713-729.
        """
        # Encontra onde começa o valor do campo chain
        match = self.chain_field_pattern.search(line)
        if not match:
            return self._format_generic_message(location, line)

        value_start = match.end()
        value_part = line[value_start:].strip()

        # Tenta identificar onde falta a seta
        words = value_part.split()
        suggestion = ' -> '.join(words)

        # Cria visualizacao do erro
        marker = " " * (column - 1) + "^" + "~" * 10

        msg = f"""erro: {location}: Cadeia causal exige operador '->' entre elementos.
    {line}
    {marker} falta '->' aqui

Use '->' para conectar elementos:
    chain: {suggestion}

Exemplo completo:
    chain: Climate Belief -> INFLUENCES -> Support"""

        return msg

    def _format_generic_unexpected_token(
        self,
        location: SourceLocation,
        error: UnexpectedToken,
        current_line: str,
        context_lines: List[str],
    ) -> str:
        """
        Formata mensagem generica para token inesperado.

        Inclui contexto e tokens esperados quando disponivel.
        """
        token_repr = repr(error.token) if error.token else "<EOF>"

        # Monta cabecalho
        msg = f"erro: {location}: Token inesperado {token_repr}\n"

        # Adiciona contexto (linhas antes e depois)
        if len(context_lines) >= 3:
            msg += "\nContexto:\n"
            for i, ctx_line in enumerate(context_lines):
                prefix = "  " if i != 1 else ">>>"
                msg += f"{prefix} {ctx_line}\n"
        else:
            msg += f"    {current_line}\n"

        # Adiciona tokens esperados
        if error.expected:
            expected_friendly = self._humanize_expected_tokens(error.expected)
            msg += f"\nEsperado: {', '.join(expected_friendly[:5])}"
            if len(expected_friendly) > 5:
                msg += f" (e {len(expected_friendly) - 5} outros)"

        return msg

    def _format_generic_unexpected_char(
        self,
        location: SourceLocation,
        error: UnexpectedCharacters,
        current_line: str,
    ) -> str:
        """Formata mensagem generica para caractere inesperado."""
        char_repr = repr(error.char) if hasattr(error, 'char') else "<unknown>"

        msg = f"erro: {location}: Caractere inesperado {char_repr}\n"
        msg += f"    {current_line}\n"
        msg += f"    {' ' * (error.column - 1)}^ aqui\n"

        # Sugestoes gerais
        msg += "\nVerifique:\n"
        msg += "  - Aspas abertas mas nao fechadas\n"
        msg += "  - Caracteres especiais invalidos\n"
        msg += "  - Indentacao incorreta\n"

        return msg

    def _format_generic_message(
        self,
        location: SourceLocation,
        line: str,
    ) -> str:
        """Fallback para mensagem generica simples."""
        return f"erro: {location}: Erro de sintaxe\n    {line}\n"

    # =========================================================================
    # UTILITARIOS
    # =========================================================================

    def _get_context_lines(
        self,
        source: str,
        line_number: int,
        context: int = 1,
    ) -> List[str]:
        """
        Extrai linhas de contexto ao redor do erro.

        Args:
            source: Codigo fonte completo
            line_number: Numero da linha com erro (1-indexed)
            context: Numero de linhas antes e depois

        Returns:
            Lista [linha_anterior, linha_erro, linha_seguinte]
        """
        lines = source.splitlines()

        # Converte para 0-indexed
        idx = line_number - 1

        # Calcula range
        start = max(0, idx - context)
        end = min(len(lines), idx + context + 1)

        return lines[start:end]

    def _humanize_expected_tokens(self, expected: List[str]) -> List[str]:
        """
        Converte nomes de tokens tecnicos para nomes amigaveis.

        Example:
            ["KW_END", "KW_ITEM"] -> ["END", "ITEM"]
            ["NEWLINE", "IDENTIFIER"] -> ["nova linha", "identificador"]
        """
        friendly_names = {
            "NEWLINE": "nova linha",
            "IDENTIFIER": "identificador",
            "FIELD_NAME": "nome de campo",
            "STRING": "texto entre aspas",
            "NUMBER": "numero",
            "BIBREF": "referencia @...",
            "CHAIN_ELEMENT": "elemento de cadeia",
            "CODE_ELEMENT": "codigo",
            "_INDENT": "indentacao",
            "_DEDENT": "fim de indentacao",
        }

        result = []
        for token in expected:
            # Remove prefixo KW_
            if token.startswith("KW_"):
                result.append(token[3:])
            elif token in friendly_names:
                result.append(friendly_names[token])
            else:
                result.append(token)

        return result


def create_pedagogical_error(
    exc: Exception,
    source: str,
    filename: str | Path = "<unknown>",
) -> str:
    """
    Factory function para criar mensagens pedagogicas a partir de excecoes.

    Args:
        exc: Excecao do Lark (UnexpectedToken ou UnexpectedCharacters)
        source: Codigo fonte completo
        filename: Nome do arquivo

    Returns:
        Mensagem de erro pedagogica formatada

    Example:
        try:
            tree = parser.parse(content)
        except (UnexpectedToken, UnexpectedCharacters) as e:
            error_msg = create_pedagogical_error(e, content, "arquivo.syn")
            print(error_msg)
    """
    handler = SynesisErrorHandler()

    if isinstance(exc, UnexpectedToken):
        return handler.handle_unexpected_token(exc, source, filename)
    elif isinstance(exc, UnexpectedCharacters):
        return handler.handle_unexpected_characters(exc, source, filename)
    else:
        # Fallback para outras excecoes
        return f"erro: {filename}: {str(exc)}"
