# Docker Compose Images Updater

Automatically update the latest image used in `docker-compose.yml`.

You can specify the Discord webhook URL in `discord_webhook_url.txt` to be notified after the update is completed.

## Requirements

- Python 3.6+
- venv
- [requirements.txt](requirements.txt): `requests`

## Installation

1. `git clone https://github.com/book000/compose-image-updater.git`
2. Change the tag of the image you want to target for automatic updates to `latest`. (e.g. `hello-world:v1.0.0` -> `hello-world:latest`)
3. (Optional) Get discord webhook url and Write to `/path/to/discord_webhook_url.txt`

## Usage

### Regularly update all projects

The following code can be used to batch update projects located under a specific directory using cron or other means.

```sh
find /path/to/projects/ -maxdepth 2 -name docker-compose.yml | xargs dirname | xargs -L1 /path/to/wrapper.sh
```

### Use Systemd `ExecStartPre` property

If you have `docker-compose up` in Systemd, you can specify the `ExecStartPre` property to perform the update process before startup.

```ini
[Unit]
After=network-online.target docker.service

[Service]
User=root
Group=root
WorkingDirectory=/path/to/project/
ExecStartPre=/path/to/wrapper.sh # <- this!
ExecStart=/usr/local/bin/docker-compose up --build
Restart=no
Type=oneshot

[Install]
WantedBy=multi-user.target
```
