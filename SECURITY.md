# Reporting security concerns

Do not include credentials, customer data or sensitive payloads in public issues.
Use GitHub's private vulnerability reporting feature when available. If private
reporting is unavailable, open an issue asking the maintainer for a private
reporting channel without describing the vulnerability.

HookFixture handles local JSON files. It does not verify provider signatures or
authenticate manifests. Its checksums detect accidental fixture changes only.
The initial alpha has no formal security audit or production support commitment.
