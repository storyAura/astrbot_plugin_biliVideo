<div align="center">
  <img src="logo.png" alt="biliVideo" width="100" height="100" style="border-radius: 20px;" />
  <h1>biliVideo 视频总结</h1>
  <p><b>丢个B站链接，AI 帮你秒出精华总结</b></p>

  <br/>

  <img src="https://img.shields.io/badge/version-v1.0.4-blue" />
  <img src="https://img.shields.io/badge/AstrBot-v4.0+-green" />
  <img src="https://img.shields.io/badge/platform-Bilibili-ff69b4" />
  <img src="https://img.shields.io/badge/license-MIT-orange" />
</div>

<br/>

> **🇨🇳 [中文](#-中文文档)** &nbsp;|&nbsp; **🇬🇧 [English](#-english-documentation)**

---

# 🇨🇳 中文文档

## 🎉 最新更新 (v1.0.4)

- 🐛 **修复无字幕视频总结崩溃** - 修复走 bcut 转写流程时 `extract_video_id` 未绑定导致的 UnboundLocalError
- 🐛 **修复短链接解析异常** - 修复 b23.tv 短链正则表达式缺少右括号导致的 unterminated subpattern 错误

[查看完整更新日志](CHANGELOG.md)

## 📖 简介

**biliVideo** 是一款运行在 [AstrBot](https://astrbot.app/) 上的 B站视频总结插件。

你只需要丢一个B站视频链接，插件就会自动下载音频、提取字幕、调用 AI 大模型，生成一份结构化的视频总结 —— 并渲染成精美的暗色主题卡片图片发送到群聊。

不仅如此，你还可以 **订阅 UP 主**，新视频发布时自动推送总结到群里，再也不怕错过喜欢的 UP 的内容了。

## 🚀 快速开始

1. **安装插件** - 在 AstrBot 管理面板上传插件 zip 包
2. **安装依赖** - 安装 FFmpeg 和 wkhtmltopdf（详见[安装](#-安装)）
3. **登录B站** - 发送 `/B站登录` 并扫码
4. **开始使用** - 发送 `/总结 <视频链接>` 即可

更多详细说明请查看下方文档。

## 📸 效果展示

### 智能搜索 + 合并转发

<div align="center">
  <img src="assets/zongjie (1).png" alt="智能搜索效果" width="600" />
  <p><i>AI 智能搜索视频并生成总结，支持合并转发模式</i></p>
</div>

### 视频总结详情

<div align="center">
  <img src="assets/zongjie (2).png" alt="视频总结详情" width="600" />
  <p><i>详细的视频信息展示，包含封面、UP主、播放数据和 AI 总结</i></p>
</div>

## 🏆 核心特性

| 特性 | 说明 |
|------|------|
| 🎨 **图片渲染输出** | 总结渲染为双栏暗色卡片图片，清晰美观 |
| 🧠 **三种总结风格** | 简洁 / 详细 / 专业，适用于不同场景 |
| 📡 **订阅自动推送** | 订阅 UP 主，新视频自动推送总结 |
| 🔍 **多格式输入** | 支持完整链接、短链、BV号、UID、空间链接、UP主昵称 |
| ⏱️ **时间戳标记** | 总结中标注视频对应时间点，便于跳转定位 |
| 🔐 **扫码登录** | 在聊天中扫码登录B站，无需手动填写 Cookie |
| 🛡️ **群聊权限控制** | 支持黑名单 / 白名单模式 |
| 📱 **小程序链接识别** | 群里分享B站小程序/短链自动推送视频信息 |
| 🤖 **AI 智能搜索** | 直接与 AI 对话搜索视频，自动转写并分析内容 |
| 📦 **合并转发模式** | 视频信息和总结打包为聊天记录形式，美观不刷屏 |
| 🎯 **智能消息过滤** | 自动识别引用消息，避免误触发识别 |
| ⚡ **优先使用字幕** | 视频有字幕时优先获取，节省30-60秒/视频 |
| 🎨 **长视频自动分图** | 长视频总结自动拆分为多张图片，避免截断 |

## 📦 安装

### 前置要求

- [AstrBot](https://astrbot.app/) v4.0+
- 已配置至少一个 LLM Provider（如 DeepSeek、OpenAI、Claude 等）

### 安装步骤

**1. 安装插件**

在 AstrBot 管理面板 → 插件管理 → 上传插件 zip 包 → 重启 AstrBot

**2. 安装系统依赖**

```bash
# FFmpeg（必须 — 用于音频处理）
# Ubuntu/Debian
apt install -y ffmpeg

# macOS
brew install ffmpeg

# Windows
# 下载 FFmpeg 并添加到系统 PATH
# https://ffmpeg.org/download.html

# wkhtmltopdf（开启图片输出时需要）
# Ubuntu/Debian
apt install -y wkhtmltopdf

# macOS
brew install wkhtmltopdf

# Windows
# 下载安装包并安装
# https://wkhtmltopdf.org/downloads.html
```

**3. 登录B站**

在聊天中发送：
```
/B站登录
```
用B站 App 扫描弹出的二维码即可。

**4. 开始使用 🎉**
```
/总结 https://www.bilibili.com/video/BV1xx411c7mD
```

## 🔧 命令一览

### 基础命令

| 命令 | 说明 |
|------|------|
| `/总结帮助` | 显示帮助信息和当前登录状态 |
| `/总结 <视频链接>` | 为指定视频生成 AI 总结 |
| `/最新视频 <UP主>` | 获取 UP 主最新视频并生成总结 |

### 登录管理

| 命令 | 说明 |
|------|------|
| `/B站登录` | 扫码登录 B站 |
| `/B站登出` | 退出B站登录 |

### 订阅管理

| 命令 | 说明 |
|------|------|
| `/订阅 <UP主>` | 订阅 UP 主，新视频自动推送总结 |
| `/取消订阅 <UP主>` | 取消订阅 |
| `/订阅列表` | 查看当前订阅 |
| `/检查更新` | 手动检查 UP 主新视频 |

### 自动识别

| 命令 | 说明 |
|------|------|
| `/识别开关` | 开关B站链接自动识别（群里分享链接自动推送视频信息） |

> **💡 提示**：`<UP主>` 支持多种格式 —— 纯数字 UID、空间链接、或者直接输入 UP 主昵称。

### 推送目标

| 命令 | 说明 |
|------|------|
| `/添加推送群 <群号>` | 将 QQ 群加入推送列表 |
| `/添加推送号 <QQ号>` | 将 QQ 号加入推送列表 |
| `/推送列表` | 查看当前推送目标 |
| `/移除推送 <群号或QQ号>` | 移除推送目标 |

> **💡 提示**：设置推送目标后，所有订阅的新视频总结将**只推送到指定的群/用户**，而不是发起订阅的群。未设置时默认推送到订阅来源群。

### 使用示例

```
/总结 https://www.bilibili.com/video/BV1xx411c7mD
/总结 BV1xx411c7mD
/最新视频 某UP主的名字
/订阅 123456789
/添加推送群 123456789
/添加推送号 987654321
/推送列表
/移除推送 123456789
/识别开关
```

## 📦 合并转发模式

### 什么是合并转发？

开启后，视频信息和AI总结将打包为**聊天记录**形式发送，包含：
- 📺 视频封面 + 标题
- 👤 UP主、简介、发布时间、播放数据
- 📝 AI总结内容（支持图片/文本，长内容自动分页）

### 如何开启？

在插件配置中设置：
```json
{
  "enable_forward_message": true
}
```

### 优势

- ✅ **信息集中** - 视频信息和总结打包在一起，不刷屏
- ✅ **美观整洁** - 类似聊天记录的卡片形式，易于阅读
- ✅ **支持长内容** - 自动分页，避免消息过长
- ✅ **保留封面** - 直观展示视频封面图

### 适用场景

- `/总结` 命令
- `/最新视频` 命令
- 自动识别链接（需同时开启 `detect_auto_summary`）
- 订阅推送

## 🎯 智能消息过滤

### 引用消息过滤

插件会智能识别**引用消息**，避免误触发识别：

**✅ 不会触发识别：**
- 引用别人的B站链接 + 回复 `好的`
- 引用别人的B站链接 + 回复 `收到`
- 引用别人的B站链接 + 回复 `@某人 1`
- 纯艾特消息：`@某人`

**✅ 仍会触发识别：**
- 引用别人的B站链接 + 回复 `总结一下`（包含触发关键词）
- 引用别人的B站链接 + 回复 `帮我看看`（包含触发关键词）
- 引用任意消息 + 发送B站链接
- 直接分享B站小程序/链接

### 触发关键词

当引用包含B站视频的消息时，只有在回复中包含以下关键词才会触发识别：

**中文关键词：**
```
总结、看看、看一下、看下、分析、讲的啥、讲什么、说的啥、说什么、
内容、视频、这个、这视频、帮我看、帮忙看、解析、翻译
```

**英文关键词：**
```
summary、summarize、analyze、video、watch、check、see
```

**示例：**
```
用户A: [分享B站视频]
用户B: 引用用户A + "帮我总结一下"  ✅ 触发（关键词：总结）
用户C: 引用用户A + "好的"          ✅ 不触发（无关键词）
```

### 调试模式

开启 `debug_mode` 可查看详细的过滤日志：
```json
{
  "debug_mode": true
}
```

## 🤖 AI 智能搜索

直接与 AI 对话即可搜索 B站视频、理解视频内容并进行深度交流，无需记忆命令。

### 使用方式

```
用户: 帮我搜索 Python 教程视频
用户: 从搜索结果里下载播放量最高的 3 个视频并总结
用户: 搜索鸣潮相关的视频，告诉我漂泊者做了什么
```

### 工作流程

AI 会自动组合使用两个工具：

1. **bilibili_search_list**: 搜索视频并返回列表（包含BV号）
2. **bilibili_search_download**: 根据BV号下载转写视频内容

转写完成后 AI 自动继续处理用户需求，转写文件保存在 `/AstrBot/data/plugin_data/astrbot_plugin_bilivideo/search_results/`

### 相关配置

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `default_count` | `20` | 搜索列表默认返回数量 |
| `default_download_count` | `3` | 建议每次下载转写的数量 |
| `search_max_concurrent` | `1` | 同时下载转写的并发数 |

## ⚙️ 配置项

在 AstrBot 管理面板 → 插件配置中可设置：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `output_image` | `true` | 总结以图片形式发送 |
| `note_style` | `professional` | 总结风格：`concise` / `detailed` / `professional` |
| `enable_link` | `true` | 嵌入时间戳标记 |
| `enable_summary` | `true` | 末尾添加 AI 总结段落 |
| `download_quality` | `fast` | 音频质量：`fast` / `medium` / `slow` |
| `enable_auto_push` | `false` | 启用自动推送新视频信息 |
| `auto_push_summary` | `true` | 推送新视频信息时否附带总结；关闭后仅发送视频基本信息 |
| `check_interval_minutes` | `600` | 定时检查间隔（分钟） |
| `max_subscriptions` | `20` | 每个群最大订阅数 |
| `max_note_length` | `3000` | 总结最大字符数 |
| `push_groups` | 空 | 推送QQ群列表，逗号分隔 |
| `push_users` | 空 | 推送QQ号列表，逗号分隔 |
| `access_mode` | `blacklist` | 群聊访问控制模式 |
| `group_list` | 空 | 群号列表，逗号分隔 |
| `enable_miniapp_detect` | `false` | 自动识别群内B站链接并推送视频信息 |
| `detect_show_cover` | `true` | 推送时显示视频封面 |
| `detect_show_uploader` | `true` | 推送时显示UP主名 |
| `detect_show_desc` | `true` | 推送时显示视频简介 |
| `detect_show_pubtime` | `true` | 推送时显示发布时间 |
| `detect_show_link` | `true` | 推送时显示BV号链接 |
| `detect_show_stats` | `true` | 推送时显示播放量等数据 |
| `detect_auto_summary` | `false` | 识别链接后自动生成总结（消耗LLM额度） |
| `enable_forward_message` | `false` | 总结以合并转发（聊天记录）形式发送 |
| `enable_auto_split` | `true` | 长视频自动分图 |
| `max_cards_per_image` | `6` | 每张图最多卡片数 |
| `default_count` | `20` | 搜索列表默认返回数量 |
| `default_download_count` | `3` | 建议每次下载转写的数量 |
| `search_max_concurrent` | `1` | 搜索下载并发数 |
| `search_show_progress` | `true` | 智能搜索时显示下载进度 |
| `prefer_subtitle` | `true` | 优先使用字幕（无字幕时自动下载音频转写） |
| `debug_mode` | `false` | 启用调试日志 |

## 📋 系统依赖

| 依赖 | 类型 | 用途 |
|------|------|------|
| **FFmpeg** | 系统 | 音频下载处理 (**必须**) |
| **wkhtmltopdf** | 系统 | 图片渲染 (开启图片输出时需要) |
| yt-dlp | Python | B站视频/音频下载 |
| aiohttp | Python | 异步 HTTP 请求 |
| requests | Python | HTTP 请求 |
| markdown | Python | Markdown → HTML |
| imgkit | Python | HTML → 图片 |

> Python 依赖会在插件安装时自动安装。

## ⚠️ 注意事项

- 首次使用必须先执行 `/B站登录`
- 需要在 AstrBot 中配置好 LLM Provider
- 视频总结生成约需 1-3 分钟（有字幕时更快）
- 图片渲染失败时会自动回退到纯文本
- 引用消息时，只识别用户实际发送的内容，不识别引用的内容
- 引用包含视频的消息时，需要在回复中包含触发关键词（如"总结"、"看看"等）才会解析
- 合并转发模式需要平台支持（部分平台可能不支持）
- 开启 `prefer_subtitle` 可显著提升处理速度，但部分视频可能没有字幕

## 💡 使用技巧

### 推荐配置组合

**基础配置（推荐新手）：**
```json
{
  "output_image": true,
  "note_style": "professional",
  "prefer_subtitle": true,
  "enable_miniapp_detect": true,
  "detect_auto_summary": false
}
```

**高级配置（群聊推荐）：**
```json
{
  "output_image": true,
  "note_style": "professional",
  "prefer_subtitle": true,
  "enable_miniapp_detect": true,
  "detect_auto_summary": false,
  "enable_forward_message": true,
  "enable_auto_split": true,
  "max_cards_per_image": 6
}
```

**订阅推送配置：**
```json
{
  "enable_auto_push": true,
  "check_interval_minutes": 600,
  "max_subscriptions": 20,
  "push_groups": "123456789,987654321",
  "enable_forward_message": true
}
```

### 常见问题

**Q1: 引用消息还是会触发识别？**  
A: 检查回复内容是否包含触发关键词（如"总结"、"看看"、"分析"等）。如果不想触发，回复简短内容即可（如"好的"、"收到"）。

**Q2: 想让引用消息触发识别？**  
A: 在回复中加入触发关键词，如"总结一下"、"帮我看看"、"分析一下"等。

**Q3: 视频处理太慢？**  
A: 开启 `prefer_subtitle: true`，有字幕的视频可节省30-60秒。

**Q4: 合并转发不显示？**  
A: 部分平台不支持合并转发，会自动回退到普通模式。

**Q5: 图片太长被截断？**  
A: 调整 `max_cards_per_image` 为更小的值（如 4 或 5），或开启 `enable_auto_split: true`。

**Q6: 想看详细日志？**  
A: 开启 `debug_mode: true`，可查看详细的消息过滤和处理日志。

**Q7: 智能搜索如何使用？**  
A: 直接与 AI 对话，如"搜索Python教程视频"、"下载播放量最高的3个视频并总结"。

## 🔎 致谢

本插件的核心总结流程（音频下载、字幕获取、Prompt 构建）参考了 **[BiliNote](https://github.com/JefferyHcool/BiliNote)** (by JefferyHcool)。

---

# 🇬🇧 English Documentation

## 🎉 What's New (v1.0.4)

- 🐛 **Fix crash on videos without subtitles** - Fixed UnboundLocalError for `extract_video_id` when using bcut transcription flow
- 🐛 **Fix short URL parsing error** - Fixed unterminated subpattern regex error when resolving b23.tv short links

[View Full Changelog](CHANGELOG.md)

## 📖 Introduction

**biliVideo** is an AstrBot plugin that generates AI-powered summaries for Bilibili videos.

Just send a Bilibili video link to your chat, and the plugin will automatically download the audio, extract subtitles, call your configured LLM, and generate a beautifully formatted summary — rendered as a stunning dark-themed card image.

You can also **subscribe to content creators** and receive automatic summary pushes whenever they upload new videos.

## 🏆 Core Features

| Feature | Description |
|---------|-------------|
| 🎨 **Image Rendering** | Summaries rendered as dual-column dark-themed card images |
| 🧠 **3 Summary Styles** | Concise / Detailed / Professional for different scenarios |
| 📡 **Auto Push** | Subscribe to creators, get summaries pushed automatically |
| 🔍 **Multi-format Input** | Accepts full URLs, short links, BV IDs, UIDs, space links, or creator names |
| ⏱️ **Timestamps** | Key moments marked with video timestamps for quick navigation |
| 🔐 **QR Login** | Login to Bilibili by scanning a QR code in chat |
| 🛡️ **Access Control** | Blacklist / whitelist modes |
| 📱 **Mini-App Detection** | Auto-detect Bilibili links shared in chat and push video info |
| 🤖 **AI Smart Search** | Search videos via natural conversation with AI, auto-transcribe and analyze |
| 📦 **Forward Message Mode** | Package video info and summary as chat history, clean and organized |
| 🎯 **Smart Message Filter** | Auto-detect quoted messages to avoid false triggers |
| ⚡ **Prefer Subtitles** | Use subtitles when available, saving 30-60s per video |
| 🎨 **Auto-split Long Videos** | Automatically split long summaries into multiple images |

## 📦 Installation

### Prerequisites

- [AstrBot](https://astrbot.app/) v4.0+
- At least one LLM Provider configured (e.g., DeepSeek, OpenAI, Claude)

### Installation Steps

**1. Install the Plugin**

Upload the plugin zip in AstrBot Admin → Plugin Management → Upload Plugin → Restart AstrBot

**2. Install System Dependencies**

```bash
# FFmpeg (required — for audio processing)
# Ubuntu/Debian
apt install -y ffmpeg

# macOS
brew install ffmpeg

# Windows
# Download FFmpeg and add to system PATH
# https://ffmpeg.org/download.html

# wkhtmltopdf (required for image output)
# Ubuntu/Debian
apt install -y wkhtmltopdf

# macOS
brew install wkhtmltopdf

# Windows
# Download installer and install
# https://wkhtmltopdf.org/downloads.html
```

**3. Login to Bilibili**

Send in chat:
```
/B站登录
```
Scan the QR code with the Bilibili mobile app.

**4. Start Using 🎉**
```
/总结 https://www.bilibili.com/video/BV1xx411c7mD
```

## 🔧 Commands

| Command | Description |
|---------|-------------|
| `/总结帮助` | Show help info and login status |
| `/总结 <video URL>` | Generate AI summary for a video |
| `/最新视频 <creator>` | Get latest video from a creator and summarize |
| `/B站登录` | QR code login to Bilibili |
| `/B站登出` | Logout from Bilibili |
| `/订阅 <creator>` | Subscribe to a creator for auto push |
| `/取消订阅 <creator>` | Unsubscribe |
| `/订阅列表` | View subscription list |
| `/检查更新` | Manually check for new videos |
| `/添加推送群 <group ID>` | Add a QQ group as push target |
| `/添加推送号 <QQ ID>` | Add a QQ user as push target |
| `/推送列表` | View push targets |
| `/移除推送 <ID>` | Remove a push target |
| `/识别开关` | Toggle auto-detect for Bilibili links |

## 📦 Forward Message Mode

Enable in plugin config:
```json
{
  "enable_forward_message": true
}
```

**Benefits:**
- ✅ Organized - Video info and summary packaged together
- ✅ Clean UI - Chat history card format
- ✅ Long content support - Auto-pagination
- ✅ Visual - Includes video cover image

## 🎯 Smart Message Filter

**Won't trigger detection:**
- Quote message with Bilibili link + reply `OK`
- Quote message with Bilibili link + reply `Got it`
- Quote message with Bilibili link + reply `@someone 1`
- Pure mention: `@someone`

**Will trigger detection:**
- Quote message with Bilibili link + reply `summarize this` (trigger keyword)
- Quote message with Bilibili link + reply `help me check` (trigger keyword)
- Quote any message + send Bilibili link
- Share Bilibili mini-app/link directly

### Trigger Keywords

When quoting a message with Bilibili video, detection only triggers if reply contains:

**Chinese keywords:**
```
总结、看看、看一下、看下、分析、讲的啥、讲什么、说的啥、说什么、
内容、视频、这个、这视频、帮我看、帮忙看、解析、翻译
```

**English keywords:**
```
summary、summarize、analyze、video、watch、check、see
```

**Example:**
```
User A: [Share Bilibili video]
User B: Quote A + "summarize this"  ✅ Trigger (keyword: summarize)
User C: Quote A + "OK"              ✅ No trigger (no keyword)
```

> **💡 Tip**: `<creator>` accepts numeric UID, space link URL, or creator nickname.
> When push targets are configured, summaries are sent **only** to those targets.

## 🤖 AI Smart Search

Search Bilibili videos, understand video content, and engage in deep conversations with AI - no commands needed.

### Usage

```
User: Search for Python tutorial videos
User: Download the top 3 videos by views and summarize them
User: Search videos about Genshin Impact, tell me what the traveler did
```

### How It Works

AI combines two tools automatically:

1. **bilibili_search_list**: Search videos and return list (with BV IDs)
2. **bilibili_search_download**: Download and transcribe video content by BV IDs

AI automatically continues processing when transcription is done. Transcripts saved to `/AstrBot/data/plugin_data/astrbot_plugin_bilivideo/search_results/`

### Related Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `default_count` | `20` | Default search list count |
| `default_download_count` | `3` | Suggested download count per batch |
| `search_max_concurrent` | `1` | Concurrent download/transcribe limit |

## ⚙️ Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `output_image` | `true` | Send summary as image |
| `note_style` | `professional` | Style: `concise` / `detailed` / `professional` |
| `enable_auto_push` | `false` | Enable automatic new video push |
| `auto_push_summary` | `true` | Generate summary on auto push; disable to send basic info only |
| `check_interval_minutes` | `600` | Check interval in minutes |
| `max_subscriptions` | `20` | Max subscriptions per group |
| `download_quality` | `fast` | Audio quality: `fast` / `medium` / `slow` |
| `push_groups` | empty | Push target QQ groups, comma-separated |
| `push_users` | empty | Push target QQ users, comma-separated |
| `access_mode` | `blacklist` | Group access control mode |
| `enable_miniapp_detect` | `false` | Auto-detect Bilibili links in chat |
| `detect_show_cover` | `true` | Show video cover in push |
| `detect_show_uploader` | `true` | Show uploader name in push |
| `detect_show_desc` | `true` | Show video description in push |
| `detect_show_pubtime` | `true` | Show publish time in push |
| `detect_show_link` | `true` | Show BV link in push |
| `detect_show_stats` | `true` | Show view/danmaku/like counts |
| `detect_auto_summary` | `false` | Auto-generate summary on link detect |
| `enable_forward_message` | `false` | Send summary as forward message (chat history) |
| `enable_auto_split` | `true` | Auto-split long videos into multiple images |
| `max_cards_per_image` | `6` | Max cards per image |
| `default_count` | `20` | Default search list count |
| `default_download_count` | `3` | Suggested download count per batch |
| `search_max_concurrent` | `1` | Concurrent download/transcribe limit |
| `search_show_progress` | `true` | Show download progress in smart search |
| `prefer_subtitle` | `true` | Prefer subtitles (auto fallback to audio transcription) |
| `debug_mode` | `false` | Enable debug logging |

## ⚠️ Notes

- Must run `/B站登录` before first use
- Requires an LLM Provider configured in AstrBot
- Summary generation takes ~1-3 minutes per video (faster with subtitles)
- Falls back to plain text if image rendering fails
- When quoting messages, only detects links in user's actual content, not quoted content
- When quoting messages with videos, reply must contain trigger keywords (e.g., "summarize", "check") to parse
- Forward message mode requires platform support (some platforms may not support it)
- Enabling `prefer_subtitle` significantly improves processing speed, but some videos may not have subtitles

## 💡 Usage Tips

### Recommended Configurations

**Basic Configuration (Recommended for Beginners):**
```json
{
  "output_image": true,
  "note_style": "professional",
  "prefer_subtitle": true,
  "enable_miniapp_detect": true,
  "detect_auto_summary": false
}
```

**Advanced Configuration (Recommended for Groups):**
```json
{
  "output_image": true,
  "note_style": "professional",
  "prefer_subtitle": true,
  "enable_miniapp_detect": true,
  "detect_auto_summary": false,
  "enable_forward_message": true,
  "enable_auto_split": true,
  "max_cards_per_image": 6
}
```

**Subscription Push Configuration:**
```json
{
  "enable_auto_push": true,
  "check_interval_minutes": 600,
  "max_subscriptions": 20,
  "push_groups": "123456789,987654321",
  "enable_forward_message": true
}
```

### FAQ

**Q1: Quoted messages still trigger detection?**  
A: Check if the reply contains trigger keywords (e.g., "summarize", "check", "analyze"). To avoid triggering, reply with short content (e.g., "OK", "Got it").

**Q2: Want quoted messages to trigger detection?**  
A: Include trigger keywords in your reply, such as "summarize this", "help me check", "analyze this".

**Q3: Video processing too slow?**  
A: Enable `prefer_subtitle: true`, videos with subtitles can save 30-60 seconds.

**Q4: Forward message not showing?**  
A: Some platforms don't support forward messages, will automatically fallback to normal mode.

**Q5: Image too long and truncated?**  
A: Adjust `max_cards_per_image` to a smaller value (e.g., 4 or 5), or enable `enable_auto_split: true`.

**Q6: Want to see detailed logs?**  
A: Enable `debug_mode: true` to view detailed message filtering and processing logs.

**Q7: How to use smart search?**  
A: Talk directly with AI, e.g., "Search for Python tutorial videos", "Download the top 3 videos by views and summarize them".

## 🔎 Credits

Core summarization flow (audio download, subtitle extraction, prompt building) is based on **[BiliNote](https://github.com/JefferyHcool/BiliNote)** by JefferyHcool.

---
