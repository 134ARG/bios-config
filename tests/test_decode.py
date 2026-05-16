import unittest
from pathlib import Path

from bioscfg.decode import decode_setting
from bioscfg.model import Efivar


class DecodeTests(unittest.TestCase):
    def test_decode_oneof(self):
        setting = {
            "type": "oneof",
            "varstore": {
                "name": "AmdSetup",
                "guid": "3a997502-647a-4c82-998e-52ef9486a247",
            },
            "offset": 0x24,
            "size_bits": 8,
            "options": [
                {"value": 0, "label": "Disabled"},
                {"value": 1, "label": "Auto"},
            ],
        }
        data = bytearray(0x30)
        data[0x24] = 1
        ev = Efivar("AmdSetup", "3a997502-647a-4c82-998e-52ef9486a247", 7, bytes(data), Path("AmdSetup"))
        current = decode_setting(setting, {("AmdSetup", ev.guid): ev})
        self.assertEqual(current["status"], "ok")
        self.assertEqual(current["decoded"], "Auto")

    def test_decode_utf16_string(self):
        setting = {
            "type": "string",
            "varstore": {
                "name": "OCMR",
                "guid": "9f0c8d2f-0000-0000-0000-000000000000",
            },
            "offset": 4,
            "max_size": 8,
        }
        data = b"\x00" * 4 + "Auto".encode("utf-16le") + b"\x00\x00" + b"\xff" * 8
        ev = Efivar("OCMR", "9f0c8d2f-0000-0000-0000-000000000000", 7, data, Path("OCMR"))
        current = decode_setting(setting, {("OCMR", ev.guid): ev})
        self.assertEqual(current["status"], "ok")
        self.assertEqual(current["decoded"], "Auto")


if __name__ == "__main__":
    unittest.main()
