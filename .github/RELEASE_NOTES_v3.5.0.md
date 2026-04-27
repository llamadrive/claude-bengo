# v3.5.0 — Template scope rename (`global` → `user`)

Renames the firm-wide template scope from `global` to `user` because the storage
(`~/.claude-bengo/templates/`) is per-machine, per-lawyer — not actually firm-wide.
The `global` name is reserved for the upcoming **firm scope**, a Shared Drive-backed
store that will sit between case and user (`case → firm → user`) in a follow-up release.

**No action required to upgrade.** Storage paths, file layout, PII gate, and audit log
behavior are all unchanged. Existing `~/.claude-bengo/templates/` contents continue to
resolve as `user` scope automatically.

## What changed

- New canonical scope name: `user` (was `global`).
- Resolver order: `case → user`. Will become `case → firm → user` once firm scope ships.
- All command docs, SKILL.md files, and CLAUDE.md updated to use the new vocabulary.

## Backward compatibility (one release; removed in 3.6.0)

For automation and scripts that hardcode the old name:

- `--scope global` and `scope="global"` still accepted with a stderr deprecation warning.
- `workspace.global_templates_dir()`, `ensure_global_templates_dir()`, `global_templates_list()`
  retained as thin aliases.
- `workspace.py templates` JSON also emits `global_templates_dir`, `"global"` bucket,
  and `shadowed_global` field on case entries.
- `workspace.py resolve-template` JSON adds `scope_legacy` (`"global"` when scope is `"user"`).
- Env var `CLAUDE_BENGO_ALLOW_PII_ON_GLOBAL` keeps its name (CI compatibility).

These all go away in 3.6.0. Update consumers now if you have any.

## What's coming next

- **Firm scope** (Phase 1): admin sets `firm_templates_path` to a local Drive-for-desktop /
  Dropbox / SMB folder; templates promoted there propagate to all lawyers via OS sync.
  Read-only at fill time, with case-local PII rescan cache and canonical xlsx hashing.
  Designed in collaboration with two PE reviews (Anthropic + OpenAI Codex) over four
  iteration rounds.

## Test coverage

- workspace 28/28, template_lib 20/20, audit 18/18, verify 52/52, e2e 37/37 — all green.

---

**Full changelog**: https://github.com/llamadrive/claude-bengo/blob/main/CHANGELOG.md
