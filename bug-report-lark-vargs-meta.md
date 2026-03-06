# Bug Report: `'Meta' object is not subscriptable` ao compilar no macOS

## Sumário

O compilador Synesis falhava com `VisitError: 'Meta' object is not subscriptable` em qualquer
tentativa de compilação (`synesis compile`), enquanto funcionava normalmente no Windows.
A causa raiz foi uma **mudança backwards-incompatible na API do Lark** entre versões,
que inverteu a ordem dos argumentos em métodos decorados com `@v_args(meta=True)`.

---

## Sintoma

```
erro: Falha inesperada durante compilacao: Error trying to process rule "include_stmt":
'Meta' object is not subscriptable
```

Qualquer arquivo `.synp` falhava na compilação. O erro ocorria em `include_stmt`, mas
todos os demais métodos com `@v_args(meta=True)` tinham o mesmo problema latente.

---

## Causa Raiz

### A API do Lark mudou a ordem dos argumentos em `@v_args(meta=True)`

O decorador `@v_args(meta=True)` instrui o Lark a passar o objeto `Meta` (com informações
de posição — linha, coluna) para o método do Transformer além da lista `items`.

O código do Synesis foi escrito assumindo a assinatura:

```python
@v_args(meta=True)
def include_stmt(self, meta: Any, items: List[Any]) -> Any:
    ...
```

Porém, no Lark **1.2.x e superior**, a função interna `_vargs_meta` chama o método com
a ordem **invertida** — `items` primeiro, `meta` segundo:

```python
# lark/visitors.py — Lark 1.3.1
def _vargs_meta(f, _data, children, meta):
    return f(children, meta)   # TODO swap these for consistency? Backwards incompatible!
```

O próprio comentário no código-fonte do Lark (`# TODO swap these for consistency?
Backwards incompatible!`) confirma que esta foi uma mudança intencional e quebrou a
compatibilidade com código escrito para versões anteriores.

### Por que funcionava no Windows?

O ambiente Windows tinha uma versão **mais antiga do Lark** instalada (provavelmente
`1.1.x`), onde a ordem era `f(meta, children)` — compatível com a assinatura original
do Synesis. O macOS tinha o Lark **1.3.1** instalado, onde a ordem já é `f(children, meta)`.

---

## Versões Envolvidas

| Ambiente | Lark    | Resultado       |
|----------|---------|-----------------|
| Windows  | ~1.1.x  | Compilava OK    |
| macOS    | 1.3.1   | Falha com erro  |

O `pyproject.toml` do Synesis especifica apenas `lark >= 1.1`, permitindo qualquer versão
a partir de 1.1 — o que expõe o projeto à quebra silenciosa quando o Lark é atualizado.

---

## Correção Aplicada

Todos os 10 métodos afetados em `synesis/parser/transformer.py` tiveram a ordem dos
parâmetros corrigida de `(self, meta, items)` para `(self, items, meta)`:

```python
# ANTES (assinatura para Lark < ~1.2)
@v_args(meta=True)
def include_stmt(self, meta: Any, items: List[Any]) -> Any:

# DEPOIS (assinatura correta para Lark 1.2+)
@v_args(meta=True)
def include_stmt(self, items: List[Any], meta: Any) -> Any:
```

### Métodos corrigidos

1. `project_block`
2. `include_stmt`
3. `source_block`
4. `item_block`
5. `ontology_block`
6. `template_header`
7. `field_def_block`
8. `value_entry`
9. `field_entry`
10. `chain_expr`

---

## Como Reproduzir / Testar no Windows

### 1. Verificar a versão atual do Lark instalada

```bash
pip show lark
```

Se a versão for **menor que 1.2.x**, o bug não aparece com o código antigo — mas aparecerá
assim que o Lark for atualizado.

### 2. Reproduzir o bug (com o código original, antes da correção)

```bash
pip install "lark==1.3.1"
synesis compile project.synp --stats
# Esperado: erro 'Meta' object is not subscriptable
```

### 3. Verificar que a correção resolve

```bash
# Após aplicar o patch em transformer.py:
synesis compile project.synp --stats
# Esperado: Stats com sources, items, ontologies, etc.
```

### 4. Fixar a versão mínima do Lark no `pyproject.toml`

Para evitar que o bug retorne, recomenda-se atualizar a restrição de dependência:

```toml
# pyproject.toml — ANTES
"lark >= 1.1"

# pyproject.toml — DEPOIS
"lark >= 1.2"
```

---

## Referência

- Código afetado: `synesis/parser/transformer.py`
- Função interna do Lark: `lark.visitors._vargs_meta`
- Comportamento documentado (implicitamente) no comentário do código-fonte do Lark:
  `# TODO swap these for consistency? Backwards incompatible!`
