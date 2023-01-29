import json
import os
import sys
import time
from pprint import pprint

from src import get_compose_images, get_error_log_count, get_latest_tag_images, pull_images, restart_containers, \
    send_to_discord


def is_restartable_project(cwd: str):
    # restartable_projects.json を読む
    # ディレクトリ名があれば True を返す
    if not os.path.exists("restartable_projects.json"):
        return False
    with open("restartable_projects.json") as f:
        projects = json.load(f)
    return cwd.split("/")[-1] in projects


def update_images(cwd: str):
    try:
        images = get_compose_images(cwd)
    except Exception as e:
        print(f"[ERROR] Failed to get docker-compose images: {e}")
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

    restart_status = 'NOT-RESTARTABLE'
    error_log_count = 0
    if is_restartable_project(cwd):
        print("[INFO] Restarting project")
        result = restart_containers(cwd)
        restart_status = "SUCCESS" if result else "FAILED"
        if result:
            # wait 10 seconds
            time.sleep(10)
            error_log_count = get_error_log_count(cwd)

    discord_webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if discord_webhook_url is None:
        print("[INFO] Discord webhook url id not found")
        return

    title = {
        "SUCCESS": "Docker image updated and restarted (%s)",
        "FAILED": "Docker image updated but FAILED to restart (%s)",
        "NOT-RESTARTABLE": "Docker image updated (%s)",
    }[restart_status]
    description = {
        "SUCCESS": None if error_log_count == 0 else f"But after restarted found error: {error_log_count}",
        "FAILED": "Please check the project manually",
        "NOT-RESTARTABLE": "Please apply the update with `docker-compose down && docker-compose up --build -d`."
    }[restart_status]
    color = {
        "SUCCESS": 0x00ff00 if error_log_count == 0 else 0xffa500,  # green or orange
        "FAILED": 0xff0000,  # red
        "NOT-RESTARTABLE": 0xffff00,  # yellow
    }[restart_status]

    send_to_discord(discord_webhook_url, "", {
        "title": title % cwd.split("/")[-1],
        "description": "%s\nTarget directory: %s" % (description, cwd),
        "fields": [
            {
                "name": image_name,
                "value": f"prev: {image['prev']}\ncurrent: {image['current']}",
                "inline": True,
            }
            for image_name, image in res.items()
        ],
        "footer": {
            "text": "Hostname: %s" % os.uname()[1],
        },
        "color": color,
    })


if __name__ == '__main__':
    main()
