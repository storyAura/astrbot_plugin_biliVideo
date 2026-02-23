<div align="center">
  <img src="logo.png" alt="biliVideo" width="100" height="100" style="border-radius: 20px;" />
  <h1>biliVideo 视频总结</h1>
  <p><b>丢个B站链接，AI 帮你秒出精华总结</b></p>

  <br/>

  <img src="https://img.shields.io/badge/version-v1.0.0-blue" />
  <img src="https://img.shields.io/badge/AstrBot-v4.0+-green" />
  <img src="https://img.shields.io/badge/platform-Bilibili-ff69b4" />
  <img src="https://img.shields.io/badge/license-MIT-orange" />
</div>

<br/>

> **🇨🇳 [中文](#-中文文档)** &nbsp;|&nbsp; **🇬🇧 [English](#-english-documentation)**

---

# 🇨🇳 中文文档

## 📖 简介

**biliVideo** 是一款运行在 [AstrBot]((https://astrbot.app/)) 上的 B站视频总结插件。

你只需要丢一个B站视频链接，插件就会自动下载音频、提取字幕、调用 AI 大模型，生成一份结构化的视频总结 —— 并渲染成精美的暗色主题卡片图片发送到群聊。

不仅如此，你还可以 **订阅 UP 主**，新视频发布时自动推送总结到群里，再也不怕错过喜欢的 UP 的内容了。

## 🏆 biliVideo

| 优势 | 说明 |
|------|------|
| 🎨 **图片渲染输出** | 总结渲染为双栏暗色卡片图片，清晰美观 |
| 🧠 **三种总结风格** | 简洁 / 详细 / 专业，适用于不同场景 |
| 📡 **订阅自动推送** | 订阅 UP 主，新视频自动推送总结 |
| 🔍 **多格式输入** | 支持完整链接、短链、BV号、UID、空间链接、UP主昵称 |
| ⏱️ **时间戳标记** | 总结中标注视频对应时间点，便于跳转定位 |
| 🔐 **扫码登录** | 在聊天中扫码登录B站，无需手动填写 Cookie |
| 🛡️ **群聊权限控制** | 支持黑名单 / 白名单模式 |

## 📦 安装

### 前置要求

- [AstrBot]((https://astrbot.app/)) v4.0+
- 已配置至少一个 LLM Provider（如 DeepSeek、OpenAI 等）

### 步骤

**1. 安装插件**

在 AstrBot 管理面板 → 插件管理 → 上传插件 zip 包

**2. 安装系统依赖**

```bash
# FFmpeg（必须 — 用于音频处理）
apt install -y ffmpeg

# wkhtmltopdf（开启图片输出时需要）
apt install -y wkhtmltopdf
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
```

## ⚙️ 配置项

在 AstrBot 管理面板 → 插件配置中可设置：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `output_image` | `true` | 总结以图片形式发送 |
| `note_style` | `professional` | 总结风格：`concise` / `detailed` / `professional` |
| `enable_link` | `true` | 嵌入时间戳标记 |
| `enable_summary` | `true` | 末尾添加 AI 总结段落 |
| `download_quality` | `fast` | 音频质量：`fast` / `medium` / `slow` |
| `enable_auto_push` | `false` | 启用自动推送新视频总结 |
| `check_interval_minutes` | `600` | 定时检查间隔（分钟） |
| `max_subscriptions` | `20` | 每个群最大订阅数 |
| `max_note_length` | `3000` | 总结最大字符数 |
| `push_groups` | 空 | 推送QQ群列表，逗号分隔 |
| `push_users` | 空 | 推送QQ号列表，逗号分隔 |
| `access_mode` | `blacklist` | 群聊访问控制模式 |
| `group_list` | 空 | 群号列表，逗号分隔 |
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
- 视频总结生成约需 1-3 分钟
- 图片渲染失败时会自动回退到纯文本

## 🔎 致谢

本插件的核心总结流程（音频下载、字幕获取、Prompt 构建）参考了 **[BiliNote](https://github.com/JefferyHcool/BiliNote)** (by JefferyHcool)。

---

# 🇬🇧 English Documentation

## 📖 Introduction

**biliVideo** is an AstrBot plugin that generates AI-powered summaries for Bilibili videos.

Just send a Bilibili video link to your chat, and the plugin will automatically download the audio, extract subtitles, call your configured LLM, and generate a beautifully formatted summary — rendered as a stunning dark-themed card image.

You can also **subscribe to content creators** and receive automatic summary pushes whenever they upload new videos.

## 🏆 biliVideo

| Advantage | Description |
|-----------|-------------|
| 🎨 **Image Rendering** | Summaries rendered as dual-column dark-themed card images |
| 🧠 **3 Summary Styles** | Concise / Detailed / Professional for different scenarios |
| 📡 **Auto Push** | Subscribe to creators, get summaries pushed automatically |
| 🔍 **Multi-format Input** | Accepts full URLs, short links, BV IDs, UIDs, space links, or creator names |
| ⏱️ **Timestamps** | Key moments marked with video timestamps for quick navigation |
| 🔐 **QR Login** | Login to Bilibili by scanning a QR code in chat |
| 🛡️ **Access Control** | Blacklist / whitelist modes |

## 📦 Installation

### Prerequisites

- [AstrBot]((https://astrbot.app/)) v4.0+
- At least one LLM Provider configured (e.g., DeepSeek, OpenAI)

### Steps

**1. Install the Plugin**

Upload the plugin zip in AstrBot Admin → Plugin Management → Restart AstrBot

**2. Install System Dependencies**

```bash
# FFmpeg (required — for audio processing)
apt install -y ffmpeg

# wkhtmltopdf (required for image output)
apt install -y wkhtmltopdf
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

> **💡 Tip**: `<creator>` accepts numeric UID, space link URL, or creator nickname.
> When push targets are configured, summaries are sent **only** to those targets.

## ⚙️ Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `output_image` | `true` | Send summary as image |
| `note_style` | `professional` | Style: `concise` / `detailed` / `professional` |
| `enable_auto_push` | `false` | Enable automatic new video push |
| `check_interval_minutes` | `600` | Check interval in minutes |
| `max_subscriptions` | `20` | Max subscriptions per group |
| `download_quality` | `fast` | Audio quality: `fast` / `medium` / `slow` |
| `push_groups` | empty | Push target QQ groups, comma-separated |
| `push_users` | empty | Push target QQ users, comma-separated |
| `access_mode` | `blacklist` | Group access control mode |
| `debug_mode` | `false` | Enable debug logging |

## ⚠️ Notes

- Must run `/B站登录` before first use
- Requires an LLM Provider configured in AstrBot
- Summary generation takes ~1-3 minutes per video
- Falls back to plain text if image rendering fails

## 🔎 Credits

Core summarization flow (audio download, subtitle extraction, prompt building) is based on **[BiliNote](https://github.com/JefferyHcool/BiliNote)** by JefferyHcool.

---
