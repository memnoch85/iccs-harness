import json
import tempfile
import unittest
from pathlib import Path

from user_profile import UserProfile


class TestUserProfile(unittest.TestCase):
    def test_missing_profile_loads_empty(self):
        profile = UserProfile.load("/tmp/this-profile-should-not-exist-nancee.json")

        self.assertTrue(profile.is_empty())
        self.assertEqual(profile.format_context(), "")

    def test_profile_formats_stable_facts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "profile.json"
            path.write_text(
                json.dumps(
                    {
                        "name": "Anders",
                        "vehicle": "black Jeep",
                        "project": "NANCEE",
                    }
                ),
                encoding="utf-8",
            )

            profile = UserProfile.load(str(path))
            context = profile.format_context(max_characters=4096)

            self.assertIn("KNOWN USER PROFILE", context)
            self.assertIn("name: Anders", context)
            self.assertIn("vehicle: black Jeep", context)
            self.assertIn("project: NANCEE", context)


if __name__ == "__main__":
    unittest.main()
