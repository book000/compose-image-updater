import subprocess
import unittest
from unittest import mock

from src import (
    DockerCommandError,
    get_deployed_images,
    get_image_identity,
    is_latest_reference,
    split_image_reference,
)


def completed(stdout: str = "", returncode: int = 0):
    return subprocess.CompletedProcess(
        [], returncode, stdout=stdout.encode(), stderr=b""
    )


class GetDeployedImagesTest(unittest.TestCase):
    def test_returns_reference_and_image_id_per_container(self):
        run = mock.Mock(
            side_effect=[
                completed("c1\nc2\n"),
                completed(
                    "web\tsha256:aaa\tciutest/x:latest\ndb\tsha256:bbb\tredis:7\n"
                ),
            ]
        )
        with mock.patch("src.subprocess.run", run):
            result = get_deployed_images("/project")

        self.assertEqual(
            result,
            [
                ("web", "ciutest/x:latest", "sha256:aaa"),
                ("db", "redis:7", "sha256:bbb"),
            ],
        )
        self.assertEqual(
            run.call_args_list[0].args[0], ["docker", "compose", "ps", "-a", "-q"]
        )
        self.assertEqual(run.call_args_list[0].kwargs["cwd"], "/project")
        self.assertEqual(
            run.call_args_list[1].args[0],
            [
                "docker",
                "container",
                "inspect",
                "-f",
                '{{index .Config.Labels "com.docker.compose.service"}}\t{{.Image}}\t{{.Config.Image}}',
                "c1",
                "c2",
            ],
        )

    def test_no_containers_returns_empty_list_without_inspect(self):
        run = mock.Mock(side_effect=[completed("")])
        with mock.patch("src.subprocess.run", run):
            self.assertEqual(get_deployed_images("/project"), [])
        self.assertEqual(run.call_count, 1)

    def test_ps_failure_raises(self):
        run = mock.Mock(side_effect=[completed("", 1)])
        with (
            mock.patch("src.subprocess.run", run),
            self.assertRaisesRegex(
                DockerCommandError, "^Failed to list docker compose containers$"
            ),
        ):
            get_deployed_images("/project")

    def test_inspect_failure_raises(self):
        run = mock.Mock(side_effect=[completed("c1\n"), completed("", 1)])
        with (
            mock.patch("src.subprocess.run", run),
            self.assertRaisesRegex(
                DockerCommandError, "^Failed to inspect docker compose containers$"
            ),
        ):
            get_deployed_images("/project")

    def test_malformed_line_raises_naming_the_line(self):
        run = mock.Mock(side_effect=[completed("c1\n"), completed("sha256:aaa\n")])
        with (
            mock.patch("src.subprocess.run", run),
            self.assertRaisesRegex(
                DockerCommandError,
                r"^Unexpected docker container inspect output: 'sha256:aaa'$",
            ),
        ):
            get_deployed_images("/project")


class GetImageIdentityTest(unittest.TestCase):
    def test_returns_id_and_label_version(self):
        data = [
            {
                "Id": "sha256:aaa",
                "Config": {"Labels": {"org.opencontainers.image.version": "v1"}},
            }
        ]
        with mock.patch("src.get_image", return_value=data):
            self.assertEqual(get_image_identity("x:latest"), ("sha256:aaa", "v1"))

    def test_missing_version_becomes_unknown(self):
        data = [{"Id": "sha256:aaa", "Config": {"Labels": None}}]
        with mock.patch("src.get_image", return_value=data):
            self.assertEqual(get_image_identity("x:latest"), ("sha256:aaa", "unknown"))

    def test_created_is_used_when_label_is_absent(self):
        data = [{"Id": "sha256:aaa", "Config": {"Labels": None}, "Created": "t0"}]
        with mock.patch("src.get_image", return_value=data):
            self.assertEqual(get_image_identity("x:latest"), ("sha256:aaa", "t0"))

    def test_empty_inspect_result_raises(self):
        with (
            mock.patch("src.get_image", return_value=[]),
            self.assertRaisesRegex(
                DockerCommandError, "^Failed to resolve image identity: x:latest$"
            ),
        ):
            get_image_identity("x:latest")

    def test_missing_id_raises(self):
        data = [{"Config": {"Labels": None}}]
        with (
            mock.patch("src.get_image", return_value=data),
            self.assertRaisesRegex(
                DockerCommandError, "^Failed to resolve image identity: x:latest$"
            ),
        ):
            get_image_identity("x:latest")


class ImageReferenceTest(unittest.TestCase):
    def test_split(self):
        cases = {
            "repo/x": ("repo/x", None),
            "repo/x:latest": ("repo/x", "latest"),
            "repo/x:1.2": ("repo/x", "1.2"),
            "host:5000/x": ("host:5000/x", None),
            "host:5000/x:latest": ("host:5000/x", "latest"),
            "repo/x@sha256:abc": ("repo/x@sha256:abc", "@digest"),
        }
        for reference, expected in cases.items():
            with self.subTest(reference=reference):
                self.assertEqual(split_image_reference(reference), expected)

    def test_is_latest(self):
        cases = {
            "repo/x": True,
            "repo/x:latest": True,
            "host:5000/x": True,
            "repo/x:1.2": False,
            "repo/x@sha256:abc": False,
        }
        for reference, expected in cases.items():
            with self.subTest(reference=reference):
                self.assertIs(is_latest_reference(reference), expected)


if __name__ == "__main__":
    unittest.main()
