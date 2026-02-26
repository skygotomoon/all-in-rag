# 微信小程序场地使用情况实时监测（示例）

> 用于“实时监测某个微信小程序场地使用情况”的工程化模板。
> 
> ⚠️ 请仅接入你**有权限**的数据来源（官方 API、你自有系统、已授权抓取端点），不要绕过平台风控或违反服务条款。

## 功能

- 定时轮询上游数据源（默认 10 秒）
- 将每次快照写入 SQLite
- 提供历史数据接口 `/history`
- 提供 SSE 实时推送接口 `/stream`
- 支持占用率阈值告警（`alert: true/false`）

## 数据格式约定

上游接口返回 JSON：

```json
{
  "total_slots": 20,
  "occupied_slots": 13
}
```

## 快速运行

```bash
cd code/C10/wechat_venue_monitor
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 9000 --reload
```

访问：

- 健康检查：http://127.0.0.1:9000/health
- 历史数据：http://127.0.0.1:9000/history
- 实时流：http://127.0.0.1:9000/stream

## 配置

默认配置：

```json
{
  "venue_name": "默认场地",
  "fetch_url": "http://localhost:9000/mock",
  "poll_interval_seconds": 10,
  "occupied_threshold": 0.85
}
```

可通过 `POST /config` 更新。

## 对接微信小程序的建议

1. 优先使用官方开放平台接口或商家后台导出的可授权接口。
2. 如无官方接口，可在你自己的后端服务中完成鉴权与数据清洗，再让本监测服务读取该后端。
3. 监测维度可扩展：
   - 按时段可预约余量
   - 取消/释放频次
   - 占用率峰值时段
