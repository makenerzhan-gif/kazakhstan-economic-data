# dictionaries/

Reserved for per-source data dictionary source material (MASTER TASK section 5),
if/when that content needs to live separately from its rendered form.

Right now `project_knowledge/DATA_DICTIONARY.md` is generated directly from
`metadata/**/*.json` by `scripts/build_project_knowledge.py` — there is no
intermediate source file yet, so this directory is currently empty other than
this placeholder.

This file exists so the directory is tracked by git at all (an empty directory
is invisible to git) — `.github/workflows/update.yml`'s commit step references
`dictionaries/` directly, and `git add` on a path that doesn't exist in the
working tree fails the whole command.
