# License decision required

**No license has been selected. This document is guidance, not a software license or permission grant.** A file named `LICENSE` has deliberately not been included.

Public source visibility is not the same as open-source licensing. Select a license that states the intended permissions and obligations before announcing an open-source release. See [GitHub: licensing a repository](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository).

## Options to review

These examples are a starting point, not a recommendation or a compatibility determination:

| Option | Main consideration | Official selection reference |
| --- | --- | --- |
| MIT | A short permissive license requiring preservation of license and copyright notices. | [MIT](https://choosealicense.com/licenses/mit/) |
| Apache-2.0 | A permissive license with an express patent grant and notice/change requirements. | [Apache License 2.0](https://choosealicense.com/licenses/apache-2.0/) |
| GPL-3.0 | Strong copyleft; distribution of covered works carries source-availability and same-license obligations. | [GNU GPLv3](https://choosealicense.com/licenses/gpl-3.0/) |

Read the complete candidate text. Consider how you want others to reuse and distribute FORGE, the ownership of the code, and the licenses of material already incorporated. Seek qualified advice if ownership or compatibility is unclear.

## Before adding `LICENSE`

1. Confirm who holds copyright and has authority to license the material. Do not infer the holder's name from a username, folder path or tool account.
2. Inventory dependencies, curriculum questions, reference solutions, icons, fonts, images, borrowed snippets and any generated material that needs provenance review. Retain required notices; your license choice does not relicense third-party content automatically.
3. Decide whether code, documentation and curriculum content share one license. If they differ, describe file-level scope clearly.
4. Add the **complete, unmodified standard license text** to the repository root as `LICENSE`, completing only fields the license requires. Add any required notices or attribution files.
5. Align package metadata and README wording with the selected identifier and scope. Replace the README's “License decision pending” notice and remove the pending-license precondition in `CONTRIBUTING.md` only after the actual license is present.
6. Check that contributors can understand the terms before submitting work. Do not claim a CLA, DCO or copyright assignment unless the maintainer deliberately adopts and documents one.

Keep or remove this guidance document after the decision. Do not rename it to `LICENSE` or publish a license badge while the choice is unresolved.
