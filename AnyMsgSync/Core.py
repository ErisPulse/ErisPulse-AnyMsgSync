import asyncio
import json
from ErisPulse import sdk
from .MessageBuilders.QQMessageBuilder import QQMessageBuilder
from .MessageBuilders.YunhuMessageBuilder import YunhuMessageBuilder


class Main:
    def __init__(self, sdk):
        self.sdk = sdk
        self.logger = sdk.logger

        # 初始化配置
        self._init_config()

        # 注册消息构建器
        self.message_builders = {
            "QQ": QQMessageBuilder(self),
            "Yunhu": YunhuMessageBuilder(self)
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
        qq_to_yunhu = self.sdk.env.get("QQ_TO_YUNHU_GROUP_MAP", {})
        yunhu_to_qq = self.sdk.env.get("YUNHU_TO_QQ_GROUP_MAP", {})

        if not qq_to_yunhu and not yunhu_to_qq:
            self.logger.info("""
请使用以下命令配置 QQ 和 Yunhu 群组映射关系:
    sdk.env.set("QQ_TO_YUNHU_GROUP_MAP", {"QQ群ID": {"group_id": "Yunhu群ID", "format": "html"}})
    sdk.env.set("YUNHU_TO_QQ_GROUP_MAP", {"Yunhu群ID": {"group_id": "QQ群ID", "format": "html"}})
""")

        self.qq_to_yunhu_group_map = self.sdk.env.get("QQ_TO_YUNHU_GROUP_MAP", {})
        self.yunhu_to_qq_group_map = self.sdk.env.get("YUNHU_TO_QQ_GROUP_MAP", {})

    async def start(self):
        self.logger.info("AnySync 模块启动中...")
        try:
            await self._setup_message_handlers()
        except Exception as e:
            self.logger.error(f"AnySync 启动失败: {e}")

    async def _setup_message_handlers(self):
        @self.sdk.adapter.QQ.on("message")
        async def forward_qq_to_yunhu(message):
            message = self.parse_message_to_dict(message)
            group_id = message.get("group_id")
            mapping = self.qq_to_yunhu_group_map.get(str(group_id))

            if not mapping:
                self.logger.warning(f"未配置对应的 Yunhu 群 | QQ群ID: {group_id}")
                return

            yunhu_group_id = mapping["group_id"]
            msg_format = mapping.get("format", "html")

            builder = self.message_builders["QQ"]
            handler_method = getattr(builder, f"build_{msg_format}", None)
            if not handler_method:
                self.logger.warning(f"不支持的消息格式: {msg_format}")
                return

            full_content = await handler_method(message)  # 传入完整 data

            res = await getattr(self.sdk.adapter.Yunhu.Send.To("group", yunhu_group_id), msg_format.capitalize())(full_content)
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

        @self.sdk.adapter.Yunhu.on("message")
        async def forward_yunhu_to_qq(message):
            message = self.parse_message_to_dict(message)
            yunhu_event = message.get("event", {})
            yunhu_msg = yunhu_event.get("message", {})
            yunhu_group_id = yunhu_msg.get("chatId")

            mapping = self.yunhu_to_qq_group_map.get(str(yunhu_group_id))
            if not mapping:
                self.logger.warning(f"未配置对应的 QQ 群 | Yunhu群ID: {yunhu_group_id}")
                return

            msg_format = mapping.get("format", "text")
            builder = self.message_builders["Yunhu"]
            handler_method = getattr(builder, f"build_{msg_format}", None)
            if not handler_method:
                self.logger.warning(f"不支持的消息格式: {msg_format}")
                return

            text_message = await handler_method(message)

            res = await getattr(self.sdk.adapter.QQ.Send.To("group", mapping["group_id"]), msg_format.capitalize())(text_message)
            self.logger.info(f"[Yunhu→QQ] 已发送至群 {mapping['group_id']} | 响应: {res}")

            yunhu_msg_id = yunhu_msg.get("msgId")
            qq_msg_id = res.get("message_id")

            if qq_msg_id and yunhu_msg_id:
                self.add_message_id_mapping(
                    qq_msg_id=qq_msg_id,
                    yunhu_msg_id=yunhu_msg_id,
                    qq_group_id=mapping["group_id"],
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

                mapping_table = self.sdk.env.get("message_id_map", {"qq_to_yunhu": {}, "yunhu_to_qq": {}})
                mapped_data = mapping_table["qq_to_yunhu"].get(str(message_id))

                if not mapped_data:
                    return

                yunhu_msg_id, yunhu_group_id = mapped_data

                if yunhu_msg_id and yunhu_group_id:
                    res = await self.sdk.adapter.Yunhu.Send.To("group", yunhu_group_id).Recall(yunhu_msg_id)
                    self.logger.info(f"[Yunhu] 已同步撤回消息 {yunhu_msg_id} | 响应: {res}")

        self.logger.info("AnySync 消息处理器已注册")

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