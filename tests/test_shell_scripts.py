import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ShellScriptsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.tool = self.root / "tool directory"
        self.tool.mkdir()
        for name in ("wrapper.sh", "update-all.sh", "generate-restartables.sh"):
            shutil.copy2(ROOT / name, self.tool / name)
        self.projects = self.root / "projects"
        self.projects.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.calls = self.root / "calls"
        self.env = {
            **os.environ,
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "INVOCATIONS": str(self.calls),
        }

        self.env.pop("BASH_ENV", None)

    def executable(self, path, text):
        path.write_text(text)
        path.chmod(0o755)

    def mock_wrapper(self):
        self.executable(
            self.tool / "wrapper.sh",
            '#!/bin/bash\nprintf "%s\\0" "$#" "$@" >> "$INVOCATIONS"\n'
            'echo "checked: $1"\n'
            'if [[ "$1" == */a-fails ]]; then exit 7; fi\n',
        )

    def project(self, name, files=("compose.yml",)):
        path = self.projects / name
        path.mkdir(parents=True, exist_ok=True)
        for filename in files:
            (path / filename).write_text("services: {}\n")
        return path

    def run_script(self, name, *args):
        return subprocess.run(
            [str(self.tool / name), *map(str, args)],
            check=False,
            cwd=self.root,
            env=self.env,
            capture_output=True,
            text=True,
            timeout=15,
        )

    def invocations(self):
        return self.calls.read_bytes().decode().split("\0")[:-1]

    def test_batch_preserves_paths_and_deduplicates_directories(self):
        self.mock_wrapper()
        names = ["project one", "quotes'\"", "tab\tproject", "line\nproject\n"]
        paths = [
            self.project(name, ("compose.yml", "compose.yaml", "docker-compose.yml"))
            for name in names
        ]
        (self.projects / "compose.yml").write_text("services: {}\n")
        result = self.run_script("update-all.sh", "projects", "relative logs")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.invocations()
        self.assertEqual(calls[::2], ["1"] * (len(paths) + 1))
        self.assertCountEqual(calls[1::2], list(map(str, [self.projects, *paths])))
        self.assertEqual(len(list((self.root / "relative logs").glob("*.log"))), 1)

    def test_empty_batch_never_invokes_wrapper(self):
        self.mock_wrapper()
        result = self.run_script("update-all.sh", self.projects, "logs")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertFalse(self.calls.exists())

    def test_batch_keeps_processing_and_propagates_failure_through_tee(self):
        self.mock_wrapper()
        paths = [self.project(name) for name in ("a-fails", "z-succeeds")]
        result = self.run_script("update-all.sh", self.projects, "logs")
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertEqual(self.invocations()[1::2], list(map(str, paths)))
        log = next((self.root / "logs").glob("*.log")).read_text()
        for path in paths:
            self.assertIn(f"checked: {path}", log)

    def test_logging_failure_fails_batch(self):
        self.mock_wrapper()
        self.executable(self.bin / "tee", "#!/bin/sh\ncat >/dev/null\nexit 8\n")
        result = self.run_script("update-all.sh", self.projects, "logs")
        self.assertEqual(result.returncode, 8)

    def test_generator_preserves_names_and_deduplicates(self):
        names = ["project one", "quotes'\"", "tab\tproject", "line\nproject\n"]
        for name in names:
            self.project(name, ("compose.yml", "compose.yaml"))
        self.project("projects")
        (self.projects / "compose.yml").write_text("services: {}\n")
        target = self.tool / "restartable_projects.json"
        target.write_text('["old"]\n')
        result = self.run_script("generate-restartables.sh", "projects")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertCountEqual(json.loads(target.read_text()), [*names, "projects"])
        self.assertIn("old", result.stdout)

    def test_empty_generator_writes_empty_array_without_errors(self):
        result = self.run_script("generate-restartables.sh", self.projects)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(
            json.loads((self.tool / "restartable_projects.json").read_text()), []
        )

    def test_failed_discovery_never_runs_or_overwrites_results(self):
        self.mock_wrapper()
        self.executable(self.bin / "find", "#!/bin/sh\nexit 9\n")
        target = self.tool / "restartable_projects.json"
        target.write_text('["keep"]\n')
        for script, args in (
            ("update-all.sh", (self.projects, "logs")),
            ("generate-restartables.sh", (self.projects,)),
        ):
            with self.subTest(script=script):
                result = self.run_script(script, *args)
                self.assertEqual(result.returncode, 9, result.stderr)
        self.assertFalse(self.calls.exists())
        self.assertEqual(json.loads(target.read_text()), ["keep"])

    def prepare_wrapper(self):
        (self.tool / "venv/bin").mkdir(parents=True)
        (self.tool / "venv/bin/activate").touch()
        self.executable(self.bin / "pip", "#!/bin/sh\nexit 0\n")
        self.executable(
            self.bin / "python3",
            '#!/bin/sh\nprintf "%s\\0" "$@" > "$INVOCATIONS"\n'
            'exit "${PYTHON_STATUS:-0}"\n',
        )

    def test_wrapper_resolves_relative_path_before_changing_directory(self):
        self.prepare_wrapper()
        path = self.project("project one\n")
        result = self.run_script("wrapper.sh", path.relative_to(self.root))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.invocations(), ["-m", "src", str(path)])

    def test_wrapper_defaults_to_callers_directory(self):
        self.prepare_wrapper()
        result = self.run_script("wrapper.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.invocations(), ["-m", "src", str(self.root)])

    def test_wrapper_propagates_python_failure(self):
        self.prepare_wrapper()
        self.env["PYTHON_STATUS"] = "7"
        result = self.run_script("wrapper.sh", self.projects)
        self.assertEqual(result.returncode, 7, result.stderr)

    def test_invalid_arguments_fail_before_invoking_python(self):
        self.prepare_wrapper()
        for script, args in (
            ("wrapper.sh", ("one", "two")),
            ("wrapper.sh", ("missing",)),
            ("wrapper.sh", ("",)),
            ("update-all.sh", ()),
            ("update-all.sh", ("projects",)),
            ("update-all.sh", ("projects", "")),
            ("generate-restartables.sh", ()),
            ("generate-restartables.sh", ("projects", "extra")),
        ):
            with self.subTest(script=script, args=args):
                result = self.run_script(script, *args)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.calls.exists())

    def test_discovery_includes_symlinked_compose_files(self):
        self.mock_wrapper()
        project = self.projects / "linked project"
        project.mkdir()
        target = self.root / "shared-compose.yml"
        target.write_text("services: {}\n")
        (project / "compose.yml").symlink_to(target)
        batch = self.run_script("update-all.sh", self.projects, "logs")
        self.assertEqual(batch.returncode, 0, batch.stderr)
        self.assertEqual(self.invocations(), ["1", str(project)])
        generator = self.run_script("generate-restartables.sh", self.projects)
        self.assertEqual(generator.returncode, 0, generator.stderr)
        self.assertEqual(
            json.loads((self.tool / "restartable_projects.json").read_text()),
            [project.name],
        )

    def test_failed_json_generation_preserves_existing_file(self):
        self.project("project one")
        self.executable(self.bin / "jq", "#!/bin/sh\nexit 6\n")
        target = self.tool / "restartable_projects.json"
        target.write_text('["keep"]\n')
        result = self.run_script("generate-restartables.sh", self.projects)
        self.assertEqual(result.returncode, 6, result.stderr)
        self.assertEqual(json.loads(target.read_text()), ["keep"])
