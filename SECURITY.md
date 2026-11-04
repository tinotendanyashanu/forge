# Security policy

## LOCAL-ONLY safety boundary

**FORGE 1.0 has no authentication and is intended for one learner on one local machine.** Its anonymous browser cookie identifies a learner; it does not authenticate a person. Do not expose the application, API or database to a shared network or the internet. Public proxies and tunnels can defeat the intended local access boundary.

Keep loopback bindings and `FORGE_LOCAL_ONLY=true`. Run one API process because the global AI call budget is process-local. CORS, security headers and an anonymous identifier do not make a shared deployment safe.

Code execution uses runc container isolation with an explicit single-user acknowledgement. **It is unsuitable for untrusted multi-tenant use.** The release report identifies gVisor, Kata or Firecracker as stronger isolation options for future work; none is claimed to be integrated or sufficient by itself.

## Report a vulnerability privately

**Maintainer setup required before publication:** enable and test GitHub private vulnerability reporting on the eventual repository, or replace this paragraph with a monitored private contact. No reporting channel or response time has been confirmed for this draft. A `SECURITY.md` file alone does not enable GitHub's reporting feature. See [GitHub's setup guidance](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/configure-vulnerability-reporting/configure-for-a-repository).

If private reporting is enabled, use the repository's **Report a vulnerability** action in its Security area. If it is unavailable and no private contact is listed, open a public issue asking only for a private contact, without vulnerability details, exploit steps or sensitive attachments. See [GitHub's reporting guidance](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/report-privately).

A helpful private report includes:

- The affected version or commit and relevant configuration, with secrets removed.
- Minimal reproduction steps against your own local instance.
- Expected and observed behavior, likely impact and any suggested mitigation.
- Sanitized logs or proof of concept, without learner records or credentials.

Do not test against other people's machines or data. Coordinate disclosure privately so that a fix and appropriate release guidance can be prepared.

## Known security limitations

The release reports request body limits, security headers and AI-review retry limits, but **Content-Security-Policy and a dependency vulnerability scan were not completed**. AI review leak filters are lexical and may miss paraphrased fixes. Advisory AI feedback can be wrong. The hourly call limit is not a guaranteed currency-denominated spending limit.

Keep model credentials and database connection strings server-side. When using cloud AI, review what content you submit to the configured provider; local application access does not make remote model processing local. Do not put production credentials or confidential third-party code into exercises, prompts or reports.

See [LIMITATIONS.md](docs/LIMITATIONS.md) for the full release scope and [SECRETS_CHECKLIST.md](docs/SECRETS_CHECKLIST.md) before publishing a repository or an attachment.

## Version and response scope

This policy describes the reported **1.0** local-use boundary. No supported-version matrix, security maintenance period, bounty or response SLA has been established in the supplied report. Report suspected vulnerabilities in the current code privately; this document does not promise fixes or ongoing support for any version.
