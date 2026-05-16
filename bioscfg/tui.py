from __future__ import annotations

import curses
import os
from typing import Any

from .display import clip, display_current, display_default, setting_location
from .table import filter_settings

os.environ.setdefault("ESCDELAY", "25")

HEADER_Y = 4
BODY_START_Y = HEADER_Y + 2
BOTTOM_RESERVED_ROWS = 4
MAIN_MAX_H = 34
MAIN_MAX_W = 120


def run_tui(settings: list[dict[str, Any]], summary: dict[str, int], initial_search: str | None = None) -> None:
    curses.wrapper(lambda stdscr: _draw(stdscr, settings, summary, initial_search or ""))


def _draw(stdscr, settings: list[dict[str, Any]], summary: dict[str, int], search: str) -> None:
    curses.curs_set(0)
    stdscr.keypad(True)
    stdscr.timeout(1000)
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_WHITE)
    curses.init_pair(2, curses.COLOR_WHITE, curses.COLOR_BLUE)
    curses.init_pair(3, curses.COLOR_WHITE, curses.COLOR_BLACK)
    curses.init_pair(4, curses.COLOR_BLACK, curses.COLOR_BLACK)
    curses.init_pair(5, curses.COLOR_BLUE, curses.COLOR_WHITE)

    page_id = ("root",)
    row = 0
    offset = 0
    show_missing = True
    show_no_efivar = False

    while True:
        filtered = filter_settings(settings, grep=search or None)
        filtered = _visible_settings(filtered, show_missing, show_no_efivar)
        root, nodes = _build_nav(filtered)
        if page_id not in nodes:
            page_id = ("root",)
            row = 0
            offset = 0
        page = nodes.get(page_id, root)
        rows = _page_rows(page)
        row = min(row, max(0, len(rows) - 1))

        h, w = stdscr.getmaxyx()
        box_h, _, _, _ = _main_box(h, w)
        body_rows = _body_rows(box_h)
        scroll_rows = max(1, body_rows)
        if row < offset:
            offset = row
        if row >= offset + scroll_rows:
            offset = row - scroll_rows + 1

        _paint(
            stdscr,
            page,
            rows,
            row,
            offset,
            body_rows,
            summary,
            search,
            show_missing,
            show_no_efivar,
            len(filtered),
        )

        key = stdscr.getch()
        if key in (ord("q"), ord("Q"), 27):
            return
        if key == curses.KEY_UP:
            row = max(0, row - 1)
        elif key == curses.KEY_DOWN:
            row = min(max(0, len(rows) - 1), row + 1)
        elif key == curses.KEY_PPAGE:
            row = max(0, row - scroll_rows)
        elif key == curses.KEY_NPAGE:
            row = min(max(0, len(rows) - 1), row + scroll_rows)
        elif key == curses.KEY_HOME:
            row = 0
        elif key == curses.KEY_END:
            row = max(0, len(rows) - 1)
        elif key in (curses.KEY_LEFT, curses.KEY_BACKSPACE, 127, 8):
            parent = page.get("parent")
            if parent is not None:
                page_id = parent
                row = 0
                offset = 0
        elif key in (ord("/"), ord("s"), ord("S")):
            search = _prompt(stdscr, "Search", search)
            page_id = ("root",)
            row = 0
            offset = 0
        elif key in (ord("c"), ord("C")):
            search = ""
            page_id = ("root",)
            row = 0
            offset = 0
        elif key in (ord("m"), ord("M")):
            show_missing = not show_missing
            page_id = ("root",)
            row = 0
            offset = 0
        elif key in (ord("e"), ord("E")):
            show_no_efivar = not show_no_efivar
            page_id = ("root",)
            row = 0
            offset = 0
        elif key in (10, 13):
            if rows:
                selected = rows[row]
                if selected["kind"] == "page":
                    page_id = selected["node"]["id"]
                    row = 0
                    offset = 0
                else:
                    _details(stdscr, selected["setting"])


def _paint(
    stdscr,
    page: dict[str, Any],
    rows: list[dict[str, Any]],
    row: int,
    offset: int,
    body_rows: int,
    summary: dict[str, int],
    search: str,
    show_missing: bool,
    show_no_efivar: bool,
    shown_settings: int,
) -> None:
    h, w = stdscr.getmaxyx()
    stdscr.bkgd(" ", curses.color_pair(2))
    stdscr.erase()
    box_h, box_w, box_y, box_x = _main_box(h, w)
    _draw_shadow(stdscr, box_y, box_x, box_h, box_w)
    stdscr.noutrefresh()

    dialog = curses.newwin(box_h, box_w, box_y, box_x)
    dialog.bkgd(" ", curses.color_pair(1))
    dialog.erase()
    _safe_box(dialog)

    title = " bioscfg-view READ ONLY "
    _safe_addnstr(dialog, 0, max(1, (box_w - len(title)) // 2), title, box_w - 2, curses.A_BOLD)
    stats = f"settings {summary.get('total', 0)} | ok {summary.get('ok', 0)} | no efivar {summary.get('missing_efivar', 0)} | shown {shown_settings}"
    _safe_addnstr(dialog, 1, 2, stats, box_w - 4, curses.color_pair(5) | curses.A_BOLD)
    filter_text = f"search: {search or '<none>'} | missing config: {'show' if show_missing else 'hide'} | no efivar: {'show' if show_no_efivar else 'hide'}"
    _safe_addnstr(dialog, 2, 2, filter_text, box_w - 4, curses.color_pair(1))

    header_y = HEADER_Y
    table_w = max(1, box_w - 4)
    page_title = _breadcrumb(page)
    _safe_addnstr(dialog, header_y, 2, page_title, table_w, curses.color_pair(1) | curses.A_BOLD)
    widths = _column_widths(table_w)
    header = _fit_cols(["Page / Setting", "Current", "Default", "Location", "Status"], widths, table_w)
    _safe_addnstr(dialog, header_y + 1, 2, header, table_w, curses.color_pair(1) | curses.A_UNDERLINE)

    for screen_idx in range(body_rows):
        y = BODY_START_Y + screen_idx
        if y >= box_h - BOTTOM_RESERVED_ROWS:
            break
        idx = offset + screen_idx
        if idx >= len(rows):
            break
        line = _nav_row_line(rows[idx], widths, table_w)
        attr = curses.color_pair(3) if idx == row else curses.color_pair(1)
        _safe_addnstr(dialog, y, 2, line.ljust(table_w), table_w, attr)
    _draw_scrollbar(dialog, len(rows), body_rows, offset, box_w - 2)

    detail_y = box_h - 3
    _safe_hline(dialog, detail_y - 1, 1, "-", box_w - 2, curses.color_pair(1))
    if rows:
        selected = rows[row]
        if selected["kind"] == "setting":
            setting = selected["setting"]
            raw = (setting.get("current") or {}).get("raw_hex") or ""
            detail = f"path: {_setting_full_path(setting)} | raw: {raw}"
        else:
            node = selected["node"]
            detail = f"path: {_breadcrumb(node)} | settings: {node['count']} | ok: {node['ok']} | other: {node['count'] - node['ok']}"
    else:
        detail = "empty"
    if detail:
        _safe_addnstr(dialog, detail_y, 2, detail, box_w - 4, curses.color_pair(1))
    controls = "CONTROLS: [Enter] Open | [Left] Up | [/] Search | [C] Clear | [M] Missing | [E] EFI vars | [Q]uit"
    _safe_addnstr(dialog, box_h - 2, 2, controls, box_w - 4, curses.color_pair(1) | curses.A_BOLD)
    mode = " [ READ ONLY MODE ] "
    _safe_addnstr(dialog, box_h - 1, max(1, (box_w - len(mode)) // 2), mode, box_w - 2, curses.A_BOLD)
    dialog.noutrefresh()
    curses.doupdate()


def _visible_settings(
    settings: list[dict[str, Any]],
    show_missing: bool,
    show_no_efivar: bool,
) -> list[dict[str, Any]]:
    visible = settings
    if not show_missing:
        visible = [setting for setting in visible if not _is_missing_config(setting)]
    if not show_no_efivar:
        visible = [setting for setting in visible if not _is_missing_efivar(setting)]
    return visible


def _body_rows(height: int) -> int:
    return max(0, height - BODY_START_Y - BOTTOM_RESERVED_ROWS)


def _main_box(screen_h: int, screen_w: int) -> tuple[int, int, int, int]:
    box_h = min(MAIN_MAX_H, max(1, screen_h - 2))
    box_w = min(MAIN_MAX_W, max(1, screen_w - 4))
    return box_h, box_w, max(0, (screen_h - box_h) // 2), max(0, (screen_w - box_w) // 2)


def _scrollbar_span(total: int, visible: int, offset: int) -> tuple[int, int] | None:
    if visible <= 0 or total <= visible:
        return None
    thumb = max(1, visible * visible // total)
    max_offset = max(1, total - visible)
    travel = max(0, visible - thumb)
    start = (max(0, offset) * travel + max_offset // 2) // max_offset
    return min(start, travel), thumb


def _draw_scrollbar(win, total: int, visible: int, offset: int, x: int) -> None:
    span = _scrollbar_span(total, visible, offset)
    if span is None:
        return
    start, thumb = span
    for idx in range(visible):
        _safe_addnstr(win, BODY_START_Y + idx, x, "|", 1, curses.color_pair(1))
    for idx in range(start, start + thumb):
        _safe_addnstr(win, BODY_START_Y + idx, x, "#", 1, curses.color_pair(3))


def _draw_shadow(stdscr, y: int, x: int, height: int, width: int) -> None:
    shadow_attr = curses.color_pair(4)
    for idx in range(height):
        _safe_addnstr(stdscr, y + idx + 1, x + 2, " " * width, width, shadow_attr)


def _is_missing_efivar(setting: dict[str, Any]) -> bool:
    return (setting.get("current") or {}).get("status") == "missing_efivar"


def _is_missing_config(setting: dict[str, Any]) -> bool:
    status = (setting.get("current") or {}).get("status")
    return status not in (None, "ok", "decoded_unknown_option", "missing_efivar")


def _build_nav(settings: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[tuple[Any, ...], dict[str, Any]]]:
    root = _new_nav_node(("root",), "Data Sources", [], None)
    nodes = {root["id"]: root}
    source_labels = _source_labels(settings)

    for setting in settings:
        source_id = _setting_backing_identity(setting)
        source = _child_nav_node(
            root,
            ("source", source_id),
            source_labels[source_id],
            [],
            nodes,
        )
        _count_nav(root, setting)
        _count_nav(source, setting)

        node = source
        path = _setting_page_path(setting)
        for idx, part in enumerate(path):
            path_prefix = path[:idx + 1]
            node = _child_nav_node(
                node,
                ("path", source_id, path_prefix),
                part,
                path_prefix,
                nodes,
            )
            _count_nav(node, setting)
        node["settings"].append(setting)

    return root, nodes


def _new_nav_node(
    node_id: tuple[Any, ...],
    name: str,
    path: list[str] | tuple[str, ...],
    parent: tuple[Any, ...] | None,
) -> dict[str, Any]:
    return {
        "id": node_id,
        "name": name,
        "path": tuple(path),
        "parent": parent,
        "crumbs": ("Data Sources",) if parent is None else (name,),
        "children": [],
        "children_by_id": {},
        "settings": [],
        "count": 0,
        "ok": 0,
    }


def _child_nav_node(
    parent: dict[str, Any],
    node_id: tuple[Any, ...],
    name: str,
    path: list[str] | tuple[str, ...],
    nodes: dict[tuple[Any, ...], dict[str, Any]],
) -> dict[str, Any]:
    child = parent["children_by_id"].get(node_id)
    if child is None:
        child = _new_nav_node(node_id, name, path, parent["id"])
        child["crumbs"] = (*parent["crumbs"], name) if parent["parent"] is not None else (name,)
        parent["children_by_id"][node_id] = child
        parent["children"].append(child)
        nodes[node_id] = child
    return child


def _count_nav(node: dict[str, Any], setting: dict[str, Any]) -> None:
    node["count"] += 1
    if (setting.get("current") or {}).get("status") == "ok":
        node["ok"] += 1


def _page_rows(page: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [{"kind": "page", "node": child} for child in page["children"]]
    rows.extend({"kind": "setting", "setting": setting} for setting in page["settings"])
    return rows


def _source_labels(settings: list[dict[str, Any]]) -> dict[tuple[str, ...], str]:
    labels: dict[tuple[str, ...], str] = {}
    ids_by_label: dict[str, set[tuple[str, ...]]] = {}
    identities = {_setting_backing_identity(setting) for setting in settings}
    for setting in settings:
        identity = _setting_backing_identity(setting)
        label = _setting_backing_label(setting)
        ids_by_label.setdefault(label, set()).add(identity)

    for setting in settings:
        identity = _setting_backing_identity(setting)
        if identity in labels:
            continue
        label = _setting_backing_label(setting)
        labels[identity] = _setting_backing_badge(setting, include_detail=len(ids_by_label[label]) > 1)
    for identity in identities:
        labels.setdefault(identity, "unknown source")
    return labels


def _setting_page_path(setting: dict[str, Any]) -> tuple[str, ...]:
    return tuple(part for part in (setting.get("path") or []) if part) or ("Unsorted",)


def _setting_backing_identity(setting: dict[str, Any]) -> tuple[str, ...]:
    varstore = setting.get("varstore") or {}
    name = varstore.get("name") or ""
    guid = varstore.get("guid") or ""
    if name or guid:
        return ("varstore", name, guid)
    source = setting.get("source") or {}
    return ("source", source.get("ifr_file") or "")


def _setting_backing_label(setting: dict[str, Any]) -> str:
    varstore = setting.get("varstore") or {}
    return varstore.get("name") or _short_guid(varstore.get("guid")) or "no varstore"


def _setting_backing_badge(setting: dict[str, Any], include_detail: bool = False) -> str:
    varstore = setting.get("varstore") or {}
    label = _setting_backing_label(setting)
    if not include_detail:
        return label
    if varstore.get("guid"):
        return f"{label}:{_short_guid(varstore['guid'])}"
    source = setting.get("source") or {}
    if source.get("ifr_file"):
        return f"{label}:{os.path.basename(source['ifr_file'])}"
    return label


def _short_guid(value: str | None) -> str:
    if not value:
        return ""
    return str(value).split("-", 1)[0]


def _breadcrumb(page: dict[str, Any]) -> str:
    return " > ".join(page.get("crumbs") or ("Data Sources",))


def _nav_row_line(row: dict[str, Any], widths: list[int], width: int) -> str:
    if row["kind"] == "page":
        return _nav_page_line(row["node"], widths, width)
    return _setting_line(row["setting"], widths, width)


def _nav_page_line(page: dict[str, Any], widths: list[int], width: int) -> str:
    cols = [
        clip(f"{page['name']}/", widths[0]),
        clip(f"{page['ok']}/{page['count']}", widths[1]),
        clip("", widths[2]),
        clip("", widths[3]),
        clip("page", widths[4]),
    ]
    return "  ".join(cols)[: max(0, width - 2)]


def _setting_full_path(setting: dict[str, Any]) -> str:
    parts = [_setting_backing_badge(setting, include_detail=True), *_setting_page_path(setting), setting.get("prompt") or ""]
    return " > ".join(part for part in parts if part)


def _setting_line(setting: dict[str, Any], widths: list[int], width: int) -> str:
    prompt = setting.get("prompt") or ""
    current = display_current(setting)
    default = display_default(setting)
    location = setting_location(setting)
    status = (setting.get("current") or {}).get("status", "")
    cols = [
        clip(prompt, widths[0]),
        clip(current, widths[1]),
        clip(default, widths[2]),
        clip(location, widths[3]),
        clip(status, widths[4]),
    ]
    return "  ".join(cols)[: max(0, width - 2)]


def _column_widths(width: int) -> list[int]:
    other = [18, 16, 24, 16] if width >= 92 else [14, 12, 18, 12]
    separators = 2 * len(other)
    label = max(18, width - 2 - sum(other) - separators)
    return [label, *other]


def _fit_cols(cols: list[str], col_widths: list[int], width: int) -> str:
    return "  ".join(clip(text, col_width) for text, col_width in zip(cols, col_widths))[: max(0, width - 2)]


def _safe_addnstr(win, y: int, x: int, value: str, width: int, attr: int = 0) -> None:
    h, w = win.getmaxyx()
    if y < 0 or y >= h or x < 0 or x >= w or width <= 0:
        return
    clipped_width = min(width, w - x)
    if clipped_width <= 0:
        return
    text = str(value).replace("\n", " ")
    try:
        win.addnstr(y, x, text, clipped_width, attr)
    except curses.error:
        pass


def _safe_hline(win, y: int, x: int, ch: str, width: int, attr: int = 0) -> None:
    h, w = win.getmaxyx()
    if y < 0 or y >= h or x < 0 or x >= w or width <= 0:
        return
    try:
        win.hline(y, x, ch, min(width, w - x), attr)
    except curses.error:
        pass


def _safe_box(win) -> None:
    try:
        win.box()
    except curses.error:
        pass


def _prompt(stdscr, title: str, initial: str) -> str:
    h, w = stdscr.getmaxyx()
    pop_w = min(70, max(30, w - 8))
    pop_h = 5
    y = max(0, h // 2 - pop_h // 2)
    x = max(0, w // 2 - pop_w // 2)
    _draw_shadow(stdscr, y, x, pop_h, pop_w)
    stdscr.noutrefresh()
    win = curses.newwin(pop_h, pop_w, y, x)
    win.bkgd(" ", curses.color_pair(1))
    win.keypad(True)
    curses.curs_set(1)
    text = initial
    while True:
        win.erase()
        _safe_box(win)
        _safe_addnstr(win, 0, 2, f" {title} ", pop_w - 4, curses.A_BOLD)
        _safe_addnstr(win, 2, 2, text, pop_w - 4)
        win.noutrefresh()
        curses.doupdate()
        key = win.getch()
        if key in (10, 13):
            curses.curs_set(0)
            return text
        if key in (27,):
            curses.curs_set(0)
            return initial
        if key in (curses.KEY_BACKSPACE, 127, 8):
            text = text[:-1]
        elif 32 <= key <= 126:
            text += chr(key)


def _details(stdscr, setting: dict[str, Any]) -> None:
    h, w = stdscr.getmaxyx()
    pop_w = min(100, max(50, w - 6))
    pop_h = min(18, max(10, h - 4))
    y = max(0, h // 2 - pop_h // 2)
    x = max(0, w // 2 - pop_w // 2)
    _draw_shadow(stdscr, y, x, pop_h, pop_w)
    stdscr.noutrefresh()
    win = curses.newwin(pop_h, pop_w, y, x)
    win.bkgd(" ", curses.color_pair(1))
    lines = _detail_lines(setting)
    top = 0
    while True:
        win.erase()
        _safe_box(win)
        _safe_addnstr(win, 0, 2, " Details ", pop_w - 4, curses.A_BOLD)
        for idx, line in enumerate(lines[top: top + pop_h - 4]):
            _safe_addnstr(win, 2 + idx, 2, line, pop_w - 4)
        _safe_addnstr(win, pop_h - 1, 2, "[Q/Esc] Close | [Up/Down] Scroll", pop_w - 4, curses.A_BOLD)
        win.noutrefresh()
        curses.doupdate()
        key = win.getch()
        if key in (ord("q"), ord("Q"), 27, 10, 13):
            return
        if key == curses.KEY_UP:
            top = max(0, top - 1)
        elif key == curses.KEY_DOWN:
            top = min(max(0, len(lines) - (pop_h - 4)), top + 1)


def _detail_lines(setting: dict[str, Any]) -> list[str]:
    current = setting.get("current") or {}
    varstore = setting.get("varstore") or {}
    lines = [
        f"path: {' > '.join(setting.get('path') or [])}",
        f"setting: {setting.get('prompt') or ''}",
        f"current: {display_current(setting)}",
        f"default: {display_default(setting)}",
        f"status: {current.get('status', '')}",
        f"location: {setting_location(setting)}",
        f"guid: {varstore.get('guid', '')}",
        f"raw: {current.get('raw_hex', '')}",
        f"help: {setting.get('help') or ''}",
    ]
    options = setting.get("options") or []
    if options:
        lines.append("options:")
        for opt in options:
            marker = " default" if opt.get("default") else ""
            lines.append(f"  {opt.get('value')}: {opt.get('label')}{marker}")
    source = setting.get("source") or {}
    location = source.get("line")
    if location is None and source.get("offset") is not None:
        location = f"0x{source['offset']:X}"
    lines.append(f"source: {source.get('ifr_file', '')}:{location or ''}")
    return lines
