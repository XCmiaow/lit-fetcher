"""Zotero 操作模块 — 导入、PDF下载、分类、状态"""

import json, re, time, uuid
from typing import List, Dict, Optional
import requests

ZOTERO = "http://127.0.0.1:23119"
SYSTEM_TAGS = {
    "Process_Simulation": ["aspen plus", "process simulation", "process systems engineering", "flowsheet"],
    "Distillation": ["distillation", "dividing wall", "pressure swing", "radfrac", "reactive distill", "extractive distill"],
    "Optimization": ["optimiz", "sensitivity analysis", "control scheme", "surrogate model", "machine learning"],
    "Energy": ["energy", "sustainability", "life cycle", "techno-economic", "biofuel", "carbon capture", "hydrogen"],
    "Organic_Chemistry": ["photocatalytic", "phosphonium", "alkyl radical", "ylide", "visible light", "photoredox"],
    "Review": ["review", "overview", "recent advances"],
}


def import_to_zotero(dois: Optional[str] = None, file_path: Optional[str] = None) -> int:
    """导入文献到 Zotero（通过 Connector API）"""
    if not _zotero_online():
        raise RuntimeError("Zotero is not running. Start Zotero and try again.")

    doi_list = []
    if dois:
        doi_list = [d.strip() for d in dois.split(",") if d.strip()]
    elif file_path:
        with open(file_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    m = re.search(r"10\.\d{4,}[^\s]*", line)
                    doi_list.append(m.group(0) if m else line)
    if not doi_list:
        return 0

    items = []
    for doi in doi_list:
        # Fetch BibTeX from doi.org
        bibtex = _fetch_bibtex(doi)
        if bibtex:
            items.append(bibtex)

    if items:
        count = _push_to_zotero(items)
        return count
    return 0


def trigger_find_fulltext():
    """通过 UI 自动化触发 Zotero 查找全文"""
    import ctypes
    from ctypes import wintypes
    import pyautogui

    user32 = ctypes.windll.user32
    hwnd = None

    def cb(h, _):
        nonlocal hwnd
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(h, buf, 256)
        if "Zotero" in buf.value and not hwnd:
            hwnd = h
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(cb), 0)

    if not hwnd:
        raise RuntimeError("Zotero window not found")

    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    cx, cy = rect.left + int(w * 0.45), rect.top + int(h * 0.3)

    user32.SetForegroundWindow(hwnd)
    time.sleep(0.4)
    pyautogui.click(cx, cy)
    time.sleep(0.2)
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.2)
    pyautogui.rightClick(cx, cy)
    time.sleep(0.6)
    pyautogui.press("f")
    time.sleep(0.3)
    pyautogui.press("enter")


def classify_library():
    """自动分类 + 去重 Zotero 文献库"""
    if not _zotero_online():
        raise RuntimeError("Zotero is not running")

    items = requests.get(f"{ZOTERO}/api/users/0/items?limit=200").json()
    papers = [i for i in items if i["data"].get("itemType") not in ("attachment", "note")]

    # Dedup
    doi_groups = {}
    for p in papers:
        doi = p["data"].get("DOI", "")
        if doi:
            doi_groups.setdefault(doi, []).append(p)

    removed = 0
    for doi, dups in doi_groups.items():
        if len(dups) > 1:
            for dup in dups[1:]:
                try:
                    requests.delete(f"{ZOTERO}/api/users/0/items/{dup['key']}", timeout=5)
                    removed += 1
                except:
                    pass

    # Classify and print tags
    print(f"Papers: {len(papers)}, Duplicates removed: {removed}")
    print(f"\nClassification:\n")
    for p in papers:
        title = (p["data"].get("title") or "").lower()
        journal = (p["data"].get("publicationTitle") or "").lower()
        text = title + " " + journal
        tags = [tag for tag, keywords in SYSTEM_TAGS.items() if any(kw in text for kw in keywords)]
        has_pdf = any(
            a["data"].get("itemType") == "attachment" and a["data"].get("parentItem") == p["key"]
            for a in items
        )
        pdf_icon = "[PDF]" if has_pdf else "[---]"
        tag_str = ", ".join(tags) if tags else "Other"
        print(f"  {pdf_icon} [{tag_str}] {p['data'].get('title', '?')[:65]}")


def show_status():
    """显示 Zotero 文献库状态"""
    if not _zotero_online():
        print("Zotero is NOT running.")
        return

    items = requests.get(f"{ZOTERO}/api/users/0/items?limit=200").json()
    papers = [i for i in items if i["data"].get("itemType") not in ("attachment", "note")]
    with_pdf = sum(
        1 for p in papers
        if any(a["data"].get("itemType") == "attachment" and a["data"].get("parentItem") == p["key"] for a in items)
    )
    cols = requests.get(f"{ZOTERO}/api/users/0/collections").json()
    print(f"Total papers: {len(papers)}")
    print(f"With PDF:     {with_pdf}")
    print(f"Without PDF:  {len(papers) - with_pdf}")
    print(f"Collections:  {len(cols)}")


# ── 内部辅助 ──

def _zotero_online() -> bool:
    try:
        r = requests.get(f"{ZOTERO}/connector/ping", timeout=3)
        return r.status_code == 200 and "Zotero" in r.text
    except:
        return False


def _fetch_bibtex(doi: str) -> Optional[str]:
    for base in [f"https://doi.org/{doi}", f"https://data.crossref.org/{doi}"]:
        try:
            r = requests.get(base, headers={"Accept": "application/x-bibtex"}, timeout=15)
            if r.status_code == 200 and "<!DOCTYPE" not in r.text[:100]:
                return r.text
        except:
            continue
    return None


def _push_to_zotero(bibtex_items: List[str]) -> int:
    session_id = f"lit-fetcher-{int(time.time())}-{uuid.uuid4().hex[:6]}"
    combined = "\n".join(bibtex_items)
    r = requests.post(
        f"{ZOTERO}/connector/import?session={session_id}",
        data=combined.encode("utf-8"),
        headers={"Content-Type": "application/x-bibtex"},
        timeout=30,
    )
    if r.status_code in (200, 201):
        try:
            return len(r.json())
        except:
            return len(bibtex_items)
    return 0
