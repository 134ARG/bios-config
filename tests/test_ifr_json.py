import json
import tempfile
import unittest
from pathlib import Path

from bioscfg.ifr_json import parse_ifr_file


class IfrJsonTests(unittest.TestCase):
    def test_parse_basic_ifr_json(self):
        with tempfile.TemporaryDirectory() as d:
            ifr = Path(d) / "sample.0.1.en-US.uefi.ifr.json"
            ifr.write_text(json.dumps({
                "operations": [
                    {
                        "opcode": "FormSet",
                        "scope_start": True,
                        "depth": 0,
                        "fields": {
                            "guid": "11111111-2222-3333-4444-555555555555",
                            "title": {"id": 1, "text": "AMD CBS"},
                            "help": {"id": 0, "text": ""},
                        },
                    },
                    {
                        "opcode": "Form",
                        "scope_start": True,
                        "depth": 1,
                        "fields": {
                            "form_id": 1,
                            "title": {"id": 2, "text": "Zen Common Options"},
                        },
                    },
                    {
                        "opcode": "VarStore",
                        "scope_start": False,
                        "depth": 2,
                        "fields": {
                            "kind": "buffer",
                            "guid": "3A997502-647A-4C82-998E-52EF9486A247",
                            "varstore_id": 0x5000,
                            "size": 0x100,
                            "name": "AmdSetup",
                        },
                    },
                    {
                        "opcode": "OneOf",
                        "scope_start": True,
                        "depth": 2,
                        "offset": 0x40,
                        "fields": {
                            "kind": "oneof",
                            "prompt": {"id": 3, "text": "Core Performance Boost"},
                            "help": {"id": 4, "text": "Disable CPB"},
                            "question_id": 1,
                            "question_flags": 0x10,
                            "varstore_id": 0x5000,
                            "var_offset": 0x24,
                            "flags": 0x10,
                            "min_max_step": {"size_bits": 8, "min": 0, "max": 1, "step": 0},
                        },
                    },
                    {
                        "opcode": "OneOfOption",
                        "scope_start": False,
                        "depth": 3,
                        "fields": {
                            "option": {"id": 5, "text": "Disabled"},
                            "value": {"type": "u8", "value": 0},
                            "default": True,
                        },
                    },
                    {
                        "opcode": "OneOfOption",
                        "scope_start": False,
                        "depth": 3,
                        "fields": {
                            "option": {"id": 6, "text": "Auto"},
                            "value": {"type": "u8", "value": 1},
                        },
                    },
                    {"opcode": "End", "scope_start": False, "depth": 2, "fields": {}},
                    {"opcode": "End", "scope_start": False, "depth": 1, "fields": {}},
                ]
            }))
            parsed = parse_ifr_file(ifr)
            setting = parsed["settings"][0]
            self.assertEqual(setting["prompt"], "Core Performance Boost")
            self.assertEqual(setting["varstore"]["name"], "AmdSetup")
            self.assertEqual(setting["offset"], 0x24)
            self.assertEqual(setting["options"][1]["label"], "Auto")

    def test_marks_suppress_if_true_as_always_suppressed(self):
        with tempfile.TemporaryDirectory() as d:
            ifr = Path(d) / "sample.ifr.json"
            ifr.write_text(json.dumps({
                "operations": [
                    {
                        "opcode": "FormSet",
                        "scope_start": True,
                        "depth": 0,
                        "fields": {"guid": "11111111-2222-3333-4444-555555555555", "title": {"text": "Setup"}},
                    },
                    {
                        "opcode": "Form",
                        "scope_start": True,
                        "depth": 1,
                        "fields": {"form_id": 1, "title": {"text": "PBO"}},
                    },
                    {
                        "opcode": "VarStore",
                        "scope_start": False,
                        "depth": 2,
                        "fields": {
                            "kind": "buffer",
                            "guid": "3A997502-647A-4C82-998E-52EF9486A247",
                            "varstore_id": 1,
                            "size": 0x100,
                            "name": "Setup",
                        },
                    },
                    {"opcode": "SuppressIf", "scope_start": True, "depth": 2, "fields": {}},
                    {"opcode": "True", "scope_start": False, "depth": 3, "fields": {}},
                    {
                        "opcode": "Numeric",
                        "scope_start": True,
                        "depth": 3,
                        "fields": {
                            "kind": "numeric",
                            "prompt": {"text": "Hidden PPT Limit"},
                            "varstore_id": 1,
                            "var_offset": 0x46E,
                            "min_max_step": {"size_bits": 32, "min": 0, "max": 65535, "step": 1},
                        },
                    },
                ]
            }))

            setting = parse_ifr_file(ifr)["settings"][0]

            self.assertTrue(setting["visibility"]["has_suppress_if"])
            self.assertTrue(setting["visibility"]["always_suppressed"])


if __name__ == "__main__":
    unittest.main()
