import asyncio
from ErisPulse import sdk
from AnyMsgSync.MessageBuilders.QQMessageBuilder import QQMessageBuilder
from AnyMsgSync.MessageBuilders.YunhuMessageBuilder import YunhuMessageBuilder


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

    async def _setup_message_handlers(self):
        @self.sdk.adapter.QQ.on("message")
        async def forward_qq_to_yunhu(message):
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

            full_content = handler_method(message)

            res = await self.sdk.adapter.Yunhu.Send.To("group", yunhu_group_id).Html(text=full_content)
            self.logger.info(f"[QQ→Yunhu] 已发送至群 {yunhu_group_id} | 响应: {res}")

        @self.sdk.adapter.Yunhu.on("message")
        async def forward_yunhu_to_qq(message):
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

            full_content = handler_method(message)

            if msg_format == "html":
                res = await self.sdk.adapter.QQ.Send.To("group", mapping["group_id"]).Html(full_content)
            elif msg_format == "image":
                # 可在此调用图像渲染服务后发送图片
                pass
            else:
                res = await self.sdk.adapter.QQ.Send.To("group", mapping["group_id"]).Text(full_content)

            self.logger.info(f"[Yunhu→QQ] 已发送至群 {mapping['group_id']} | 响应: {res}")