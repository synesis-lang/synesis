"""
test_guidelines.py - Testes do bloco GUIDELINES...END GUIDELINES em FIELD definitions

Cobre: parsing, armazenamento, serialização e regressão do campo guidelines em FieldSpec.

Gerado conforme: Especificação Synesis v1.1 / Feature GUIDELINES v0.3.0
"""


from synesis.parser.template_loader import load_template_from_string

# ===========================================================================
# Caso 2.1 — FIELD com GUIDELINES multilinha é parseado corretamente
# ===========================================================================

def test_guidelines_multiline_parsed():
    """FIELD com GUIDELINES armazena texto multilinha em spec.guidelines."""
    template = """\
TEMPLATE test

ITEM FIELDS
    REQUIRED citation
END ITEM FIELDS

FIELD citation TYPE QUOTATION
    SCOPE ITEM
    GUIDELINES
        Extract the exact quote from the source.
        Preserve original punctuation.
        Maximum 3 sentences.
    END GUIDELINES
END FIELD
"""
    result = load_template_from_string(template)
    spec = result.field_specs["citation"]
    assert spec.guidelines is not None
    assert "Extract the exact quote" in spec.guidelines
    assert "Preserve original punctuation" in spec.guidelines
    assert "Maximum 3 sentences" in spec.guidelines


# ===========================================================================
# Caso 2.2 — FIELD sem GUIDELINES retorna None
# ===========================================================================

def test_guidelines_absent_is_none():
    """FIELD sem bloco GUIDELINES → spec.guidelines é None."""
    template = """\
TEMPLATE test

ITEM FIELDS
    REQUIRED citation
END ITEM FIELDS

FIELD citation TYPE QUOTATION
    SCOPE ITEM
    DESCRIPTION A simple field.
END FIELD
"""
    result = load_template_from_string(template)
    spec = result.field_specs["citation"]
    assert spec.guidelines is None


# ===========================================================================
# Caso 2.3 — GUIDELINES preserva múltiplas linhas com pontuação e símbolos
# ===========================================================================

def test_guidelines_preserves_content():
    """GUIDELINES preserva pontuação, símbolos e linhas múltiplas."""
    template = """\
TEMPLATE test

ITEM FIELDS
    REQUIRED citation
END ITEM FIELDS

FIELD citation TYPE QUOTATION
    SCOPE ITEM
    GUIDELINES
        Use n=2383 samples minimum.
        p-value < 0.05 is required.
        Ratio: signal/noise > 3.
    END GUIDELINES
END FIELD
"""
    result = load_template_from_string(template)
    spec = result.field_specs["citation"]
    assert "n=2383" in spec.guidelines
    assert "p-value < 0.05" in spec.guidelines
    assert "signal/noise > 3" in spec.guidelines


# ===========================================================================
# Caso 2.4 — GUIDELINES é case-insensitive
# ===========================================================================

def test_guidelines_case_insensitive():
    """keywords guidelines/end guidelines aceitam qualquer capitalização."""
    template_lower = """\
TEMPLATE test

ITEM FIELDS
    REQUIRED citation
END ITEM FIELDS

FIELD citation TYPE QUOTATION
    SCOPE ITEM
    guidelines
        Extract the exact text.
    end guidelines
END FIELD
"""
    result = load_template_from_string(template_lower)
    spec = result.field_specs["citation"]
    assert spec.guidelines is not None
    assert "Extract the exact text" in spec.guidelines


# ===========================================================================
# Caso 2.5 — GUIDELINES aparece no JSON exportado via to_dict()
# ===========================================================================

def test_guidelines_in_to_dict():
    """spec.to_dict() inclui 'guidelines' com o texto correto."""
    template = """\
TEMPLATE test

ITEM FIELDS
    REQUIRED citation
END ITEM FIELDS

FIELD citation TYPE QUOTATION
    SCOPE ITEM
    GUIDELINES
        Write the extracted quote here.
    END GUIDELINES
END FIELD
"""
    result = load_template_from_string(template)
    spec = result.field_specs["citation"]
    d = spec.to_dict()
    assert "guidelines" in d
    assert d["guidelines"] == "Write the extracted quote here."


# ===========================================================================
# Caso 2.6 — GUIDELINES vazio retorna None
# ===========================================================================

def test_guidelines_empty_block_is_none():
    """Bloco GUIDELINES sem conteúdo textual → spec.guidelines é None."""
    template = """\
TEMPLATE test

ITEM FIELDS
    REQUIRED citation
END ITEM FIELDS

FIELD citation TYPE QUOTATION
    SCOPE ITEM
    GUIDELINES
    END GUIDELINES
END FIELD
"""
    result = load_template_from_string(template)
    spec = result.field_specs["citation"]
    assert spec.guidelines is None


# ===========================================================================
# Caso 2.7 — Templates existentes sem GUIDELINES compilam sem erros (regressão)
# ===========================================================================

def test_guidelines_regression_existing_templates(template_basic):
    """Templates sem GUIDELINES continuam compilando — sem regressão."""
    result = load_template_from_string(template_basic)
    for name, spec in result.field_specs.items():
        assert spec.guidelines is None, f"spec '{name}' deveria ter guidelines=None"
