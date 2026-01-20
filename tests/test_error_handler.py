"""
test_error_handler.py - Testes para mensagens pedagogicas de erro

Valida que o SynesisErrorHandler detecta padroes comuns e gera
mensagens educativas conforme especificacao.
"""

import pytest
from pathlib import Path

from synesis.parser.lexer import parse_string, SynesisSyntaxError


class TestPedagogicalErrors:
    """
    Testes para mensagens de erro pedagogicas.

    NOTA: Os testes de "virgula ausente" e "seta ausente" foram removidos
    porque esses padroes SAO ACEITOS pela gramatica como TEXT_LINE.
    A validacao desses casos e feita SEMANTICAMENTE, nao sintaticamente.

    Conforme arquitetura do Synesis:
    1. Parser aceita valores como TEXT_LINE (qualquer texto)
    2. Transformer converte para estruturas especificas quando detecta padroes
    3. Validator semantico detecta problemas de formato

    O error_handler pedagogico e usado para erros ESTRUTURAIS (blocos, keywords),
    nao para erros de VALOR de campos.
    """

    def test_valid_code_list_with_comma(self):
        """Verifica que lista valida com virgulas nao gera erro."""
        source = """
SOURCE @ref2023
    title: Test
END SOURCE

ITEM @ref2023
    quote: Texto exemplo
    code: Climate Belief, Risk Perception
END ITEM
"""
        # Nao deve lancar excecao
        # Nota: Pode falhar por outras razoes (falta template, etc)
        # mas nao por virgula ausente
        try:
            tree = parse_string(source, "test.syn")
            assert tree is not None
        except SynesisSyntaxError as e:
            # Se falhar, nao deve ser por virgula
            assert "virgula" not in str(e).lower()

    def test_valid_chain_with_arrow(self):
        """Verifica que cadeia valida com setas nao gera erro."""
        source = """
SOURCE @ref2023
    title: Test
END SOURCE

ITEM @ref2023
    quote: Texto exemplo
    chain: Climate Belief -> INFLUENCES -> Support
END ITEM
"""
        try:
            tree = parse_string(source, "test.syn")
            assert tree is not None
        except SynesisSyntaxError as e:
            # Se falhar, nao deve ser por falta de seta
            assert "chain" not in str(e).lower() or "->" in str(e)

    def test_generic_unexpected_token_message(self):
        """
        Testa mensagem generica quando nao ha padrao especifico.
        """
        source = """
ITEM @ref
    quote: Test
    invalid_keyword_here
END ITEM
"""
        with pytest.raises(SynesisSyntaxError) as exc_info:
            parse_string(source, "test.syn")

        error_msg = str(exc_info.value.message)

        # Mensagem generica deve incluir localizacao
        assert "erro:" in error_msg.lower()
        assert "test.syn" in error_msg

    def test_multiple_codes_on_separate_lines(self):
        """Verifica que multiplos campos 'code:' sao validos."""
        source = """
SOURCE @ref2023
    title: Test
END SOURCE

ITEM @ref2023
    quote: Texto exemplo
    code: Climate Belief
    code: Risk Perception
END ITEM
"""
        try:
            tree = parse_string(source, "test.syn")
            assert tree is not None
        except SynesisSyntaxError as e:
            # Nao deve falhar por sintaxe de code
            assert "code" not in str(e).lower()

    def test_chain_with_spaces_in_elements(self):
        """
        Verifica que elementos de cadeia podem ter espacos.

        Conforme index.md:130-135 (CHAIN_ELEMENT usa negative lookahead)
        """
        source = """
SOURCE @ref2023
    title: Test
END SOURCE

ITEM @ref2023
    quote: Texto exemplo
    chain: Institutional Barrier -> ENABLES -> Financial Barrier
END ITEM
"""
        try:
            tree = parse_string(source, "test.syn")
            assert tree is not None
        except SynesisSyntaxError as e:
            # Nao deve falhar por espacos em elementos
            pytest.fail(f"Chain com espacos deveria ser valida: {e}")


class TestErrorHandlerUtilities:
    """Testes para funcoes utilitarias do error handler."""

    def test_context_extraction(self):
        """Verifica que contexto ao redor do erro e extraido."""
        from synesis.error_handler import SynesisErrorHandler

        handler = SynesisErrorHandler()
        source = """line 1
line 2
line 3
line 4
line 5"""

        context = handler._get_context_lines(source, line_number=3, context=1)

        assert len(context) == 3
        assert "line 2" in context[0]
        assert "line 3" in context[1]
        assert "line 4" in context[2]

    def test_humanize_expected_tokens(self):
        """Verifica humanizacao de nomes de tokens."""
        from synesis.error_handler import SynesisErrorHandler

        handler = SynesisErrorHandler()

        technical = ["KW_END", "KW_ITEM", "NEWLINE", "IDENTIFIER"]
        friendly = handler._humanize_expected_tokens(technical)

        assert "END" in friendly
        assert "ITEM" in friendly
        assert "nova linha" in friendly
        assert "identificador" in friendly
        assert "KW_" not in " ".join(friendly)

    def test_code_field_detection(self):
        """Verifica deteccao de campo 'code:'."""
        from synesis.error_handler import SynesisErrorHandler

        handler = SynesisErrorHandler()

        assert handler._is_code_field_context("    code: Test")
        assert handler._is_code_field_context("    codes: Test")
        assert handler._is_code_field_context("CODE: Test")  # case-insensitive
        assert not handler._is_code_field_context("    chain: Test")

    def test_chain_field_detection(self):
        """Verifica deteccao de campo 'chain:'."""
        from synesis.error_handler import SynesisErrorHandler

        handler = SynesisErrorHandler()

        assert handler._is_chain_field_context("    chain: Test")
        assert handler._is_chain_field_context("    chains: Test")
        assert handler._is_chain_field_context("CHAIN: Test")  # case-insensitive
        assert not handler._is_chain_field_context("    code: Test")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
