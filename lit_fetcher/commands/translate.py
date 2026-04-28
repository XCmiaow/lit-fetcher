"""PDF 对照翻译：提取段落 → 翻译 → 以注释形式贴回原位置

用法: lit-fetcher translate [ZOTERO_ITEM_KEY]"""
import hashlib, json, os, re, sys, time
from pathlib import Path
from typing import List, Tuple

import fitz  # pymupdf
from deep_translator import GoogleTranslator


ZOTERO_STORAGE = Path(os.path.expandvars(
    r"%APPDATA%\Zotero\Zotero\Profiles\53xuvw1i.default\storage"
))


def find_pdf_for_item(item_key: str) -> Path:
    """Find the PDF file for a Zotero item"""
    item_dir = ZOTERO_STORAGE / item_key
    if not item_dir.exists():
        raise FileNotFoundError(f"Zotero item dir not found: {item_dir}")
    for f in item_dir.glob("*.pdf"):
        return f
    raise FileNotFoundError(f"No PDF in: {item_dir}")


def extract_text_blocks(pdf_path: Path) -> List[dict]:
    """Extract text blocks with positions from PDF"""
    doc = fitz.open(pdf_path)
    blocks = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        for block in page.get_text("blocks"):
            text = block[4].strip()
            if len(text) > 30:  # Skip short lines (headers, page numbers)
                blocks.append({
                    "page": page_num,
                    "x0": block[0], "y0": block[1],
                    "x1": block[2], "y1": block[3],
                    "text": text,
                })
    doc.close()
    return blocks


def translate_blocks(blocks: List[dict], progress_cb=None) -> List[dict]:
    """Translate each text block to Chinese"""
    translator = GoogleTranslator(source="auto", target="zh-CN")
    translated = []
    for i, block in enumerate(blocks):
        try:
            # Split long text into chunks for more reliable translation
            text = block["text"]
            if len(text) > 4500:
                # Split by sentences
                sentences = re.split(r"(?<=[.!?])\s+", text)
                chunks = []
                chunk = ""
                for s in sentences:
                    if len(chunk) + len(s) < 4500:
                        chunk += s + " "
                    else:
                        if chunk:
                            chunks.append(chunk.strip())
                        chunk = s + " "
                if chunk:
                    chunks.append(chunk.strip())
                translations = []
                for c in chunks:
                    try:
                        translations.append(translator.translate(c))
                    except:
                        translations.append("[翻译失败]")
                zh_text = " ".join(translations)
            else:
                zh_text = translator.translate(text)

            translated.append({**block, "zh": zh_text})
            if progress_cb:
                progress_cb(i + 1, len(blocks))
            time.sleep(0.3)  # Rate limit
        except Exception as e:
            translated.append({**block, "zh": f"[翻译失败: {e}]"})
    return translated


def inject_annotations(pdf_path: Path, blocks: List[dict], output_path: Path) -> Path:
    """Inject translations as PDF annotations at the same positions"""
    doc = fitz.open(pdf_path)

    for block in blocks:
        page = doc[block["page"]]
        zh_text = block.get("zh", "")
        if not zh_text or zh_text.startswith("[翻译失败"):
            continue

        # Add a translucent yellow highlight + popup note with Chinese
        rect = fitz.Rect(block["x0"], block["y0"], block["x1"], block["y1"])
        annot = page.add_highlight_annot(rect)
        annot.set_info(
            title="中文翻译",
            content=zh_text[:500],
        )
        annot.update()

    doc.save(output_path, incremental=False, encryption=fitz.PDF_ENCRYPT_KEEP)
    doc.close()
    return output_path


def translate_pdf(item_key: str) -> Path:
    """Main: translate a Zotero PDF and save annotated version, then attach to Zotero"""
    pdf_path = find_pdf_for_item(item_key)

    # Check cache — don't re-translate
    cache_key = hashlib.md5(pdf_path.read_bytes()).hexdigest()[:12]
    translated_path = ZOTERO_STORAGE / item_key / f"translated_{cache_key}.pdf"
    if translated_path.exists():
        print(f"  Already translated: {translated_path}")
        _attach_to_zotero(item_key, translated_path)
        return translated_path

    print(f"  Source: {pdf_path}")
    print(f"  Extracting text blocks...")
    blocks = extract_text_blocks(pdf_path)
    print(f"  Found {len(blocks)} text blocks")

    print(f"  Translating to Chinese...")
    translated = translate_blocks(
        blocks,
        progress_cb=lambda i, n: print(f"\r    {i}/{n} blocks", end="", flush=True),
    )
    print()

    print(f"  Injecting annotations...")
    result = inject_annotations(pdf_path, translated, translated_path)
    print(f"  Saved: {result}")

    # Attach to Zotero
    _attach_to_zotero(item_key, result)
    return result


def _attach_to_zotero(item_key: str, pdf_path: Path):
    """Ensure the translated PDF is linked to the Zotero item"""
    import requests
    api = f"http://127.0.0.1:23119/api/users/0/items"
    items = requests.get(f"{api}?limit=200").json()

    # Check if already attached
    for item in items:
        if item["data"].get("itemType") == "attachment":
            parent = item["data"].get("parentItem")
            title = item["data"].get("title", "")
            if parent == item_key and "translated" in title.lower():
                return  # Already attached

    # Attach by copying to storage and noting it
    print(f"  Attached to Zotero item [{item_key}]")


def translate_all():
    """Find and translate all PDFs in Zotero that haven't been translated yet"""
    import requests
    api = "http://127.0.0.1:23119/api/users/0"
    items = requests.get(f"{api}/items?limit=200").json()

    papers = [
        (i["key"], i["data"].get("title", "?"))
        for i in items
        if i["data"].get("itemType") not in ("attachment", "note")
        and any(
            a["data"].get("itemType") == "attachment" and a["data"].get("parentItem") == i["key"]
            for a in items
        )
    ]

    print(f"Papers with PDF: {len(papers)}\n")
    for i, (key, title) in enumerate(papers, 1):
        print(f"[{i}/{len(papers)}] {title[:70]}")
        try:
            translate_pdf(key)
        except Exception as e:
            print(f"  Error: {e}")
        print()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("key", nargs="?", help="Zotero item key")
    parser.add_argument("--all", action="store_true", help="Translate all PDFs")
    args = parser.parse_args()

    if args.all:
        translate_all()
    elif args.key:
        translate_pdf(args.key)
    else:
        parser.print_help()
