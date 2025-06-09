import asyncio
import json
from ErisPulse import sdk
from .MessageBuilders.QQMessageBuilder import QQMessageBuilder
from .MessageBuilders.YunhuMessageBuilder import YunhuMessageBuilder
from .MessageBuilders.TelegramMessageBuilder import TelegramMessageBuilder


class Main:
    def __init__(self, sdk):
        self.sdk = sdk
        self.logger = sdk.logger

        # 初始化配置
        self._init_config()

        # 动态初始化消息构建器
        self.message_builders = {}
        for platform in ["QQ", "Yunhu", "Telegram"]:
            if hasattr(self.sdk.adapter, platform.lower()):
                try:
                    builder_class = globals()[f"{platform}MessageBuilder"]
                    self.message_builders[platform] = builder_class(self)
                except Exception as e:
                    self.logger.warning(f"无法初始化 {platform} 消息构建器: {e}")

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
        forward_map = self.sdk.env.get("AnyMsgSync", {})

        # 按平台提取映射关系
        self.qq_to = forward_map.get("qq", {})
        self.yunhu_to = forward_map.get("yunhu", {})
        self.telegram_to = forward_map.get("telegram", {})

        if not (self.qq_to or self.yunhu_to or self.telegram_to):
            self.logger.info("""
请使用以下命令配置跨平台群组映射关系:

示例：
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
""")

    async def start(self):
        self.logger.info("AnyMsgSync 模块启动中...")
        try:
            await self._setup_message_handlers()
        except Exception as e:
            self.logger.error(f"AnyMsgSync 启动失败: {e}")

    async def _setup_message_handlers(self):

        # 动态注册 QQ 消息处理器
        if hasattr(self.sdk.adapter, "QQ"):

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

                    builder = self.message_builders.get("QQ")
                    if not builder:
                        self.logger.warning("QQ 消息构建器未加载")
                        return

                    handler_method = getattr(builder, f"build_{msg_format}", None)
                    if not handler_method:
                        self.logger.warning(f"不支持的消息格式: {msg_format}")
                        continue

                    full_content = await handler_method(message)

                    if not hasattr(self.sdk.adapter, target_type.lower()):
                        self.logger.warning(f"适配器 {target_type} 不存在，跳过转发")
                        continue

                    try:
                        res = await getattr(
                            self.sdk.adapter[target_type].Send.To("group", target_group_id),
                            msg_format.capitalize()
                        )(full_content)
                        self.logger.info(f"[QQ→{target_type.capitalize()}] 已发送至群 {target_group_id} | 响应: {res}")
                    except Exception as e:
                        self.logger.error(f"[QQ→{target_type.capitalize()}] 发送失败: {e}")

                    # 记录消息 ID 映射
                    qq_msg_id = message.get("message_id")
                    other_msg_id = res.get("message_id") or res.get("data", {}).get("messageInfo", {}).get("msgId")
                    if qq_msg_id and other_msg_id:
                        self.add_message_id_mapping(
                            msg_id=qq_msg_id,
                            target_msg_id=other_msg_id,
                            from_platform="qq",
                            to_platform=target_type.lower(),
                            group_id=group_id,
                            target_group_id=target_group_id
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

                    mapping_table = self.sdk.env.get("message_id_map", {})

                    # 查找是否有来自 QQ 的转发映射
                    mapped_data = None
                    if mapping_table.get("qq", {}).get("yunhu", {}).get(str(message_id)):
                        mapped_data = mapping_table["qq"]["yunhu"][str(message_id)]
                    elif mapping_table.get("qq", {}).get("telegram", {}).get(str(message_id)):
                        mapped_data = mapping_table["qq"]["telegram"][str(message_id)]
                    else:
                        return

                    other_msg_id, other_group_id = mapped_data

                    if "yunhu" in str(mapped_data):
                        if hasattr(self.sdk.adapter, "yunhu"):
                            res = await self.sdk.adapter.Yunhu.Send.To("group", other_group_id).Recall(other_msg_id)
                            self.logger.info(f"[Yunhu] 已同步撤回消息 {other_msg_id} | 响应: {res}")
                    elif "telegram" in str(mapped_data):
                        if hasattr(self.sdk.adapter, "telegram"):
                            res = await self.sdk.adapter.Telegram.Send.To("group", other_group_id).DeleteMessage(other_msg_id)
                            self.logger.info(f"[Telegram] 已同步删除消息 {other_msg_id} | 响应: {res}")

        # 动态注册 Yunhu 消息处理器
        if hasattr(self.sdk.adapter, "Yunhu"):

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

                    builder = self.message_builders.get("Yunhu")
                    if not builder:
                        self.logger.warning("Yunhu 消息构建器未加载")
                        return

                    handler_method = getattr(builder, f"build_{msg_format}", None)
                    if not handler_method:
                        self.logger.warning(f"不支持的消息格式: {msg_format}")
                        continue

                    full_content = await handler_method(message)

                    if not hasattr(self.sdk.adapter, target_type.lower()):
                        self.logger.warning(f"适配器 {target_type} 不存在，跳过转发")
                        continue

                    try:
                        res = await getattr(
                            self.sdk.adapter[target_type].Send.To("group", target_group_id),
                            msg_format.capitalize()
                        )(full_content)
                        self.logger.info(f"[Yunhu→{target_type.capitalize()}] 已发送至群 {target_group_id} | 响应: {res}")
                    except Exception as e:
                        self.logger.error(f"[Yunhu→{target_type.capitalize()}] 发送失败: {e}")

                    # 记录消息 ID 映射
                    yunhu_msg_id = yunhu_msg.get("msgId")
                    other_msg_id = res.get("message_id") or res.get("data", {}).get("messageInfo", {}).get("msgId")
                    if yunhu_msg_id and other_msg_id:
                        self.add_message_id_mapping(
                            msg_id=yunhu_msg_id,
                            target_msg_id=other_msg_id,
                            from_platform="yunhu",
                            to_platform=target_type.lower(),
                            group_id=yunhu_group_id,
                            target_group_id=target_group_id
                        )

        # 动态注册 Telegram 消息处理器
        if hasattr(self.sdk.adapter, "Telegram"):

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

                    builder = self.message_builders.get("Telegram")
                    if not builder:
                        self.logger.warning("Telegram 消息构建器未加载")
                        return

                    handler_method = getattr(builder, f"build_{msg_format}", None)
                    if not handler_method:
                        self.logger.warning(f"不支持的消息格式: {msg_format}")
                        continue

                    full_content = await handler_method(message)

                    if not hasattr(self.sdk.adapter, target_type.lower()):
                        self.logger.warning(f"适配器 {target_type} 不存在，跳过转发")
                        continue

                    try:
                        res = await getattr(
                            self.sdk.adapter[target_type].Send.To("group", target_group_id),
                            msg_format.capitalize()
                        )(full_content)
                        self.logger.info(f"[Telegram→{target_type.capitalize()}] 已发送至群 {target_group_id} | 响应: {res}")
                    except Exception as e:
                        self.logger.error(f"[Telegram→{target_type.capitalize()}] 发送失败: {e}")
                    # 记录消息 ID 映射
                    telegram_msg_id = message.get("message_id")
                    other_msg_id = res.get("message_id") or res.get("data", {}).get("messageInfo", {}).get("msgId")
                    if telegram_msg_id and other_msg_id:
                        self.add_message_id_mapping(
                            msg_id=telegram_msg_id,
                            target_msg_id=other_msg_id,
                            from_platform="telegram",
                            to_platform=target_type.lower(),
                            group_id=chat_id,
                            target_group_id=target_group_id
                        )
            @self.sdk.adapter.Telegram.on("message_delete")
            async def handle_telegram_message_delete(event):
                chat_id = event.get("chat", {}).get("id")
                message_id = event.get("message_id")

                # 查找该消息是否被转发到了其他平台
                mapping_table = self.sdk.env.get("message_id_map", {})
                mapped_data = None

                if mapping_table.get("telegram", {}).get("qq", {}).get(str(message_id)):
                    mapped_data = mapping_table["telegram"]["qq"][str(message_id)]
                elif mapping_table.get("telegram", {}).get("yunhu", {}).get(str(message_id)):
                    mapped_data = mapping_table["telegram"]["yunhu"][str(message_id)]

                if not mapped_data:
                    return

                target_msg_id, target_group_id = mapped_data

                # 同步撤回 QQ 消息
                if "qq" in str(mapped_data) and hasattr(self.sdk.adapter, "qq"):
                    try:
                        res = await self.sdk.adapter.QQ.Send.To("group", target_group_id).Recall(target_msg_id)
                        self.logger.info(f"[QQ] 已同步撤回消息 {target_msg_id} | 响应: {res}")
                    except Exception as e:
                        self.logger.error(f"[QQ] 撤回失败: {e}")

                # 同步撤回 Yunhu 消息
                elif "yunhu" in str(mapped_data) and hasattr(self.sdk.adapter, "yunhu"):
                    try:
                        res = await self.sdk.adapter.Yunhu.Send.To("group", target_group_id).Recall(target_msg_id)
                        self.logger.info(f"[Yunhu] 已同步撤回消息 {target_msg_id} | 响应: {res}")
                    except Exception as e:
                        self.logger.error(f"[Yunhu] 撤回失败: {e}")
        self.logger.info("AnyMsgSync 消息处理器已注册")

    def add_message_id_mapping(self, *, msg_id, target_msg_id, from_platform, to_platform, group_id, target_group_id):
        mapping = self.sdk.env.get("message_id_map", {})

        # 初始化平台层级结构
        mapping.setdefault(from_platform, {})
        mapping[from_platform].setdefault(to_platform, {})

        # 存储映射信息
        mapping[from_platform][to_platform][str(msg_id)] = (str(target_msg_id), str(target_group_id))

        # 反向映射
        mapping.setdefault(to_platform, {})
        mapping[to_platform].setdefault(from_platform, {})
        mapping[to_platform][from_platform][str(target_msg_id)] = (str(msg_id), str(group_id))

        self.sdk.env.set("message_id_map", mapping)

    def get_original_platform(self, msg_id):
        mapping = self.sdk.env.get("message_id_map", {})
        for src_platform, targets in mapping.items():
            for dst_platform, msg_map in targets.items():
                if str(msg_id) in msg_map:
                    return src_platform
        return None