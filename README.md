# Feishu Streaming Card — Hermes Agent Patch

Hermes Agent 飞书适配器**真正的增量流式卡片**。文档+补丁+完整源码+一键部署脚本，clone 即用。

---

## 效果

飞书对话中，Hermes 的回复不再是"一次性弹出"或"全量闪烁替换"，而是像打字机一样**逐段生长**。每个新段落作为新的卡片元素追加，视觉流畅，开销 O(N) 而非 O(N²)。

## 项目结构

```
hermes-feishu-streaming-card/
├── deploy.sh                    # 一键部署脚本（推荐）
├── feishu-streaming-card.patch  # 补丁文件
├── restart-gateway.py           # 独立进程重启脚本
├── README.md                    # 本文件
└── src/
    └── adapter.py               # 完整修改后的 adapter.py（可直接替换）
```

| 文件 | 说明 |
|------|------|
| `deploy.sh` | **一键部署**：备份原文件 → 应用补丁 → 语法验证 → 重启提示 |
| `feishu-streaming-card.patch` | 与 Hermes `main` 分支的 git diff 补丁 |
| `src/adapter.py` | 完整的适配器源码（已包含所有改动） |
| `restart-gateway.py` | 独立进程重启 gateway（替代 `sudo systemctl`） |

## 快速部署

```bash
# 方法一：一键脚本（推荐）
git clone https://github.com/Leorand-dev/hermes-feishu-streaming-card.git
cd hermes-feishu-streaming-card
bash deploy.sh

# 方法二：手动复制
cp src/adapter.py ~/.hermes/hermes-agent/plugins/platforms/feishu/adapter.py

# 方法三：Git 补丁
cd ~/.hermes/hermes-agent
git apply /path/to/feishu-streaming-card.patch
```

### 重启 Gateway

```bash
sudo systemctl restart hermes-gateway
```

> ⚠️ Gateway 不能从内部自行重启。请从另一个终端窗口执行。

升级 Hermes 后重新部署即可恢复补丁：

```bash
cd ~/.hermes/hermes-agent
git pull
bash /path/to/hermes-feishu-streaming-card/deploy.sh
```

## 架构

### 旧实现（全量重建，O(N²)）

```
每步重建整个卡片，已发送的内容被反复处理：
edit#1: format_message(1000 chars) → 整个卡片 PATCH(1000ch)
edit#2: format_message(2000 chars) → 整个卡片 PATCH(2000ch)  ← 1000 chars 重处理
edit#3: format_message(3000 chars) → 整个卡片 PATCH(3000ch)  ← 2000 chars 重处理
```

### 新实现（增量 delta 追加，O(N)）

```
按字符位置追踪已提交的内容，每步只处理新增部分：
send:   format_message(initial) → 发初始卡片（1 个 markdown 元素）
        sent_chars = len(content), elements = [element1]

edit#1: delta = content[sent_chars:]     ← 只取新字符
        format_message(delta)            ← 只处理 delta
        elements.append(new element)     ← 追加新元素
        PATCH(所有 elements)

edit#2: delta = content[sent_chars:]     ← 又一批新字符
        format_message(delta)
        elements.append(...)             ← 再追加一个元素
        PATCH(所有 elements)

finalize: header 改为 "done", 清理状态
```

## 核心改动

```
__init__
  └─ _stream_card_parts[msg_id] = List[markdown_element_dict]
  └─ _stream_card_chars[msg_id] = int  # 已提交的字符数

send()
  └─ _build_stream_card_content(formatted)   → 发初始卡片
  └─ 初始化增量状态: _stream_card_parts + _stream_card_chars

edit_message()
  └─ message_id in _card_stream_messages?
     ├─ 是 → _edit_stream_card()   (增量路径)
     └─ 否 → 原编辑逻辑

_edit_stream_card()  [核心]
  └─ delta = content[sent_chars:]           ← 提取增量
  └─ if delta: format + append element      ← 只处理新内容
  └─ _build_stream_card_from_elements()     ← 从已积累的元素构建
  └─ HTTP PATCH → 飞书
  └─ finalize=True: 清理状态

_build_stream_card_from_elements()
  └─ elements 列表 + header → 完整卡片 JSON
```

## 边界处理

| 场景 | 行为 |
|------|------|
| 首次编辑（无状态） | 初始化为空列表，delta 全量捕获 |
| HTTP PATCH 失败 | 状态保留，下次编辑可继续追加 |
| finalize PATCH 成功 | 自动清理 `_stream_card_parts` + `_card_stream_messages` |
| finalize PATCH 失败 | 状态保留，不会泄漏 |
| `format_message()` 改变长度 | `sent_chars` 基于原始 `content` 长度，与 delta 提取一致 |

## 依赖

- Hermes Agent（任意版本，`adapter.py` 含 `edit_message` 接口）
- Python 3.10+
- Feishu/Lark 机器人凭证（配置于 `~/.hermes/.env`）
