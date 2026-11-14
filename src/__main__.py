import json
import os
import sys
import time
from pprint import pprint

from src import (
    down_containers,
    get_compose_images,
    get_error_log_count,
    get_latest_tag_images,
    pull_images,
    send_to_discord,
    up_containers,
)


def is_restartable_project(cwd: str):
    """Return True if the last path component of cwd is listed in restartable_projects.json."""
    path = os.path.join(
        os.path.abspath(os.path.dirname(os.path.dirname(__file__))),
        "restartable_projects.json",
    )
    if not os.path.exists(path):
        return False
    with open(path) as f:
        projects = json.load(f)
    return cwd.split("/")[-1] in projects


def update_images(cwd: str):
    try:
        images = get_compose_images(cwd)
    except Exception as e:  # noqa: BLE001  # catch everything on purpose: log the error and skip this project
        print(f"[ERROR] Failed to get docker compose images: {e}")
        return None

    prev_versions = get_latest_tag_images(images)
    if prev_versions is None:
        return None
    pprint(prev_versions)

    update_result = pull_images(cwd)
    if not update_result:
        print("[ERROR] Failed to update images")
        return None

    versions = get_latest_tag_images(images)
    if versions is None:
        return None
    pprint(versions)

    update_versions = {}
    for image_name, version in versions.items():
        if prev_versions[image_name] == version:
            continue
        update_versions[image_name] = {
            "prev": prev_versions[image_name],
            "current": version,
        }

    return update_versions


def main():
    if len(sys.argv) > 1:
        cwd = sys.argv[1]
    else:
        cwd = os.getcwd()

    res = update_images(cwd)
    if res is None:
        print("[INFO] Target image not found")
        return

    if len(res) == 0:
        print("[INFO] Update not found")
        return

    restart_status = "NOT-RESTARTABLE"
    error_log_count = 0
    if is_restartable_project(cwd):
        print("[INFO] Restarting project")
        down_result = down_containers(cwd)
        up_result = up_containers(cwd)
        if not down_result and up_result:
            restart_status = "FAILED (DOWN)"
        if down_result and not up_result:
            restart_status = "FAILED (UP)"
        if not down_result and not up_result:
            restart_status = "FAILED (DOWN & UP)"

        if down_result and up_result:
            restart_status = "SUCCESS"
            # give the containers time to start before scanning their logs
            time.sleep(10)
            error_log_count = get_error_log_count(cwd)

    discord_webhook_url = os.getenv("CIU_DISCORD_WEBHOOK_URL")
    if discord_webhook_url is None:
        print("[INFO] Discord webhook url id not found")
        return

    status_key = "FAILED" if restart_status.startswith("FAILED") else restart_status

    title = {
        "SUCCESS": "Docker image updated and restarted (%s)",
        "FAILED": "Docker image updated but FAILED to restart (%s)",
        "NOT-RESTARTABLE": "Docker image updated (%s)",
    }[status_key]
    description = {
        "SUCCESS": ""
        if error_log_count == 0
        else f"But after restarted found error: {error_log_count}\n",
        "FAILED": "Please check the project manually",
        "NOT-RESTARTABLE": "Please apply the update with `docker compose down && docker compose up --build -d`.",
    }[status_key]
    color = {
        "SUCCESS": 0x00FF00 if error_log_count == 0 else 0xFFA500,  # green or orange
        "FAILED": 0xFF0000,  # red
        "NOT-RESTARTABLE": 0xFFFF00,  # yellow
    }[status_key]

    send_to_discord(
        discord_webhook_url,
        "",
        {
            "title": title % cwd.split("/")[-1],
            "description": f"{description}Target directory: {cwd}",
            "fields": [
                {
                    "name": image_name,
                    "value": f"prev: {image['prev']}\ncurrent: {image['current']}",
                    "inline": True,
                }
                for image_name, image in res.items()
            ],
            "footer": {
                "text": f"Hostname: {os.uname()[1]}",
            },
            "color": color,
        },
    )


if __name__ == "__main__":
    main()
