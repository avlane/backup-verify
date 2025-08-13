import os
import tomllib
import unittest

import backup_verify

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class VersionTest(unittest.TestCase):
    def test_package_and_pyproject_agree(self):
        with open(os.path.join(ROOT, "pyproject.toml"), "rb") as fh:
            project = tomllib.load(fh)["project"]
        self.assertEqual(project["version"], backup_verify.__version__)

    def test_changelog_mentions_the_current_version(self):
        with open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8") as fh:
            self.assertIn("## " + backup_verify.__version__, fh.read())
