# Agent instructions (esp-pylib)

When you change anything user-facing in `esp_pylib/`, update the migration skill in the **same PR** as the code change.

Follow the checklist in [Keeping the skill in sync with new features](README.md#keeping-the-skill-in-sync-with-new-features) in `README.md`:

1. Implement and test the code change.
2. Update `README.md` module summaries and examples as needed.
3. Update `migrate-to-esp-pylib/SKILL.md` (module status table, step markers, frontmatter trigger keywords).
4. Update `migrate-to-esp-pylib/references/workflow.md` (concrete examples, install pin, backward-compat notes).
5. Do not hand-edit `CHANGELOG.md` — `cz bump` handles it via the conventional commit message.

Stale `[Planned]` / `[Available]` markers cause agents to skip shipped features or invent imports for unshipped ones. When in doubt, update the skill.

## Docstrings

Do not use Sphinx cross-reference roles (`:class:`, `:meth:`, `:func:`, `:mod:`, `:data:`, `:attr:`, `:exc:`, etc.) in docstrings or comments. This project does not generate Sphinx docs, so the roles only add noise. Use plain double-backtick code spans instead — e.g. write `` `ToolConfig` `` rather than ``:class:`ToolConfig` ``.
