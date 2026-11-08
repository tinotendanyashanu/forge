+++
slug = "git-commits-index-and-object-identity"
skill = "git"
topic = "commits"
difficulty = "beginner"
title = "Git commits: the index, snapshots and object identity"
summary = "Predict exactly which version a commit records, distinguish tracked files from ignore rules, and understand why history identity changes even when file contents do not."
estimated_minutes = 30
objectives = ["Distinguish working-tree content, index content and the last committed snapshot.", "Explain why ignore patterns do not remove already tracked files.", "Describe blobs, trees and commits, including parent-dependent commit identity."]
prerequisites = ["tracing-program-state"]
misconceptions = ["git add means commit will automatically include the latest future edits to that file.", "Adding a tracked path to .gitignore removes it from history.", "Two commits with the same files must have the same commit ID."]
checks = ["git-staged-snapshot", "git-ignore-tracked-file", "git-hash-chain"]
status = "reviewed"
version = 1
provenance = "Original AI-assisted P6 writing; Git commands executed only in disposable repositories; advisory review in P6_REPORT.md; no human subject-matter verification"
[[resources]]
title = "Git book: Recording changes to the repository"
url = "https://git-scm.com/book/en/v2/Git-Basics-Recording-Changes-to-the-Repository"
[[resources]]
title = "Git book: Git objects"
url = "https://git-scm.com/book/en/v2/Git-Internals-Git-Objects"
[[resources]]
title = "Git documentation: gitignore"
url = "https://git-scm.com/docs/gitignore"
+++
## Why it matters

A developer stages a fix, makes a final correction, then commits without staging again. The commit still contains the earlier version. Another developer adds an exposed configuration file to .gitignore and assumes it disappeared from the repository. Both mistakes confuse a path's current visible contents with what Git is tracking and about to record.

Prerequisites: basic terminal use, text files and the tracing habit of inspecting state after each operation. No branch manipulation is needed. The shell example requires Git 2.28 or later and a new temporary repository; it does not touch the current project or any remote. The object-inspection commands, including cat-file and rev-parse, can be revisited after mastering the three ordinary states.

## Mental model

Keep three representations distinct. The **working tree** is the files you edit. The **index**, often called staging, describes the snapshot prepared for the next commit. **HEAD** normally identifies the current commit through the checked-out branch. A path can differ between all three representations at once.

Staging captures the relevant file contents at that moment. It is not a subscription to later edits. A commit records the prepared snapshot plus history and metadata; it does not simply zip whatever happens to be visible in the working directory when you press Enter.

Git's logical model is snapshots connected by parents. Its physical storage can use compression and pack deltas, but that does not change the snapshot semantics that matter when reviewing a commit.

## How it works

Use an unstaged diff to compare working-tree changes with the index, and a staged diff to compare the index with the current commit. After a final edit, inspect both. Staging a path again updates the prepared version; partial staging can intentionally select only part of a file's changes.

Ignore patterns normally keep untracked paths out of routine discovery and addition. They do not untrack an existing file or erase old commits. Stopping future tracking while keeping a local copy requires an explicit index operation and a reviewed commit. If the file contains an exposed credential, revoke the credential; an ignore rule is not a security incident response.

At the object level, a **blob** stores file content without the filename. A **tree** connects names and modes to blobs or subtrees. A **commit** identifies a tree and parent commits and includes author/committer information and a message. Its ID is derived from the commit object's bytes. The exact object-ID format depends on repository hash configuration; do not build tools around an assumed fixed length.

Changing a commit's message, metadata or parent changes its object identity even when its tree is unchanged. Replaying an altered ancestor also changes the parent references of recreated descendants. This explains why a rebase can produce a new chain of commit IDs without changing the final files. History editing and recovery are separate operations from understanding this model.

## Worked example

Run the complete shell block. It creates its own temporary repository, configures identity only there and makes no network request. The new repository is left available for inspection.

```bash
set -eu
task_repo=$(mktemp -d)
git init -q --initial-branch=main "$task_repo"
cd "$task_repo"
git config user.name "FORGE Learner"
git config user.email "learner@example.test"
git config commit.gpgsign false
git config core.autocrlf false

printf 'draft\n' > note.txt
git add note.txt
printf 'revised\n' > note.txt
git show :note.txt
git commit -q -m 'Record staged draft'
git show HEAD:note.txt
cat note.txt

printf 'note.txt\n' > .gitignore
git add .gitignore
git commit -q -m 'Add an ignore pattern'
git ls-files --error-unmatch note.txt >/dev/null  # exits nonzero if the path is not tracked
printf 'still tracked\n'

git cat-file -t HEAD
git cat-file -t 'HEAD^{tree}'
git cat-file -t HEAD:note.txt
alternate=$(printf 'Alternative commit\n' | git commit-tree 'HEAD^{tree}' -p HEAD)
test "$(git rev-parse "${alternate}^{tree}")" = "$(git rev-parse 'HEAD^{tree}')"
printf 'same tree\n'
test "$alternate" != "$(git rev-parse HEAD)"
printf 'different commit\n'
```

Output:

```text
draft
draft
revised
still tracked
commit
tree
blob
same tree
different commit
```

The staged draft becomes the committed file while the later working edit remains local. The ignore pattern does not remove note.txt from tracking. The alternate commit object has the same tree but a different parent/message combination; creating it with commit-tree does not move the checked-out branch. Object identity includes more than the visible file snapshot.

## Common mistakes

- Reviewing only the working-tree diff and assuming it describes the next commit. Inspect the staged diff too.
- Using a broad add command without checking whether unrelated local files or generated output were selected.
- Treating an ignore file as deletion, untracking or secret revocation.
- Comparing commit IDs as though they represented only source-file content. A release reference also represents a position in history and metadata.

## In production

Build and deploy a specific reviewed commit, and record the release reference alongside artifacts. A dirty checkout can contain runtime changes that the commit ID does not describe. If local modifications are intentional, preserve and account for them explicitly rather than silently overwriting them during deployment.

Keep commits reviewable: inspect the staged diff, include only coherent changes and verify what the resulting commit contains. Secret scanning and ignore patterns reduce accidental additions, but generated archives and CI logs need separate controls. A credential committed briefly may already have been copied; removing it from the latest tree is not containment.

## Trade-offs and limits

Staging allows carefully shaped commits but introduces another state to inspect. A simple workflow that stages all intended paths can be appropriate for a small coherent change; partial staging is useful when multiple concerns share a file. Either way, the final staged snapshot is the review boundary.

Object inspection explains identity but does not tell you whether a change is correct, authorized or safe to deploy. Signed commits, branch policy, tests and artifact provenance address additional questions. Do not rewrite shared history merely to make its IDs look cleaner; coordinate any such operation with the affected collaborators.

## Check your understanding

1. Why does the first commit contain draft even though cat prints revised afterward?
   - Feedback: the index captured draft before the later edit. Commit used that prepared snapshot.
2. Why does ignoring a tracked file not prevent later tracked modifications from appearing in status?
   - Feedback: ignore rules primarily govern untracked discovery, not the lifetime of an already tracked index entry.
3. Can two commit objects share a tree but differ in identity? What else participates?
   - Feedback: yes. Parents, author/committer metadata and message are part of the commit object too.

The linked FORGE checks cover staged snapshots, ignore rules and hash-chain reasoning. Begin with beginner Git, then use intermediate and advanced assessments for tracking and history identity.

## Practice

In another disposable repository, stage two files, edit only one again, and predict the working-tree, index and HEAD contents before every commit. Use the appropriate diffs to verify your prediction. Add an ignore rule for one tracked file and explain why its tracking status remains unchanged.

Acceptance criteria: every commit contains exactly the intended staged version; no global Git settings or remote repository is changed; object inspection distinguishes content snapshots from commit identity. As a transfer task, explain why a deployed commit ID alone is insufficient evidence if the application checkout has unrecorded local modifications.
