import asyncio
import json
from ErisPulse import sdk
from .MessageBuilders.QQMessageBuilder import QQMessageBuilder
from .MessageBuilders.YunhuMessageBuilder import YunhuMessageBuilder
from .MessageBuilders.TelegramMessageBuilder import TelegramMessageBuilder  # 新增 Telegram 构建器导入


class Main:
    def __init__(self, sdk):
        self.sdk = sdk
        self.logger = sdk.logger

        # 初始化配置
        self._init_config()

        # 注册消息构建器
        self.message_builders = {
            "QQ": QQMessageBuilder(self),
            "Yunhu": YunhuMessageBuilder(self),
            "Telegram": TelegramMessageBuilder(self)
        }

    def parse_message_to_dict(self, message):
        if isinstance(message, dict):
            return message
        elif isinstance(message, str):
            try:
                return json.loads(message)
            except json.JSONDecodeError:
                self.logger.error("无法解析消息为字典，JSON 格式错误")
                return {}
        else:
            self.logger.warning(f"未知消息类型: {type(message)}")
            return {}

    def _init_config(self):
        self.qq_to = self.sdk.env.get("QQ_TO", {})
        self.yunhu_to = self.sdk.env.get("YUNHU_TO", {})
        self.telegram_to = self.sdk.env.get("TELEGRAM_TO", {})

        if not (self.qq_to or self.yunhu_to or self.telegram_to):
            self.logger.info("""
请使用以下命令配置跨平台群组映射关系:

示例：
sdk.env.set("QQ_TO", {
    "QQ群ID1": [
        {"type": "yunhu", "group_id": "Yunhu群ID1", "format": "html"},
        {"type": "telegram", "group_id": -1001234567890, "format": "markdown"}
    ]
})

sdk.env.set("YUNHU_TO", {
    "Yunhu群ID1": [
        {"type": "qq", "group_id": "QQ群ID1", "format": "text"},
        {"type": "telegram", "group_id": -1001234567890, "format": "markdown"}
    ]
})

sdk.env.set("TELEGRAM_TO", {
    "-1001234567890": [
        {"type": "qq", "group_id": "QQ群ID1", "format": "text"},
        {"type": "yunhu", "group_id": "Yunhu群ID1", "format": "html"}
    ]
})
""")

    async def start(self):
        self.logger.info("AnyMsgSync 模块启动中...")
        try:
            await self._setup_message_handlers()
        except Exception as e:
            self.logger.error(f"AnyMsgSync 启动失败: {e}")

    async def _setup_message_handlers(self):

        @self.sdk.adapter.QQ.on("message")
        async def forward_qq_to_other(message):
            message = self.parse_message_to_dict(message)
            group_id = message.get("group_id")
            mappings = self.qq_to.get(str(group_id))

            if not mappings:
                self.logger.warning(f"未配置对应的转发目标 | QQ群ID: {group_id}")
                return

            for mapping in mappings:
                target_type = mapping["type"]
                target_group_id = mapping["group_id"]
                msg_format = mapping.get("format", "text")

                builder = self.message_builders["QQ"]
                handler_method = getattr(builder, f"build_{msg_format}", None)
                if not handler_method:
                    self.logger.warning(f"不支持的消息格式: {msg_format}")
                    continue

                full_content = await handler_method(message)

                try:
                    res = await getattr(self.sdk.adapter[target_type].Send.To("group", target_group_id), msg_format.capitalize())(full_content)
                    self.logger.info(f"[QQ→{target_type.capitalize()}] 已发送至群 {target_group_id} | 响应: {res}")
                except Exception as e:
                    self.logger.error(f"[QQ→{target_type.capitalize()}] 发送失败: {e}")

                # 记录消息 ID 映射
                qq_msg_id = message.get("message_id")
                other_msg_id = res.get("message_id") or res.get("data", {}).get("messageInfo", {}).get("msgId")
                if qq_msg_id and other_msg_id:
                    self.add_message_id_mapping(
                        qq_msg_id=qq_msg_id,
                        **{f"{target_type.lower()}_msg_id": other_msg_id},
                        qq_group_id=group_id,
                        **{f"{target_type.lower()}_group_id": target_group_id}
                    )

        @self.sdk.adapter.Yunhu.on("message")
        async def forward_yunhu_to_other(message):
            message = self.parse_message_to_dict(message)
            yunhu_event = message.get("event", {})
            yunhu_msg = yunhu_event.get("message", {})
            yunhu_group_id = yunhu_msg.get("chatId")
            mappings = self.yunhu_to.get(str(yunhu_group_id))

            if not mappings:
                self.logger.warning(f"未配置对应的转发目标 | Yunhu群ID: {yunhu_group_id}")
                return

            for mapping in mappings:
                target_type = mapping["type"]
                target_group_id = mapping["group_id"]
                msg_format = mapping.get("format", "text")

                builder = self.message_builders["Yunhu"]
                handler_method = getattr(builder, f"build_{msg_format}", None)
                if not handler_method:
                    self.logger.warning(f"不支持的消息格式: {msg_format}")
                    continue

                full_content = await handler_method(message)

                try:
                    res = await getattr(self.sdk.adapter[target_type].Send.To("group", target_group_id), msg_format.capitalize())(full_content)
                    self.logger.info(f"[Yunhu→{target_type.capitalize()}] 已发送至群 {target_group_id} | 响应: {res}")
                except Exception as e:
                    self.logger.error(f"[Yunhu→{target_type.capitalize()}] 发送失败: {e}")

                # 记录消息 ID 映射
                yunhu_msg_id = yunhu_msg.get("msgId")
                other_msg_id = res.get("message_id") or res.get("data", {}).get("messageInfo", {}).get("msgId")
                if yunhu_msg_id and other_msg_id:
                    self.add_message_id_mapping(
                        yunhu_msg_id=yunhu_msg_id,
                        **{f"{target_type.lower()}_msg_id": other_msg_id},
                        yunhu_group_id=yunhu_group_id,
                        **{f"{target_type.lower()}_group_id": target_group_id}
                    )

        @self.sdk.adapter.Telegram.on("message")
        async def forward_telegram_to_other(message):
            message = self.parse_message_to_dict(message)
            chat = message.get("chat", {})
            chat_id = chat.get("id")
            mappings = self.telegram_to.get(str(chat_id))

            if not mappings:
                self.logger.warning(f"未配置对应的转发目标 | Telegram群ID: {chat_id}")
                return

            for mapping in mappings:
                target_type = mapping["type"]
                target_group_id = mapping["group_id"]
                msg_format = mapping.get("format", "text")

                builder = self.message_builders["Telegram"]
                handler_method = getattr(builder, f"build_{msg_format}", None)
                if not handler_method:
                    self.logger.warning(f"不支持的消息格式: {msg_format}")
                    continue

                full_content = await handler_method(message)

                try:
                    res = await getattr(self.sdk.adapter[target_type].Send.To("group", target_group_id), msg_format.capitalize())(full_content)
                    self.logger.info(f"[Telegram→{target_type.capitalize()}] 已发送至群 {target_group_id} | 响应: {res}")
                except Exception as e:
                    self.logger.error(f"[Telegram→{target_type.capitalize()}] 发送失败: {e}")

                # 记录消息 ID 映射
                telegram_msg_id = message.get("message_id")
                other_msg_id = res.get("message_id") or res.get("data", {}).get("messageInfo", {}).get("msgId")
                if telegram_msg_id and other_msg_id:
                    self.add_message_id_mapping(
                        telegram_msg_id=telegram_msg_id,
                        **{f"{target_type.lower()}_msg_id": other_msg_id},
                        telegram_group_id=chat_id,
                        **{f"{target_type.lower()}_group_id": target_group_id}
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

                mapping_table = self.sdk.env.get("message_id_map", {"qq_to_yunhu": {}, "yunhu_to_qq": {}, "qq_to_telegram": {}, "telegram_to_qq": {}})
                mapped_data = mapping_table["qq_to_yunhu"].get(str(message_id)) or \
                              mapping_table["qq_to_telegram"].get(str(message_id))

                if not mapped_data:
                    return

                other_msg_id, other_group_id = mapped_data

                if "yunhu" in str(mapped_data):
                    res = await self.sdk.adapter.Yunhu.Send.To("group", other_group_id).Recall(other_msg_id)
                    self.logger.info(f"[Yunhu] 已同步撤回消息 {other_msg_id} | 响应: {res}")
                elif "telegram" in str(mapped_data):
                    res = await self.sdk.adapter.Telegram.Send.To("group", other_group_id).DeleteMessage(other_msg_id)
                    self.logger.info(f"[Telegram] 已同步删除消息 {other_msg_id} | 响应: {res}")

        self.logger.info("AnyMsgSync 消息处理器已注册")

    def add_message_id_mapping(self, *, qq_msg_id=None, yunhu_msg_id=None, telegram_msg_id=None, qq_group_id=None, yunhu_group_id=None, telegram_group_id=None):
        if not any([qq_msg_id, yunhu_msg_id, telegram_msg_id]):
            return

        mapping = self.sdk.env.get("message_id_map", {
            "qq_to_yunhu": {},
            "yunhu_to_qq": {},
            "qq_to_telegram": {},
            "telegram_to_qq": {},
        })

        if qq_msg_id and yunhu_msg_id and yunhu_group_id:
            mapping["qq_to_yunhu"][str(qq_msg_id)] = (yunhu_msg_id, yunhu_group_id)
            mapping["yunhu_to_qq"][yunhu_msg_id] = (qq_msg_id, qq_group_id)

        if qq_msg_id and telegram_msg_id and telegram_group_id:
            mapping["qq_to_telegram"][str(qq_msg_id)] = (telegram_msg_id, telegram_group_id)
            mapping["telegram_to_qq"][telegram_msg_id] = (qq_msg_id, qq_group_id)

        if telegram_msg_id and yunhu_msg_id and telegram_group_id and yunhu_group_id:
            mapping["telegram_to_yunhu"][telegram_msg_id] = (yunhu_msg_id, yunhu_group_id)
            mapping["yunhu_to_telegram"][yunhu_msg_id] = (telegram_msg_id, telegram_group_id)

        self.sdk.env.set("message_id_map", mapping)

    def get_original_platform(self, msg_id):
        mapping = self.sdk.env.get("message_id_map", {
            "qq_to_yunhu": {},
            "yunhu_to_qq": {},
            "qq_to_telegram": {},
            "telegram_to_qq": {},
        })
        if str(msg_id) in mapping["qq_to_yunhu"] or str(msg_id) in mapping["qq_to_telegram"]:
            return "qq"
        elif msg_id in mapping["yunhu_to_qq"] or msg_id in mapping["yunhu_to_telegram"]:
            return "yunhu"
        elif msg_id in mapping["telegram_to_qq"] or msg_id in mapping["telegram_to_yunhu"]:
            return "telegram"
        else:
            return None