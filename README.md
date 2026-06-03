<div align="center">
  <img src="logo.png" alt="biliVideo" width="120">

# biliVideo · AstrBot B 站视频解析与 AI 总结

**丢一个 B 站链接,AI 帮你秒出精华总结。**

[![AstrBot](https://img.shields.io/badge/AstrBot-v4.0%2B-blueviolet)](https://astrbot.app/)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-2.0.0-orange)](CHANGELOG.md)
[![Tests](https://img.shields.io/badge/tests-190%20passing-success)](tests/)

</div>

---

## ✨ 为什么是 v2.0?

biliVideo v2.0 是一次**完全重写**的工程升级。主要目标:

- **可维护性**:`main.py` 从 2,000 行单一巨型文件瘦身到约 160 行。所有逻辑下放到 `bilivideo/` 子包,按职责严格分层。
- **健壮性**:HTTP 层采用共享 `aiohttp.ClientSession` + 指数退避重试;订阅文件原子写入 + `fsync`;Cookie 文件 0600 权限。
- **响应速度**:带 TTL 的 LRU 缓存避免同一 BV 重复请求 B 站;single-flight 让多人同时粘贴同一链接只触发一次工作。
- **可测试**:190 个 PyTest 单元/集成测试覆盖 URL 解析、分页、智能截断、订阅持久化、冷却、缓存、消息路由、渲染降级链等。
- **类型化**:所有 API 返回 `dataclass`(`VideoInfo` / `UploaderInfo` / …),配置读取经 `PluginConfig` 校验。

> 命令、配置项、行为对终端用户**完全向后兼容**。配置文件不需要改动即可升级。

---

## 🚀 快速开始

```text
1. AstrBot 插件市场搜索 biliVideo,或「安装插件 → 填 Git 仓库地址」一键安装 → 重启
   依赖全部由 AstrBot 自动 pip 安装(含静态 ffmpeg + 内建中文字体),VPS / Docker 无需手动装系统依赖
2. /B站登录  → 扫码登录
3. /总结 https://www.bilibili.com/video/BV1xx411c7mD
```

---

## 🏆 核心特性

| 类别 | 特性 |
| --- | --- |
| 输出 | 双栏暗色卡片图片 / 纯文本回退 / 合并转发模式 |
| 总结 | 简洁 / 详细 / 专业 三种风格,LLM 可换 |
| 输入 | 完整链接、短链、BV 号、UID、空间链接、UP 主昵称 |
| 智能 | 自动识别小程序/链接/短链;**触发关键词**配置化 |
| 订阅 | 订阅 UP 主自动推送;支持指定推送群/QQ |
| 加速 | 优先平台字幕(无字幕再下载音频转写) |
| 长视频 | 按章节自动分图,LLM 生成的多章节内容不被截断 |
| 安全 | 群级黑/白名单;用户冷却;并发 BV 去重 |
| 工具 | AI function-call:`bilibili_search_list` / `bilibili_search_download` |

---

## 📦 安装

### 前置要求

- AstrBot v4.0+
- Python 3.10+
- 至少配置一个 LLM Provider(DeepSeek、OpenAI、Claude 等),或在配置中切到 `openai_compatible` 自填 API。

### 开箱即用(VPS / Docker / Zeabur 一键安装)

本插件**无需手动安装任何系统依赖**。AstrBot 安装插件时会自动 `pip install -r requirements.txt`,其中已包含:

- **ffmpeg**:由 `imageio-ffmpeg` 提供静态二进制,无字幕视频走 ASR 转写时自动调用;系统若已装 ffmpeg 则优先用系统版。
- **图片渲染**:内建 Noto Sans SC 中文字型(GB2312 子集,SIL OFL)+ Pillow,容器无图形环境也能出图。
- 装好后用 `/总结状态` 即可看到检测出的渲染后端与 ffmpeg 来源(系统 / 内建)。

### 可选增强(非必须)

#### wkhtmltopdf — 更精美的图片

不装也能出图(Pillow 简洁卡片版)。装了可获得双栏暗色卡片的高保真渲染:

```bash
# Ubuntu / Debian
apt install -y wkhtmltopdf fonts-wqy-zenhei

# Docker(无图形环境时配 xvfb)
apt install -y wkhtmltopdf xvfb fonts-wqy-zenhei fonts-noto-cjk
printf '#!/bin/bash\nxvfb-run --auto-servernum /usr/bin/wkhtmltoimage "$@"\n' > /usr/local/bin/wkhtmltoimage
chmod +x /usr/local/bin/wkhtmltoimage

# macOS
brew install wkhtmltopdf
```

#### 系统中文字体 — 更全的字形覆盖

内建字型为 GB2312 子集,已覆盖绝大多数简体中文。若需繁体 / 日文 / 生僻字的完整覆盖,装一个系统 CJK 字体即可(会被优先使用):

```bash
apt install -y fonts-noto-cjk    # 或 fonts-wqy-zenhei
```

> 纯文本模式:把 `output_image` 设为 `false` 即可完全免图片渲染依赖。

---

## 🔧 命令一览

### 基础

| 命令 | 说明 |
| --- | --- |
| `/总结帮助` | 显示帮助 + 当前登录状态 |
| `/总结 <链接 \| BV>` | 为单个视频生成 AI 总结 |
| `/最新视频 <UID \| 空间链接 \| 昵称>` | 获取 UP 主最新视频并总结 |

### 管理

| 命令 | 说明 |
| --- | --- |
| `/总结状态` | 查看版本 / 登录 / LLM / 渲染后端 / 缓存等 |
| `/总结清缓存` | 清除视频信息 + WBI + 总结结果缓存 |
| `/总结模型 [provider ID]` | 列出 / 切换 AstrBot 内置对话模型(仅 astrbot 模式) |

### 登录

| 命令 | 说明 |
| --- | --- |
| `/B站登录` | 扫码登录 |
| `/B站登出` | 清除登录状态 |

### 订阅

| 命令 | 说明 |
| --- | --- |
| `/订阅 <UP>` | 订阅 UP 主,新视频自动推送 |
| `/取消订阅 <UP>` | 取消订阅 |
| `/订阅列表` | 查看当前订阅 |
| `/检查更新` | 立即手动检查 |

### 推送目标

| 命令 | 说明 |
| --- | --- |
| `/添加推送群 <群号>` | 加入推送群列表 |
| `/添加推送号 <QQ号>` | 加入推送私聊列表 |
| `/推送列表` | 查看推送目标 |
| `/移除推送 <id>` | 移除推送目标 |

### 自动识别

| 命令 | 说明 |
| --- | --- |
| `/识别开关` | 开关 B 站链接自动识别 |

> `<UP>` 支持纯数字 UID、空间链接、或 UP 主昵称。
> 设置推送目标后,所有订阅总结仅推送到指定目标;未设置则推到订阅来源。

---

## 🧠 智能消息过滤

引用消息默认**不**触发自动识别,除非引用回复中包含触发关键词。

```text
A: [分享 B 站视频]
B: 引用 A + "帮我总结一下"   ✅ 触发(命中"总结"关键词)
C: 引用 A + "好的"            ❌ 不触发(无关键词)
```

触发关键词在 `_conf_schema.json` 的 `trigger_keywords` 字段里,逗号分隔。
支持中英文混合自定义。

---

## 📦 合并转发模式

```json
{ "enable_forward_message": true }
```

视频信息 + AI 总结打包成聊天记录。

- 视频封面 + 标题
- UP 主、简介、发布时间、播放数据
- 长内容自动分页

---

## 🤖 AI 智能搜索

直接和 AI 对话,无需记忆命令:

```text
搜索 Python 教程视频
从结果里选播放量最高的 3 个,下载并总结
```

AI 自动组合调用两个工具:`bilibili_search_list` 与 `bilibili_search_download`。
转写文件存于 `<data_dir>/search_results/<task_id>_<keyword>/`。

---

## ⚙️ 配置项

配置面板已按功能分组(🔧 通用 / 🤖 LLM / 📝 总结 / 🎨 渲染 / 💬 消息 / 🔍 识别 / 📡 订阅 / 🔐 访问 / 🔎 搜索 / 🧪 实验)。部分常用配置:

| 配置 | 默认 | 说明 |
| --- | --- | --- |
| `output_image` | `true` | 总结以图片形式发送 |
| `note_style` | `professional` | `concise` / `detailed` / `professional` |
| `enable_link` | `true` | 在总结中嵌入时间戳标记 |
| `enable_summary` | `true` | 末尾添加 AI 总结段落 |
| `download_quality` | `fast` | `fast`(32k) / `medium`(64k) / `slow`(128k) |
| `prefer_subtitle` | `true` | 优先平台字幕,无字幕才下载音频 |
| `enable_multi_platform` | `false` | 🧪 实验:`/总结` 支持 YouTube/抖音(yt-dlp,字幕优先;非中文 ASR 质量不保证)。YouTube 登录用 `/YT登录` 在聊天里贴 cookies(机器人自动保存,无需建文件;有封号风险,请用小号) |
| `llm_provider_id` | `""` | 指定 AstrBot 内置模型 ID(留空=当前模型;用 `/总结模型` 查看可用 ID) |
| `enable_auto_push` | `false` | 启用定时推送新视频 |
| `auto_push_summary` | `true` | 推送新视频时是否附带 AI 总结 |
| `check_interval_minutes` | `600` | 定时检查间隔 |
| `max_subscriptions` | `20` | 每个会话最大订阅数 |
| `enable_miniapp_detect` | `false` | 自动识别群内 B 站链接 |
| `detect_auto_summary` | `false` | 识别后自动生成总结 |
| `enable_forward_message` | `false` | 总结合并转发(聊天记录形式) |
| `enable_auto_split` | `true` | 长视频自动分图 |
| `max_cards_per_image` | `6` | 每张图最大章节卡片数 |
| `image_width` | `1400` | 图片宽度像素 |
| `user_cooldown_seconds` | `8` | 用户冷却(防刷屏) |
| `trigger_keywords` | (默认列表) | 引用消息触发关键词,逗号分隔 |
| `access_mode` | `blacklist` | `blacklist` / `whitelist` |
| `group_list` | `""` | 黑/白名单群号,逗号分隔 |

完整配置请见 `_conf_schema.json`。

---

## 🧪 开发与测试

```bash
git clone https://github.com/storyAura/astrbot_plugin_biliVideo
cd astrbot_plugin_biliVideo

python -m pip install -r requirements.txt
python -m pip install pytest pytest-asyncio ruff mypy

python -m pytest -q
ruff check .
mypy bilivideo
```

测试覆盖了所有纯逻辑:URL 解析、分页、智能截断、消息路由、订阅持久化、
冷却追踪、LRU 缓存、in-flight 去重、访问控制、配置校验等。

---

## 📁 项目结构

```
bilivideo/
├── core/          # 配置、常量、错误、类型、日志
├── api/           # Bilibili HTTP 客户端 / WBI / endpoints
├── auth/          # Cookie 持久化 / QR 登录
├── parsing/       # URL/BV 提取、消息路由、触发关键词
├── transcription/ # 字幕→ASR pipeline / 必剪 BCut
├── downloader/    # yt-dlp 包装
├── llm/           # Provider 抽象 + AstrBot/OpenAI 实现 + Prompt
├── summarize/     # 总结编排 + 后处理
├── render/        # Markdown→PNG (主题、模板、分页)
├── messaging/     # 合并转发、文本切分、视频信息渲染
├── subscription/  # 原子 JSON 存储 / 管理器 / 调度器
├── access/        # 黑白名单 / 冷却 / in-flight dedup
├── cache/         # LRU + TTL 缓存
├── handlers/      # 命令处理器(每个命令一个文件)
├── tools/         # AI function-call 注册
├── search.py      # 批次搜索/转写服务
└── services.py    # 服务容器(composition root)
```

更多请阅 [CONTRIBUTING.md](CONTRIBUTING.md)。

---

## ⚠️ 注意事项

- 首次使用必须先 `/B站登录`。
- 视频总结约需 1-3 分钟(有字幕时更快)。
- 图片渲染失败会自动回退为纯文本。
- 引用消息时只识别用户实际发送的内容,引用部分仅在命中触发关键词时被提取。
- 合并转发需要平台支持(部分平台可能不支持,会自动降级)。

---

## 🔎 致谢

- 总结流程(音频下载、字幕获取、Prompt 构建)的核心思路参考自
  [BiliNote](https://github.com/JefferyHcool/BiliNote)。
- 旧版 v1.x 的实现由 [@storyAura](https://github.com/storyAura) 维护;
  v2.0 重构在保留所有功能的前提下完成。
- 引用消息硬拦截的 PR 灵感来自 [@Jeric-X](https://github.com/Jeric-X)。

---

## 📄 License

[MIT](LICENSE) © 2025 storyAura
