# AnySync 使用指南

本项目基于 [ErisPulse SDK](https://github.com/ErisPulse/ErisPulse) 实现 QQ 与 云湖群之间的消息同步功能。以下是完整的使用步骤：

---

## 安装与初始化

### 1. 安装 ErisPulse SDK
```bash
pip install ErisPulse
```

### 2. 添加官方源
```bash
epsdk origin add https://sdkframe.anran.xyz
```
CLI 会提示是否更新 SDK，建议选择更新以获得最新功能和修复。

### 3. 安装适配器与同步模块
```bash
epsdk install OneBotAdapter YunhuAdapter AnyMsgSync
```

---

## 💔 悼念 Amer 同步机器人

<div style="background-color: #f9f9f9; border: 1px solid #ddd; border-radius: 10px; padding: 20px; font-family: Arial, sans-serif; box-shadow: 0 2px 5px rgba(0,0,0,0.1);">
    <h4 style="color: #333; margin-bottom: 15px;">致敬 Amer</h4>
    <p>Amer 曾为多个群组提供稳定的消息同步服务，为开源社区做出了重要贡献。感谢它一直以来的努力与陪伴。</p>
    <p>Amer 开源项目地址：<a href="http://github.com/wsu2059q/amer">http://github.com/wsu2059q/amer</a></p>
</div>

---

## 配置说明

### 1. 修改 env.py 文件

请根据以下结构配置你的环境参数：

```python
from ErisPulse import sdk

# OneBot 配置
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

# 云湖配置
sdk.env.set("YunhuAdapter", {
    "token": "2439e944a5434716b6d4056c7029a0ab",
    "server": {
        "host": "127.0.0.1",
        "port": 5888,
        "path": "/webhook"
    }
})

# 群组映射配置
sdk.env.set("QQ_TO_YUNHU_GROUP_MAP", {"QQ群ID": {"group_id": "Yunhu群ID", "format": "html"}})
sdk.env.set("YUNHU_TO_QQ_GROUP_MAP", {"Yunhu群ID": {"group_id": "QQ群ID", "format": "text"}})

```

---

## 启动服务

在项目根目录下运行主程序：

```bash
python main.py
```

---

# 推荐使用 NapCat 作为 OneBot 适配器的连接方式

NapCat 是一个现代化的基于 NTQQ 的 Bot 协议端实现，我们强烈推荐使用 NapCat 来连接 QQ。

前往 [NapCat Release 页面](https://github.com/NapNeko/NapCatQQ/releases) 下载最新版本。
首次使用请务必查看官方文档了解详细使用教程。
