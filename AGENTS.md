# AGENTS.md

Guidance for AI coding agents and contributors. `CLAUDE.md` imports this file, and `.github/copilot-instructions.md` adds the review checklist.

## Language

- All deliverables are written in **English**: commit messages, PR/Issue titles and bodies, review comments, code comments and docstrings, and documentation (`README.md`, `AGENTS.md`, etc.).
- Exceptions (keep as is): quotations, technical identifiers, generated files, and external source text.
- Runtime messages (logs, errors, Discord notification text) are English.
- Do not rewrite Git history to change the language of past commits.

## Overview

`compose-image-updater` is a small Python CLI plus shell wrappers. For a Docker Compose project it selects eligible services from the resolved configuration, pulls their images, and compares each deployed container's image ID with its configured image reference after the pull. When they differ, it optionally recreates the changed services and posts the result to a Discord webhook.

- Only services with deployed containers and an image tagged `latest` or untagged (Docker's default tag is `latest`) in `docker compose config --format json` are tracked and pulled. Build-only services are skipped.
- Services configured with any other tag or a digest reference are not tracked, pulled, or recreated. Eligibility uses the current configuration, even if an existing container was created with a different reference.
- A differing image ID is an update, even if the version label is unchanged or an earlier run already pulled the tag, so an update that was not applied (restart failed or not restartable) is reported again on the next run.
- The version of an image is the `org.opencontainers.image.version` label, falling back to `Created`. It is only used for display: the notification shows `<version> (<first 12 hex chars of the image ID>)`, and `unknown` when the deployed image is no longer in the local image store.
- A project with no containers is not checked ("No latest tag image found").
- Changed eligible services are recreated with `docker compose up --no-deps --pull never -d SERVICE...` only if the project directory name is listed in `restartable_projects.json`. No project-wide shutdown or build is performed. After a successful update, error lines in the project-wide logs are counted in the notification (see the README).
- The only runtime dependency is `requests`. Docker with the Compose plugin must be available.

## Commands

```bash
./wrapper.sh /path/to/project                  # update one project (creates ./venv, runs pip install, then python3 -m src)
./update-all.sh /path/to/projects/ /path/to/logs/   # run wrapper.sh for every compose project found (cron use)
./generate-restartables.sh /path/to/projects/  # regenerate restartable_projects.json (requires jq)
python3 -m src /path/to/project                # run without the wrapper (needs requests installed; defaults to the current directory)
```

Tests live in `tests/` (stdlib `unittest`, mocked Docker calls, collected by `pytest` in CI) and run with `python3 -m unittest discover -s tests` (needs `requests` installed). CI (`.github/workflows/`, reusable workflows from `book000/templates`) runs the following; run the same locally before opening a PR:

```bash
python3 -m compileall -q .
ruff check .
ruff format --check .
shellcheck --severity=warning ./*.sh
```

Verify behavior changes manually against a real or throwaway Compose project and describe the check in the PR.

## Structure

- `src/__main__.py`: entry point. `update_images()` selects eligible deployed services, pulls them, and compares deployed vs configured image identity; `ImageUpdates` carries the changed image versions and service names. `get_deployed_identity()` and `format_identity()` look up and format an image identity for the notification, `main()` applies changes to the selected services and sends the notification, and `is_restartable_project()` reads `restartable_projects.json` from the repository root.
- `src/__init__.py`: helpers that call `docker` through `subprocess` (list arguments, no shell): `get_deployed_images()` returns service/reference/image-ID triples using `docker compose ps -a -q` and `docker container inspect` with the `com.docker.compose.service` label; `get_service_images()` reads configured image references using `docker compose config --format json`; `pull_images()` and `up_containers()` require explicit service lists. Other helpers handle image references and identity, version lookup, project-wide logs, and `send_to_discord()`.
- `tests/`: `unittest` tests for the helpers and `update_images()` with Docker calls mocked.
- `wrapper.sh`: changes to its own directory, loads `discord_webhook_url.txt` into `CIU_DISCORD_WEBHOOK_URL` (the file takes precedence over an existing variable), prepares `venv`, installs `requirements.txt`, and runs `python3 -m src`. It is also used from systemd `ExecStartPre`.
- `update-all.sh`: finds `docker-compose.yml`, `compose.yaml` and `compose.yml` in the given directory and its immediate subdirectories (`find -maxdepth 2`) and runs `wrapper.sh` per directory, teeing output to `<log dir>/<timestamp>.log`.
- `generate-restartables.sh`: writes the names of those directories to `restartable_projects.json` and shows a diff against the previous file.

## Conventions

- Call Docker through `subprocess` with list arguments, as the existing code does. Do not add dependencies beyond `requests` for what the standard library covers.
- Python is formatted and linted with ruff using its defaults (there is no ruff configuration file). Shell scripts must pass ShellCheck.
- When making a non-obvious design decision, state the choice, the rejected alternatives and the assumptions in the PR description.
- Update `README.md` and this file when arguments, configuration files or environment variables change.
- Commits follow [Conventional Commits](https://www.conventionalcommits.org/); branches follow [Conventional Branch](https://conventional-branch.github.io) short form (`feat/...`, `fix/...`).
- Do not commit to Renovate PRs; open a new PR instead.

## Security

- Never commit the Discord webhook URL. It is read from `CIU_DISCORD_WEBHOOK_URL` or `discord_webhook_url.txt`; the file and `restartable_projects.json` are in `.gitignore`.
- Do not print secrets in code or logs.
