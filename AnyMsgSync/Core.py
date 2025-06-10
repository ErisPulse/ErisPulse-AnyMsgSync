import asyncio
import json
from ErisPulse import sdk


class Main:
    def __init__(self, sdk):
        self.sdk = sdk
        self.logger = sdk.logger

        # 初始化配置
        self._init_config()

        # 动态初始化消息构建器
        self.message_builders = {}

        from .MessageBuilders.QQMessageBuilder import QQMessageBuilder
        from .MessageBuilders.YunhuMessageBuilder import YunhuMessageBuilder
        from .MessageBuilders.TelegramMessageBuilder import TelegramMessageBuilder

        builder_map = {
            "QQ": QQMessageBuilder,
            "Yunhu": YunhuMessageBuilder,
            "Telegram": TelegramMessageBuilder
        }

        self.logger.debug("当前适配器支持平台: %s", dir(self.sdk.adapter))
        for platform in ["QQ", "Yunhu", "Telegram"]:
            if hasattr(self.sdk.adapter, platform):
                try:
                    builder_class = builder_map[platform]
                    self.message_builders[platform] = builder_class(self)
                    self.logger.info(f"{platform} 消息构建器已加载")
                except Exception as e:
                    self.logger.warning(f"无法初始化 {platform} 消息构建器: {e}")
            else:
                self.logger.debug(f"适配器 {platform} 不存在，跳过构建器初始化")
    async def handle_message_recall(self, from_platform, message_id, group_id=None):
        mapping_table = self.sdk.env.get("message_id_map", {})
        mapped_targets = []

        # 查找所有目标平台映射
        for target_platform in ["yunhu", "qq", "telegram"]:
            if mapping_table.get(from_platform, {}).get(target_platform, {}).get(str(message_id)):
                mapped_data = mapping_table[from_platform][target_platform][str(message_id)]
                other_msg_id, other_group_id = mapped_data
                mapped_targets.append({
                    "target_platform": target_platform,
                    "other_msg_id": other_msg_id,
                    "other_group_id": other_group_id
                })
                self.logger.debug(f"[{from_platform.upper()}→{target_platform.upper()}] 找到映射: 消息ID={other_msg_id}, 群ID={other_group_id}")

        if not mapped_targets:
            self.logger.warning(f"[{from_platform.upper()}] 无法找到对应的目标消息 ID: {message_id}")
            return

        for item in mapped_targets:
            target_platform = item["target_platform"]
            other_msg_id = item["other_msg_id"]
            other_group_id = item["other_group_id"]

            if not hasattr(self.sdk.adapter, target_platform.capitalize()):
                self.logger.warning(f"[{target_platform.upper()}] 适配器不存在，跳过撤回")
                continue

            try:
                self.logger.info(f"[{target_platform.upper()}] 即将撤回消息 {other_msg_id}（群 {other_group_id}）")
                if target_platform == "yunhu":
                    res = await self.sdk.adapter.Yunhu.Send.To("group", other_group_id).Recall(other_msg_id)
                elif target_platform == "qq":
                    res = await self.sdk.adapter.QQ.Send.To("group", other_group_id).Recall(other_msg_id)
                elif target_platform == "telegram":
                    res = await self.sdk.adapter.Telegram.Send.To("group", other_group_id).DeleteMessage(other_msg_id)
                else:
                    continue

                self.logger.info(f"[{target_platform.upper()}] 已同步撤回消息 {other_msg_id} | 响应: {res}")
            except Exception as e:
                self.logger.error(f"[{target_platform.upper()}] 撤回失败: {e}", exc_info=True)
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
            self.logger.error(f"AnyMsgSync 启动失败: {e}", exc_info=True)

    async def _setup_message_handlers(self):

        # 动态注册 QQ 消息处理器
        if hasattr(self.sdk.adapter, "QQ"):

            @self.sdk.adapter.QQ.on("message")
            async def forward_qq_to_other(message):
                message = self.parse_message_to_dict(message)
                group_id = message.get("group_id")
                mappings = self.qq_to.get(str(group_id))
                self.logger.debug(f"当前可用的消息构建器: {list(self.message_builders.keys())}")
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
                        continue  # 不中断整体流程

                    handler_method = getattr(builder, f"build_{msg_format}", None)
                    if not handler_method:
                        self.logger.warning(f"不支持的消息格式: {msg_format}")
                        continue

                    full_content = await handler_method(message)

                    if not hasattr(self.sdk.adapter, target_type.lower()):
                        self.logger.warning(f"适配器 {target_type} 不存在，跳过转发")
                        continue

                    try:
                        adapter = getattr(self.sdk.adapter, target_type.lower())
                        send_method = getattr(adapter.Send.To("group", target_group_id), msg_format.capitalize())
                        res = await send_method(full_content)
                        self.logger.info(f"[QQ→{target_type.capitalize()}] 已发送至群 {target_group_id} | 响应: {res}")
                    except Exception as e:
                        self.logger.error(f"[QQ→{target_type.capitalize()}] 发送失败: {e}", exc_info=True)
                        continue  # 避免后续继续操作 res

                    # 只有成功发送后才记录映射
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
                    user_id = notice.get("user_id")
                    operator_id = notice.get("operator_id")
                    if user_id != operator_id:
                        self.logger.debug("非自己撤回的消息，忽略")
                        return

                    message_id = notice.get("message_id")
                    group_id = notice.get("group_id")
                    self.logger.info(f"[QQ] 收到撤回通知，消息 ID: {message_id}")
                    await self.handle_message_recall("qq", message_id, group_id)

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
                        continue

                    handler_method = getattr(builder, f"build_{msg_format}", None)
                    if not handler_method:
                        self.logger.warning(f"不支持的消息格式: {msg_format}")
                        continue

                    full_content = await handler_method(message)

                    if not hasattr(self.sdk.adapter, target_type.lower()):
                        self.logger.warning(f"适配器 {target_type} 不存在，跳过转发")
                        continue

                    try:
                        adapter = getattr(self.sdk.adapter, target_type.lower())
                        send_method = getattr(adapter.Send.To("group", target_group_id), msg_format.capitalize())
                        res = await send_method(full_content)
                        self.logger.info(f"[Yunhu→{target_type.capitalize()}] 已发送至群 {target_group_id} | 响应: {res}")
                    except Exception as e:
                        self.logger.error(f"[Yunhu→{target_type.capitalize()}] 发送失败: {e}", exc_info=True)
                        continue

                    # 只有成功发送后才记录映射
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
            @self.sdk.adapter.Yunhu.on("recall")
            async def handle_yunhu_recall(event):
                yunhu_msg = event.get("message", {})
                msg_id = yunhu_msg.get("msgId")
                chat_id = yunhu_msg.get("chatId")
                self.logger.info(f"[Yunhu] 收到撤回通知，消息 ID: {msg_id}")
                await self.handle_message_recall("yunhu", msg_id, chat_id)

        # 动态注册 Telegram 消息处理器
        if hasattr(self.sdk.adapter, "Telegram"):
            @self.sdk.adapter.Telegram.on("message")
            async def forward_telegram_to_other(message):
                self.logger.info(f"[Telegram] 收到消息：{message}")
                message = self.parse_message_to_dict(message)

                # 提取 chat_id
                msg_body = message.get("message", {})
                chat = msg_body.get("chat", {})
                chat_id = chat.get("id")
                if not chat_id:
                    self.logger.warning("[Telegram] 消息中未找到群组ID，忽略转发")
                    return

                mappings = self.telegram_to.get(str(chat_id))
                if not mappings:
                    self.logger.warning(f"[Telegram] 未配置对应的转发目标 | 群组ID: {chat_id}")
                    return

                for mapping in mappings:
                    target_type = mapping["type"]
                    target_group_id = mapping["group_id"]
                    msg_format = mapping.get("format", "text").lower()

                    # 获取消息构建器
                    builder = self.message_builders.get("Telegram")
                    if not builder:
                        self.logger.warning("[Telegram] 消息构建器未加载")
                        continue

                    # 构建内容
                    handler_method = getattr(builder, f"build_{msg_format}", None)
                    if not handler_method:
                        self.logger.warning(f"[Telegram] 不支持的消息格式: {msg_format}")
                        continue

                    full_content = await handler_method(message)

                    # 检查目标平台是否存在
                    if not hasattr(self.sdk.adapter, target_type.lower()):
                        self.logger.warning(f"[Telegram] 适配器 {target_type} 不存在，跳过转发")
                        continue

                    try:
                        adapter = getattr(self.sdk.adapter, target_type.lower())
                        send_method = getattr(adapter.Send.To("group", target_group_id), msg_format.capitalize(), None)
                        if not send_method:
                            self.logger.warning(f"[Telegram→{target_type.capitalize()}] 发送方法不存在")
                            continue

                        res = await send_method(full_content)
                        self.logger.info(f"[Telegram→{target_type.capitalize()}] 已发送至群 {target_group_id} | 响应: {res}")
                    except Exception as e:
                        self.logger.error(f"[Telegram→{target_type.capitalize()}] 发送失败: {e}", exc_info=True)
                        continue

                    # 记录映射关系
                    telegram_msg_id = msg_body.get("message_id")
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