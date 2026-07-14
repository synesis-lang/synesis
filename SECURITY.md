# Security Policy

## Supported versions

Synesis is in active beta. Security fixes are applied to the latest released
version on the `main` branch. Older versions are not maintained.

## Reporting a vulnerability

Please report security issues **privately**, not through public issues or pull
requests.

- Preferred: open a [GitHub private security advisory](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
  ("Report a vulnerability" in the Security tab).
- Alternatively, email **christiandebritto@usp.br** with a description, the
  affected component and version, and steps to reproduce.

You can expect an initial acknowledgement within **7 days**. Once a fix is
available, the advisory is published crediting the reporter (unless anonymity is
requested).

## Threat model

Synesis treats project files — `.synp`, `.syn`, `.synt`, `.syno`, `.bib` — as
**untrusted input**: they circulate between researchers, come from third-party
repositories, and are generated automatically by `synesis-coder`. Opening
someone else's Synesis project must not compromise your machine.

Reports that demonstrate a way to break this boundary are especially valued, for
example: code execution when opening or compiling a project, reading or writing
files outside the project directory, or resource exhaustion of the language
server from a crafted project file.

## Scope

This policy covers the `synesis` (compiler), `synesis-lsp` (language server) and
`synesis-vscode` (VS Code extension) repositories. Vulnerabilities in
third-party dependencies should be reported upstream, though we welcome a heads
up so we can pin or patch.
