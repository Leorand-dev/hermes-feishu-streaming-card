# Feishu Streaming Card — Hermes Agent Patch

Hermes Agent 飞书适配器**真正的增量流式卡片**补丁。

## 解决的问题

Hermes Agent 飞书适配器虽然能发送交互卡片，但流式编辑的实现是 **O(N²) 的**：

```
旧实现（每步重发全文）:
  edit#1: format_message(1000 chars) → 重建 → PATCH(1000ch)
  edit#2: format_message(2000 chars) → 重建 → PATCH(2000ch)  ← 1000 chars 重复处理
  edit#3: format_message(3000 chars) → 重建 → PATCH(3000ch)  ← 2000 chars 重复处理
  …总处理量 O(N²)…
```

长响应时这种全量重建浪费严重，且卡片内容整个闪烁替换，视觉不流畅。

## 原理

本补丁实现**按字符位置跟踪的增量 delta 追加**：

```
新实现（增量 delta 追加）:
  send:   format_message(initial) → 发初始卡片 (1 个 markdown 元素)
          存储: sent_chars = len(content), elements = [element1]

  edit#1: delta = content[sent_chars:]  ← 只取新字符
          format_message(delta)          ← 只处理 delta
          elements.append({tag:"markdown", content:formatted_delta})
          PATCH(所有 elements)           ← 卡片追加新元素

  edit#2: delta = content[sent_chars:]  ← 又一批新字符
          format_message(delta)          ← 只处理新内容
          elements.append(...)           ← 再追加一个元素
          PATCH(所有 elements)           ← 卡片又多一段

  finalize: 更新 header 为 "done"，清理临时状态
  …总处理量 O(N)…
```

**卡片视觉**：不再是整个内容闪烁替换，而是像聊天记录一样**逐段生长**，每段独立渲染。

## 架构

```
┌───────────────────────────────────────────────────┐
│               _card_stream_messages               │
│               (消息 ID 集合: 哪些是卡片)           │
├───────────────────────────────────────────────────┤
│  _stream_card_parts[msg_id]  = [element1, ...]    │
│  _stream_card_chars[msg_id]  = 已提交字符数        │
│                                                    │
│  send():                                           │
│    → 建初始元素, 初始化 _stream_card_parts/chars   │
│    → 发送卡片                                      │
│                                                    │
│  edit_message() → _edit_stream_card():             │
│    → delta = content[sent_chars:]                  │
│    → 如有 delta: format + append element           │
│    → _build_stream_card_from_elements(elements)    │
│    → HTTP PATCH                                    │
│                                                    │
│  finalize=True:                                    │
│    → header 改为 "done"                            │
│    → 清理 _stream_card_parts/chars                 │
│    → 清理 _card_stream_messages                    │
└───────────────────────────────────────────────────┘
```

## 安装

```bash
# 1. 进入 Hermes Agent 目录
cd ~/.hermes/hermes-agent

# 2. 应用补丁
git apply /path/to/feishu-streaming-card.patch

# 3. 重启 Gateway（见下方）
```

## 重启 Gateway

Gateway 无法自杀。在**另一个终端窗口**执行：

```bash
hermes gateway restart
```

或：

```bash
sudo systemctl restart hermes-gateway
```

## 升级后恢复

每次 `git pull` 升级 Hermes 后，重新 apply 补丁：

```bash
cd ~/.hermes/hermes-agent
git pull
git apply /path/to/feishu-streaming-card.patch
sudo systemctl restart hermes-gateway
```

## 核心 API 变更

| 方法 | 变更 |
|------|------|
| `__init__` | 新增 `_stream_card_parts`, `_stream_card_chars` 字典 |
| `send()` | 发送卡片后初始化增量状态，初始元素 + sent_chars |
| `edit_message()` | 路由到 `_edit_stream_card`，去掉重复清理 |
| `_edit_stream_card` | **完全重写**：delta 提取 → 元素追加 → 多元素卡片 |
| `_build_stream_card_content` | 保持单元素构建（用于 send） |
| **新增** `_build_stream_card_from_elements` | 从元素列表构建多元素卡片 |

## 文件

| 文件 | 说明 |
|------|------|
| `feishu-streaming-card.patch` | adapter.py 完整补丁（含增量更新逻辑） |
| `restart-gateway.py` | 独立进程重启 gateway 脚本 |
