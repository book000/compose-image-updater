# Docker Compose Images Updater

Automatically updates the `latest` images used by Docker Compose projects.

For each project it selects deployed services whose images are tagged `latest` or untagged in the current Compose configuration, pulls only those services, and compares their deployed image IDs with the pulled images. If they differ, it can recreate only the changed eligible services and send the result to a Discord webhook. Services using other tags or digest references are neither pulled nor recreated, including dependencies of updated services. An update that was not applied (for example because the restart failed, or the project is not restartable) is reported again on the next run.

## Requirements

- Bash, `find` supporting `-maxdepth` and `-printf`, and `sort` supporting `-z` for the shell scripts
- Python 3.9+ with the `venv` module
- Docker with the Compose plugin (`docker compose`), supporting `config --format json` and `up --no-deps --pull never`
- `jq`, only for `generate-restartables.sh`
- [requests](requirements.txt), installed automatically into `venv/` by `wrapper.sh`

## Installation

1. `git clone https://github.com/book000/compose-image-updater.git`
2. Change the tag of every image you want to update automatically to `latest` in the project's compose file (e.g. `hello-world:v1.0.0` -> `hello-world:latest`). Images with any other tag are not updated.
3. (Optional) Create a Discord webhook URL and configure it as described in [Configuration](#configuration).

## Configuration

### Discord notification

Notifications are sent only when at least one image was updated and a webhook URL is configured. Set the URL in one of the following ways:

- Write it to `discord_webhook_url.txt` in the repository root, next to `wrapper.sh`. `wrapper.sh` exports it as `CIU_DISCORD_WEBHOOK_URL` and the file takes precedence over an existing variable.
- Set the `CIU_DISCORD_WEBHOOK_URL` environment variable (also when running `python3 -m src` directly).

### Restarting projects

By default an update is only reported. Apply it yourself with `docker compose up --no-deps --pull never -d SERVICE...`, replacing `SERVICE...` with the changed eligible service names. The Discord notification includes the command for those services.

To let the tool apply updates with `docker compose up --no-deps --pull never -d SERVICE...`, list the project's directory name in `restartable_projects.json` in the repository root:

```json
["project-a", "project-b"]
```

`./generate-restartables.sh /path/to/projects/` regenerates this file with the directory names of all projects found under the given directory and shows a diff against the previous file. Names containing whitespace or quotes are preserved, duplicate names are removed, and an empty search writes `[]`. A failed search leaves the existing file unchanged. Edit the result if only some projects should allow automatic updates. The tool does not stop the whole project or rebuild images; it recreates changed eligible services from the images already pulled. Dependencies are left running with their existing images, so start any required stopped dependencies manually. Services without deployed containers and build-only services without an image reference are skipped. After a successful update the tool waits 10 seconds and counts `ERROR`/`error` lines in the last 100 log lines, which is shown in the notification.

## Usage

Update a single project:

```bash
./wrapper.sh /path/to/project
```

If the argument is omitted, the current directory is used. A single relative path is resolved from the caller's directory. Extra arguments or an invalid target directory are rejected.

### Regularly update all projects

`update-all.sh` runs `wrapper.sh` for every directory that contains `docker-compose.yml`, `compose.yaml` or `compose.yml` (the given directory itself and its immediate subdirectories) and writes the output to `<log dir>/<timestamp>.log`. Each project directory is processed once, even if it contains multiple matching files, and relative paths and names containing whitespace or quotes are supported. An empty search succeeds without invoking the updater. The batch continues after a project fails and returns the first failing project's exit code; discovery or log-writing errors also produce a non-zero exit status. The Python CLI and wrapper return non-zero on discovery, pull, image inspection, or automatic update failure, while no eligible images or no changes is a successful result. For example, add it to cron:

```cron
0 * * * * /path/to/compose-image-updater/update-all.sh /path/to/projects/ /path/to/logs/
```

### Use Systemd `ExecStartPre` property

If you start a project with `docker compose up` from Systemd, you can run the update before startup with the `ExecStartPre` property. `wrapper.sh` uses `WorkingDirectory` as the target project.

```ini
[Unit]
After=network-online.target docker.service

[Service]
User=root
Group=root
WorkingDirectory=/path/to/project
ExecStartPre=/path/to/compose-image-updater/wrapper.sh # <- this!
ExecStart=/usr/local/bin/docker compose up --build
Restart=no
Type=oneshot

[Install]
WantedBy=multi-user.target
```

## Disclaimer

The developer is not responsible for any problems caused by the user using this project.

## License

The license for this project is [MIT License](LICENSE).
