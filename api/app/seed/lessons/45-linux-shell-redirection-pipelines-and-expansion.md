+++
slug = "linux-shell-redirection-pipelines-and-expansion"
skill = "linux"
topic = "shell"
difficulty = "intermediate"
title = "Shell: redirection, pipeline status and expansion"
summary = "See that > truncates before the command runs, that a pipeline reports the last status unless pipefail is on, and that an unset variable can rewrite a cleanup command into a root glob."
estimated_minutes = 32
objectives = ["Predict the contents of a file after > and after >>, including the effect of noclobber.", "Explain why set -e does not fail a pipeline whose last command succeeds, and what pipefail changes.", "Show the expansion of an unset or empty path variable without executing a destructive removal, and name a guard that rejects the empty value."]
prerequisites = ["linux-filesystem-paths-and-permissions"]
misconceptions = ["> appends when the file already exists.", "set -e makes a pipeline fail when any command in it fails.", "GNU rm --preserve-root makes an expanded rm -rf /* safe, so an unset variable needs no guard."]
checks = ["linux-redirect-truncate", "linux-pipefail", "linux-unset-variable-rm"]
status = "reviewed"
version = 1
provenance = "Original AI-assisted P7 writing; the shell example was executed with Bash 3.2.57 and never ran rm against / or /*; advisory review recorded separately; no human subject-matter verification"
[[resources]]
title = "Bash manual: Redirections"
url = "https://www.gnu.org/software/bash/manual/html_node/Redirections.html"
[[resources]]
title = "Bash manual: Pipelines"
url = "https://www.gnu.org/software/bash/manual/html_node/Pipelines.html"
[[resources]]
title = "Bash manual: The Set Builtin"
url = "https://www.gnu.org/software/bash/manual/html_node/The-Set-Builtin.html"
[[resources]]
title = "Bash manual: Shell parameter expansion"
url = "https://www.gnu.org/software/bash/manual/html_node/Shell-Parameter-Expansion.html"
[[resources]]
title = "GNU coreutils: rm invocation"
url = "https://www.gnu.org/software/coreutils/manual/html_node/rm-invocation.html"
+++
## Why it matters

A restart line was supposed to be added to a week of application logs. The file now contains only that one line, and the week is gone. A backup script has `set -e` and still uploads an archive from a dump that failed, because the compressor at the end of the pipeline exits 0. A cleanup variable is unset and the command the shell is about to run is no longer aimed at the build directory. These failures happen before the program you thought you started does the work you intended. The shell sets up redirections, pipeline status, and expansions first.

Prerequisites: the filesystem lesson's path and permission model. This lesson is about what the shell does with those paths. The example was run with Bash 3.2.57. It writes a log only inside a temporary directory. It prints a dangerous expansion. It does not execute `rm` on `/` or on `/*`. The only removal is `rm -rf` of the temporary directory the script created.

## Mental model

A redirection is part of the command setup, not a feature of `echo`. The [Bash redirections manual](https://www.gnu.org/software/bash/manual/html_node/Redirections.html) specifies what the operators do. `>` opens the target for writing and truncates an existing regular file. `>>` opens it for appending. `noclobber` can make `>` fail when the regular file already exists. It is off unless you turn it on. A script that assumes the operator will ask first is assuming a setting most shells do not have.

A pipeline is several commands with the output of one connected to the input of the next. The [pipelines section](https://www.gnu.org/software/bash/manual/html_node/Pipelines.html) says the exit status is the status of the last command, unless `pipefail` is enabled. With `pipefail`, the status is the rightmost non-zero status, or zero if every command succeeds. `set -e` reacts to the status the pipeline reports. It does not independently inspect the earlier commands. A dump that fails, followed by a compressor that succeeds, is a successful pipeline under the default rule.

Parameter expansion also happens before the command runs. An unset variable with no default contributes no text. The [parameter expansion manual](https://www.gnu.org/software/bash/manual/html_node/Shell-Parameter-Expansion.html) defines `${parameter:?word}` as writing an error and, in a non-interactive shell, exiting when the parameter is unset or null. The [set builtin](https://www.gnu.org/software/bash/manual/html_node/The-Set-Builtin.html) defines `-u` as an error on expansion of an unset variable. A variable set to the empty string is not unset. `set -u` does not catch it. The `:?` form does, because "null" is part of that rule.

## How it works

Start with a file that contains one line, `week of logs`. Run `echo restarted > app.log`. The shell truncates `app.log` before `echo` writes. The measured result is one line whose text is `restarted`. Recreate the original line, then `echo restarted >> app.log`. Both lines are present. `paste` joins them with `|` so the two-line file can be shown on one output line: `week of logs|restarted`.

Turn `noclobber` on and try `>` again. The redirection fails and the existing contents stay. The script records status 1. On the Bash 3.2.57 run, standard error included `app.log: cannot overwrite existing file`. The message prefix depends on whether you execute a file or pass the text to `bash -c`. The status and the refusal are the contract. `noclobber` is a seatbelt you opt into. It is not the default, and it does not change `>>`.

For the pipeline, the script turns `-e` off so it can print both statuses instead of exiting at the first failure. `false | true` reports 0. After `set -o pipefail`, the same pipeline reports 1, which is the status of `false`, the last command that failed. In a real backup script you would leave `-e` and `pipefail` on, and you would also check the artifact. A zero status means the pipeline met the status rule you configured. It does not mean the archive contains a restorable database. The example uses `false` and `true` so it does not need a database.

The cleanup illustration is a print, not a removal. With `BUILD_DIR` unset, `${BUILD_DIR-}` expands to nothing, and the printed text is `rm -rf /*`. The `-` supplies an empty default and also avoids the `set -u` error, which is why the script can print the line while nounset is still on. The next line runs `: "$BUILD_DIR"` in a subshell with `-u`. The subshell exits because the variable is unset. The parent prints status 1 and continues. A second subshell expands `${BUILD_DIR:?BUILD_DIR is required}` and also exits. On the file run, standard error contained `BUILD_DIR: unbound variable` and `BUILD_DIR: BUILD_DIR is required`.

A separate probe, not part of the script, used the same Bash and did not run `rm`: `set -u; BUILD_DIR=; printf '%s\n' "rm -rf ${BUILD_DIR-}/*"`. It printed `rm -rf /*` and the shell status was 0. The variable was set to empty, so `-u` did not fire, and the expansion was still the root glob. Quote the path and reject both unset and empty before you get there. `"${BUILD_DIR:?BUILD_DIR is required}"` does both. An empty check you write yourself, such as a test that the value is an absolute directory you intended, is the application-level version of the same idea.

GNU `rm` is a last line of defense for one specific argument, not for this expansion. The [coreutils rm manual](https://www.gnu.org/software/coreutils/manual/html_node/rm-invocation.html), for version 9.12 of that manual, says `--preserve-root` fails an attempt to remove the root directory `/` when used with `--recursive`, and that this is the default. The same page says `--preserve-root=all` rejects a command-line argument that is not on the same file system as its parent. The shell has already turned `$BUILD_DIR/*` into a list of names when `BUILD_DIR` is empty. That list is not the single argument `/`. This lesson does not execute either form. Do not treat the default as permission to expand an untrusted or empty variable. The [chapter on treating `/` specially](https://www.gnu.org/software/coreutils/manual/html_node/Treating-_002f-specially.html) is the longer statement of the `/` rule. Read it. Do not test it.

## Worked example

The script's standard output is the contract below. Its standard error, when the file itself is executed, is the unbound-variable line, the `:?` line, and the noclobber line described above. Those lines are not part of the text block because their prefix includes the path `bash` was given.

```bash
#!/bin/bash
set -eu
root=$(mktemp -d)
cd "$root"
printf 'week of logs\n' > app.log
echo restarted > app.log
echo "truncated_lines $(wc -l < app.log | tr -d ' ')"
echo "truncated_text $(cat app.log)"
printf 'week of logs\n' > app.log
echo restarted >> app.log
echo "appended_text $(paste -sd '|' app.log)"
set +e
false | true
echo "plain_pipeline $?"
set -o pipefail
false | true
echo "pipefail_pipeline $?"
set +e
unset BUILD_DIR || true
echo "unset_expansion rm -rf ${BUILD_DIR-}/*"
( set -u; : "$BUILD_DIR" )
echo "nounset $?"
( : "${BUILD_DIR:?BUILD_DIR is required}" )
echo "required_guard $?"
set -o noclobber
echo extra > app.log
echo "noclobber $?"
set +o noclobber
rm -rf "$root"
```

```text
truncated_lines 1
truncated_text restarted
appended_text week of logs|restarted
plain_pipeline 0
pipefail_pipeline 1
unset_expansion rm -rf /*
nounset 1
required_guard 1
noclobber 1
```

`truncated_lines 1` and `truncated_text restarted` are the truncation. `appended_text` shows the original line and the added line. The plain pipeline status is 0 and the pipefail status is 1. The unset expansion is the printed text `rm -rf /*`. Both guards exit 1 inside their subshells when this file is executed. Noclobber makes the following truncation attempt exit 1. Executed as a file with Bash 3.2.57. Passing the same text to `bash -c` on that Bash still fails the guards, and the printed statuses are 127 rather than 1. The failure is the result that matters. The status number is not a portable contract. `rm` ran only as `rm -rf` of the temporary directory stored in `root`.

## Common mistakes

- Reaching for `>` because it is shorter, in a command whose purpose is to add a line to an existing log.
- Believing the shell will prompt before an overwrite. It will not, unless `noclobber` or another option you set says so.
- Putting `set -e` at the top of a backup script and leaving pipelines on the default status rule. The last command hides the failure.
- Testing only the happy pipeline. `true | true` cannot show you which status rule is active.
- Quoting the whole command in documentation and forgetting that the unquoted expansion is what the script actually runs.
- Trusting `set -u` to reject an empty string. It rejects unset names. The empty assignment in the separate probe still printed the root glob.
- Relying on `--preserve-root` after the shell has expanded a glob. The manual's protection is about removing `/`, and this lesson does not demonstrate the expanded command.
- Running the dangerous command "to see if the safety catches it." The safe observation is the `echo` or `printf` of the expansion.

## In production

Turn `set -u` and `set -o pipefail` on in scripts that deploy, back up, or delete. Keep `set -e` if you want a failed simple command to stop the script, and remember that you must not disable it around the pipeline you actually care about. The example disables `-e` only so it can print the failing statuses and continue. A production backup should stop.

Check the thing the pipeline produced. A dump compressed into a file can be tiny and still have come from a failed dump if you got the status rule wrong. A minimum size is a weak check. A restore into an empty database, or a tool that reads the archive's catalog, tells you the bytes are usable. Status plus an artifact check is the production pair. Status alone is what this lesson measures.

For deletion, build the argument list in a way that cannot become "everything." Require the variable, quote it, and test that it is a directory you created. Prefer `rm -rf -- "$BUILD_DIR"` of a path your script just made with `mktemp` over a glob of a path that came from the environment. The script at the bottom of the example is that pattern: `root` is the directory `mktemp` returned, and it is quoted.

Shell differences matter. The status rules above are Bash, and `pipefail` is a Bash option. A POSIX `sh` on another system may not have it. The shebang in the example is Bash. If production runs the file with `sh`, read that shell's manual before you depend on `pipefail`, `noclobber`, or `set -u`. The truncation behavior of `>` is the common case. Confirm it where you run.

## Trade-offs and limits

`noclobber` protects an existing regular file from `>`. It does not append for you, it does not protect `>>`, and a script that turns it on can fail a later command that expected to replace a file. Use it as a guard around the dangerous line, or leave it on and use `>|` only where replacement is intentional. The Bash manual documents `>|` as the override. This example uses `set +o noclobber` afterward instead, so the temporary directory can be removed by a later command that does not depend on that override.

`pipefail` can fail a pipeline on a command you considered optional, such as a progress logger in the middle. Put optional commands outside the pipeline, or handle their status explicitly. Do not turn `pipefail` off for the whole script because one pipeline was noisy.

`set -u` breaks some older idioms that used an unset variable as an empty string. That breakage is the point. Fix the call site with a default you chose on purpose, `${name-}` or `${name:-}`, and use that form only where empty is acceptable. Do not use the empty default on a path you will delete.

The subshells in the example are what let the parent print both guard statuses. In a production script you usually want the opposite: the guard should exit the script that is about to delete. Run `${BUILD_DIR:?}` in the parent, with `-e` on, before any removal. The example's structure is for measurement. Copying it into a cleanup script would record the failure and continue, which is the bug the guard is supposed to prevent.

The printed expansion `rm -rf /*` is specific to this unset variable and this unquoted glob. Quoted `"$BUILD_DIR"/*` with an unset variable and `set -u` errors instead of expanding the root. Quoting changes the result. The lesson's dangerous line is the unquoted form, because that is the form that becomes the broad glob. Different Bash versions can format the standard-error text differently. The statuses in the text block were measured on 3.2.57. The manual, not the wording of the error, is the specification.

## Check your understanding

1. A file already holds a week of logs. What does the shell do when the next command is `echo restarted > app.log`, and why is the default not a prompt?
   - Feedback: `>` truncates the existing file before `echo` writes, so the week is replaced by that one line. A prompt or a refusal requires an option such as `noclobber`, which is off unless the script or the interactive shell enabled it.
2. A script starts with `set -e` and then runs a dump piped into a compressor. The dump fails and the compressor exits 0. Why does the script continue?
   - Feedback: without `pipefail`, the pipeline's status is the last command's status. `set -e` sees success. `pipefail` makes the pipeline fail when any command fails. You still want a check that the archive itself is usable.
3. `BUILD_DIR` is unset in `rm -rf $BUILD_DIR/*`. Why is the default GNU `--preserve-root` not the guard you depend on, and what does catch an empty value as well as an unset one?
   - Feedback: the unquoted expansion is no longer the single argument `/`. The coreutils default refuses to remove `/` recursively. It is not a test of your variable. `${BUILD_DIR:?}` fails when the value is unset or null. `set -u` catches unset names and still allows a variable that was set to empty, which the separate probe expanded to the same printed glob.

## Practice

In a temporary directory, repeat the log steps: create a one-line file, replace it with `>`, record the line count, recreate it, and append with `>>`. Turn `noclobber` on and show that a further `>` fails. Then print the statuses of `false | true` with and without `pipefail`.

For the cleanup case, print the expansions only. Show the text of an unset `BUILD_DIR` and of a `BUILD_DIR` set to empty while `set -u` is on. Show `${BUILD_DIR:?}` exiting. Do not execute `rm` on `/` or on `/*`.

Acceptance criteria: the truncation result is a single line; the append result contains both lines; `noclobber` is shown off by default or explicitly enabled before the refusal; the two pipeline statuses differ in the way the Bash manual describes; the unset and empty cases are printed rather than executed; the guard you would leave in a parent script uses `${BUILD_DIR:?}` or an equivalent test that rejects empty, and the only `rm -rf` in the exercise targets a directory your script created with `mktemp`. As a transfer task, take a deploy script that pipes a database dump into a compressor and name the status option plus one artifact check you would add before the upload.
