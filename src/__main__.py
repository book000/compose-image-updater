import json
import os
import sys
import time
from dataclasses import dataclass
from pprint import pprint
from shlex import join

from src import (
    DockerCommandError,
    get_deployed_images,
    get_error_log_count,
    get_image_identity,
    get_service_images,
    is_latest_reference,
    pull_images,
    send_to_discord,
    split_image_reference,
    up_containers,
)


def get_project_name(cwd: str):
    """Return the directory name of the project, ignoring any trailing slash."""
    return os.path.basename(os.path.abspath(cwd))


def is_restartable_project(cwd: str):
    """Return True if the project directory name is listed in restartable_projects.json."""
    path = os.path.join(
        os.path.abspath(os.path.dirname(os.path.dirname(__file__))),
        "restartable_projects.json",
    )
    if not os.path.exists(path):
        return False
    with open(path) as f:
        projects = json.load(f)
    return get_project_name(cwd) in projects


def format_identity(identity: tuple[str, str]):
    """Return "<version> (<12 hex chars of the image ID>)" for an (image_id, version) pair."""
    image_id, version = identity
    return f"{version} ({image_id.removeprefix('sha256:')[:12]})"


def get_deployed_identity(image_id: str):
    """Return (image_id, version) of a container's image, or (image_id, "unknown") if the image is gone locally.

    The container's image ID is enough to compare with the pulled tag, so a missing image must not abort the run.
    """
    try:
        return get_image_identity(image_id)
    except DockerCommandError as e:
        print(f"[WARN] Deployed image {image_id} is not available locally: {e}")
        return image_id, "unknown"


@dataclass
class ImageUpdates:
    versions: dict[str, dict[str, str]]
    services: list[str]


def update_images(cwd: str):
    """Return changed image versions and service names after pulling eligible services.

    Returns None when the project cannot be checked (listing containers failed, no tracked image, pull failure).
    Raises DockerCommandError if the target image cannot be inspected after the pull.
    """
    try:
        deployed = get_deployed_images(cwd)
        configured = get_service_images(cwd)
    except Exception as e:  # noqa: BLE001  # catch everything on purpose: log the error and skip this project
        print(f"[ERROR] Failed to get docker compose images: {e}")
        return None

    deployed = [
        (service, configured[service], image_id)
        for service, _, image_id in deployed
        if service in configured and is_latest_reference(configured[service])
    ]
    if not deployed:
        print("No latest tag image found")
        return None

    prev_identities = [get_deployed_identity(image_id) for _, _, image_id in deployed]
    pprint(prev_identities)

    update_result = pull_images(
        cwd, list(dict.fromkeys(service for service, _, _ in deployed))
    )
    if not update_result:
        print("[ERROR] Failed to update images")
        return None

    identities = [get_image_identity(ref) for _, ref, _ in deployed]
    pprint(identities)

    update_versions = {}
    updated_services = []
    for (service, ref, _), prev, current in zip(deployed, prev_identities, identities):
        if prev[0] == current[0]:
            continue
        if service not in updated_services:
            updated_services.append(service)
        update_versions.setdefault(
            split_image_reference(ref)[0],
            {"prev": format_identity(prev), "current": format_identity(current)},
        )

    return ImageUpdates(update_versions, updated_services)


def main():
    if len(sys.argv) > 1:
        cwd = sys.argv[1]
    else:
        cwd = os.getcwd()

    res = update_images(cwd)
    if res is None:
        print("[INFO] Target image not found")
        return

    if not res.versions:
        print("[INFO] Update not found")
        return

    restart_status = "NOT-RESTARTABLE"
    error_log_count = 0
    if is_restartable_project(cwd):
        print("[INFO] Applying updates to eligible services")
        if up_containers(cwd, res.services):
            restart_status = "SUCCESS"
            # give the containers time to start before scanning their logs
            time.sleep(10)
            error_log_count = get_error_log_count(cwd)
        else:
            restart_status = "FAILED (UP)"

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
    apply_command = join(
        ["docker", "compose", "up", "--no-deps", "--pull", "never", "-d", *res.services]
    )
    description = {
        "SUCCESS": ""
        if error_log_count == 0
        else f"But after restarted found error: {error_log_count}\n",
        "FAILED": "Please check the project manually",
        "NOT-RESTARTABLE": f"Please apply the update with `{apply_command}`.\n",
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
            "title": title % get_project_name(cwd),
            "description": f"{description}Target directory: {cwd}",
            "fields": [
                {
                    "name": image_name,
                    "value": f"prev: {image['prev']}\ncurrent: {image['current']}",
                    "inline": True,
                }
                for image_name, image in res.versions.items()
            ],
            "footer": {
                "text": f"Hostname: {os.uname()[1]}",
            },
            "color": color,
        },
    )


if __name__ == "__main__":
    main()
