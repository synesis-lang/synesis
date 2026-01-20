"""
test_error_handler_structural.py - Testes para erros estruturais pedagogicos

Testa mensagens pedagogicas para erros de ESTRUTURA de blocos,
nao de valores de campos (que sao validados semanticamente).
"""

import pytest
from synesis.parser.lexer import parse_string, SynesisSyntaxError


class TestStructuralErrors:
    """Testes para erros estruturais que o parser detecta."""

    def test_missing_end_keyword(self):
        """Testa erro quando falta END."""
        source = """
SOURCE @ref2023
    title: Test
# FALTA: END SOURCE
"""
        with pytest.raises(SynesisSyntaxError) as exc_info:
            parse_string(source, "test.syn")

        error_msg = str(exc_info.value.message)
        assert "erro:" in error_msg.lower()

    def test_invalid_block_keyword(self):
        """Testa erro com keyword invalida."""
        source = """
INVALID_BLOCK @ref2023
    title: Test
END INVALID_BLOCK
"""
        with pytest.raises(SynesisSyntaxError) as exc_info:
            parse_string(source, "test.syn")

        error_msg = str(exc_info.value.message)
        assert "erro:" in error_msg.lower()

    def test_missing_bibref_after_source(self):
        """Testa erro quando falta bibref apos SOURCE."""
        source = """
SOURCE
    title: Test
END SOURCE
"""
        with pytest.raises(SynesisSyntaxError) as exc_info:
            parse_string(source, "test.syn")

        error_msg = str(exc_info.value.message)
        assert "erro:" in error_msg.lower()

    def test_pedagogical_message_includes_context(self):
        """Verifica que mensagem inclui contexto ao redor do erro."""
        source = """
SOURCE @ref2023
    title: Test
    year: 2023
    INVALID LINE HERE WITHOUT COLON
    author: Silva
END SOURCE
"""
        with pytest.raises(SynesisSyntaxError) as exc_info:
            parse_string(source, "test.syn")

        error_msg = str(exc_info.value.message)

        # Deve incluir informacao sobre o erro
        assert "erro:" in error_msg.lower()
        assert "test.syn" in error_msg

    def test_indentation_error(self):
        """Testa erro de indentacao."""
        source = """
SOURCE @ref2023
title: Test
END SOURCE
"""
        with pytest.raises(SynesisSyntaxError) as exc_info:
            parse_string(source, "test.syn")

        error_msg = str(exc_info.value.message)
        assert "erro:" in error_msg.lower()


class TestPedagogicalMessageFormat:
    """Testes para formato das mensagens pedagogicas."""

    def test_error_message_has_location(self):
        """Verifica que erro tem localizacao (arquivo:linha:coluna)."""
        source = """
INVALID
"""
        with pytest.raises(SynesisSyntaxError) as exc_info:
            parse_string(source, "example.syn")

        error_msg = str(exc_info.value)
        # Formato: example.syn:2:1 ou similar
        assert "example.syn" in error_msg
        assert ":" in error_msg

    def test_error_message_humanizes_tokens(self):
        """Verifica que tokens tecnicos sao humanizados."""
        from synesis.error_handler import SynesisErrorHandler

        handler = SynesisErrorHandler()

        # Testa conversao de tokens tecnicos
        technical = ["KW_END", "NEWLINE", "IDENTIFIER"]
        friendly = handler._humanize_expected_tokens(technical)

        # Nao deve ter prefixo KW_
        assert all("KW_" not in token for token in friendly)

        # Deve ter versoes amigaveis
        assert "END" in friendly
        assert any("linha" in token.lower() for token in friendly)


class TestErrorHandlerIntegration:
    """Testes de integracao do error handler com o parser."""

    def test_error_handler_activated_on_parse_error(self):
        """Verifica que error handler e chamado em erros de parsing."""
        source = """
SOURCE @ref
    title Test without colon
END SOURCE
"""
        with pytest.raises(SynesisSyntaxError) as exc_info:
            parse_string(source, "test.syn")

        # A mensagem deve vir do error handler, nao do Lark bruto
        error_msg = str(exc_info.value.message)
        assert "erro:" in error_msg.lower()

        # Nao deve ser mensagem bruta do Lark
        assert "UnexpectedToken" not in error_msg or "erro:" in error_msg.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
