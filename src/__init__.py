import json
import subprocess
import time

import requests


def get_compose_images(cwd: str):
    result = subprocess.run(["docker-compose", "images"], cwd=cwd, capture_output=True)
    if result.returncode != 0:
        raise Exception("Failed to get docker-compose images")

    stdout = result.stdout.decode("utf-8")
    lines = stdout.splitlines()
    lines = lines[1:]  # remove header
    lines = [line for line in lines if line]
    lines = [line.split() for line in lines]
    return lines  # [[container, repository, tag, image_id, size], ...]


def get_image(image_name: str):
    result = subprocess.run(["docker", "image", "inspect", image_name], capture_output=True)
    if result.returncode != 0:
        raise Exception("Failed to get docker image")

    stdout = result.stdout.decode("utf-8")
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        raise Exception("Failed to parse docker image inspect result")

    return data


def get_latest_tag_from_ls(image_name: str):
    result = subprocess.run(["docker", "image", "ls"], capture_output=True)
    if result.returncode != 0:
        raise Exception("Failed to get docker image ls")

    stdout = result.stdout.decode("utf-8")
    lines = stdout.splitlines()
    lines = lines[1:]  # remove header
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
    if not image_data:
        return None
    if image_data[0]["Config"]["Labels"] is not None and "org.opencontainers.image.version" in image_data[0]["Config"][
        "Labels"]:
        return image_data[0]["Config"]["Labels"]["org.opencontainers.image.version"]
    if "Created" in image_data[0]:
        return image_data[0]["Created"]
    return None


def get_latest_tag_images(images: list[list[str]]):
    # check latest tag image
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
    result = subprocess.run(["docker-compose", "pull"], cwd=cwd)
    return result.returncode == 0


def send_to_discord(discord_webhook_url, message, embed=None):
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Bot"
    }
    params = {
        "content": message,
        "embeds": [embed]
    }
    response = requests.post(
        discord_webhook_url,
        headers=headers,
        json=params)
    print(response.status_code)
    time.sleep(1)
