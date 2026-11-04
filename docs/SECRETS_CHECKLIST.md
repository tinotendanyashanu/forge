# Secrets and Git publication checklist

Use this before the first public push and before adding release assets, screenshots or support attachments. The starter root `.gitignore` reduces accidental staging; it is not a secret scanner or a security boundary.

## Files and content to inspect

- [ ] Keep actual `api/.env`, `web/.env`, `.env.*`, provider tokens, database URLs and private keys out of commits. Review sanitized `.env.example` files manually.
- [ ] Never reuse the Compose example database password outside local development. Keep actual configuration private, even when it uses the same development defaults.
- [ ] Exclude database dumps, backups, local volumes, learner histories, browser cookies, exported readiness reports and private exercise drafts. Check archives and binary attachments too.
- [ ] Review logs, exception traces, shell snippets and screenshots for tokens, paths, personal data, connection strings, learner IDs and copied confidential code.
- [ ] Check package manager configuration, registry tokens, cloud credential files and editor settings. Avoid placing secrets in browser-visible environment variables.
- [ ] Keep legitimate manifests, lockfiles, migrations, seed questions, exercise definitions, reference solutions and test harnesses tracked. Broad `*.sql` or `*.json` ignore rules can hide essential source.
- [ ] Confirm permissions and attribution for included code, questions, images, icons and other third-party material before applying the chosen project license.

## Review what Git will publish

From your actual source repository, use these read-only checks:

```bash
git status --short --untracked-files=all
git diff
git diff --cached --stat
git diff --cached --name-status
git diff --cached
git ls-files
git log --all --oneline
```

Inspect the complete changed content, not just the filenames. Git diffs may not show binary contents. Confirm that no unrelated material is staged before you manually commit or push.

Check representative ignore behavior:

```bash
git check-ignore -v --no-index api/.env web/.env.local
git ls-files -- api/.env web/.env
```

`git check-ignore` can explain a matching rule, but it does not prove a file is absent from existing commits. **Ignore rules do not affect already tracked files.** See the [Git manual](https://git-scm.com/docs/gitignore). Review existing history separately; no history-wide secret scan was performed by this package.

## Scan and handle findings

- [ ] Run a trusted secret scan over the working tree and all history you plan to publish. Review findings locally; do not copy detected values into public issues, chat, scan logs or screenshots.
- [ ] Review false positives and omissions manually. A clean scan is not proof that no secret exists.
- [ ] If a real credential was committed or shared, revoke or rotate it with the issuer, then remove the exposure from files and relevant history. Deleting the latest file does not undo earlier disclosure. Use [GitHub's sensitive-data removal guidance](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository) for the cleanup process.
- [ ] If a file should remain local but is already tracked, review an explicit untracking change and its staged diff. Do not force-add ignored secrets to bypass the rules.
- [ ] Coordinate any history rewrite with collaborators. No destructive cleanup or force push is performed by this documentation package.

## Separate dependency review

A **dependency vulnerability scan was not completed in the 1.0 report**. Secret scanning does not replace it. Run the appropriate dependency checks on the real checkout, assess findings and record what was actually run. Update release claims only when new evidence supports the change.

## Final review

Read the rendered README, open every image and inspect release attachments. Confirm that the local-only warning is visible, the license choice is finalized, and the private security channel works. Publishing source for local use does not authorize exposing the running application as a shared service.
