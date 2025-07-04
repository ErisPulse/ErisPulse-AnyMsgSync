# AnyMsgSync

一个基于 [ErisPulse SDK](https://github.com/ErisPulse/ErisPulse) 的跨平台消息同步方案，支持 **QQ群 ↔ 云湖群 ↔ Telegram群** 的多向消息同步。

该项目由 **ErisPulse SDK 社区团队直接维护**，将第一时间适配 SDK 最新功能与优化，保障长期更新与技术支持。

---

## 功能特性

- 支持 QQ、云湖、Telegram 平台之间的双向实时消息同步
- 消息格式转换（text / html / markdown）
- 跨平台消息撤回同步
- 支持 webhook + 反向代理部署，便于公网访问
- 模块化设计，按需安装适配器

---

## 安装与初始化

### 1. 安装 ErisPulse SDK

```bash
pip install ErisPulse
```

### 2. 更新内置官方源

```bash
epsdk update
```

### 3. 安装模块与适配器（按需）

```bash
epsdk install AnyMsgSync           # 必须：核心同步模块

# 以下为可选模块，根据需要安装：
epsdk install OneBotAdapter       # QQ 同步支持
epsdk install YunhuAdapter        # 云湖 同步支持
epsdk install TelegramAdapter     # Telegram 同步支持
```

---

## 配置说明

在项目根目录创建或修改 `env.py` 文件进行配置。

### 示例完整配置如下：

```python
from ErisPulse import sdk

# QQ 适配器配置（OneBot）
sdk.env.set("OneBotAdapter", {
    "mode": "client",
    "server": {
        "host": "127.0.0.1",
        "port": 3001,
        "path": "/",
        "token": ""
    },
    "client": {
        "url": "ws://127.0.0.1:3001",
        "token": ""
    }
})

# 云湖适配器配置
sdk.env.set("YunhuAdapter", {
    "token": "你的云湖 Token",
    "server": {
        "host": "127.0.0.1",
        "port": 5888,
        "path": "/webhook"
    }
})

# Telegram 适配器配置
sdk.env.set("TelegramAdapter", {
    "token": "你的 Telegram Bot Token",
    "mode": "polling",

    "server": {
        "host": "127.0.0.1",
        "port": 8443,
        "path": "/telegram/webhook"
    },

    "webhook": {
        "host": "tme.wsu2059.workers.dev",
        "port": 443,
        "path": "/telegram/webhook"
    },

    "proxy": {
        "type": "socks5",
        "host": "127.0.0.1",
        "port": 7898
    }
})

# 群组映射关系配置
sdk.env.set("AnyMsgSync", {
    "qq": {
        "QQ群ID1": [
            {"type": "yunhu", "group_id": "Yunhu群ID1", "format": "html"},
            {"type": "telegram", "group_id": -1001234567890, "format": "markdown"}
        ]
    },
    "yunhu": {
        "Yunhu群ID1": [
            {"type": "qq", "group_id": "QQ群ID1", "format": "text"},
            {"type": "telegram", "group_id": -1001234567890, "format": "markdown"}
        ]
    },
    "telegram": {
        "-1001234567890": [
            {"type": "qq", "group_id": "QQ群ID1", "format": "text"},
            {"type": "yunhu", "group_id": "Yunhu群ID1", "format": "html"}
        ]
    }
})
```

> 建议搭配 [NapCat](https://github.com/NapNeko/NapCatQQ) 使用 QQ 协议，以获得更稳定的连接体验。

---

## 启动服务

在项目根目录运行主程序：

```bash
python main.py
```

### 示例 main.py 内容：

```python
from ErisPulse import sdk
import asyncio

async def main():
    sdk.init()
    try:
        await sdk.adapter.startup()
        if hasattr(sdk, "AnyMsgSync"):
            await sdk.AnyMsgSync.start()
        await asyncio.Event().wait()

    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        await sdk.adapter.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
```

## 参考链接
- [ErisPulse 主库](https://github.com/ErisPulse/ErisPulse/)

---

## 💔 悼念 Amer 同步机器人

<div style="background-color: #f9f9f9; border: 1px solid #ddd; border-radius: 10px; padding: 20px; font-family: Arial, sans-serif; box-shadow: 0 2px 5px rgba(0,0,0,0.1);">
    <h4 style="color: #333; margin-bottom: 15px;">致敬 Amer</h4>
    <p>Amer 曾为多个群组提供稳定的消息同步服务，为开源社区做出了重要贡献。感谢它一直以来的努力与陪伴。</p>
    <p>Amer 开源项目地址：<a href="Amer">http://github.com/wsu2059q/amer</a></p>
</div>

