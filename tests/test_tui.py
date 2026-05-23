import unittest

from bioscfg.tui import (
    _body_rows,
    _build_nav,
    _column_widths,
    _experimental_distinct_settings,
    _is_must_suppressed,
    _main_box,
    _page_rows,
    _safe_addnstr,
    _scrollbar_span,
    _selection_detail,
    _setting_line,
    _visible_settings,
)


def setting(
    path,
    prompt,
    status="ok",
    varstore="Setup",
    guid="11111111-2222-3333-4444-555555555555",
    offset=0,
    setting_type="oneof",
    size_bits=8,
    visibility=None,
):
    return {
        "path": path,
        "prompt": prompt,
        "type": setting_type,
        "offset": offset,
        "size_bits": size_bits,
        "varstore": {"name": varstore, "guid": guid},
        "current": {"status": status, "available": status == "ok", "decoded": "Auto"},
        "visibility": visibility or {},
    }


class TuiPageTests(unittest.TestCase):
    def test_root_groups_by_data_source(self):
        root, _ = _build_nav([
            setting(["Page A", "Subpage 1"], "Setting 1"),
            setting(["Page B"], "Setting 2", varstore="Store 2"),
            setting(["Page A", "Subpage 2"], "Setting 3"),
        ])
        rows = _page_rows(root)

        self.assertEqual([row["node"]["name"] for row in rows], ["Setup", "Store 2"])
        self.assertEqual(rows[0]["node"]["count"], 2)
        self.assertEqual(rows[1]["node"]["count"], 1)

    def test_drills_down_by_path_levels(self):
        root, _ = _build_nav([
            setting(["Page B", "Subpage 1"], "Setting 1"),
            setting(["Page B", "Subpage 1"], "Setting 2"),
            setting(["Page C"], "Setting 3"),
        ])

        source = _page_rows(root)[0]["node"]
        self.assertEqual([row["node"]["name"] for row in _page_rows(source)], ["Page B", "Page C"])

        page_b = _page_rows(source)[0]["node"]
        self.assertEqual([row["node"]["name"] for row in _page_rows(page_b)], ["Subpage 1"])

        subpage = _page_rows(page_b)[0]["node"]
        self.assertEqual([row["setting"]["prompt"] for row in _page_rows(subpage)], ["Setting 1", "Setting 2"])

    def test_same_path_under_different_sources_stays_separate(self):
        root, _ = _build_nav([
            setting(["Page D"], "Setting 1", status="missing_efivar", varstore="Store B"),
            setting(["Page D"], "Setting 1", varstore="Store A"),
        ])

        sources = [row["node"] for row in _page_rows(root)]
        self.assertEqual([source["name"] for source in sources], ["Store B", "Store A"])
        self.assertEqual(_page_rows(sources[0])[0]["node"]["name"], "Page D")
        self.assertEqual(_page_rows(sources[1])[0]["node"]["name"], "Page D")

    def test_same_varstore_name_with_different_guid_stays_distinguishable(self):
        root, _ = _build_nav([
            setting(["Page F"], "Setting 1", varstore="Shared Store", guid="aaaaaaaa-0000-0000-0000-000000000000"),
            setting(["Page F"], "Setting 1", varstore="Shared Store", guid="bbbbbbbb-0000-0000-0000-000000000000"),
        ])
        rows = _page_rows(root)

        self.assertEqual([row["node"]["name"] for row in rows], [
            "Shared Store:aaaaaaaa",
            "Shared Store:bbbbbbbb",
        ])

    def test_missing_config_and_no_efivar_filters_are_separate(self):
        settings = [
            setting(["Page"], "Ok"),
            setting(["Page"], "No EFI var", status="missing_efivar"),
            setting(["Page"], "Missing config", status="missing_varstore"),
            setting(["Page"], "Unknown option", status="decoded_unknown_option"),
        ]

        def prompts(show_missing=True, show_no_efivar=False):
            visible = _visible_settings(settings, show_missing, show_no_efivar)
            return [item["prompt"] for item in visible]

        self.assertEqual(prompts(), ["Ok", "Missing config", "Unknown option"])
        self.assertEqual(prompts(show_missing=False), ["Ok", "Unknown option"])
        self.assertEqual(
            prompts(show_no_efivar=True),
            ["Ok", "No EFI var", "Missing config", "Unknown option"],
        )
        self.assertEqual(
            prompts(show_missing=False, show_no_efivar=True),
            ["Ok", "No EFI var", "Unknown option"],
        )

    def test_experimental_distinct_mode_groups_by_storage_offset(self):
        settings = [
            setting(["Page A"], "Missing alias", status="missing_efivar", offset=16),
            setting(["Page B"], "Live alias", status="ok", offset=16),
            setting(["Page C"], "Other offset", status="ok", offset=17),
            setting(["Page D"], "No offset A", status="ok", offset=None),
            setting(["Page E"], "No offset B", status="ok", offset=None),
        ]

        distinct = _experimental_distinct_settings(settings)

        self.assertEqual([item["prompt"] for item in distinct], [
            "Live alias",
            "Other offset",
            "No offset A",
            "No offset B",
        ])
        self.assertEqual(distinct[0]["_distinct_alias_count"], 1)
        self.assertIn("Missing alias", distinct[0]["_distinct_aliases"][0])

    def test_experimental_distinct_mode_keeps_different_types_separate(self):
        settings = [
            setting(["Page"], "Numeric", offset=16, setting_type="numeric", size_bits=16),
            setting(["Page"], "OneOf", offset=16, setting_type="oneof", size_bits=8),
        ]

        distinct = _experimental_distinct_settings(settings)

        self.assertEqual([item["prompt"] for item in distinct], ["Numeric", "OneOf"])

    def test_setting_line_starts_with_offset_column(self):
        widths = _column_widths(120)

        line = _setting_line(setting(["Page"], "Offset setting", offset=16), widths, 120)
        no_offset = _setting_line(setting(["Page"], "No offset", offset=None), widths, 120)

        self.assertTrue(line.startswith("0x10"))
        self.assertTrue(no_offset.startswith(" " * widths[0]))

    def test_must_suppressed_setting_is_detected_and_marked(self):
        item = setting(["Page"], "Suppressed", visibility={"always_suppressed": True})

        self.assertTrue(_is_must_suppressed(item))
        self.assertIn("suppressed", _setting_line(item, _column_widths(140), 140))

    def test_selection_detail_uses_setting_name_not_full_path(self):
        item = setting(["Very Long", "Nested", "Path"], "Readable setting")
        item["current"]["raw_hex"] = "0x1234"

        detail = _selection_detail({"kind": "setting", "setting": item})

        self.assertEqual(detail, "setting: Readable setting | raw: 0x1234")

    def test_selection_detail_uses_page_name_not_full_breadcrumb(self):
        root, _ = _build_nav([setting(["Long Parent", "Child"], "Setting")])
        source = _page_rows(root)[0]["node"]
        page = _page_rows(source)[0]["node"]

        detail = _selection_detail({"kind": "page", "node": page})

        self.assertEqual(detail, "page: Long Parent | settings: 1 | ok: 1 | other: 0")

    def test_safe_addnstr_ignores_out_of_bounds_draws(self):
        win = FakeWindow(2, 4)

        _safe_addnstr(win, 1, 2, "abcd", 20)
        _safe_addnstr(win, 3, 0, "nope", 20)
        _safe_addnstr(win, 0, 4, "nope", 20)

        self.assertEqual(win.draws, [(1, 2, "ab")])

    def test_body_rows_match_visible_table_area(self):
        self.assertEqual(_body_rows(24), 14)
        self.assertEqual(_body_rows(12), 2)
        self.assertEqual(_body_rows(10), 0)

    def test_main_box_is_centered_and_capped(self):
        self.assertEqual(_main_box(40, 160), (34, 120, 3, 20))
        self.assertEqual(_main_box(24, 80), (22, 76, 1, 2))

    def test_scrollbar_span_tracks_long_pages(self):
        self.assertIsNone(_scrollbar_span(10, 10, 0))
        self.assertIsNone(_scrollbar_span(20, 0, 0))
        self.assertEqual(_scrollbar_span(20, 10, 0), (0, 5))
        self.assertEqual(_scrollbar_span(20, 10, 5), (3, 5))
        self.assertEqual(_scrollbar_span(20, 10, 10), (5, 5))


class FakeWindow:
    def __init__(self, h, w):
        self.h = h
        self.w = w
        self.draws = []

    def getmaxyx(self):
        return self.h, self.w

    def addnstr(self, y, x, value, width, attr=0):
        if y < 0 or y >= self.h or x < 0 or x >= self.w:
            raise RuntimeError("out of bounds")
        self.draws.append((y, x, str(value)[:width]))


if __name__ == "__main__":
    unittest.main()
