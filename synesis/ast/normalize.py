"""
normalize.py - Funcoes de normalizacao compartilhadas do Synesis

Proposito:
    Centralizar a normalizacao de codigos e bibrefs usada pelo compilador
    e pelo LSP. Substitui as 9 copias independentes de _norm_code dispersas
    entre validator.py, linker.py e modulos do synesis-lsp.

Funcoes:
    - normalize_code: colapsa whitespace e converte para lowercase
    - normalize_bibref: remove @ e converte para lowercase

Uso:
    from synesis.ast.normalize import normalize_code, normalize_bibref

    norm = normalize_code("  FOO  BAR  ")          # -> "foo bar"
    norm = normalize_code("A201", cache)            # -> "a201" (com cache)
    ref  = normalize_bibref("@Smith2024")           # -> "smith2024"
"""

from __future__ import annotations


def normalize_code(code: str, cache: dict | None = None) -> str:
    """Normaliza codigo: colapsa whitespace e converte para lowercase.

    Args:
        code: Codigo bruto (ex: "  FOO  BAR  " ou "A201")
        cache: Dict opcional para cache entre chamadas (mutable, modificado in-place)

    Returns:
        Codigo normalizado (ex: "foo bar" ou "a201")
    """
    if cache is not None and code in cache:
        return cache[code]
    result = " ".join(code.strip().split()).lower()
    if cache is not None:
        cache[code] = result
    return result


def normalize_bibref(bibref: str) -> str:
    """Normaliza bibref: remove @ e converte para lowercase.

    Args:
        bibref: Referencia bibliografica bruta (ex: "@Smith2024" ou "smith2024")

    Returns:
        Bibref normalizada (ex: "smith2024")
    """
    return bibref.lstrip("@").strip().lower()
