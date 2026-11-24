import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.__main__ import ImageUpdates, main

ROOT = Path(__file__).resolve().parents[1]


class ExitStatusTest(unittest.TestCase):
    def test_no_images_and_no_changes_succeed(self):
        for result in (None, ImageUpdates({}, [])):
            with (
                self.subTest(result=result),
                mock.patch("src.__main__.update_images", return_value=result),
                mock.patch("src.__main__.is_restartable_project") as restartable,
            ):
                self.assertEqual(main(), 0)
                restartable.assert_not_called()

    def test_failed_restart_returns_failure_with_or_without_notification(self):
        for webhook in ({}, {"CIU_DISCORD_WEBHOOK_URL": "test"}):
            with (
                self.subTest(webhook=bool(webhook)),
                mock.patch.dict("os.environ", webhook, clear=True),
                mock.patch(
                    "src.__main__.update_images",
                    return_value=ImageUpdates(
                        {"app": {"prev": "old", "current": "new"}}, ["web"]
                    ),
                ),
                mock.patch("src.__main__.is_restartable_project", return_value=True),
                mock.patch("src.__main__.up_containers", return_value=False),
                mock.patch("src.__main__.send_to_discord") as notify,
            ):
                self.assertEqual(main(), 1)
                self.assertEqual(notify.called, bool(webhook))

    def test_successful_and_manual_updates_return_success(self):
        for restartable in (True, False):
            with (
                self.subTest(restartable=restartable),
                mock.patch.dict("os.environ", {}, clear=True),
                mock.patch(
                    "src.__main__.update_images",
                    return_value=ImageUpdates(
                        {"app": {"prev": "old", "current": "new"}}, ["web"]
                    ),
                ),
                mock.patch(
                    "src.__main__.is_restartable_project", return_value=restartable
                ),
                mock.patch("src.__main__.up_containers", return_value=True),
                mock.patch("src.__main__.get_error_log_count", return_value=0),
                mock.patch("src.__main__.time.sleep"),
            ):
                self.assertEqual(main(), 0)


class CliExitStatusTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / "src", self.root / "src")
        self.bin = self.root / "bin"
        self.bin.mkdir()
        docker = self.bin / "docker"
        docker.write_text(
            "#!/bin/sh\n"
            'if [ "$2" = "$FAIL_COMMAND" ]; then exit 7; fi\n'
            'case "$1 $2 $3" in\n'
            '  "compose ps -a")\n'
            '    if [ "$NO_CONTAINERS" != 1 ]; then echo c1; fi ;;\n'
            '  "compose config --format")\n'
            '    if [ "$FAIL_COMMAND" = config ]; then exit 7; fi\n'
            '    echo \'{"services":{"web":{"image":"app:latest"}}}\' ;;\n'
            '  "container inspect -f")\n'
            "    printf 'web\\tsha256:old\\tapp:latest\\n' ;;\n"
            '  "image inspect app:latest")\n'
            '    echo \'[{"Id":"sha256:new","Config":{"Labels":null}}]\' ;;\n'
            '  "image inspect sha256:old")\n'
            '    echo \'[{"Id":"sha256:old","Config":{"Labels":null}}]\' ;;\n'
            "esac\n"
        )
        docker.chmod(0o755)
        self.env = {
            **os.environ,
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "FAIL_COMMAND": "",
            "NO_CONTAINERS": "0",
        }
        self.env.pop("CIU_DISCORD_WEBHOOK_URL", None)

    def run_cli(self):
        return subprocess.run(
            [sys.executable, "-m", "src", str(self.root)],
            check=False,
            cwd=self.root,
            env=self.env,
            capture_output=True,
            text=True,
            timeout=15,
        )

    def test_discovery_pull_and_restart_failures_exit_nonzero(self):
        (self.root / "restartable_projects.json").write_text(
            json.dumps([self.root.name])
        )
        for command in ("ps", "config", "inspect", "pull", "up"):
            with self.subTest(command=command):
                self.env["FAIL_COMMAND"] = command
                result = self.run_cli()
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_no_eligible_images_exit_zero(self):
        self.env["NO_CONTAINERS"] = "1"
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_manual_update_exit_zero(self):
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_batch_propagates_real_wrapper_and_cli_failure(self):
        for script in ("wrapper.sh", "update-all.sh"):
            shutil.copy2(ROOT / script, self.root / script)
        (self.root / "venv/bin").mkdir(parents=True)
        (self.root / "venv/bin/activate").touch()
        for name, body in (
            ("pip", "exit 0"),
            ("python3", f'exec {shlex.quote(sys.executable)} "$@"'),
        ):
            path = self.bin / name
            path.write_text(f"#!/bin/sh\n{body}\n")
            path.chmod(0o755)
        projects = self.root / "projects"
        project = projects / "project one"
        project.mkdir(parents=True)
        (project / "compose.yml").write_text("services: {}\n")
        (project / "compose.yaml").write_text("services: {}\n")
        self.env.pop("BASH_ENV", None)
        for failure, expected in (("pull", 1), ("", 0)):
            with self.subTest(failure=failure):
                self.env["FAIL_COMMAND"] = failure
                result = subprocess.run(
                    [str(self.root / "update-all.sh"), "projects", "logs"],
                    check=False,
                    cwd=self.root,
                    env=self.env,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                self.assertEqual(result.returncode, expected, result.stderr)
                self.assertEqual(result.stdout.count("Target directory:"), 1)
