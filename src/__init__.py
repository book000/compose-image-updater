import json
import subprocess
import time

import requests


class DockerCommandError(Exception):
    """Raised when a docker command fails or its output cannot be parsed."""


def get_deployed_images(cwd: str):
    """Return [(service, image_reference, full_image_id), ...] for project containers.

    The image ID is the image each container was created from, so it stays correct
    after a pull has moved the tag. The reference is the one used to create the container.
    """
    result = subprocess.run(
        ["docker", "compose", "ps", "-a", "-q"],
        check=False,
        cwd=cwd,
        capture_output=True,
    )
    if result.returncode != 0:
        raise DockerCommandError("Failed to list docker compose containers")

    container_ids = result.stdout.decode("utf-8").split()
    if not container_ids:
        return []

    result = subprocess.run(
        [
            "docker",
            "container",
            "inspect",
            "-f",
            '{{index .Config.Labels "com.docker.compose.service"}}\t{{.Image}}\t{{.Config.Image}}',
            *container_ids,
        ],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        raise DockerCommandError("Failed to inspect docker compose containers")

    deployed = []
    for line in result.stdout.decode("utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) != 3 or not fields[0] or fields[0] == "<no value>":
            raise DockerCommandError(
                f"Unexpected docker container inspect output: {line!r}"
            )
        service, image_id, reference = fields
        deployed.append((service, reference, image_id))
    return deployed


def split_image_reference(reference: str):
    """Return (repository, tag) of an image reference; tag is None when absent.

    A reference with a digest returns the tag "@digest", which is never `latest`.
    """
    if "@" in reference:
        return reference, "@digest"
    last_segment = reference.rsplit("/", 1)[-1]
    if ":" not in last_segment:
        return reference, None
    repository, tag = reference.rsplit(":", 1)
    return repository, tag


def is_latest_reference(reference: str):
    """Return True if the reference is tracked: tagged `latest` or untagged."""
    return split_image_reference(reference)[1] in ("latest", None)


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


def get_image_version(image_data: dict):
    """Return the `org.opencontainers.image.version` label, falling back to `Created`."""
    if not image_data:
        return None
    labels = image_data[0]["Config"]["Labels"]
    if labels is not None and "org.opencontainers.image.version" in labels:
        return labels["org.opencontainers.image.version"]
    if "Created" in image_data[0]:
        return image_data[0]["Created"]
    return None


def get_image_identity(image_ref: str):
    """Return (full_image_id, version) of an image ID or reference; version is "unknown" if unavailable."""
    image_data = get_image(image_ref)
    if not image_data or "Id" not in image_data[0]:
        raise DockerCommandError(f"Failed to resolve image identity: {image_ref}")
    return image_data[0]["Id"], get_image_version(image_data) or "unknown"


def get_service_images(cwd: str):
    """Return configured image references keyed by Compose service name."""
    result = subprocess.run(
        ["docker", "compose", "config", "--format", "json"],
        check=False,
        cwd=cwd,
        capture_output=True,
    )
    if result.returncode != 0:
        raise DockerCommandError("Failed to read docker compose configuration")
    try:
        config = json.loads(result.stdout)
        return {
            service: definition["image"]
            for service, definition in config["services"].items()
            if definition.get("image")
        }
    except (ValueError, KeyError, TypeError, AttributeError):
        raise DockerCommandError(
            "Failed to parse docker compose configuration"
        ) from None


def pull_images(cwd: str, services: list[str]):
    if not services:
        return False
    result = subprocess.run(
        ["docker", "compose", "pull", *services], check=False, cwd=cwd
    )
    return result.returncode == 0


def up_containers(cwd: str, services: list[str]):
    if not services:
        return False
    result = subprocess.run(
        ["docker", "compose", "up", "--no-deps", "--pull", "never", "-d", *services],
        check=False,
        cwd=cwd,
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
