import os
import sys
from pprint import pprint

from src import get_latest_tag_images, pull_images, send_to_discord


def update_images(cwd: str):
    prev_versions = get_latest_tag_images(cwd)
    if prev_versions is None:
        return None
    pprint(prev_versions)

    update_result = pull_images(cwd)
    if not update_result:
        print("[ERROR] Failed to update images")
        return None

    versions = get_latest_tag_images(cwd)
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

    discord_webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if discord_webhook_url is None:
        print("[INFO] Discord webhook url id not found")
        return

    send_to_discord(discord_webhook_url, "", {
        "title": "Docker image updated (%s)" % cwd.split("/")[-1],
        "description": "Please apply the update with `docker-compose down && docker-compose up --build -d`.\n"
                       "Target directory: %s" % cwd,
        "fields": [
            {
                "name": image_name,
                "value": f"prev: {image['prev']}\ncurrent: {image['current']}",
            }
            for image_name, image in res.items()
        ],
        "footer": {
            "text": "Hostname: %s" % os.uname()[1],
        },
        "color": 0x00ff00,
    })


if __name__ == '__main__':
    main()
