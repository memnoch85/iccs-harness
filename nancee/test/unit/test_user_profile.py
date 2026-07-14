import json
import tempfile
import unittest
from pathlib import Path

from user_profile import UserProfile


class TestUserProfile(unittest.TestCase):
    def test_missing_profile_loads_empty(self):
        profile = UserProfile.load(
            "/tmp/this-profile-should-not-exist-nancee.json"
        )

        self.assertTrue(profile.is_empty())
        self.assertEqual(profile.facts, {})

    def test_profile_loads_structured_facts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"

            expected = {
                "name": "Anders",
                "vehicle": "black Jeep",
                "project": "NANCEE",
            }

            path.write_text(
                json.dumps(expected),
                encoding="utf-8",
            )

            profile = UserProfile.load(str(path))

            self.assertFalse(profile.is_empty())
            self.assertEqual(
                profile.facts,
                expected,
            )

    def test_non_object_profile_is_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"

            path.write_text(
                json.dumps(["not", "an", "object"]),
                encoding="utf-8",
            )

            profile = UserProfile.load(str(path))

            self.assertTrue(profile.is_empty())
            self.assertEqual(profile.facts, {})


if __name__ == "__main__":
    unittest.main()
