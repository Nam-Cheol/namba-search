# Legacy Claude Plugin

The final Claude Code plugin baseline was version `0.8.2`.

The Codex 1.0.0 line removes:

- `.claude-plugin/`
- first-run Claude setup scripts
- Claude settings edits
- Claude session update hooks
- GitHub star prompt flow
- Skill instructions that call Claude-specific web, shell, or Playwright tools

Rollback path for maintainers:

```bash
git fetch origin
git switch -c legacy/claude v0.8.2
```

If the `v0.8.2` tag does not yet exist, create it from the last verified Claude
release commit after maintainer review:

```bash
git tag -a v0.8.2 <claude-release-commit> -m "Claude final v0.8.2"
```

Do not recreate or push tags from an unverified migration worktree.
