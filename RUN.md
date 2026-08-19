# 5 分钟运行指南

## 前置条件

- Docker Desktop 已启动。
- 当前目录为 `/Users/wuzexue/work/test`。

## 一条命令生成简报

```bash
docker compose run --rm --build agent "给我生成一份关于 Pilbara 锂矿的今日简报" --mode fixture --output /app/output/pilbara-daily.md
```

命令会构建镜像、启动三个独立 MCP `stdio` Server、由 Agent Client 并行调用工具，
并把结果写到 `output/pilbara-daily.md`。fixture 数据均带明显标识，不会被误认为实时信息。

## 运行质量检查

```bash
docker compose run --rm test
docker compose run --rm --entrypoint ruff test check .
docker compose run --rm --entrypoint mypy test
```

## 接入 Cursor / Claude Desktop

先执行 `docker compose build`，再把 `mcp-config.json` 中的 `mcpServers` 合并到客户端配置。
配置直接运行已经构建的 `mining-rights-agent:local` 镜像，不依赖本机 Python。

可用的必选工具：

- `mining-news-mcp`: `search`, `fetch_article`
- `mineral-pdf-mcp`: `extract_resources`
- `lme-price-mcp`: `get_price`, `get_trend`

`find_reports` 是为 Agent 自动定位技术报告增加的辅助工具。

## 实时模式

复制 `.env.example` 为 `.env`，把 `APP_MODE` 改为 `live`。新闻服务会读取 Mining.com
和 S&P Global RSS，PDF 工具接受公开 HTTPS PDF。价格服务需要配置已授权的 LME JSON
数据端点；如果没有授权端点，工具会明确返回 `unavailable`，不会使用 COMEX、Yahoo
或其他代理价格冒充 LME 数据。

可选的模型配置使用 OpenAI-compatible `chat/completions` 协议。未配置模型时，Agent 使用
确定性摘要模板，完整 MCP 流程、数据校验和引用机制仍然可用。

## 安全边界

- 仅下载公开 HTTPS URL，拒绝内网、回环和保留地址。
- 每次下载限制响应大小、超时和重定向次数。
- MCP 日志只写标准错误，不污染 `stdio` 协议。
- PDF 数值保留原始行、页码、报告准则和置信度。
- 锂不是 LME 挂牌品种，系统会明确提示行情缺口。

