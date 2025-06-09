import aiohttp
import re
import asyncio

def decode_utf8(text):
    return re.sub(r'\\u([09a-fA-F]{4})', lambda x: chr(int(x.group(1), 16)), text)


class YunhuMessageBuilder:
    def __init__(self, main):
        self.main = main
        self.sdk = main.sdk
        self.logger = self.sdk.logger
        self.session = None

    async def _get_session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session

    async def _fetch_data(self, url, check_string, patterns):
        session = await self._get_session()
        try:
            async with session.get(url, timeout=5) as response:
                if response.status != 200:
                    return {"code": -1, "msg": f"请求失败: HTTP {response.status}"}
                text = await response.text()
        except Exception as e:
            return {"code": -1, "msg": f"请求失败: {str(e)}"}

        if check_string in text:
            return {"code": 2, "msg": "对象不存在，请检查输入的 ID 是否正确"}

        data = {}
        for key, pattern in patterns.items():
            match = re.search(pattern, text)
            if match:
                value = match.group(1)
                if key.endswith('Id') or key == 'headcount':
                    value = int(value)
                elif key == 'private':
                    value = value == "1"
                elif key == 'isVip':
                    value = value != "0"
                elif key == 'medal':
                    value = [decode_utf8(m) for m in re.findall(pattern, text)]
                else:
                    value = decode_utf8(value)
                data[key] = value

        if all(key in data for key in patterns):
            return {"code": 1, "msg": "ok", "data": data}
        else:
            return {"code": -3, "msg": "解析数据失败"}

    async def get_user_info(self, user_id):
        url = f"https://www.yhchat.com/user/homepage/{user_id}"
        check_string = 'data-v-34a9b5c4>ID </span>'
        patterns = {
            "userId": r'userId:"(.*?)"',
            "nickname": r'nickname:"(.*?)"',
            "avatarUrl": r'avatarUrl:"(.*?)"',
        }
        return await self._fetch_data(url, check_string, patterns)

    async def get_group_info(self, group_id):
        url = f"https://www.yhchat.com/group/homepage/{group_id}"
        check_string = 'data-v-6eef215f>ID </span>'
        patterns = {
            "groupId": r'ID\s+(\w+)',
            "name": r'name:"(.*?)"',
        }
        return await self._fetch_data(url, check_string, patterns)

    async def get_bot_info(self, bot_id):
        url = f"https://www.yhchat.com/bot/homepage/{bot_id}"
        check_string = 'data-v-4f86f6dc>ID </span>'
        patterns = {
            "botId": r'ID\s+(\w+)',
            "nickname": r'nickname:"(.*?)"',
            "avatarUrl": r'avatarUrl:"(.*?)"',
        }
        return await self._fetch_data(url, check_string, patterns)

    async def _get_sender_info(self, sender_id):
        result = await self.get_user_info(sender_id)
        if result["code"] == 1:
            user_data = result["data"]
            nickname = user_data.get("nickname", sender_id)
            avatar_url = user_data.get("avatarUrl", "https://yunhu.io/static/images/default_avatar.png")
        else:
            nickname = sender_id
            avatar_url = "https://yunhu.io/static/images/default_avatar.png"
        return nickname, avatar_url

    async def build_html(self, data):
        yunhu_event = data.get("event", {})
        yunhu_msg = yunhu_event.get("message", {})
        yunhu_user = yunhu_event.get("sender", {})

        sender_id = yunhu_user.get("senderId", "未知ID")
        sender_nickname, avatar_url = await self._get_sender_info(sender_id)
        content = yunhu_msg.get("content", {}).get("text", "")

        user_info = f"""
<div style="display: flex; align-items: center; justify-content: space-between; padding: 10px; background: #ffffff; color: #333333; border-radius: 8px;">
    <div style="display: flex; align-items: center;">
        <img src="{avatar_url}" alt="用户头像" style="width: 36px; height: 36px; border-radius: 50%; margin-right: 10px;">
        <div>
            <strong>{sender_nickname}</strong><br>
            <small style="font-size: 12px; color: #888;">用户ID: {sender_id}</small>
        </div>
    </div>
    <div style="padding: 5px; background-color: #e0f7fa; color: #00796b; font-size: 12px; font-weight: bold; border-radius: 4px;">
        来自: Yunhu
    </div>
</div>
"""

        message_content = f"""
<div style="padding: 10px; background: #f1f1f1; color: #000000; border-radius: 6px; margin-top: 5px;">
    {content}
</div>
"""

        return user_info + message_content

    async def build_md(self, data):
        yunhu_event = data.get("event", {})
        yunhu_user = yunhu_event.get("sender", {})
        yunhu_msg = yunhu_event.get("message", {})

        sender_id = yunhu_user.get("senderId", "未知ID")
        sender_nickname, _ = await self._get_sender_info(sender_id)
        content = yunhu_msg.get("content", {}).get("text", "")

        return f"**{sender_nickname}** (`{sender_id}`): {content}"

    async def build_text(self, data):
        yunhu_event = data.get("event", {})
        yunhu_user = yunhu_event.get("sender", {})
        yunhu_msg = yunhu_event.get("message", {})

        sender_id = yunhu_user.get("senderId", "未知ID")
        sender_nickname, _ = await self._get_sender_info(sender_id)
        content = yunhu_msg.get("content", {}).get("text", "")

        return f"{sender_nickname}({sender_id}): {content}"