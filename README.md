# 旧件回收估价工作台 · 合肥包河3C站点

单文件网页工作台，给站点工程师做旧件回收议价参考。手机优先，打开即用。

## 组成

| 文件 | 说明 |
| --- | --- |
| `index.html` | 工作台前端，单文件，纯静态 |
| `prices.json` | 价格快照，由 Actions 定时刷新 |
| `fetch_prices.py` | 抓价脚本，调用转转开放平台 MCP |
| `models.json` | 抓价型号清单，增删型号改这里 |
| `.github/workflows/fetch-prices.yml` | 定时任务，每天两次刷新快照 |

## 数据口径（务必知悉）

1. **转转实时区间**：标记「转转实时」的型号，价格来自转转开放平台 `evaluate_price`，是**该型号近7天成交的回收价区间（最低成色～最佳成色）**，不是按成色精确定价，只作议价锚点。
2. **站点参考价**：配件类（显卡/内存/CPU/固态/主板/打印机）转转不覆盖，前端使用内置经验区间，明确标注「站点参考」。
3. **实收价**：站点实际成交价由工程师现场录入，存在浏览器 localStorage，不上传服务器。
4. 估价只用于内部议价，不对外承诺。

## 部署与维护

### 首次启用定时任务

1. 仓库 Settings → Secrets and variables → Actions → New repository secret
2. 名称 `ZZ_TOKEN`，值为转转开放平台 MCP 的 Bearer token
3. Actions 标签页 → 抓取转转回收价 → Run workflow 手动跑一次验证

### 调整刷新频率

改 `.github/workflows/fetch-prices.yml` 里的 `cron`。注意 cron 是 UTC 时间，北京时间减 8 小时。

### 增减型号

改 `scripts/models.json`，按现有格式加条目：

```json
{ "key": "品类|品牌|型号|规格", "query": "识别用关键词", "detail_query": "估价用补充描述", "expect_brand": "预期品牌" }
```

`key` 必须与前端 `index.html` 里 `BASELINE` 的字段拼接格式一致，否则前端匹配不上实时价。

### 本地手动跑一次

```bash
ZZ_TOKEN=你的token python3 scripts/fetch_prices.py
```

## 已知限制

- 转转 MCP 的 CORS 是白名单制，浏览器不能跨域直连，所以必须用 Actions 服务端抓、前端读同源 `prices.json`。
- 转转只做整机（手机、笔记本）回收，配件与打印机无价格数据。
- 内存条、CPU 型号识别不稳定，目前依赖站点参考价。
- Token 只存 Actions Secrets，不写入仓库、不进入前端。
