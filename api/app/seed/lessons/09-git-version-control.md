+++
slug = "git-version-control"
skill = "devops"
topic = "ci-cd"
difficulty = "beginner"
title = "Git: commits, branches and safe history"
summary = "How Git stores history as snapshots and pointers, how branches and merges really work, and which operations are safe on shared history."
estimated_minutes = 22
objectives = [
  "Explain commits as snapshots linked to their parents, and branches as movable pointers.",
  "Choose between merge and rebase, and know when rewriting history is unsafe.",
  "Explain why a secret pushed to a remote must be treated as leaked, even after deletion.",
]
prerequisites = []
misconceptions = [
  "A branch is a copy of the code.",
  "Deleting a file in a new commit removes it from the repository's history.",
  "Force-pushing is fine whenever your local history looks right.",
]
checks = ["sec-leaked-api-key", "devops-build-once-promote"]
status = "reviewed"
version = 1
provenance = "ai-assisted draft (Claude), self-reviewed; commands checked with git 2.x; pending independent human review"

[[resources]]
title = "Pro Git: Git basics"
url = "https://git-scm.com/book/en/v2/Git-Basics-Getting-a-Git-Repository"

[[resources]]
title = "Pro Git: Branches in a nutshell"
url = "https://git-scm.com/book/en/v2/Git-Branching-Branches-in-a-Nutshell"

[[resources]]
title = "Pro Git: Rebasing (the perils of rebasing)"
url = "https://git-scm.com/book/en/v2/Git-Branching-Rebasing"

[[resources]]
title = "GitHub docs: Removing sensitive data from a repository"
url = "https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository"
+++
## Why it matters

Every team change flows through version control: code review, CI pipelines, deployments and rollbacks all start from a commit. Engineers who understand Git's model recover calmly from mistakes; engineers who memorise commands lose work, break teammates' branches, or leak secrets into permanent history.

## Mental model

Git is a database of **snapshots**.

- A **commit** records the full state of the tracked files, a message, an author, and a pointer to its **parent** commit(s). Commits are identified by a hash of their content, so they never change.
- A **branch** is just a named pointer to one commit. Making a new commit on a branch moves the pointer forward.
- `HEAD` is the pointer to "where you are now", usually a branch.

History is therefore a graph of immutable commits, plus a few movable labels.

## How it works

**The three areas.** The working directory holds your files; the **staging area** (index) holds what will go into the next commit; the repository holds commits. `git add` copies changes into the staging area; `git commit` turns the staging area into a new commit.

**Branching.** `git switch -c feature` creates a pointer at your current commit and moves `HEAD` to it. Nothing is copied.

**Merging.** `git merge feature` combines two lines of work. If your branch has not moved since `feature` started, Git just moves the pointer forward (a fast-forward). Otherwise it creates a **merge commit** with two parents.

**Rebasing.** `git rebase main` replays your branch's commits on top of the latest `main`, creating *new* commits with new hashes. The result reads linearly, but the old commits are replaced.

**Remotes.** `git fetch` downloads commits from a remote such as GitHub; `git pull` fetches and integrates; `git push` uploads your commits and moves the remote branch pointer.

## Worked example

```bash
git switch -c fix-rounding        # new pointer at the current commit
# edit pricing.py
git add pricing.py                # stage the change
git commit -m "Round discounts half-up"
git fetch origin
git rebase origin/main            # replay your one commit on the latest main
git push -u origin fix-rounding   # publish the branch, open a pull request
```

Later, someone reviews and merges the pull request into `main`. You delete the branch pointer; the commits remain reachable from `main`.

If you accidentally commit an API key and push it, deleting the file in a new commit does not help: the old commit, with the key inside, is still in history and in every clone. Revoke and rotate the key first, then clean history if needed.

## Common mistakes

- **Rewriting shared history.** Rebasing or amending commits that others have already pulled, then force-pushing, breaks their branches. Rewrite only commits nobody else has.
- **Huge mixed commits.** One commit that renames files, reformats code and changes behaviour is hard to review and to revert.
- **Committing generated or secret files.** Add build outputs, `.env` files and keys to `.gitignore` before the first commit.
- **Panicking after a mistake.** `git reflog` lists where `HEAD` has been, so "lost" commits can usually be recovered.

## In production

Teams protect `main` with required reviews and passing CI. Release pipelines build an artifact from a specific commit hash, so a deployment can always be traced to the exact code. Secret scanning runs on every push, because automated scrapers harvest keys from public commits within minutes. When a release goes wrong, `git revert` creates a new commit that undoes a change without rewriting history.

## Trade-offs and limits

Merge commits preserve exactly what happened but make history branchy; rebasing gives a clean line but rewrites commits. Many teams rebase private branches and merge (or squash-merge) into `main`. Squashing simplifies history at the cost of losing intermediate commits. Git is excellent for text and poor for large binary files, which need tools such as Git LFS.

## Check your understanding

1. What does creating a branch copy?
   - Answer: nothing but a pointer; the branch points at an existing commit.
2. Why does rebasing a branch that teammates already pulled cause trouble?
   - Answer: rebase creates new commits with new hashes, so their copies diverge from the rewritten branch.
3. You pushed a secret and deleted it in the next commit. Is it safe?
   - Answer: no. It remains in history and may already be copied; revoke and rotate it.

## Practice

In a scratch repository, create a `main` branch with three commits, then a `feature` branch with two commits while you add one more commit to `main`. Integrate `feature` once with `merge` and once (after resetting) with `rebase`, and compare `git log --oneline --graph` for each. Finally, use `git reflog` to recover a commit you "lost" with `git reset --hard`.
