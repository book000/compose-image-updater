import unittest
from contextlib import ExitStack
from unittest import mock

from src import DockerCommandError
from src.__main__ import update_images

ID_OLD = "sha256:" + "a" * 64
ID_NEW = "sha256:" + "b" * 64
ID_REDIS = "sha256:" + "c" * 64


def patched(deployed, identities, pull=True):
    """Patch the docker-facing helpers; identities maps an ID or reference to (id, version)."""
    return (
        mock.patch(
            "src.__main__.get_deployed_images",
            return_value=[(ref, ref, image_id) for ref, image_id in deployed],
        ),
        mock.patch(
            "src.__main__.get_service_images",
            return_value={ref: ref for ref, _ in deployed},
        ),
        mock.patch(
            "src.__main__.get_image_identity", side_effect=identities.__getitem__
        ),
        mock.patch("src.__main__.pull_images", return_value=pull),
        mock.patch("src.__main__.pprint"),
    )


def run_update(deployed, identities, pull=True):
    with ExitStack() as stack:
        for patch in patched(deployed, identities, pull):
            stack.enter_context(patch)
        result = update_images("/project")
        return result.versions if result is not None else None


class UpdateImagesTest(unittest.TestCase):
    def test_update_with_different_labels(self):
        result = run_update(
            [("ciutest/x:latest", ID_OLD)],
            {ID_OLD: (ID_OLD, "v1"), "ciutest/x:latest": (ID_NEW, "v2")},
        )
        self.assertEqual(
            result,
            {
                "ciutest/x": {
                    "prev": "v1 (aaaaaaaaaaaa)",
                    "current": "v2 (bbbbbbbbbbbb)",
                }
            },
        )

    def test_update_with_same_label_but_new_image_id(self):
        result = run_update(
            [("ciutest/x:latest", ID_OLD)],
            {ID_OLD: (ID_OLD, "v1"), "ciutest/x:latest": (ID_NEW, "v1")},
        )
        self.assertEqual(
            result,
            {
                "ciutest/x": {
                    "prev": "v1 (aaaaaaaaaaaa)",
                    "current": "v1 (bbbbbbbbbbbb)",
                }
            },
        )

    def test_no_update_when_ids_are_equal(self):
        result = run_update(
            [("ciutest/x:latest", ID_OLD)],
            {ID_OLD: (ID_OLD, "v1"), "ciutest/x:latest": (ID_OLD, "v1")},
        )
        self.assertEqual(result, {})

    def test_deferred_update_is_reported_on_every_run(self):
        # The local latest tag already points to the new image; the container still runs the old one.
        identities = {ID_OLD: (ID_OLD, "v1"), "ciutest/x:latest": (ID_NEW, "v2")}
        expected = {
            "ciutest/x": {"prev": "v1 (aaaaaaaaaaaa)", "current": "v2 (bbbbbbbbbbbb)"}
        }
        for _ in range(2):
            self.assertEqual(
                run_update([("ciutest/x:latest", ID_OLD)], identities), expected
            )

    def test_no_latest_image_returns_none(self):
        result = run_update([("redis:7", ID_REDIS)], {})
        self.assertIsNone(result)

    def test_no_containers_returns_none(self):
        self.assertIsNone(run_update([], {}))

    def test_untracked_images_are_ignored(self):
        result = run_update(
            [("redis:7", ID_REDIS), ("ciutest/x", ID_OLD)],
            {ID_OLD: (ID_OLD, "v1"), "ciutest/x": (ID_NEW, "v2")},
        )
        self.assertEqual(
            result,
            {
                "ciutest/x": {
                    "prev": "v1 (aaaaaaaaaaaa)",
                    "current": "v2 (bbbbbbbbbbbb)",
                }
            },
        )

    def test_first_differing_container_wins_per_repository(self):
        id_older = "sha256:" + "d" * 64
        result = run_update(
            [("ciutest/x:latest", ID_OLD), ("ciutest/x:latest", id_older)],
            {
                ID_OLD: (ID_OLD, "v1"),
                id_older: (id_older, "v0"),
                "ciutest/x:latest": (ID_NEW, "v2"),
            },
        )
        self.assertEqual(
            result,
            {
                "ciutest/x": {
                    "prev": "v1 (aaaaaaaaaaaa)",
                    "current": "v2 (bbbbbbbbbbbb)",
                }
            },
        )

    def test_deployed_image_missing_locally_is_still_reported(self):
        def identity(ref):
            if ref == ID_OLD:
                raise DockerCommandError("Failed to get docker image")
            return {"ciutest/x:latest": (ID_NEW, "v2")}[ref]

        with (
            mock.patch(
                "src.__main__.get_deployed_images",
                return_value=[("web", "ciutest/x:latest", ID_OLD)],
            ),
            mock.patch(
                "src.__main__.get_service_images",
                return_value={"web": "ciutest/x:latest"},
            ),
            mock.patch("src.__main__.get_image_identity", side_effect=identity),
            mock.patch("src.__main__.pull_images", return_value=True),
            mock.patch("src.__main__.pprint"),
        ):
            result = update_images("/project").versions

        self.assertEqual(
            result,
            {
                "ciutest/x": {
                    "prev": "unknown (aaaaaaaaaaaa)",
                    "current": "v2 (bbbbbbbbbbbb)",
                }
            },
        )

    def test_target_lookup_failure_is_not_swallowed(self):
        def identity(ref):
            if ref == ID_OLD:
                return ID_OLD, "v1"
            raise DockerCommandError("Failed to get docker image")

        with (
            mock.patch(
                "src.__main__.get_deployed_images",
                return_value=[("web", "ciutest/x:latest", ID_OLD)],
            ),
            mock.patch(
                "src.__main__.get_service_images",
                return_value={"web": "ciutest/x:latest"},
            ),
            mock.patch("src.__main__.get_image_identity", side_effect=identity),
            mock.patch("src.__main__.pull_images", return_value=True),
            mock.patch("src.__main__.pprint"),
            self.assertRaisesRegex(DockerCommandError, "^Failed to get docker image$"),
        ):
            update_images("/project")

    def test_pull_failure_raises(self):
        with self.assertRaisesRegex(DockerCommandError, "Failed to update images"):
            run_update(
                [("ciutest/x:latest", ID_OLD)],
                {ID_OLD: (ID_OLD, "v1"), "ciutest/x:latest": (ID_NEW, "v2")},
                pull=False,
            )

    def test_docker_error_while_listing_raises(self):
        with (
            mock.patch(
                "src.__main__.get_deployed_images", side_effect=RuntimeError("boom")
            ),
            mock.patch("src.__main__.pull_images") as pull,
            self.assertRaises(DockerCommandError),
        ):
            update_images("/project")
        pull.assert_not_called()


if __name__ == "__main__":
    unittest.main()
