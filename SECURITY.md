# Security policy

We take security seriously and appreciate responsible disclosure.

## Reporting a vulnerability

Please do **not** open a public GitHub issue for security reports.

Instead, use one of the following:

- **GitHub Security Advisories** (preferred, if enabled on the repository)
- **Email**: contact@abstractcore.ai

Include as much of the following as you can:
- affected version(s) and how you installed (`pip`, source checkout, etc.)
- impact and likely threat model
- minimal reproduction steps or proof-of-concept
- relevant logs or stack traces (redact secrets)

## Coordinated disclosure

If you are able, please give us a reasonable time window to investigate and patch before public disclosure.

## Scope notes

AbstractAssistant is an agent host that can execute tools after explicit approval. When reporting issues, please
call out whether the vulnerability:
- bypasses tool approvals / allowlists
- leaks local data unexpectedly (files, paths, transcripts, artifacts)
- affects durability/resume semantics (runs, waits, ledger)

Thank you for helping keep the ecosystem safe.

