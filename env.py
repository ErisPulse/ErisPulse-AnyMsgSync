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

sdk.env.set("QQ_TO_YUNHU_GROUP_MAP", {"782199153": "785017366"})  # QQ群ID -> Yunhu群ID
sdk.env.set("YUNHU_TO_QQ_GROUP_MAP", {"785017366": "782199153"})  # Yunhu群ID -> QQ群ID
