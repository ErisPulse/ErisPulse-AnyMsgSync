class TelegramMessageBuilder:
    def __init__(self, main):
        self.main = main
        self.sdk = main.sdk
        self.logger = self.sdk.logger

    async def build_html(self, data):
        msg = data.get("message", {})
        from_user = msg.get("from", {})
        user_id = from_user.get("id")
        first_name = from_user.get("first_name", "未知用户")
        last_name = from_user.get("last_name")
        full_name = f"{first_name} {last_name}" if last_name else first_name

        try:
            avatar_text = first_name[0].upper() if first_name and first_name[0].isalpha() else "#"
        except IndexError:
            avatar_text = "#"

        color_hash = hash(str(user_id)) % 360
        background_color = f"hsl({color_hash}, 70%, 50%)"

        user_info = f"""
<div style="display: flex; align-items: center; justify-content: space-between; padding: 10px; background: #ffffff; color: #333333; border-radius: 8px;">
    <div style="display: flex; align-items: center;">
        <div style="
            width: 36px;
            height: 36px;
            border-radius: 50%;
            background-color: {background_color};
            color: white;
            font-size: 16px;
            font-weight: bold;
            display: flex;
            align-items: center;
            justify-content: center;
            margin-right: 10px;
            flex-shrink: 0;
        ">
            {avatar_text}
        </div>
        <div>
            <strong>{full_name}</strong><br>
            <small style="font-size: 12px; color: #888;">用户ID: {user_id}</small>
        </div>
    </div>
    <div style="padding: 5px; background-color: #e0f7fa; color: #00796b; font-size: 12px; font-weight: bold; border-radius: 4px;">
        来自: Telegram
    </div>
</div>
"""

        content = []
        msg_type = msg.get("type", "text")

        if msg_type == "text":
            content.append(msg.get("text", ""))
        elif msg_type == "photo":
            photo_url = msg.get("photo", [{}])[-1].get("file_url", "")
            content.append(f'<img src="{photo_url}" alt="图片" style="max-width: 100%;">')
        elif msg_type == "sticker":
            sticker_url = msg.get("sticker", {}).get("file_url", "")
            content.append(f'<img src="{sticker_url}" alt="表情包" style="width: 100px;">')
        elif msg_type == "forward":
            forwarded = await self.build_html({"message": msg.get("forwarded_message", {})})
            content.append(f'<div class="forward">{forwarded}</div>')
        elif msg_type == "video":
            video_url = msg.get("video", {}).get("file_url", "")
            content.append(f'<video src="{video_url}" controls style="max-width: 100%;"></video>')
        elif msg_type == "voice":
            voice_url = msg.get("voice", {}).get("file_url", "")
            content.append(f'<audio src="{voice_url}" controls></audio>')

        message_content = f"""
<div style="padding: 10px; background: #f1f1f1; color: #000000; border-radius: 6px; margin-top: 5px;">
    {''.join(content)}
</div>
"""

        return user_info + message_content

    async def build_markdown(self, data):
        msg = data.get("message", {})
        from_user = msg.get("from", {})
        user_id = from_user.get("id")
        first_name = from_user.get("first_name", "未知用户")
        last_name = from_user.get("last_name")
        full_name = f"{first_name} {last_name}" if last_name else first_name

        msg_type = msg.get("type", "text")
        if msg_type == "text":
            text = msg.get("text", "")
            return f"**{full_name}** (`{user_id}`)\n{text}"
        elif msg_type == "photo":
            photo_url = msg.get("photo", [{}])[-1].get("file_url", "")
            return f"**{full_name}** (`{user_id}`)\n![图片]({photo_url})"
        elif msg_type == "sticker":
            sticker_url = msg.get("sticker", {}).get("file_url", "")
            return f"**{full_name}** (`{user_id}`)\n![表情包]({sticker_url})"
        elif msg_type == "forward":
            forwarded = await self.build_markdown({"message": msg.get("forwarded_message", {})})
            return f"**{full_name}** (`{user_id}`)\n> 转发消息：\n{forwarded}"
        elif msg_type == "video":
            video_url = msg.get("video", {}).get("file_url", "")
            return f"**{full_name}** (`{user_id}`)\n[视频]({video_url})"
        elif msg_type == "voice":
            voice_url = msg.get("voice", {}).get("file_url", "")
            return f"**{full_name}** (`{user_id}`)\n[语音]({voice_url})"
        return ""

    async def build_text(self, data):
        msg = data.get("message", {})
        from_user = msg.get("from", {})
        first_name = from_user.get("first_name", "未知用户")
        last_name = from_user.get("last_name")
        full_name = f"{first_name} {last_name}" if last_name else first_name

        msg_type = msg.get("type", "text")
        if msg_type == "text":
            return f"{full_name}: {msg.get('text', '')}"
        elif msg_type in ["photo", "sticker"]:
            return f"{full_name}: [图片]"
        elif msg_type == "forward":
            return f"{full_name}: [转发消息]"
        elif msg_type == "video":
            return f"{full_name}: [视频]"
        elif msg_type == "voice":
            return f"{full_name}: [语音]"
        return ""