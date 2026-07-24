# Instructions for Claude

## Version control — do not run git write commands

Do not run `git add`, `git commit`, `git push`, or any other git
command that modifies the repo or its history in this workspace.
Edit/create files as needed, but leave staging, committing, and
pushing to the user.

Why: this repo is a synced workspace folder, and git operations run
here have previously left a stale `.git/index.lock` behind (from a
command that got cut off mid-operation) that then blocked the user's
own commits in VS Code until manually deleted. Read-only commands
(`git status`, `git log`, `git diff`) are fine if genuinely needed,
but avoid them by default too — they aren't necessary for editing
files, and it's easy to reach for one out of habit.

When work is ready to be committed, just say so and let the user
handle it (or ask them to paste back any errors if something looks
off) rather than running the commands yourself.

## Project orientation

- [README.md](README.md) — user-facing docs (what this is, install,
  usage).
- [CONTRIBUTING.md](CONTRIBUTING.md) — architecture, how to add a
  printer driver, PR expectations.
- [TESTING.md](TESTING.md) — what the test suite and CI do and don't
  cover; run tests with `pytest tests/ -v`.
