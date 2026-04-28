# lit-fetcher

全自动文献抓取工作流：**搜索 → 导入 Zotero → 下载 PDF → 自动分类**

一条命令完成从研究问题到可阅读 PDF 的全流程。

## 安装

```bash
pip install -e .
```

## 依赖

- Python 3.10+
- Zotero 7（需安装 sci-pdf 插件并在运行中）
- Windows（UI 自动化依赖）

## 用法

### 搜索文献

```bash
lit-fetcher search "Aspen Plus distillation sensitivity analysis"
lit-fetcher search "reactive distillation process optimization" --max 20 --year-from 2020
```

### 导入 Zotero

```bash
# 按 DOI 导入
lit-fetcher import --dois "10.1016/j.cep.2022.109073,10.1002/aic.16526"

# 搜索后导入
lit-fetcher import --query "pressure swing distillation optimization" --max 15

# 从文件导入
lit-fetcher import --file dois.txt
```

### 下载 PDF

```bash
lit-fetcher pdf
```

自动聚焦 Zotero 窗口 → 全选文献 → 右键「查找全文」→ Zotero 通过 Sci-Hub + Unpaywall 批量下载。

### 自动分类

```bash
lit-fetcher classify
```

按主题自动打标签、检测重复条目。

### 状态

```bash
lit-fetcher status
```

### 一键全流程

```bash
lit-fetcher all "Aspen Plus distillation column optimization" --max 20
```

等价于：

```bash
lit-fetcher search "..."  →  lit-fetcher import --dois "..."  →  lit-fetcher pdf  →  lit-fetcher classify
```

## 工作流

```
研究问题
  │  lit-fetcher search "关键词"
  ▼
OpenAlex / Semantic Scholar → DOI 列表
  │  lit-fetcher import --dois "..."
  ▼
Zotero 文献库（元数据 + 标签）
  │  lit-fetcher pdf
  ▼
Zotero 查找全文 (Sci-Hub + Unpaywall + 机构订阅)
  │  lit-fetcher classify
  ▼
18 篇可阅读 PDF + 主题分类 + 去重
```

## 配置

在 Zotero 中安装 [sci-pdf 插件](https://github.com/syt2/zotero-scipdf)：

1. 下载 `sci-pdf.xpi`
2. Zotero → 工具 → 插件 → 从文件安装
3. 重启 Zotero

确保 Zotero 正在运行且 Sci-Hub 解析器已配置。

## License

MIT
