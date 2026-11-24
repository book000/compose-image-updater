import json
import subprocess
import unittest
from unittest import mock

from src import DockerCommandError, get_service_images, pull_images, up_containers
from src.__main__ import ImageUpdates, main, update_images


def completed(value="", returncode=0):
    return subprocess.CompletedProcess([], returncode, stdout=value.encode())


class ServiceScopeTest(unittest.TestCase):
    def test_only_changed_eligible_services_are_applied(self):
        for reference in ("app:latest", "app"):
            with self.subTest(reference=reference):
                commands = []

                def run(args, commands=commands, reference=reference, **kwargs):
                    commands.append(args)
                    if args[1:3] == ["container", "inspect"]:
                        return completed(
                            f"web\tsha256:old\t{reference}\n"
                            "db\tsha256:db-old\tdatabase:stable\n"
                            "worker\tsha256:worker\tworker:latest\n"
                            f"web\tsha256:old\t{reference}\n"
                        )
                    if args[1:3] == ["image", "inspect"]:
                        ref = args[3]
                        image_id = "sha256:new" if ref == reference else ref
                        if ref == "worker:latest":
                            image_id = "sha256:worker"
                        return completed(
                            json.dumps(
                                [
                                    {
                                        "Id": image_id,
                                        "Config": {"Labels": None},
                                    }
                                ]
                            )
                        )
                    if args[2] == "ps":
                        return completed("c1\nc2\nc3\nc4\n")
                    if args[2] == "config":
                        return completed(
                            json.dumps(
                                {
                                    "services": {
                                        "web": {
                                            "image": reference,
                                            "depends_on": {"db": {}},
                                        },
                                        "db": {"image": "database:stable"},
                                        "worker": {"image": "worker:latest"},
                                    }
                                }
                            )
                        )
                    return completed()

                with (
                    mock.patch("src.subprocess.run", side_effect=run),
                    mock.patch("src.__main__.sys.argv", ["updater", "/project"]),
                    mock.patch(
                        "src.__main__.is_restartable_project", return_value=True
                    ),
                    mock.patch("src.__main__.time.sleep"),
                    mock.patch.dict("os.environ", {}, clear=True),
                ):
                    main()

                self.assertEqual(
                    [cmd for cmd in commands if cmd[2] in ("pull", "up", "down")],
                    [
                        ["docker", "compose", "pull", "web", "worker"],
                        [
                            "docker",
                            "compose",
                            "up",
                            "--no-deps",
                            "--pull",
                            "never",
                            "-d",
                            "web",
                        ],
                    ],
                )

    def test_current_configuration_controls_eligibility(self):
        with (
            mock.patch(
                "src.__main__.get_deployed_images",
                return_value=[
                    ("web", "app:latest", "sha256:old"),
                ],
            ),
            mock.patch(
                "src.__main__.get_service_images", return_value={"web": "app:stable"}
            ),
            mock.patch("src.__main__.pull_images") as pull,
        ):
            self.assertIsNone(update_images("/project"))
        pull.assert_not_called()

    def test_configuration_failures_do_not_pull(self):
        for error in (DockerCommandError("config failed"), ValueError("bad config")):
            with (
                self.subTest(error=error),
                mock.patch("src.__main__.get_deployed_images", return_value=[]),
                mock.patch("src.__main__.get_service_images", side_effect=error),
                mock.patch("src.__main__.pull_images") as pull,
            ):
                self.assertIsNone(update_images("/project"))
                pull.assert_not_called()

    def test_empty_selection_never_runs_project_wide_commands(self):
        with mock.patch("src.subprocess.run") as run:
            self.assertFalse(pull_images("/project", []))
            self.assertFalse(up_containers("/project", []))
        run.assert_not_called()

    def test_failed_commands_return_false(self):
        with mock.patch("src.subprocess.run", return_value=completed(returncode=1)):
            self.assertFalse(pull_images("/project", ["web"]))
            self.assertFalse(up_containers("/project", ["web"]))

    def test_manual_apply_command_is_scoped(self):
        with (
            mock.patch(
                "src.__main__.update_images",
                return_value=ImageUpdates(
                    {"app": {"prev": "old", "current": "new"}}, ["web"]
                ),
            ),
            mock.patch("src.__main__.sys.argv", ["updater", "/project"]),
            mock.patch("src.__main__.is_restartable_project", return_value=False),
            mock.patch("src.__main__.up_containers") as up,
            mock.patch.dict(
                "os.environ", {"CIU_DISCORD_WEBHOOK_URL": "test"}, clear=True
            ),
            mock.patch("src.__main__.send_to_discord") as notify,
        ):
            main()
        up.assert_not_called()
        self.assertIn(
            "docker compose up --no-deps --pull never -d web",
            notify.call_args.args[2]["description"],
        )

    def test_failed_apply_is_reported(self):
        with (
            mock.patch(
                "src.__main__.update_images",
                return_value=ImageUpdates(
                    {"app": {"prev": "old", "current": "new"}}, ["web"]
                ),
            ),
            mock.patch("src.__main__.sys.argv", ["updater", "/project"]),
            mock.patch("src.__main__.is_restartable_project", return_value=True),
            mock.patch("src.__main__.up_containers", return_value=False),
            mock.patch("src.__main__.get_error_log_count") as logs,
            mock.patch.dict(
                "os.environ", {"CIU_DISCORD_WEBHOOK_URL": "test"}, clear=True
            ),
            mock.patch("src.__main__.send_to_discord") as notify,
        ):
            main()
        logs.assert_not_called()
        self.assertIn("FAILED", notify.call_args.args[2]["title"])


class ServiceConfigurationTest(unittest.TestCase):
    def test_resolves_service_images_and_skips_build_only_services(self):
        config = {"services": {"web": {"image": "app:latest"}, "local": {"build": "."}}}
        with mock.patch(
            "src.subprocess.run", return_value=completed(json.dumps(config))
        ):
            self.assertEqual(get_service_images("/project"), {"web": "app:latest"})

    def test_invalid_configuration_raises(self):
        for output in ("invalid json", "{}", '{"services": []}'):
            with (
                self.subTest(output=output),
                mock.patch("src.subprocess.run", return_value=completed(output)),
                self.assertRaises(DockerCommandError),
            ):
                get_service_images("/project")

    def test_failed_configuration_command_raises(self):
        with (
            mock.patch("src.subprocess.run", return_value=completed(returncode=1)),
            self.assertRaises(DockerCommandError),
        ):
            get_service_images("/project")
