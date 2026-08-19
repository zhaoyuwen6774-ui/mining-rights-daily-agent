# Mining Rights Daily Agent

一个由三个 MCP Server 和一个 Agent Client 组成的矿权日报系统。Agent 通过真实 MCP
`stdio` 会话调用新闻、技术报告 PDF 和 LME 价格工具，生成带逐项引用的 Markdown 简报。

## Components

- `mining-news-mcp`: `search(query, days)` and `fetch_article(url)`
- `mineral-pdf-mcp`: `find_reports(project)` and `extract_resources(pdf_url)`
- `lme-price-mcp`: `get_price(commodity, date_value)` and `get_trend(commodity, days)`
- `mining-daily-agent`: intent parsing, concurrent tool calls, validation and rendering

The default demo uses clearly labelled synthetic fixtures so it is repeatable and needs no secret.
Live mode never substitutes a non-LME benchmark when LME data is unavailable.

See [RUN.md](RUN.md) for the five-minute setup and live-provider configuration.

