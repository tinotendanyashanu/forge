# Screenshot capture and replacement

The README shows three **real captures** of FORGE 1.0, taken on 4 November 2026 from a local install with a sample learner:

| File | What it shows |
| --- | --- |
| `docs/assets/screenshots/learning.png` | Learning path with evidence-based recommendations |
| `docs/assets/screenshots/workspace.png` | Workspace IDE with public tests passing in the verified Docker sandbox |
| `docs/assets/screenshots/career.png` | Career readiness report reporting insufficient evidence |

They were captured from the page only (no browser chrome, URLs, cookies or learner IDs visible). The FORGE banner (`docs/assets/forge-banner.svg`) is documentation artwork, not a product capture. Use the guidance below when you update them.

## Capture plan

Use the real application running locally and sample content you are comfortable publishing. Capture only states that actually exist; do not fabricate scores, review output or success states.

| Slot | Suggested actual capture | Suggested final file |
| --- | --- | --- |
| Learning overview | The actual local learning/mastery page, showing available evidence or gaps without private history. | `docs/assets/screenshots/learning.png` |
| FORGE Workspace | A real multi-file project with editor and test feedback. Use a local sample exercise, and identify mock or disabled execution if shown. | `docs/assets/screenshots/workspace.png` |
| Career readiness | An actual readiness report with sample or consented data. Show its evidence and limitations, not an invented readiness claim. | `docs/assets/screenshots/career.png` |

Optional later captures can cover interviews, design review or OPS. Show advisory labels and error/disabled states honestly. A model transcript is not proof of correctness.

## Practical capture steps

1. Follow `DEVELOPMENT.md` and open the real local web app. Keep the app on loopback; do not create a public demo to obtain images.
2. Use a clean browser window with unrelated tabs, bookmarks, notifications and extensions hidden. Prefer a separate local sample learner over your real history.
3. Frame one clear activity per image. Around 1440 × 900 is a useful capture target, but use whatever size keeps the actual interface readable. Keep the app's real theme and layout.
4. Remove credentials, connection strings, cookies, learner IDs, names, private source, job descriptions, paths and browser account details. Prefer recapturing a clean state; if redacting, flatten the image so hidden material cannot be recovered from layers.
5. Review the exported image at full size. Confirm it matches the current source and that captions describe exactly what was captured.

## Replace a screenshot

Save the reviewed capture over the matching file in `docs/assets/screenshots/` (PNG), then update the alt text and caption in the root README so they describe exactly what is shown. Record the version, date, AI provider mode and execution mode in the caption where relevant.

## Image rights

Use captures you have permission to publish. Check third-party avatars, logos, fonts, exercise content and model-output content visible in the image. Do not imply that a provider endorses FORGE. Review [SECRETS_CHECKLIST.md](SECRETS_CHECKLIST.md) before attaching images to GitHub issues, releases or portfolio pages.
