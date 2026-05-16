import tempfile
import unittest
from pathlib import Path

from bioscfg.efivarfs import load_efivarfs, split_efivar_name


class EfivarfsTests(unittest.TestCase):
    def test_split_efivar_name(self):
        self.assertEqual(
            split_efivar_name("AmdSetup-3a997502-647a-4c82-998e-52ef9486a247"),
            ("AmdSetup", "3a997502-647a-4c82-998e-52ef9486a247"),
        )

    def test_load_efivarfs_strips_attributes(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            p = root / "AmdSetup-3a997502-647a-4c82-998e-52ef9486a247"
            p.write_bytes((7).to_bytes(4, "little") + b"\x00\x01\x02")
            ev = load_efivarfs(root)[("AmdSetup", "3a997502-647a-4c82-998e-52ef9486a247")]
            self.assertEqual(ev.attributes, 7)
            self.assertEqual(ev.data, b"\x00\x01\x02")


if __name__ == "__main__":
    unittest.main()
