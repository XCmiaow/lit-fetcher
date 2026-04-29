"""PDF 对照翻译 — 调用 pdf2zh 生成双语 PDF，挂载到 Zotero

用法: lit-fetcher translate [ZOTERO_ITEM_KEY]"""

import hashlib
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Optional

import requests

# ── Zotero profile auto-detection ──

def _find_zotero_storage() -> Path:
    """Auto-detect Zotero storage directory, or from env override"""
    env = os.environ.get("ZOTERO_STORAGE")
    if env:
        return Path(env)

    profiles = Path(os.path.expandvars(r"%APPDATA%\Zotero\Zotero\Profiles"))
    if not profiles.exists():
        raise FileNotFoundError(f"Zotero profiles not found: {profiles}")

    defaults = sorted(profiles.glob("*.default*"))
    if not defaults:
        raise FileNotFoundError(f"No default profile in: {profiles}")

    storage = defaults[0] / "storage"
    if not storage.exists():
        raise FileNotFoundError(f"No storage in profile: {defaults[0]}")
    return storage


ZOTERO_STORAGE = _find_zotero_storage()


def find_pdf_for_item(item_key: str) -> Path:
    """Find the PDF file for a Zotero item"""
    item_dir = ZOTERO_STORAGE / item_key
    if not item_dir.exists():
        raise FileNotFoundError(f"Zotero item dir not found: {item_dir}")
    for f in item_dir.glob("*.pdf"):
        # Skip already-translated files
        if "translated" not in f.name and "-dual" not in f.name and "-zh" not in f.name:
            return f
    raise FileNotFoundError(f"No untranslated PDF in: {item_dir}")


def _run_pdf2zh(pdf_path: Path, output_dir: Path) -> Path:
    """Run pdf2zh to produce a bilingual PDF. Returns path to *-dual.pdf."""
    cmd = [
        "pdf2zh", str(pdf_path),
        "-lo", "zh-CN",
        "-s", "google",
    ]
    result = subprocess.run(
        cmd,
        cwd=str(output_dir),
        capture_output=True,
        text=True,
        timeout=600,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pdf2zh failed:\n{result.stderr}")

    stem = pdf_path.stem
    dual = output_dir / f"{stem}-dual.pdf"
    if dual.exists():
        return dual
    # fallback: pdf2zh might produce a different naming pattern
    candidates = sorted(output_dir.glob(f"{stem}*-dual*.pdf"))
    if candidates:
        return candidates[0]
    raise FileNotFoundError(f"pdf2zh output not found for: {stem}")


def _attach_to_zotero(item_key: str, pdf_path: Path, parent_title: str = ""):
    """Register translated PDF as attachment to Zotero item.

    Strategy: try Zotero Web API first (needs API key), else save file locally
    and instruct user. The dual PDF is already in the Zotero storage directory.
    """
    local_api = "http://127.0.0.1:23119/api/users/0"
    try:
        items = requests.get(f"{local_api}/items?limit=200", timeout=10).json()
    except requests.RequestException:
        print(f"  Zotero not reachable. File saved at: {pdf_path}")
        return

    # Check if already attached (look for dual-pdf child attachment)
    for item in items:
        data = item.get("data", {})
        if data.get("itemType") == "attachment":
            if data.get("parentItem") == item_key and "dual" in (data.get("title") or "").lower():
                print(f"  Already attached: [{item_key}]")
                return

    api_key = os.environ.get("ZOTERO_API_KEY", "")
    library_id = _detect_library_id(items)

    if api_key and library_id:
        _attach_via_web_api(item_key, pdf_path, parent_title, api_key, library_id)
    else:
        # Fallback: file already in storage dir, user can add manually
        print(f"  Translated PDF ready: {pdf_path.name}")
        print(f"  To attach in Zotero: right-click [{item_key}] → Add Attachment →")
        print(f"  Attach Stored Copy of File → select '{pdf_path.name}'")
        print(f"  (Set ZOTERO_API_KEY env var for automatic attachment)")


def _detect_library_id(items: list) -> str:
    """Extract library user ID from Zotero API response"""
    for item in items:
        lib = item.get("library", {})
        uid = lib.get("id")
        if uid:
            return str(uid)
    return ""


def _attach_via_web_api(
    item_key: str, pdf_path: Path, parent_title: str,
    api_key: str, library_id: str,
):
    """Create attachment via Zotero Web API (api.zotero.org)"""
    import base64

    # 1. Upload file to Zotero
    filename = pdf_path.name
    content = pdf_path.read_bytes()
    md5 = hashlib.md5(content).hexdigest()
    mtime = int(pdf_path.stat().st_mtime * 1000)
    content_b64 = base64.b64encode(content).decode()

    upload_url = (
        f"https://api.zotero.org/users/{library_id}/items/{item_key}/children"
    )
    headers = {
        "Zotero-API-Key": api_key,
        "Content-Type": "application/json",
    }
    payload = [{
        "itemType": "attachment",
        "parentItem": item_key,
        "title": "CN Translation (zh-CN)",
        "contentType": "application/pdf",
        "filename": filename,
        "md5": md5,
        "mtime": mtime,
        "note": f"Bilingual Chinese translation via pdf2zh",
        "tags": [{"tag": "translated"}, {"tag": "zh-CN"}],
        "linkMode": "imported_file",
    }]

    try:
        r = requests.post(upload_url, json=payload, headers=headers, timeout=30)
        if r.status_code in (200, 201):
            print(f"  Attached to Zotero [{item_key}]")
        else:
            print(f"  Web API error ({r.status_code}): {r.text[:150]}")
    except requests.RequestException as e:
        print(f"  Web API unreachable: {e}")


def translate_pdf(item_key: str) -> Path:
    """Translate a Zotero PDF via pdf2zh and attach bilingual version"""
    pdf_path = find_pdf_for_item(item_key)

    # Check cache
    cache_key = hashlib.md5(pdf_path.read_bytes()).hexdigest()[:12]
    dual_path = ZOTERO_STORAGE / item_key / f"translated_{cache_key}-dual.pdf"
    if dual_path.exists():
        print(f"  Already translated: {dual_path.name}")
        _attach_to_zotero(item_key, dual_path, pdf_path.stem)
        return dual_path

    print(f"  Source: {pdf_path.name}")
    print(f"  Translating with pdf2zh (this may take several minutes)...")
    t0 = time.time()

    # Run pdf2zh in the item's storage directory
    item_dir = ZOTERO_STORAGE / item_key
    result = _run_pdf2zh(pdf_path, item_dir)

    elapsed = time.time() - t0
    print(f"  Done in {elapsed:.0f}s")

    # Rename to cache-friendly name
    final = item_dir / f"translated_{cache_key}-dual.pdf"
    if result != final:
        result.rename(final)

    # Clean up the zh-only version if present
    zh_only = item_dir / f"{pdf_path.stem}-zh.pdf"
    if zh_only.exists():
        zh_only.unlink()

    # Remove original pdf2zh output files (*-dual.pdf) if not renamed
    orig_dual = item_dir / f"{pdf_path.stem}-dual.pdf"
    if orig_dual.exists() and orig_dual != final:
        orig_dual.unlink()

    print(f"  Saved: {final.name}")
    _attach_to_zotero(item_key, final, pdf_path.stem)
    return final


def translate_all():
    """Translate all PDFs in Zotero that haven't been translated yet"""
    api = "http://127.0.0.1:23119/api/users/0"
    try:
        items = requests.get(f"{api}/items?limit=500", timeout=10).json()
    except requests.RequestException:
        print("Zotero is not running or Connector API not available.")
        return

    # Find papers with PDFs but without translated attachments
    papers = []
    for i in items:
        data = i.get("data", {})
        if data.get("itemType") in ("attachment", "note"):
            continue
        key = i["key"]
        has_translated = any(
            a.get("data", {}).get("itemType") == "attachment"
            and a["data"].get("parentItem") == key
            and "dual" in (a["data"].get("title") or "").lower()
            for a in items
        )
        has_pdf = any(
            a.get("data", {}).get("itemType") == "attachment"
            and a["data"].get("parentItem") == key
            for a in items
        )
        if has_pdf and not has_translated:
            papers.append((key, data.get("title", "?")))

    if not papers:
        print("All papers with PDFs already translated.")
        return

    print(f"Papers to translate: {len(papers)}\n")
    for i, (key, title) in enumerate(papers, 1):
        print(f"[{i}/{len(papers)}] {title[:70]}")
        try:
            translate_pdf(key)
        except Exception as e:
            print(f"  Error: {e}")
        print()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="PDF 对照翻译：调用 pdf2zh 生成双语 PDF")
    parser.add_argument("key", nargs="?", help="Zotero item key")
    parser.add_argument("--all", action="store_true", help="Translate all PDFs in library")
    args = parser.parse_args()

    if args.all:
        translate_all()
    elif args.key:
        translate_pdf(args.key)
    else:
        parser.print_help()
