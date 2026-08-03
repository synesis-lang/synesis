# Contributing to Synesis

Thank you for your interest in contributing to Synesis! This document provides guidelines and information for contributors.

## Code of Conduct

Be respectful, constructive, and professional in all interactions. We aim to maintain an inclusive and welcoming environment for all contributors.

## Getting Started

### Prerequisites

- Python 3.10 or higher
- Git
- Basic understanding of compilers and DSLs (helpful but not required)

### Development Setup

1. **Fork and clone the repository**

```bash
git clone https://github.com/YOUR_USERNAME/synesis.git
cd synesis
```

2. **Create a virtual environment**

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. **Install in development mode**

```bash
pip install -e ".[dev]"
```

4. **Run tests to verify setup**

```bash
pytest
```

## Development Workflow

### Branch Naming

- `feature/description` - New features
- `fix/description` - Bug fixes
- `docs/description` - Documentation updates
- `refactor/description` - Code refactoring
- `test/description` - Test additions/improvements

### Making Changes

1. **Create a new branch**

```bash
git checkout -b feature/your-feature-name
```

2. **Make your changes**

Follow the coding standards outlined below.

3. **Write/update tests**

All new features and bug fixes must include tests.

```bash
pytest tests/test_your_feature.py
```

4. **Run the full test suite**

```bash
pytest
pytest --cov=synesis --cov-report=html  # With coverage
```

5. **Commit your changes**

Follow conventional commit format:

```
type(scope): brief description

Detailed explanation if needed.

Fixes #123
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`

6. **Push and create a Pull Request**

```bash
git push origin feature/your-feature-name
```

## Coding Standards

### Python Style

- **PEP 8 compliance** with pragmatic exceptions
- **Type hints** are mandatory for all function signatures
- **Docstrings** required for all public modules, classes, and methods

### Module Docstring Template

Every Python file must start with:

```python
"""
module_name.py - One-line description (max 80 characters)

Purpose:
    Explanation of this module's role in the Synesis compiler.
    Maximum 3-4 lines describing main responsibilities.

Components:
    - Class/Function 1: brief description
    - Class/Function 2: brief description

Dependencies:
    - module.submodule: why it's used
    - other.module: why it's used

Example:
    from synesis.module import Class
    obj = Class(args)
    result = obj.method()

Generated conforming to: Synesis Specification v1.1
"""
```

### Class Docstring Template

```python
class SemanticValidator:
    """
    Brief description of class purpose.

    Detailed explanation of what this class does and when to use it.

    Attributes:
        attr1: Description
        attr2: Description

    Example:
        validator = SemanticValidator(template, bib, ontologies)
        result = validator.validate_item(item)
    """
```

### Function Docstring Template

```python
def validate_chain(chain: ChainNode, field_spec: FieldSpec) -> ValidationResult:
    """
    Brief description of function purpose.

    Args:
        chain: Description of parameter
        field_spec: Description of parameter

    Returns:
        ValidationResult containing:
            - ErrorType1: when it occurs
            - ErrorType2: when it occurs

    Raises:
        ValueError: When it might raise (if applicable)

    Example:
        result = validate_chain(chain_node, field_spec)
        if result.is_valid():
            ...
    """
```

### Design Principles

1. **Procedural where appropriate**: Use functions over classes when no state is needed
2. **No premature abstraction**: Three similar lines > unnecessary helper function
3. **Explicit over implicit**: Clear code > clever code
4. **Result types over exceptions**: Use Ok/Err pattern for expected failures
5. **No redundant comments**: Code should be self-documenting; comment only complex logic

### Grammar Changes

If modifying the grammar (`synesis/grammar/synesis.lark`):

1. **Document the change** in grammar comments
2. **Update transformer** (`synesis/parser/transformer.py`)
3. **Add test cases** for new syntax
4. **Update specification** documentation
5. **Consider backward compatibility**

Grammar is frozen for v1.x releases - breaking changes require v2.0.

## Testing Guidelines

### Test Structure

```python
def test_feature_description():
    """Test that feature behaves correctly under normal conditions."""
    # Arrange
    input_data = create_test_data()

    # Act
    result = function_under_test(input_data)

    # Assert
    assert result.is_ok()
    assert result.value == expected_value
```

### Test Coverage

- Aim for 80%+ coverage on new code
- All public APIs must be tested
- Test both success and failure paths
- Include edge cases and boundary conditions

### Test Fixtures

Use fixtures from `tests/conftest.py`:

```python
def test_with_template(minimal_template):
    """Use existing fixtures when possible."""
    validator = SemanticValidator(minimal_template, {}, {})
    # ...
```

### Running Specific Tests

```bash
# Single test file
pytest tests/test_validator.py

# Single test function
pytest tests/test_validator.py::test_required_fields

# With verbose output
pytest -v tests/test_validator.py

# With coverage
pytest --cov=synesis tests/
```

## Pull Request Process

1. **Ensure all tests pass**
2. **Update documentation** if needed
3. **Add entry to CHANGELOG.md** under `[Unreleased]`
4. **Describe your changes** clearly in the PR description
5. **Link related issues** using `Fixes #123` or `Relates to #456`
6. **Wait for review** - maintainers will review within 1 week

### PR Checklist

- [ ] Tests added/updated and passing
- [ ] Documentation updated (README, docstrings)
- [ ] CHANGELOG.md updated
- [ ] No breaking changes (or clearly documented if unavoidable)
- [ ] Code follows style guidelines
- [ ] All functions have type hints
- [ ] All public APIs have docstrings

## Reporting Bugs

### Before Submitting

1. **Search existing issues** to avoid duplicates
2. **Check if it's already fixed** in the main branch
3. **Verify it's a bug** and not a feature request

### Bug Report Template

```markdown
**Description**
Clear description of the bug.

**To Reproduce**
Steps to reproduce:
1. Create file with content: ...
2. Run command: `synesis compile ...`
3. See error: ...

**Expected Behavior**
What you expected to happen.

**Actual Behavior**
What actually happened.

**Environment**
- Synesis version: 0.1.0
- Python version: 3.10.5
- OS: Windows 11

**Additional Context**
Any other relevant information.
```

## Feature Requests

Feature requests are welcome! Please:

1. **Check existing issues** first
2. **Describe the use case** clearly
3. **Explain why it's useful** for the community
4. **Consider implementation** complexity

## Documentation Contributions

Documentation improvements are highly valued:

- Fix typos or unclear explanations
- Add examples and use cases
- Improve API documentation
- Translate documentation (future)

## Questions?

- Open a [Discussion](https://github.com/synesis-lang/synesis/discussions) for questions
- Use [Issues](https://github.com/synesis-lang/synesis/issues) for bugs and features
- Check [Documentation](https://synesis-lang.github.io/synesis-docs) first

## License and Contributor Agreement

Synesis is distributed under the **AGPL-3.0-only license with the Synesis
Data-Output Exception** (see [LICENSE](LICENSE) and
[LICENSE.exception](LICENSE.exception)).

Contributions are accepted under that same license.

**For almost everyone, this is the whole story:** before your first pull
request is merged, a bot will comment with a link to the **Individual
Contributor License Agreement (ICLA)**. You click to confirm, and you are done
— roughly thirty seconds, once, ever. Nothing to print, scan, or email.

The ICLA lets the maintainer license your contribution under other terms,
including a commercial edition. You keep full ownership of your contribution:
it grants a license, not an assignment, and you remain free to use your own
work however you wish.

### Contributing as part of your job

If you are contributing on behalf of an employer — including work done on
company time or equipment — your employer may own the copyright, in which case
your personal ICLA alone cannot grant the rights. A **Corporate CLA (CCLA)**,
accepted by someone authorized to act for the company, covers that.

This is a **one-time step per company, not per person or per pull request**.
Once a company is on file, every current and future contributor from that
company is cleared automatically, with no further paperwork for anyone.

If your company is already on file, you will not notice any of this. If it is
not, open an issue titled `CCLA: <company name>` and we will send you the
document. We aim to turn these around within a few business days — if it is
holding up a pull request, say so in the issue and we will prioritize it.

Not sure whether this applies to you? Open the pull request anyway and ask. It
is a common question and never a problem.

> **Current status:** the CLA automation is still being set up, so external
> pull requests are not being merged yet. Please do open issues and pull
> requests in the meantime — they will be reviewed, and merged as soon as the
> automation is live. The delay is deliberate: accepting even one contribution
> without a CLA on record would permanently compromise the project's ability
> to offer a commercially licensed edition, and that cannot be fixed later
> without tracking down every past contributor.

---

Thank you for contributing to Synesis! 🎉
