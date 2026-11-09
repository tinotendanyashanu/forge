+++
slug = "git-history-amend-revert-and-recovery"
skill = "git"
topic = "history"
difficulty = "intermediate"
title = "Git history: amend, revert and local recovery"
summary = "Replace an unpushed tip when the change is still private, add a revert commit when other people already have the history, and use the local reflog to recover a hard reset."
estimated_minutes = 34
objectives = ["Decide when amending the current tip is safe and when it rewrites a commit someone else may already have.", "Undo a shared change by adding a new commit that leaves the original commit in history.", "Recover a local commit after reset --hard from the reflog, and explain why that record does not exist on a clone that never had the commit."]
prerequisites = ["git-commits-index-and-object-identity"]
misconceptions = ["git commit --amend edits the existing commit object in place.", "git revert deletes the bad commit from the branch.", "git reset --hard destroys the commit objects immediately, so a local mistake cannot be undone."]
checks = ["git-amend-unpushed", "git-revert-shared", "git-reflog-recover", "git-force-pushed-main"]
status = "reviewed"
version = 1
provenance = "Original AI-assisted P7 writing; the history example was executed with Git 2.55.0 in a disposable repository; advisory review recorded separately; no human subject-matter verification"
[[resources]]
title = "Git documentation: git-commit"
url = "https://git-scm.com/docs/git-commit"
[[resources]]
title = "Git documentation: git-revert"
url = "https://git-scm.com/docs/git-revert"
[[resources]]
title = "Git documentation: git-reflog"
url = "https://git-scm.com/docs/git-reflog"
[[resources]]
title = "Pro Git: Undoing things"
url = "https://git-scm.com/book/en/v2/Git-Basics-Undoing-Things"
[[resources]]
title = "Git documentation: git-gc"
url = "https://git-scm.com/docs/git-gc"
+++
## Why it matters

A typo in a commit message that nobody else has is a small rewrite. The same command after the commit is on a shared branch forces every teammate to reconcile two versions of history. A bad line that is already on that shared branch needs the opposite shape: a new commit that undoes the change and leaves the original in the log, so a pull moves everyone forward. A local `reset --hard` that drops the last commit looks final in `git log` and is often still recoverable on that same computer. These are three different operations. Mixing them up is how a message fix becomes a broken pull, and how a recoverable commit gets described as deleted.

Prerequisites: the commits lesson, including the index, trees, and the fact that a commit id is the identity of one commit object. The script uses `git init --initial-branch=main`, which Git added in 2.28. It was run with Git 2.55.0. The repository is temporary. There is no remote and no push.

## Mental model

A branch is a movable name for one commit. The commits themselves are objects. Moving the branch name does not, by itself, erase the object the name used to identify.

`git commit --amend` does not open the last commit and patch its bytes. The [git-commit documentation](https://git-scm.com/docs/git-commit) describes amend as replacing the tip of the current branch by creating a new commit. The new commit has a new id. If you change only the message, the tree can stay the same, which is what this example measures. The previous tip is no longer what the branch name points at. It remains a commit object for as long as something else can still find it.

`git revert` moves history forward. It applies the inverse of a chosen commit and, unless you ask it not to, records that inverse as a new commit. The commit you reverted stays in the history. Teammates who already have it can pull the new commit. They do not have to throw away their copy of the old one.

`git reset --hard` moves the branch name and makes the index and work tree match the commit you name. `git log` follows the branch, so the commits that are no longer ancestors disappear from that view. The local reflog is a journal of where HEAD and the branch have pointed. The [git-reflog documentation](https://git-scm.com/docs/git-reflog) is the reference for that journal. It is local. A clone does not download your reflog.

Garbage collection removes objects that nothing can reach, and only after an expiry window. The [git-gc documentation](https://git-scm.com/docs/git-gc) says `gc.reflogExpire` defaults to 90 days and `gc.reflogExpireUnreachable` defaults to 30 days. The same page notes that amend and rebase are exactly how unreachable reflog entries get created. This example does not run `git gc` and does not wait 30 days. It shows that the old object is still a commit immediately after the branch moves.

## How it works

Amend a tip only when you are sure nobody else has that commit. A commit you have not pushed, on a branch nobody else fetched, meets that test. A commit on a shared `main` does not. Amending and then pushing the replacement requires a history rewrite on the remote. People who already pulled the old tip now have a parent your new tip does not have. Their next push is rejected or, if someone force-pushes, their work can disappear from the branch. For a shared mistake, revert.

The example amends a message typo, `Add ntoe`, into `Add note`. It records the commit id and the tree id before and after. The tree comparison answers "did the files change?" The commit comparison answers "did the history identity change?" It then asks `git cat-file -t` for the old id. The type is still `commit`. That is the immediate proof. It is not a promise that the object will survive forever.

To undo a later bad line, the example uses `git revert -n`. The `-n` form, documented as `--no-commit`, applies the inverse to the index and work tree and does not create the commit itself. The script then commits with a fixed message and a fixed timestamp so the exercise is repeatable. A revert without `-n` would also add a new commit and would also leave the bad commit in place. The point of the measurement is that the file returns to its earlier contents, the bad object is still a commit, and the branch has one more commit rather than one fewer.

The recovery drill is local and immediate. `git reset --hard HEAD~1` moves the branch to the parent. The commit count drops. `HEAD@{1}` is the reflog entry for where HEAD pointed before that reset, and the script quotes it so the shell does not treat the braces as its own syntax. Resetting to that entry puts the revert commit back on the branch. This works here because nothing else moved HEAD between the two commands. If you had committed, pulled, or reset again, `HEAD@{1}` would be a different position. Read `git reflog` and pick the entry whose subject is the commit you still want.

A bad force-push of a shared branch is a different recovery, and this lesson does not perform one. There is no remote in the example. If someone force-pushes an older local copy onto a shared `main`, the commits that vanish from the remote branch can still exist in a clone that fetched them before the push. That clone's remote-tracking reflog, or another ref that still points at the old tip, is a place to look. The person who only ever had the old copy does not have the missing commits in their own reflog. Find a repository or a host record that still names the old tip, check that the history you expect is in it, and restore the branch through the host's protected update path. Prevention is a branch rule that rejects force-pushes and deletion of the shared branch. `--force-with-lease` compares against the remote-tracking tip you last saw; it is still a rewrite, and it belongs on a branch you are allowed to rewrite. The [git-push documentation](https://git-scm.com/docs/git-push) defines that option. Do not use this exercise to try it against a real shared branch.

## Worked example

The script creates a temporary repository, sets the user name, email, signing, and line-ending options only in that repository, and pins the commit timestamps. It prints labels rather than raw object ids. At the end it deletes only that temporary directory.

```bash
#!/bin/bash
set -eu
root=$(mktemp -d)
cd "$root"
export GIT_AUTHOR_DATE='2026-01-01T00:00:00Z'
export GIT_COMMITTER_DATE='2026-01-01T00:00:00Z'
git init -q --initial-branch=main
git config user.name "FORGE Learner"
git config user.email "learner@example.test"
git config commit.gpgsign false
git config core.autocrlf false
printf 'one\n' > note.txt
git add note.txt
git commit -q -m 'Add ntoe'
before=$(git rev-parse HEAD)
before_tree=$(git rev-parse 'HEAD^{tree}')
git commit -q --amend -m 'Add note'
after=$(git rev-parse HEAD)
after_tree=$(git rev-parse 'HEAD^{tree}')
echo "amend_same_tree $([ "$before_tree" = "$after_tree" ] && echo yes || echo no)"
echo "amend_new_commit $([ "$before" != "$after" ] && echo yes || echo no)"
echo "amend_subject $(git log -1 --format=%s)"
echo "old_tip_still_in_object_db $(git cat-file -t "$before")"
printf 'bad\n' >> note.txt
git add note.txt
GIT_AUTHOR_DATE='2026-01-01T00:05:00Z' GIT_COMMITTER_DATE='2026-01-01T00:05:00Z' git commit -q -m 'Add a bad line'
bad=$(git rev-parse HEAD)
git revert -n "$bad"
GIT_AUTHOR_DATE='2026-01-01T00:10:00Z' GIT_COMMITTER_DATE='2026-01-01T00:10:00Z' git commit -q -m 'Revert bad line'
echo "commits_after_revert $(git rev-list --count HEAD)"
echo "file_after_revert $(cat note.txt)"
echo "bad_commit_type $(git cat-file -t "$bad")"
git reset -q --hard HEAD~1
echo "commits_after_reset $(git rev-list --count HEAD)"
git reset -q --hard 'HEAD@{1}'
echo "commits_after_reflog_reset $(git rev-list --count HEAD)"
echo "subject_after_recovery $(git log -1 --format=%s)"
rm -rf "$root"
```

```text
amend_same_tree yes
amend_new_commit yes
amend_subject Add note
old_tip_still_in_object_db commit
commits_after_revert 3
file_after_revert one
bad_commit_type commit
commits_after_reset 2
commits_after_reflog_reset 3
subject_after_recovery Revert bad line
```

Read the labels in order. The amended commit has the same tree and a different commit id, and its subject is `Add note`. The id from before the amend is still a commit object. After the revert there are three commits: the amended first commit, the bad line, and the revert. Command substitution strips the trailing newline, so the printed file text is `one`. The bad id is still a commit. Resetting one step leaves two commits. The following reflog reset restores three commits and the subject `Revert bad line`. Executed with Git 2.55.0. No remote was configured.

## Common mistakes

- Amending a commit that is already on a shared branch, then force-pushing so the remote matches. The message is fixed and everyone else's history is now wrong.
- Using `reset --hard` on a shared branch to "undo" a pushed commit. That rewrites the branch. Revert adds a commit instead.
- Treating revert as deletion. The bad commit remains reachable from the new history, which is what lets the next `git log` and the next bisect still see it.
- Assuming `reset --hard` has already deleted the objects because `git log` no longer lists them.
- Typing `HEAD@{1}` and trusting it after several later commands. The number means "one reflog step ago," not "the commit I remember."
- Expecting a fresh clone to contain the reflog from the machine that did the reset.
- Looking for the missing commits in the reflog of the person who force-pushed an older copy they never updated. Those commits were never in that repository.

## In production

Protect the shared default branch. The host setting that rejects force-pushes and branch deletion is the control that makes the amend rule enforceable, rather than a convention in a README. Personal feature branches can allow a rewrite before review. Once other people build on a branch, treat it as shared even if it is not `main`.

When a bad commit has already been pulled, the revert commit is the change you review and deploy. Say in the message which commit it inverts. If the bad commit was a migration or a release tag, reverting the Git tree may not revert the data. That is an application problem. The Git operation only restores the tree you record.

If a force-push has already removed commits from the shared branch, stop further updates to that branch, tell the people who had the old tip, and recover from a repository that still has it. Verify the tip contains the commits you mean to restore before you move the branch. Keep the legitimate work that arrived in the bad update, and merge or cherry-pick it after the branch points at the history you intended. This lesson's script is not that procedure. It never contacts a remote.

Local reflogs expire. The documented defaults are 90 days for reachable entries and 30 days for entries that are not reachable from the current tip. A recovery you care about should become a branch or a tag while you still have the id, so it does not depend on the expiry window. Servers often disable reflogs on bare repositories. Do not plan an incident response that assumes the server has the same journal your laptop has.

## Trade-offs and limits

Amend is a sharp tool because it throws away the published identity of the tip even when the tree is unchanged. Tools, review comments, and deployment records that stored the old id now point at a commit the branch no longer names. That cost is acceptable for a private typo. It is a poor trade for a one-word fix on a commit that is already the parent of someone else's work. Make a new commit in that case, or revert, depending on whether you are adding a correction or undoing a change.

Revert keeps a noisy history. A large accidental commit followed by its revert stays in every future clone. That is usually cheaper than a rewrite. Squashing either commit later is another rewrite and has the same sharing rule as amend.

Reflog recovery is local, unordered in time beyond the journal, and subject to expiry and `git gc`. The example proves an immediate recovery on the same machine. It does not prove that the object will exist next month, on another laptop, or on the remote after a force-push. Host activity logs differ by product. This lesson does not claim a particular host keeps a particular API. It claims you need some copy of the old tip that you can name and verify.

The fixed dates make the exercise repeatable. They also mean these commits are not a record of when a person typed them. Signing is turned off in the temporary repository so the script does not wait on a key agent. A team that requires signed commits would see a different amend workflow, because the replacement commit must be signed too.

## Check your understanding

1. You amend the message of the latest commit. The tree id is unchanged. Why is the commit id still different, and when is publishing that replacement the wrong next step?
   - Feedback: the commit object contains the message, so a new message is a new object even when the tree matches. Publishing it rewrites a tip other people may already have. Amend before anyone else has the commit. After they do, add a new commit or a revert instead of replacing the tip.
2. A bad change is already on the shared branch and other people have pulled it. Why does a revert commit leave the bad commit in `git log`?
   - Feedback: revert records the inverse as a new child. The old commit stays so every existing clone can fast-forward. Deleting it from the branch would be a rewrite.
3. `git log` no longer shows the commit you removed with a local `reset --hard`. Where do you look first, and why might that place be empty on a colleague's new clone?
   - Feedback: look in the reflog on the computer that had the commit, then reset the branch to the entry you verified. A new clone does not receive that reflog. Commits that were never fetched there are not in that clone's object database either.

## Practice

In a new temporary repository, repeat the three moves with your own file. Amend an unpushed message and record whether the tree id matches and the commit id changes. Confirm the previous id still has type `commit`. Add a line, revert it, and show that the bad commit is still reachable from the branch tip. Reset one commit and restore it from the reflog entry you actually read, not from memory of the number.

Then write a short recovery note for this situation: a shared default branch was updated to an older tip, and several newer commits disappeared from the remote. Name where a surviving copy can exist, how you would check it is the right tip, and which host setting would reject the rewrite next time.

Acceptance criteria: the repository has no remote; the amend happens only before any push; the revert increases the commit count and preserves the bad object; the restored subject is the commit you meant to recover; the note names a concrete surviving copy and a branch protection that rejects force-pushes, and it does not include a force-push command against a real shared branch. As a transfer task, explain why a database migration that already ran in production is not undone just because `git revert` restored the migration file.
