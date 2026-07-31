import re
import unittest
from pathlib import Path

import juryrig

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


class VersionTest(unittest.TestCase):
    @unittest.skipUnless(PYPROJECT.is_file(), "running outside the source tree")
    def test_version_matches_pyproject(self):
        # Two hand-maintained copies of the version drift silently and only
        # show up as a mislabelled release; tomllib is 3.11+, so parse by hand.
        declared = re.search(
            r'^version = "([^"]+)"', PYPROJECT.read_text(), re.MULTILINE
        )
        self.assertIsNotNone(declared, "pyproject.toml has no version field")
        self.assertEqual(juryrig.__version__, declared.group(1))


class TypeMarkerTest(unittest.TestCase):
    def test_py_typed_marker_present(self):
        # Without this file, PEP 561 tells type checkers to ignore our hints.
        marker = Path(juryrig.__file__).parent / "py.typed"
        self.assertTrue(marker.is_file(), f"missing PEP 561 marker at {marker}")


class ExportsTest(unittest.TestCase):
    def test_all_names_are_importable(self):
        for name in juryrig.__all__:
            with self.subTest(name=name):
                self.assertTrue(hasattr(juryrig, name))

    def test_all_is_sorted_and_unique(self):
        self.assertEqual(list(juryrig.__all__), sorted(set(juryrig.__all__)))


if __name__ == "__main__":
    unittest.main()
