# Security Policy

## Reporting a Vulnerability

We take the security of AI Saham seriously. If you discover a security vulnerability or sensitive information exposure, please report it responsibly.

### How to Report

**Please DO NOT open a public GitHub issue for security vulnerabilities.**

Instead, please report security issues through one of the following channels:

1. **GitHub Security Advisories**: Use the "Report a vulnerability" button under the **Security** tab of the repository on GitHub.
2. **Private Email**: Send details of the issue to the repository maintainer at `satriyopamungkas@gmail.com`.

### Information to Include

Please include as much information as possible to help us reproduce and resolve the issue:

* Type of issue (e.g. credential exposure, injection vulnerability, dependency vulnerability)
* Full path to the affected files or components
* Step-by-step instructions or proof-of-concept to reproduce the issue
* Any potential impact or suggested remediation

### Security Principles & Best Practices

* **Zero Hardcoded Secrets**: Do not commit API keys, personal access tokens, session cookies, or JWTs to the repository. Use environment variables or local `.env` files (which are gitignored).
* **Local-First Architecture**: AI Saham stores market data and user state locally in SQLite files. Keep your database files secure on your local filesystem.
* **Third-Party Integrations**: AI Saham interfaces with external APIs and data providers. Users are responsible for safeguarding their own provider credentials and complying with provider policies.
