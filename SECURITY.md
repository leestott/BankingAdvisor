# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please report it responsibly.

**Do NOT open a public GitHub issue for security vulnerabilities.**

### How to Report

1. **Email:** Send a detailed report to the repository maintainers via the contact information in their GitHub profiles.
2. **GitHub Security Advisories:** Use [GitHub's private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability) if enabled on this repository.

### What to Include

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

### Response Timeline

- **Acknowledgement:** Within 48 hours
- **Initial assessment:** Within 5 business days
- **Fix or mitigation:** Best effort, typically within 30 days for confirmed vulnerabilities

## Security Considerations

This project is a **demonstration / educational tool** and is NOT intended for production use with real financial data. Please note:

### Data Handling
- All demo data in `/data/*.json` is **synthetic** — no real customer, transaction, or financial data is included.
- The application processes data **locally only** — no data is sent to external services (when using Foundry Local).

### Model Inference
- The application uses **Foundry Local** for on-device inference. No data leaves the local machine.
- In mock mode, no model inference occurs at all.

### AML / Financial Crime Outputs
- Structuring detection outputs are **heuristic demonstrations only**.
- They are **NOT** suitable for real AML investigations or regulatory filings.
- All AML outputs include safety notes stating: *"This is NOT a determination of wrongdoing; investigatory lead only."*

### Prompt Injection
- The application uses constrained JSON schema output and validation to mitigate prompt injection risks.
- The repair loop caps retries at 2 to prevent infinite loops from adversarial inputs.
- Invalid model outputs fall back to a schema-valid error object rather than passing through raw text.

### Dependencies
- Keep dependencies up to date. Run `pip audit` periodically to check for known vulnerabilities.
- Pin dependency versions in production deployments.

## Disclaimer

This software is provided for educational and demonstration purposes. It should not be used as the sole basis for any financial, regulatory, or compliance decision. Always consult qualified professionals for real-world financial analysis and AML compliance.
