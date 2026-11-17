# Docker Compose Images Updater

Automatically updates the `latest` images used by Docker Compose projects.

For each project it runs `docker compose pull` and compares the image each container is running with the image the `latest` tag points to afterwards. If they differ, it can restart the project and send the result to a Discord webhook. An update that was not applied (for example because the restart failed, or the project is not restartable) is reported again on the next run.

## Requirements

- Python 3.9+ with the `venv` module
- Docker with the Compose plugin (`docker compose`)
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

By default an updated project is only reported; apply the update yourself with `docker compose down && docker compose up --build -d`.

To let the tool restart a project (`docker compose down`, then `docker compose up --build -d`), list its directory name in `restartable_projects.json` in the repository root:

```json
["project-a", "project-b"]
```

`./generate-restartables.sh /path/to/projects/` regenerates this file with the directory names of all projects found under the given directory and shows a diff against the previous file. Edit the result if only some projects should be restarted. After a successful restart the tool waits 10 seconds and counts `ERROR`/`error` lines in the last 100 log lines, which is shown in the notification.

## Usage

Update a single project:

```bash
./wrapper.sh /path/to/project
```

If the argument is omitted, the current directory is used.

### Regularly update all projects

`update-all.sh` runs `wrapper.sh` for every directory that contains `docker-compose.yml`, `compose.yaml` or `compose.yml` (the given directory itself and its immediate subdirectories) and writes the output to `<log dir>/<timestamp>.log`. For example, add it to cron:

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
