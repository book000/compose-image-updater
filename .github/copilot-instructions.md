# Copilot code review instructions

Read `AGENTS.md` at the repository root first; it is the source of truth for structure, commands and conventions.

## Language

Write review comments in English, and expect all deliverables (code comments, docs, commit messages, PR text) in English.
Runtime log, error and notification messages are English too.

## Review checklist

- Every `subprocess.run` result is checked (`returncode`); a failed `docker compose` call must not be silently ignored, and a failing Discord request must not break the update flow.
- The Discord webhook URL (`CIU_DISCORD_WEBHOOK_URL`, `discord_webhook_url.txt`) and other secrets never reach code, logs or commits; `.gitignore` entries are not dropped.
- Shell scripts (`wrapper.sh`, `update-all.sh`, `generate-restartables.sh`) quote variables, validate arguments and pass ShellCheck.
- Only configured `latest` or untagged services with deployed containers are pulled. Only changed eligible services are recreated with `up --no-deps --pull never`; other tags, digest references, and dependencies must remain untouched. Automatic updates require the project to be listed in `restartable_projects.json`. Versions come from `org.opencontainers.image.version` with `Created` as fallback.
- Python passes `ruff check` and `ruff format --check` (default configuration).
- Behavior changes include stdlib `unittest` coverage in `tests/` with mocked Docker calls, plus a manual verification note in the PR description.
- `README.md` and `AGENTS.md` are updated when arguments, configuration files or environment variables change.
- Commit and PR titles follow Conventional Commits.

## Do not flag

- `subprocess.run([...])` with list arguments and no shell is intentional; do not report shell injection.
- Keeping dependencies to the standard library plus `requests` is intentional; do not suggest heavier libraries.
