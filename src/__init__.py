import json
import subprocess
import time

import requests


class DockerCommandError(Exception):
    """Raised when a docker command fails or its output cannot be parsed."""


def get_compose_images(cwd: str):
    result = subprocess.run(
        ["docker", "compose", "images"], check=False, cwd=cwd, capture_output=True
    )
    if result.returncode != 0:
        raise DockerCommandError("Failed to get docker compose images")

    stdout = result.stdout.decode("utf-8")
    lines = stdout.splitlines()
    lines = lines[1:]
    lines = [line for line in lines if line]
    lines = [line.split() for line in lines]
    return lines  # [[container, repository, tag, image_id, size], ...]


def get_image(image_name: str):
    result = subprocess.run(
        ["docker", "image", "inspect", image_name], check=False, capture_output=True
    )
    if result.returncode != 0:
        raise DockerCommandError("Failed to get docker image")

    stdout = result.stdout.decode("utf-8")
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        raise DockerCommandError("Failed to parse docker image inspect result")

    return data


def get_latest_tag_from_ls(image_name: str):
    """Return the image ID of the `latest` tag of image_name from `docker image ls`, or None."""
    result = subprocess.run(["docker", "image", "ls"], check=False, capture_output=True)
    if result.returncode != 0:
        raise DockerCommandError("Failed to get docker image ls")

    stdout = result.stdout.decode("utf-8")
    lines = stdout.splitlines()
    lines = lines[1:]
    lines = [line for line in lines if line]
    lines = [line.split() for line in lines]

    lines = list(filter(lambda img: img[0] == image_name, lines))
    if len(lines) == 0:
        return None
    lines = list(filter(lambda img: img[1] == "latest", lines))
    if len(lines) == 0:
        return None
    return lines[0][2]


def get_image_version(image_data: dict):
    """Return the `org.opencontainers.image.version` label, falling back to `Created`."""
    if not image_data:
        return None
    if (
        image_data[0]["Config"]["Labels"] is not None
        and "org.opencontainers.image.version" in image_data[0]["Config"]["Labels"]
    ):
        return image_data[0]["Config"]["Labels"]["org.opencontainers.image.version"]
    if "Created" in image_data[0]:
        return image_data[0]["Created"]
    return None


def get_latest_tag_images(images: list[list[str]]):
    """Return {repository: version} for the `latest` images in images, or None if there are none."""
    if len(list(filter(lambda img: img[2] == "latest", images))) == 0:
        print("No latest tag image found")
        return None

    versions = {}
    for image in images:
        if image[2] != "latest":
            continue

        image_name = image[1]
        image_id = get_latest_tag_from_ls(image_name)
        image_data = get_image(image_id)
        image_version = get_image_version(image_data)

        versions[image_name] = image_version
    return versions


def pull_images(cwd: str):
    result = subprocess.run(["docker", "compose", "pull"], check=False, cwd=cwd)
    return result.returncode == 0


def down_containers(cwd: str):
    result = subprocess.run(["docker", "compose", "down"], check=False, cwd=cwd)
    return result.returncode == 0


def up_containers(cwd: str):
    result = subprocess.run(
        ["docker", "compose", "up", "--build", "-d"], check=False, cwd=cwd
    )
    return result.returncode == 0


def get_error_log_count(cwd: str):
    result = subprocess.run(
        ["docker", "compose", "logs", "--tail=100"],
        check=False,
        cwd=cwd,
        capture_output=True,
    )
    if result.returncode != 0:
        raise DockerCommandError("Failed to get docker compose logs")

    stdout = result.stdout.decode("utf-8")
    lines = stdout.splitlines()
    lines = [line for line in lines if line]
    lines = list(filter(lambda line: "ERROR" in line or "error" in line, lines))
    return len(lines)


def send_to_discord(discord_webhook_url, message, embed=None):
    """Post message (and optionally one embed) to a Discord webhook.

    Delivery is best-effort: failures are printed as `[ERROR]` lines and never raised.
    Only the exception class name is logged, because requests exception messages can contain the webhook URL.
    """
    headers = {"Content-Type": "application/json", "User-Agent": "Bot"}
    params = {"content": message}
    if embed is not None:
        params["embeds"] = [embed]

    try:
        response = requests.post(
            discord_webhook_url, headers=headers, json=params, timeout=10
        )
    except requests.RequestException as e:
        print(f"[ERROR] Failed to send Discord notification: {type(e).__name__}")
        return

    if 200 <= response.status_code < 300:
        print(f"[INFO] Discord notification sent (HTTP {response.status_code})")
    else:
        print(
            f"[ERROR] Discord webhook returned HTTP {response.status_code}: "
            f"{response.text[:200]}"
        )
    time.sleep(1)
