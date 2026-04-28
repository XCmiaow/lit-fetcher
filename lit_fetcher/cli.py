"""
lit-fetcher — 全自动文献抓取 CLI

用法:
  lit-fetcher search "Aspen Plus distillation sensitivity analysis"  # 搜索文献
  lit-fetcher import --dois "10.1016/j.cep.2022.109073,..."          # 按 DOI 导入
  lit-fetcher pdf                                                      # 触发 Zotero 查找全文
  lit-fetcher classify                                                 # 自动分类+去重
  lit-fetcher all "research topic" --max 20                            # 一键全流程
"""
import click
from .commands.search import search_papers
from .commands.zotero_ops import import_to_zotero, trigger_find_fulltext, classify_library, show_status


@click.group()
def main():
    """全自动文献抓取工具：搜索 → 导入 Zotero → 下载 PDF → 自动分类"""


@main.command()
@click.argument("query")
@click.option("--max", "-m", default=10, help="最大结果数")
@click.option("--year-from", "-y", default=2018, help="起始年份")
@click.option("--source", "-s", default="openalex", type=click.Choice(["openalex", "semantic_scholar", "both"]))
def search(query, max, year_from, source):
    """搜索文献并显示结果"""
    papers = search_papers(query, max_results=max, year_from=year_from, source=source)
    click.echo(f"\nFound {len(papers)} papers:\n")
    for i, p in enumerate(papers, 1):
        click.echo(f"  {i}. {p['title'][:70]}")
        click.echo(f"     DOI: {p.get('doi', 'N/A')[:50]}  |  {p.get('journal', '')[:40]}")
        click.echo(f"     OA: {p.get('is_oa', False)}  |  Cited: {p.get('cited_by_count', 0)}")
        click.echo()


@main.command()
@click.option("--dois", help="逗号分隔的 DOI 列表")
@click.option("--file", "-f", help="包含 DOI 列表的文件")
@click.option("--query", "-q", help="搜索关键词（自动搜索后导入）")
@click.option("--max", "-m", default=10, help="搜索最大结果数")
def import_papers(dois, file, query, max):
    """导入文献到 Zotero"""
    if query:
        click.echo(f"Searching: {query}")
        papers = search_papers(query, max_results=max)
        dois = ",".join(p["doi"] for p in papers if p.get("doi"))

    if not dois and not file:
        click.echo("请提供 --dois、--file 或 --query", err=True)
        return

    count = import_to_zotero(dois=dois, file_path=file)
    click.echo(f"Imported {count} papers to Zotero.")


@main.command()
def pdf():
    """触发 Zotero 查找全文（自动下载所有缺失的 PDF）"""
    click.echo("Triggering Zotero Find Full Text...")
    trigger_find_fulltext()
    click.echo("Done. Check Zotero status bar for progress.")


@main.command()
def classify():
    """自动分类 Zotero 文献 + 去重"""
    click.echo("Classifying Zotero library...")
    classify_library()


@main.command()
def status():
    """显示 Zotero 文献库状态"""
    show_status()


@main.command()
@click.argument("query")
@click.option("--max", "-m", default=20, help="最大结果数")
@click.option("--year-from", "-y", default=2018, help="起始年份")
def all(query, max, year_from):
    """一键全流程：搜索 → 导入 → PDF → 分类"""
    click.echo(f"=== lit-fetcher: {query} ===\n")

    # Step 1: Search
    click.echo("[1/4] Searching...")
    papers = search_papers(query, max_results=max, year_from=year_from)
    click.echo(f"  Found {len(papers)} papers")

    # Step 2: Import to Zotero
    click.echo("[2/4] Importing to Zotero...")
    dois = ",".join(p["doi"] for p in papers if p.get("doi"))
    count = import_to_zotero(dois=dois)
    click.echo(f"  Imported {count} papers")

    # Step 3: Download PDFs
    click.echo("[3/4] Triggering PDF download (Zotero Find Full Text)...")
    trigger_find_fulltext()
    click.echo("  Zotero is downloading PDFs...")

    # Step 4: Classify
    click.echo("[4/4] Auto-classifying...")
    classify_library()
    click.echo("  Done")

    click.echo(f"\n{'='*50}")
    click.echo("Complete! Open Zotero to read your papers.")
    click.echo(f"{'='*50}")


if __name__ == "__main__":
    main()
