import asyncio
import json
from ErisPulse import sdk
from typing import Dict, List, Optional, Tuple, Any, Callable

# 格式映射表：将用户配置的 format 字段标准化为统一名称
FORMAT_MAP = {
    "text": "Text",
    "txt": "Text",
    "plain": "Text",
    "markdown": "Markdown",
    "md": "Markdown",
    "html": "Html",
}

class MessageSyncManager:
    
    def __init__(self, main_instance):
        self.main = main_instance
        self.logger = main_instance.logger
        self.sdk = main_instance.sdk
        
    async def handle_message_recall(self, from_platform: str, message_id: str, group_id: Optional[str] = None):
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

                platform_actions = {
                    "yunhu": lambda: self.sdk.adapter.Yunhu.Send.To("group", other_group_id).Recall(other_msg_id),
                    "qq": lambda: self.sdk.adapter.QQ.Send.To("group", other_group_id).Recall(other_msg_id),
                    "telegram": lambda: self.sdk.adapter.Telegram.Send.To("group", other_group_id).DeleteMessage(other_msg_id)
                }
                res = await platform_actions[target_platform]()
                self.logger.info(f"[{target_platform.upper()}] 已同步撤回消息 {other_msg_id} | 响应: {res}")
            except Exception as e:
                self.logger.error(f"[{target_platform.upper()}] 撤回失败: {e}", exc_info=True)

    def add_message_id_mapping(self, *, msg_id: str, target_msg_id: str, from_platform: str, to_platform: str, group_id: str, target_group_id: str):
        """添加消息ID映射关系"""
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
        self.logger.debug(f"[Mapping] 新增映射: {from_platform}({msg_id}) → {to_platform}({target_msg_id}, {target_group_id})")

    def get_mapped_message_id(self, from_platform: str, msg_id: str, to_platform: str, 
                            group_id: Optional[str] = None) -> Optional[Tuple[str, str]]:
        mapping_table = self.sdk.env.get("message_id_map", {})
        mappings = mapping_table.get(from_platform, {}).get(to_platform, {})
        msg_id = str(msg_id)
        if msg_id in mappings:
            stored_group_id = mappings[msg_id][1]
            if group_id is None or str(group_id) == stored_group_id:
                return mappings[msg_id]
        return None

class MessageParser:
    """消息解析工具类"""
    
    def __init__(self, main_instance):
        self.main = main_instance
        self.logger = main_instance.logger

    def parse_message_to_dict(self, message: Any) -> Dict:
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

    def get_message_id(self, message: Any) -> Optional[str]:
        message = self.parse_message_to_dict(message)

        # 尝试直接获取 message_id
        if "message_id" in message:
            return str(message["message_id"])

        # Telegram: message/message_id
        if "message" in message:
            msg = message["message"]
            if isinstance(msg, dict) and "message_id" in msg:
                return str(msg["message_id"])

        # Telegram: edited_message/message_id
        if "edited_message" in message:
            msg = message["edited_message"]
            if isinstance(msg, dict) and "message_id" in msg:
                return str(msg["message_id"])

        # Yunhu: event/message/msgId
        if "event" in message and "message" in message["event"]:
            return str(message["event"]["message"].get("msgId"))

        # Yunhu: 直接 msgId
        if "msgId" in message:
            return str(message["msgId"])

        return None

    def get_adapter_message_id(self, platform: str, res: Dict) -> Optional[str]:
        if not isinstance(res, dict):
            self.logger.warning(f"[{platform.upper()}] 无效的响应数据类型: {type(res)}")
            return None

        platform_extractors = {
            "telegram": lambda r: str(r.get("result", {}).get("message_id")),
            "yunhu": lambda r: str(r.get("data", {}).get("messageInfo", {}).get("msgId")),
            "qq": lambda r: str(r.get("message_id") or r.get("data", {}).get("messageInfo", {}).get("msgId"))
        }
        if platform in platform_extractors:
            return platform_extractors[platform](res)
        self.logger.warning(f"未知平台 {platform}，无法提取 message_id")
        return None

class PlatformHandler:
    """平台处理器基类"""
    def __init__(self, main_instance, platform_name: str):
        self.main = main_instance
        self.logger = main_instance.logger
        self.sdk = main_instance.sdk
        self.platform_name = platform_name
        self.forward_config = main_instance.forward_config.get(platform_name.lower(), {})

    async def handle_message(self, message: Any):
        """处理平台消息"""
        raise NotImplementedError
    async def handle_recall(self, message: Any):
        """处理平台撤回事件"""
        raise NotImplementedError
    async def handle_edit(self, message: Any):
        """处理平台编辑事件"""
        raise NotImplementedError
    async def forward_message(self, message: Dict, group_id: str):
        mappings = self.forward_config.get(str(group_id))
        if not mappings:
            self.logger.warning(f"未配置对应的转发目标 | {self.platform_name}群ID: {group_id}")
            return

        for mapping in mappings:
            target_type = mapping["type"]
            target_group_id = mapping["group_id"]
            msg_format = mapping.get("format", "text").lower()
            standard_format = FORMAT_MAP.get(msg_format, None)

            if not standard_format:
                self.logger.warning(f"[{self.platform_name}] 不支持的消息格式: {msg_format}")
                continue

            builder = self.main.message_builders.get(self.platform_name)
            if not builder:
                self.logger.warning(f"{self.platform_name} 消息构建器未加载")
                continue

            handler_method = getattr(builder, f"build_{standard_format.lower()}", None)
            if not handler_method:
                self.logger.warning(f"[{self.platform_name}] 不支持的消息格式: {standard_format}")
                continue

            full_content = await handler_method(message)

            if not hasattr(self.sdk.adapter, target_type.capitalize()):
                self.logger.warning(f"[{target_type}] 适配器不存在，跳过转发")
                continue

            try:
                adapter = getattr(self.sdk.adapter, target_type.capitalize())
                send_method = getattr(adapter.Send.To("group", target_group_id), standard_format)
                res = await send_method(full_content)
                self.logger.info(f"[{self.platform_name}→{target_type.capitalize()}] 已发送至群 {target_group_id} | 响应: {res}")

                # 记录消息ID映射
                msg_id = self.main.parser.get_message_id(message)
                other_msg_id = self.main.parser.get_adapter_message_id(target_type.lower(), res)
                if msg_id and other_msg_id:
                    self.main.sync_manager.add_message_id_mapping(
                        msg_id=msg_id,
                        target_msg_id=other_msg_id,
                        from_platform=self.platform_name.lower(),
                        to_platform=target_type.lower(),
                        group_id=group_id,
                        target_group_id=target_group_id
                    )
            except Exception as e:
                self.logger.error(f"[{self.platform_name}→{target_type.capitalize()}] 发送失败: {e}", exc_info=True)

class QQHandler(PlatformHandler):
    def __init__(self, main_instance):
        super().__init__(main_instance, "QQ")

    async def handle_message(self, message: Any):
        group_id = message.get("group_id")
        await self.forward_message(message, group_id)

    async def handle_recall(self, notice: Dict):
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
            await self.main.sync_manager.handle_message_recall("qq", message_id, group_id)

class YunhuHandler(PlatformHandler):
    def __init__(self, main_instance):
        super().__init__(main_instance, "Yunhu")

    async def handle_message(self, message: Any):
        message = self.main.parser.parse_message_to_dict(message)
        yunhu_event = message.get("event", {})
        yunhu_msg = yunhu_event.get("message", {})
        yunhu_group_id = yunhu_msg.get("chatId")
        await self.forward_message(message, yunhu_group_id)

    async def handle_recall(self, event: Dict):
        yunhu_msg = event.get("message", {})
        msg_id = yunhu_msg.get("msgId")
        chat_id = yunhu_msg.get("chatId")
        self.logger.info(f"[Yunhu] 收到撤回通知，消息 ID: {msg_id}")
        await self.main.sync_manager.handle_message_recall("yunhu", msg_id, chat_id)


class TelegramHandler(PlatformHandler):
    """Telegram平台处理器"""
    def __init__(self, main_instance):
        super().__init__(main_instance, "Telegram")

    async def handle_message(self, message: Any):
        """处理Telegram消息"""
        message = self.main.parser.parse_message_to_dict(message)
        msg_body = message.get("message", {})
        chat = msg_body.get("chat", {})
        chat_id = chat.get("id")
        if not chat_id:
            self.logger.warning("[Telegram] 消息中未找到群组ID，忽略转发")
            return
        await self.forward_message(message, str(chat_id))

    async def handle_edit(self, data: Dict):
        self.logger.info("[Telegram] 收到消息编辑事件")
        edited_message = data.get("edited_message", {})
        chat = edited_message.get("chat", {})
        chat_id = chat.get("id")
        message_id = edited_message.get("message_id")

        if not chat_id or not message_id:
            self.logger.warning("[Telegram] 缺少必要的 chat_id 或 message_id，忽略处理")
            return

        mappings = self.forward_config.get(str(chat_id))
        if not mappings:
            self.logger.warning(f"[Telegram] 未配置对应的转发目标 | 群组ID: {chat_id}")
            return

        for mapping in mappings:
            target_type = mapping["type"]
            target_group_id = mapping["group_id"]
            msg_format = mapping.get("format", "text").lower()
            standard_format = FORMAT_MAP.get(msg_format, None)

            if not standard_format:
                self.logger.warning(f"[Telegram] 不支持的消息格式: {msg_format}")
                continue

            builder = self.main.message_builders.get("Telegram")
            if not builder:
                self.logger.warning("[Telegram] 消息构建器未加载")
                continue

            handler_method = getattr(builder, f"build_{standard_format.lower()}", None)
            if not handler_method:
                self.logger.warning(f"[Telegram] 不支持的消息格式: {standard_format}")
                continue

            full_content = await handler_method({"message": edited_message})

            if not hasattr(self.sdk.adapter, target_type.lower()):
                self.logger.warning(f"[Telegram] 适配器 {target_type} 不存在，跳过转发")
                continue

            try:
                adapter = getattr(self.sdk.adapter, target_type.capitalize())
                if target_type == "yunhu":
                    yunhu_msg_id = self.main.sync_manager.get_mapped_message_id(
                        "telegram", message_id, "yunhu", target_group_id
                    )
                    if yunhu_msg_id:
                        res = await adapter.Send.To("group", target_group_id).Edit(
                            yunhu_msg_id[0], full_content, standard_format.lower()
                        )
                        self.logger.info(f"[Telegram→Yunhu] 已编辑消息 {yunhu_msg_id[0]} 至群 {target_group_id} | 响应: {res}")
                    else:
                        self.logger.warning("[Telegram→Yunhu] 未找到对应 Yunhu 消息 ID，跳过编辑")
                elif target_type == "qq":
                    qq_msg_id = self.main.sync_manager.get_mapped_message_id(
                        "telegram", message_id, "qq", target_group_id
                    )
                    if qq_msg_id:
                        await adapter.call_api(
                            endpoint="delete_msg",
                            message_id=qq_msg_id[0]
                        )
                    send_method = getattr(adapter.Send.To("group", target_group_id), standard_format)
                    res = await send_method(full_content)
                    self.logger.info(f"[Telegram→QQ] 已发送新消息至群 {target_group_id} | 响应: {res}")

                    other_msg_id = self.main.parser.get_adapter_message_id(target_type.lower(), res)
                    if other_msg_id:
                        self.main.sync_manager.add_message_id_mapping(
                            msg_id=message_id,
                            target_msg_id=other_msg_id,
                            from_platform="telegram",
                            to_platform=target_type.lower(),
                            group_id=chat_id,
                            target_group_id=target_group_id
                        )
            except Exception as e:
                self.logger.error(f"[Telegram→{target_type.capitalize()}] 处理失败: {e}", exc_info=True)

class Main:
    def __init__(self, sdk):
        self.sdk = sdk
        self.logger = sdk.logger
        self.logger.debug("当前 sdk.adapter 成员: %s", dir(self.sdk.adapter))
        # 初始化核心组件
        self.parser = MessageParser(self)
        self.sync_manager = MessageSyncManager(self)

        # 初始化配置
        self._init_config()

        # 初始化消息构建器
        self._init_message_builders()

        # 初始化平台处理器
        self.platform_handlers = {}
        self._init_platform_handlers()

    def _init_config(self):
        """初始化配置"""
        forward_map = self.sdk.env.get("AnyMsgSync", {})
        self.forward_config = {
            "qq": forward_map.get("qq", {}),
            "yunhu": forward_map.get("yunhu", {}),
            "telegram": forward_map.get("telegram", {})
        }

        if not any(self.forward_config.values()):
            self.logger.info("""
请使用以下命令配置跨平台群组映射关系:

示例：
sdk.env.set("AnyMsgSync", {
    "qq": {
        "QQ群ID1": [
            {"type": "yunhu", "group_id": "Yunhu群ID1", "format": "html"},
            {"type": "telegram", "group_id": -1001234567890, "format": "md"}
        ]
    },
    "yunhu": {
        "Yunhu群ID1": [
            {"type": "qq", "group_id": "QQ群ID1", "format": "text"},
            {"type": "telegram", "group_id": -1001234567890, "format": "md"}
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

    def _init_message_builders(self):
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

    def _init_platform_handlers(self):
        handler_classes = {
            "QQ": QQHandler,
            "Yunhu": YunhuHandler,
            "Telegram": TelegramHandler
        }
        for platform in ["QQ", "Yunhu", "Telegram"]:
            if hasattr(self.sdk.adapter, platform):
                try:
                    self.platform_handlers[platform] = handler_classes[platform](self)
                    self.logger.info(f"{platform} 处理器已加载")
                except Exception as e:
                    self.logger.warning(f"无法初始化 {platform} 处理器: {e}")
            else:
                self.logger.debug(f"适配器 {platform} 不存在，跳过处理器初始化")

    async def start(self):
        self.logger.info("AnyMsgSync 模块启动中...")
        try:
            await self._setup_message_handlers()
        except Exception as e:
            self.logger.error(f"AnyMsgSync 启动失败: {e}", exc_info=True)

    async def _setup_message_handlers(self):
        # 动态注册平台处理器
        for platform, handler in self.platform_handlers.items():
            adapter = getattr(self.sdk.adapter, platform)

            # 注册消息处理器
            @adapter.on("message")
            async def handle_message(message, handler=handler):
                await handler.handle_message(message)

            # 注册撤回处理器（如果平台支持）
            if hasattr(handler, "handle_recall"):
                @adapter.on("notice" if platform == "QQ" else "recall")
                async def handle_recall(event, handler=handler):
                    await handler.handle_recall(event)

            # 注册编辑处理器（如果平台支持）
            if hasattr(handler, "handle_edit"):
                @adapter.on("message_edit")
                async def handle_edit(data, handler=handler):
                    await handler.handle_edit(data)

        self.logger.info("AnyMsgSync 消息处理器已注册")