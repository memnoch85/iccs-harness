from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / "sherpa" / "config.py").read_text(encoding="utf-8")


class MemoryDebugBooleanV41Tests(unittest.TestCase):
    def test_memory_debug_is_disabled_by_default_and_enabled_by_true(self):
        block_match = re.search(
            r"MEMORY_DEBUG_ENABLED\s*=\s*\([\s\S]*?NANCEE_MEMORY_DEBUG[\s\S]*?\n\)",
            SOURCE,
        )
        self.assertIsNotNone(block_match)
        block = block_match.group(0)
        self.assertIn('"false"', block)
        self.assertRegex(block, r'\.lower\(\)\s*\n?\s*==\s*"true"')
        self.assertNotRegex(block, r'==\s*"false"')


if __name__ == "__main__":
    unittest.main()
