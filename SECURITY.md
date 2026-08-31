# Security Policy

## Supported versions

SELMA Labs is under active development. Security fixes are applied to the
latest `main` branch. Historical branches, unmerged pull requests, and local
forks are not supported release lines.

| Version | Supported |
|---|---|
| Latest `main` | Yes |
| Historical branches or commits | No |

## Report a vulnerability privately

Do not open a public issue for a suspected vulnerability. Use GitHub's
[private vulnerability reporting form](https://github.com/Kerem-1903/Selma-Labs/security/advisories/new).

Include, when possible:

- the affected commit or component;
- a concise impact assessment;
- reproducible steps or a minimal proof of concept;
- relevant logs with secrets and personal paths removed;
- suggested mitigations; and
- whether the issue is already public or under active exploitation.

Please allow up to seven days for an initial acknowledgement. Remediation and
disclosure timing will depend on severity, reproducibility, and downstream
impact. Please avoid public disclosure until a coordinated fix or disclosure
plan is agreed.

## Security scope

Examples include credential exposure, unsafe command execution, path traversal
or storage-boundary escapes, malicious provider payloads, dependency or CI
supply-chain risks, and approval-gate bypasses that could publish unreviewed
media. Ordinary rendering failures and output-quality problems should use the
public bug report form instead.

Never attach live credentials, private source media, model weights without
redistribution rights, or personally identifying data to a report.
