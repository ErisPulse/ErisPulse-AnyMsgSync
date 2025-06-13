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

        return f"""
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
<div style="padding: 10px; background: #f1f1f1; color: #000000; border-radius: 6px; margin-top: 5px;">
    {msg.get('text', '')}
</div>
"""

    async def build_markdown(self, data):
        msg = data.get("message", {})
        from_user = msg.get("from", {})
        user_id = from_user.get("id")
        first_name = from_user.get("first_name", "未知用户")
        last_name = from_user.get("last_name")
        full_name = f"{first_name} {last_name}" if last_name else first_name

        return f"**{full_name}** (`{user_id}`)\n{msg.get('text', '')}"

    async def build_text(self, data):
        msg = data.get("message", {})
        from_user = msg.get("from", {})
        first_name = from_user.get("first_name", "未知用户")
        last_name = from_user.get("last_name")
        full_name = f"{first_name} {last_name}" if last_name else first_name

        return f"{full_name}: {msg.get('text', '')}"