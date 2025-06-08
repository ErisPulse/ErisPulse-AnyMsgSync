class QQMessageBuilder:
    def __init__(self, main):
        self.main = main
        self.sdk = main.sdk
        self.logger = self.sdk.logger

    async def build_html(self, data):
        sender = data.get("sender", {})
        user_id = sender.get("user_id", "未知ID")
        nickname = sender.get("nickname", "未知用户")
        message_parts = data.get("message", [])

        avatar_url = f"https://q1.qlogo.cn/g?b=qq&nk={user_id}&s=640"
        user_info = f"""
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

        content = []
        for part in message_parts:
            msg_type = part.get("type")
            handler = self._get_handler(msg_type)
            if handler:
                try:
                    content.append(handler(part.get("data", {})))
                except Exception as e:
                    self.logger.error(f"处理消息类型 {msg_type} 出错: {e}")
                    content.append(f"[处理失败: {msg_type}]")

        message_content = f"""
<div style="padding: 10px; background: #f1f1f1; color: #000000; border-radius: 6px; margin-top: 5px;">
    {''.join(content)}
</div>
"""

        return user_info + message_content

    async def build_md(self, data):
        sender = data.get("sender", {})
        user_id = sender.get("user_id", "未知ID")
        nickname = sender.get("nickname", "未知用户")
        message_parts = data.get("message", [])

        avatar_url = f"https://q1.qlogo.cn/g?b=qq&nk={user_id}&s=640"
        user_info = f"**{nickname}** (`{user_id}`)\n![](https://q1.qlogo.cn/g?b=qq&nk={user_id}&s=640) | 来自: QQ\n---\n"

        content = []
        for part in message_parts:
            msg_type = part.get("type")
            handler = self._get_handler(msg_type, is_md=True)
            if handler:
                try:
                    content.append(handler(part.get("data", {})))
                except Exception as e:
                    self.logger.error(f"处理消息类型 {msg_type} 出错: {e}")
                    content.append(f"[处理失败: {msg_type}]")

        message_content = "\n".join(content)

        return f"{user_info}\n{message_content}"

    async def build_text(self, data):
        sender = data.get("sender", {})
        nickname = sender.get("nickname", "未知用户")
        message_parts = data.get("message", [])

        content = []
        for part in message_parts:
            msg_type = part.get("type")
            handler = self._get_handler(msg_type, is_text=True)
            if handler:
                try:
                    content.append(handler(part.get("data", {})))
                except Exception as e:
                    self.logger.error(f"处理消息类型 {msg_type} 出错: {e}")
                    content.append(f"[处理失败: {msg_type}]")

        message_content = " ".join(content)

        return f"{nickname}: {message_content}"

    async def build_image(self, data):
        html = await self.build_html(data)
        return html  # 后续可调用截图服务生成图片

    def _get_handler(self, msg_type, is_md=False, is_text=False):
        handlers = {
            "text": lambda data: data["text"],
            "image": lambda data: f"<img src='{data['url']}' style='max-width: 100%;'>",
            "at": lambda data: f"@{data.get('qq', 'someone')} ",
            "face": lambda data: f"<img src='https://koishi.js.org/QFace/assets/qq_emoji/thumbs/gif_{data['id']}.gif' style='width:24px;height:24px;vertical-align:middle;' />",
            "voice": lambda data: f"<audio src='{data['url']}' controls></audio>",
            "video": lambda data: f"<video src='{data['url']}' controls style='max-width: 100%;'></video>",
            "forward": lambda data: "".join([self.build_html({"message": [msg]}) for msg in data.get("messages", [])]),
            "reply": lambda data: "<div class='reply'>回复</div>",
        }

        if is_md:
            handlers["image"] = lambda data: f"![图片]({data['url']})"
            handlers["at"] = lambda data: f"@{data.get('qq', 'someone')} "
            handlers["face"] = lambda data: f"![表情](https://koishi.js.org/QFace/assets/qq_emoji/thumbs/gif_{data['id']}.gif)"
            handlers["voice"] = lambda data: f"[语音]({data['url']})"
            handlers["video"] = lambda data: f"[视频]({data['url']})"

        if is_text:
            handlers["image"] = lambda data: "[图片]"
            handlers["at"] = lambda data: ""
            handlers["face"] = lambda data: "[表情]"
            handlers["voice"] = lambda data: "[语音]"
            handlers["video"] = lambda data: "[视频]"
            handlers["forward"] = lambda data: "[转发消息]"
            handlers["reply"] = lambda data: "[回复]"

        return handlers.get(msg_type)