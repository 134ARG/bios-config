import unittest

from bioscfg.tui import (
    _body_rows,
    _build_nav,
    _main_box,
    _page_rows,
    _safe_addnstr,
    _scrollbar_span,
    _visible_settings,
)


def setting(path, prompt, status="ok", varstore="Setup", guid="11111111-2222-3333-4444-555555555555"):
    return {
        "path": path,
        "prompt": prompt,
        "varstore": {"name": varstore, "guid": guid},
        "current": {"status": status, "available": status == "ok", "decoded": "Auto"},
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
