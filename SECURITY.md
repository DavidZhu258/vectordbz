# Security Policy

VectorDBZ handles provider tokens, database credentials, server profiles, and
source evidence. Treat repository hygiene as part of the product.

## Reporting a Vulnerability

Do not report security vulnerabilities through public GitHub issues. Use
GitHub's private security advisory flow for this repository or contact the
maintainer privately.

Include:

- vulnerability description and impact,
- steps to reproduce,
- affected commit/tag,
- whether any credential, token, cookie, or server address was exposed,
- suggested mitigation if known.

## Secret Handling

The repository must not contain:

- provider API keys,
- GitHub PATs,
- SSH passwords or private keys,
- database passwords,
- `.env` files with real values,
- browser cookies or profile dumps,
- local archives, screenshots, vector stores, or generated caches that may
  include private data.

Use environment variables, server-local `/etc/vectordbz/v2.env`, GitHub Actions
secrets, or a dedicated secret manager.

## If a Secret Leaks

1. Revoke or rotate the secret immediately.
2. Replace the runtime value in the relevant server or GitHub secret store.
3. Search tracked files and commit history for other occurrences.
4. Decide whether history cleanup is required after rotation. Rewriting history
   is disruptive and should be coordinated.
5. Enable or verify GitHub secret scanning and push protection.

## Supported Versions

Security fixes are applied to the latest v2 release line. The v1 tag is a
historical baseline and should not receive new secret-bearing operational work.
