import unittest
import tempfile
from pathlib import Path

from bioscfg.extract import _contains_hii_package, detect_capsule_header_size, normalize_bios_input


class ExtractTests(unittest.TestCase):
    def test_detects_b650ei_capsule_header(self):
        path = Path("tests/smoking/ROG-STRIX-B650E-I-GAMING-WIFI-ASUS-3854.CAP")
        self.assertEqual(detect_capsule_header_size(path), 0x1000)

    def test_normalizes_b650ei_capsule(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path("tests/smoking/ROG-STRIX-B650E-I-GAMING-WIFI-ASUS-3854.CAP")
            image = normalize_bios_input(path, Path(d))
            self.assertEqual(image.input_format, "uefi-capsule")
            self.assertEqual(image.capsule_header_size, 0x1000)
            self.assertEqual(image.normalized_path.stat().st_size, 0x2000000)

    def test_detects_hii_package_signatures(self):
        form = b"\x08\x00\x00\x02\x0e\x00\x29\x02"
        strings = b"\x3a\x00\x00\x04\x34\x00\x00\x00" + b"\x00" * (0x3A - 10) + b"\x00\x00"
        self.assertTrue(_contains_hii_package(b"xx" + form, 0x02))
        self.assertTrue(_contains_hii_package(b"yy" + strings, 0x04))
        self.assertFalse(_contains_hii_package(b"not hii", 0x02))


if __name__ == "__main__":
    unittest.main()
