+++
slug = "linux-filesystem-paths-and-permissions"
skill = "linux"
topic = "filesystem"
difficulty = "beginner"
title = "Linux filesystems: paths, permissions and open-file lifetime"
summary = "Reason through directory traversal, mode bits, names and open descriptors so permission fixes and disk investigations target the actual cause."
estimated_minutes = 32
objectives = ["Interpret owner/group/other mode bits and directory search permission.", "Distinguish a pathname, directory entry, inode and open descriptor.", "Explain why unlinking an open log can leave its storage in use."]
prerequisites = ["linux-processes-files-permissions"]
misconceptions = ["A readable file is accessible even if a parent directory denies traversal.", "File write permission decides whether its name can be deleted.", "Removing a pathname immediately frees space held by every open descriptor."]
checks = ["linux-octal-mode", "linux-directory-execute", "linux-deleted-open-file"]
status = "reviewed"
version = 1
provenance = "Original AI-assisted P6 writing; permission and unlink examples checked on Linux as an unprivileged user; advisory review in P6_REPORT.md; no human subject-matter verification"
[[resources]]
title = "Linux man-pages: path_resolution"
url = "https://man7.org/linux/man-pages/man7/path_resolution.7.html"
[[resources]]
title = "Linux man-pages: inode and file modes"
url = "https://man7.org/linux/man-pages/man7/inode.7.html"
[[resources]]
title = "Linux man-pages: unlink"
url = "https://man7.org/linux/man-pages/man2/unlink.2.html"
[[resources]]
title = "Linux man-pages: open and file descriptions"
url = "https://man7.org/linux/man-pages/man2/open.2.html"
+++
## Why it matters

A service cannot read its configuration even though the file has a read bit. Another service reports a full disk after an operator deletes a large log, while a directory-size scan shows little usage. Looking only at the visible filename misses directory traversal in the first case and open-file lifetime in the second.

Read the processes/files lesson first. You should understand a process, a file path and basic shell navigation. This lesson develops the filesystem model behind the earlier permission summary. Its complete Python example must run on Linux as an ordinary unprivileged user, using only a temporary directory. A root process with bypass capabilities can invalidate the permission experiment.

## Mental model

A path is a sequence of name lookups through directories. A directory entry connects a name to a filesystem object. An inode holds metadata and identifies that object within its filesystem. Opening a file produces a descriptor in the process, referring through the kernel's open-file description to the underlying object.

A name is therefore not the same thing as an open file. Multiple hard-link names can refer to one inode. Removing one name does not invalidate an already open descriptor, and does not remove any other hard links. A symbolic link is different: it contains a path to resolve rather than another direct name for the same inode.

Permissions are checked along the operation's actual path. The leaf file's mode is only one part of a successful lookup and access decision.

## How it works

Traditional mode bits divide permissions among owner, group and others. Each triplet uses read=4, write=2 and execute=1. Mode 640 grants owner read/write, group read and no access through the other triplet. The relevant permission class is selected from the process's identity and groups; it is not simply the union of every permissive triplet.

For directories, read permits listing names, execute permits searching/traversing known names, and write participates in changing directory entries. A known readable file can be opened in a searchable directory even when listing that directory is denied. Conversely, seeing a filename does not prove the process can traverse the directory and access that object.

Creating, renaming or unlinking names generally requires appropriate write and search permissions on the containing directory, subject to other rules such as sticky-bit restrictions. A file's own write bit controls writing its contents, not the whole policy for removing its directory entry. ACLs, mount options, security modules and capabilities can add to or alter the simple mode-bit picture.

Unlink removes a directory entry. Storage can remain referenced by other links or open files. When the last name and open references are gone, its storage can be reclaimed. A long-running process can therefore keep writing to an unlinked log. The pathname disappears, but the process's descriptor still refers to the file.

## Worked example

Run as an unprivileged Linux user with Python 3.12 or later. The script changes permissions only inside its own temporary directory and restores directory access before cleanup.

```python
import os
from pathlib import Path
import stat
from tempfile import TemporaryDirectory

with TemporaryDirectory() as scratch:
    directory = Path(scratch, "private")
    directory.mkdir()
    note = directory / "note.txt"
    note.write_text("kept alive\n", encoding="utf-8")
    directory.chmod(0o700)
    note.chmod(0o640)
    print(oct(stat.S_IMODE(note.stat().st_mode)))

    directory.chmod(0o600)  # owner can list, but cannot search this directory
    try:
        print(sorted(item.name for item in directory.iterdir()))
        note.read_text(encoding="utf-8")
    except PermissionError:
        print("search denied")
    finally:
        directory.chmod(0o700)

    directory.chmod(0o100)  # owner can search a known name, but cannot list
    try:
        print(note.read_text(encoding="utf-8").strip())
        try:
            list(directory.iterdir())
        except PermissionError:
            print("listing denied")
    finally:
        directory.chmod(0o700)

    with note.open(encoding="utf-8") as handle:
        note.unlink()
        print(note.exists())
        print(handle.read().strip())
```

Output:

```text
0o640
['note.txt']
search denied
kept alive
listing denied
False
kept alive
```

Names could be enumerated with directory read permission even without search permission; reading the named file still failed. The file's owner-read bit did not bypass that missing directory search bit. With search restored but directory read absent, the known pathname was readable while listing was denied. Finally, unlink removed the name but the open handle still read the data. This demonstrates lifetime without allocating a large file or filling a disk.

## Common mistakes

- Applying mode 777 recursively to fix an unexplained denial. This broadens authority and can still fail when another control is responsible.
- Inspecting only the final path component. Check every parent directory and the service process's actual identity and groups.
- Confusing chmod with the creation mask. The umask restricts requested creation permissions; changing it does not retroactively change existing files, and chmod sets permissions explicitly.
- Deleting additional unrelated files because an unlinked log did not immediately free visible space. Identify which process still owns the descriptor first.

## In production

Give service identities only the directory traversal and file operations they need. Separate read-only configuration from writable data and temporary files. Use appropriate group membership or ACLs for legitimate sharing rather than making everything world-writable. Recheck permissions when deploying new parent directories, not only when replacing leaf files.

For a disk-usage discrepancy, inspect the relevant filesystem, mounts, deleted-open descriptors and process ownership. Linux tools such as lsof's deleted-open listing or the process's `/proc` descriptor entries can help. Coordinate a supported log-reopen or service restart when needed; do not assume an arbitrary signal safely reopens every application's logs.

## Trade-offs and limits

Mode bits provide a compact baseline but are not the full authorization model. Container root, user namespaces, read-only mounts, ACLs and security policies affect observations. Record the user and execution context before drawing conclusions from a permission test.

Pathnames can also change between a check and a later open. In privileged tools operating on untrusted directories, consider directory-relative operations and appropriate no-follow/open policies rather than assuming an earlier string validation guarantees a later object. That is a larger design problem than choosing one octal mode.

## Check your understanding

1. Why can a process read a known file when it cannot list the parent directory?
   - Feedback: search permission resolves the known name; directory read permission governs enumeration. The leaf still needs appropriate read permission.
2. Why can a read-only file's name sometimes be removed?
   - Feedback: unlink changes the containing directory entry, so directory permissions and other policies govern that operation rather than the file's content-write bit alone.
3. Why can a deleted log still consume disk space?
   - Feedback: an open descriptor or another hard link can retain the underlying object. Removing one name does not end every reference.

The linked FORGE checks cover octal modes, directory execute/search permission and deleted-open files. Begin with beginner Linux and use intermediate/advanced assessments for traversal and lifetime investigations.

## Practice

In a disposable directory as a non-root user, build a matrix of directory modes 700, 600 and 100 with a readable leaf file. Predict listing and known-path reading before testing. Then create two hard links and an open handle and track which names and reads survive each unlink.

Acceptance criteria: only scratch paths are modified, permissions are restored for cleanup, and conclusions name the user and relevant control. Explain when storage becomes reclaimable without creating a large file. As a transfer task, design a service layout where configuration is readable but data writes cannot replace the configuration directory's entries.
