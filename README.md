# Feishu Streaming Card — Hermes Agent Patch

Hermes Agent 飞书适配器增量流式卡片补丁。

## 解决的问题

Hermes Agent v0.18.0 的飞书适配器虽然内置了流式卡片接口（`_card_stream_messages` + `_edit_stream_card`），
但 `send()` 方法始终一次性发送完整内容，用户只看到卡片一次性弹出，没有增量填充效果。

## 原理

```
Before (原版):
  模型生成完整回复 → send(完整内容) → 一次性弹出卡片

After (补丁后):
  模型生成完整回复 → send(完整内容) → 拆分为4段累积内容
    → 发第1段（初始卡片）
    → 0.6s后 PATCH 更新为第1+2段
    → 0.6s后 PATCH 更新为第1+2+3段
    → 0.6s后 PATCH 最终版（完整内容）
```

## 安装

```bash
# 1. 进入 Hermes Agent 目录
cd ~/.hermes/hermes-agent

# 2. 应用补丁
git apply patches/feishu-streaming-card.patch

# 3. 重启 Gateway（见下方）
```

## 重启 Gateway

Gateway 无法自杀，用独立进程脚本重启：

```bash
python3 patches/restart-gateway.py
```

> ⚠️ 脚本中的 `GW_PID` 需根据实际 gateway PID 修改。先用 `ps aux | grep "hermes.*gateway"` 查看。

## 升级后恢复

每次 `git pull` 升级 Hermes 后，重新 apply 补丁即可：

```bash
cd ~/.hermes/hermes-agent
git pull
git apply ~/.local/share/weather-cron/patches/feishu-streaming-card.patch
```

## 技术细节

- **短消息不拆分**：< 150 字符的消息直接发送，不流式
- **段落感知**：拆分会优先在段落边界（`\n\n`）处断开，避免截断句子
- **去重保护**：连续相同内容的 chunk 自动合并
- **错误容忍**：某个中间更新失败不影响最终结果
- **延迟**：每次更新间隔 0.6 秒，共 3 次更新（4 段 → 完整）

## 文件

| 文件 | 说明 |
|------|------|
| `feishu-streaming-card.patch` | adapter.py 补丁（新增 `_split_stream_chunks` + 修改 `send()`） |
| `restart-gateway.py` | 独立进程重启 gateway 脚本 |