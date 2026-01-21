# Publicando no TestPyPI

Guia para testar a distribuição do Synesis antes de publicar no PyPI oficial.

## Pré-requisitos

1. Conta no TestPyPI: https://test.pypi.org/account/register/
2. Token de API configurado
3. Package já construído (`./build.bat` executado com sucesso)

## Passo 1: Criar Token de API

1. Acesse https://test.pypi.org/manage/account/
2. Role até "API tokens"
3. Clique em "Add API token"
4. Nome: `synesis-upload` (ou qualquer nome)
5. Escopo: "Entire account" (primeira vez) ou projeto específico
6. Copie o token (começa com `pypi-`)

## Passo 2: Configurar Credenciais

### Opção A: Arquivo `.pypirc` (recomendado)

Crie/edite `~/.pypirc` (Windows: `C:\Users\SEU_USUARIO\.pypirc`):

```ini
[testpypi]
username = __token__
password = pypi-SEU_TOKEN_AQUI
```

### Opção B: Variáveis de Ambiente

```bash
set TWINE_USERNAME=__token__
set TWINE_PASSWORD=pypi-SEU_TOKEN_AQUI
```

## Passo 3: Upload para TestPyPI

```bash
twine upload --repository testpypi dist/*
```

Saída esperada:
```
Uploading synesis-0.2.0-py3-none-any.whl
Uploading synesis-0.2.0.tar.gz
View at: https://test.pypi.org/project/synesis/0.2.0/
```

## Passo 4: Testar Instalação

Em um ambiente limpo (venv novo):

```bash
# Criar ambiente de teste
python -m venv test_env
test_env\Scripts\activate

# Instalar do TestPyPI
pip install -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ synesis

# Testar import
python -c "import synesis; print(synesis.__version__)"
```

> **Nota:** `--extra-index-url https://pypi.org/simple/` permite instalar dependências (lark, bibtexparser) do PyPI oficial.

## Passo 5: Testar Funcionalidades

```python
import synesis

# Teste básico da API
result = synesis.load(
    project_content='PROJECT Test TEMPLATE "t.synt" END PROJECT',
    template_content='''TEMPLATE Test
ITEM FIELDS
    REQUIRED quote
END ITEM FIELDS
FIELD quote TYPE QUOTATION SCOPE ITEM
END FIELD
''',
)
print(f"Success: {result.success}")
```

## Comandos Resumidos

```bash
# 1. Build (se ainda não fez)
./build.bat

# 2. Upload
twine upload --repository testpypi dist/*

# 3. Testar instalação
pip install -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ synesis
```

## Troubleshooting

| Erro | Solução |
|------|---------|
| `403 Forbidden` | Token inválido ou expirado |
| `400 File already exists` | Versão já existe - incremente em `pyproject.toml` |
| `InvalidDistribution` | Rode `twine check dist/*` antes do upload |

## Após Validação

Quando estiver satisfeito com os testes, publique no PyPI oficial:

```bash
twine upload dist/*
```

---

**Links úteis:**
- TestPyPI: https://test.pypi.org/project/synesis/
- Documentação Twine: https://twine.readthedocs.io/
