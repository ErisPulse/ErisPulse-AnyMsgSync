import asyncio
from ErisPulse import sdk


class Main:
    def __init__(self, sdk):
        self.sdk = sdk
        self.logger = sdk.logger

        # 初始化配置
        self._init_config()
        self.message_handlers = {
            "text": lambda data: data["text"],
            "image": lambda data: f"<img src='{data['url']}' style='max-width: 100%;'>",
            "at": lambda data: f"<span style='color:#007bff;'>@{data.get('qq', 'someone')}</span> ",
            "face": lambda data: f"<img src='https://koishi.js.org/QFace/assets/qq_emoji/thumbs/gif_{data['id']}.gif' style='width:24px;height:24px;vertical-align:middle;' />",
            "voice": lambda data: f"<audio src='{data['url']}' controls></audio>",
            "video": lambda data: f"<video src='{data['url']}' controls style='max-width: 100%;'></video>",
            "forward": lambda data: "".join(self.build_message_content(data.get("messages", []))),
            "reply": lambda data: "<div class='reply'>回复</div>",
        }
    def _init_config(self):
        qq_to_yunhu = self.sdk.env.get("QQ_TO_YUNHU_GROUP_MAP", {})
        yunhu_to_qq = self.sdk.env.get("YUNHU_TO_QQ_GROUP_MAP", {})

        if not qq_to_yunhu and not yunhu_to_qq:
            self.logger.info("""
请使用以下命令配置 QQ 和 Yunhu 群组映射关系:
    sdk.env.set("QQ_TO_YUNHU_GROUP_MAP", {"QQ群ID": "Yunhu群ID"})
    sdk.env.set("YUNHU_TO_QQ_GROUP_MAP", {"Yunhu群ID": "QQ群ID"})
""")

        self.qq_to_yunhu_group_map = self.sdk.env.get("QQ_TO_YUNHU_GROUP_MAP")
        self.yunhu_to_qq_group_map = self.sdk.env.get("YUNHU_TO_QQ_GROUP_MAP")

    async def start(self):
        self.logger.info("AnySync 模块启动中...")
        try:
            await self._setup_message_handlers()
        except Exception as e:
            self.logger.error(f"AnySync 启动失败: {e}")

    async def _setup_message_handlers(self):
        @self.sdk.adapter.QQ.on("message")
        async def forward_qq_to_yunhu(message):
            group_id = message.get("group_id")
            yunhu_group_id = self.qq_to_yunhu_group_map.get(str(group_id))
            if not yunhu_group_id:
                self.logger.warning(f"未配置对应的 Yunhu 群 | QQ群ID: {group_id}")
                return

            reply_data = next((item for item in message.get("message", []) if item["type"] == "reply"), None)
            qq_original_msg_id = str(reply_data.get("data", {}).get("id")) if reply_data else None

            sender = message.get("sender", {})
            user_id = sender.get("user_id", "未知ID")
            nickname = sender.get("nickname", "未知用户")

            message_parts = message.get("message", [])
            user_info_html = self.build_user_info(sender, user_id, nickname)
            message_html = self.build_message_content(message_parts)
            full_html = user_info_html + message_html

            parent_id = ""
            if qq_original_msg_id:
                mapping = self.sdk.env.get("message_id_map", {"qq_to_yunhu": {}, "yunhu_to_qq": {}})
                mapped_data = mapping["qq_to_yunhu"].get(qq_original_msg_id)
                if mapped_data:
                    yunhu_parent_id, _ = mapped_data
                    parent_id = yunhu_parent_id
                    self.logger.info(f"[QQ→Yunhu] 使用映射 parent_id: {parent_id} (来自 QQ msgId: {qq_original_msg_id})")
                else:
                    self.logger.warning(f"[QQ→Yunhu] 未找到对应 Yunhu 消息 | 原始QQ msgId: {qq_original_msg_id}")

            res = await self.sdk.adapter.Yunhu.send(
                "group",
                yunhu_group_id,
                full_html,
                content_type="html",
                parent_id=parent_id
            )
            self.logger.info(f"[QQ→Yunhu] 已发送至群 {yunhu_group_id} | 响应: {res}")

            yunhu_msg_id = res.get("data", {}).get("messageInfo", {}).get("msgId")
            qq_msg_id = message.get("message_id")

            if qq_msg_id and yunhu_msg_id:
                self.add_message_id_mapping(
                    qq_msg_id=qq_msg_id,
                    yunhu_msg_id=yunhu_msg_id,
                    qq_group_id=group_id,
                    yunhu_group_id=yunhu_group_id
                )
        def build_yunhu_text_message(self, yunhu_user, content):
            nickname = yunhu_user.get("senderNickname", "未知用户")
            sender_id = yunhu_user.get("senderId", "未知ID")
            return f"[来自 Yunhu] {nickname}({sender_id}): {content}"

        @self.sdk.adapter.Yunhu.on("message")
        async def forward_yunhu_to_qq(message):
            yunhu_event = message.get("event", {})
            yunhu_msg = yunhu_event.get("message", {})
            yunhu_user = yunhu_event.get("sender", {})
            content = yunhu_msg.get("content", {}).get("text", "")
            yunhu_group_id = yunhu_msg.get("chatId")

            qq_group_id = self.yunhu_to_qq_group_map.get(str(yunhu_group_id))
            if not qq_group_id:
                self.logger.warning(f"未配置对应的 QQ 群 | Yunhu群ID: {yunhu_group_id}")
                return

            text_message = self.build_yunhu_text_message(yunhu_user, content)

            res = await self.sdk.adapter.QQ.send("group", qq_group_id, text_message)
            self.logger.info(f"[Yunhu→QQ] 已发送至群 {qq_group_id} | 响应: {res}")

            yunhu_msg_id = yunhu_msg.get("msgId")
            qq_msg_id = res.get("message_id")

            if qq_msg_id and yunhu_msg_id:
                self.add_message_id_mapping(
                    qq_msg_id=qq_msg_id,
                    yunhu_msg_id=yunhu_msg_id,
                    qq_group_id=qq_group_id,
                    yunhu_group_id=yunhu_group_id
                )

        @self.sdk.adapter.QQ.on("notice")
        async def handle_qq_notice(notice):
            notice_type = notice.get("notice_type")
            if notice_type == "group_recall":
                group_id = notice.get("group_id")
                user_id = notice.get("user_id")
                operator_id = notice.get("operator_id")
                message_id = notice.get("message_id")

                if user_id != operator_id:
                    return  # 不是自己撤回的不处理

                mapping = self.sdk.env.get("message_id_map", {"qq_to_yunhu": {}, "yunhu_to_qq": {}})
                mapped_data = mapping["qq_to_yunhu"].get(str(message_id))

                if not mapped_data:
                    return

                yunhu_msg_id, yunhu_group_id = mapped_data

                if yunhu_msg_id and yunhu_group_id:
                    res = await self.sdk.adapter.Yunhu.recall(yunhu_msg_id, "group", yunhu_group_id)
                    self.logger.info(f"[Yunhu] 已同步撤回消息 {yunhu_msg_id} | 响应: {res}")

        self.logger.info("AnySync 消息处理器已注册")

    def build_user_info(self, sender, user_id, nickname):
        avatar_url = f"https://q1.qlogo.cn/g?b=qq&nk={user_id}&s=640"
        return f"""
<div style="display: flex; align-items: center; justify-content: space-between; padding: 10px; background: #ffffff; color: #333333; border-radius: 8px;">
    <div style="display: flex; align-items: center;">
        <img src="{avatar_url}" alt="用户头像" style="width: 36px; height: 36px; border-radius: 50%; margin-right: 10px;">
        <div>
            <strong>{nickname}</strong><br>
            <small style="font-size: 12px; color: #888;">用户ID: {user_id}</small>
        </div>
    </div>
    <div style="padding: 5px; background-color: #e0f7fa; color: #00796b; font-size: 12px; font-weight: bold; border-radius: 4px;">
        来自: QQ
    </div>
</div>
"""

    def build_message_content(self, parts):
        content = []
        for part in parts:
            msg_type = part.get("type")
            if msg_type not in self.message_handlers:
                self.sdk.logger.warning(f"未知消息类型: {msg_type}, 数据: {part}")
                content.append(f"[不支持的消息类型: {msg_type}]")
                continue
            try:
                handler = self.message_handlers[msg_type]
                content.append(handler(part.get("data", {})))
            except Exception as e:
                self.sdk.logger.error(f"处理消息类型 {msg_type} 出错: {e}")
                content.append(f"[处理失败: {msg_type}]")
        return f"""
<div style="padding: 10px; background: #f1f1f1; color: #000000; border-radius: 6px; margin-top: 5px;">
    {''.join(content)}
</div>
"""

    def add_message_id_mapping(self, *, qq_msg_id=None, yunhu_msg_id=None, qq_group_id=None, yunhu_group_id=None):
        if not qq_msg_id or not yunhu_msg_id or not qq_group_id or not yunhu_group_id:
            return

        mapping = self.sdk.env.get("message_id_map", {
            "qq_to_yunhu": {},
            "yunhu_to_qq": {}
        })

        mapping["qq_to_yunhu"][str(qq_msg_id)] = (yunhu_msg_id, yunhu_group_id)
        mapping["yunhu_to_qq"][yunhu_msg_id] = (qq_msg_id, qq_group_id)

        self.sdk.env.set("message_id_map", mapping)

    def get_original_platform(self, msg_id):
        mapping = self.sdk.env.get("message_id_map", {"qq_to_yunhu": {}, "yunhu_to_qq": {}})
        if str(msg_id) in mapping["qq_to_yunhu"]:
            return "yunhu"
        elif msg_id in mapping["yunhu_to_qq"]:
            return "qq"
        else:
            return None