# utils/helpers.py

import telebot
import logging
import random
import string

# این خط برای دسترسی به لیست ادمین‌ها اضافه شده است
from config import ADMIN_IDS

logger = logging.getLogger(__name__)


# تابع is_admin در اینجا تعریف شده است
def is_admin(user_id: int) -> bool:
    """بررسی می‌کند که آیا کاربر ادمین است یا خیر."""
    return user_id in ADMIN_IDS


def is_user_member_of_channel(bot: telebot.TeleBot, channel_id: int, user_id: int) -> bool:
    """
    بررسی می‌کند که آیا کاربر در کانال مورد نظر عضو است یا خیر.
    """
    if channel_id is None:
        return True

    try:
        chat_member = bot.get_chat_member(channel_id, user_id)
        return chat_member.status in ['member', 'creator', 'administrator']
    except Exception as e:
        logger.error(f"Error checking user {user_id} membership in channel {channel_id}: {e}")
        # در صورت بروز خطا (مثلا اگر ربات از کانال حذف شده باشد)، دسترسی را مجاز می‌دانیم تا ربات متوقف نشود
        return True


def is_float_or_int(value) -> bool:
    """
    بررسی می‌کند که آیا یک رشته می‌تواند به float یا int تبدیل شود یا خیر.
    """
    try:
        float(value)
        return True
    except (ValueError, TypeError):
        return False


def escape_markdown_v1(text: str) -> str:
    """
    کاراکترهای خاص Markdown V1 را برای جلوگیری از خطا در پارس کردن، Escape می‌کند.
    """
    escape_chars = r'_*`[]()~>#+-=|{}!.'

    if not isinstance(text, str):
        text = str(text)

    # استفاده از str.translate برای کارایی بهتر
    return text.translate(str.maketrans({c: f'\\{c}' for c in escape_chars}))


def generate_random_string(length=10) -> str:
    """
    یک رشته تصادفی از حروف کوچک و اعداد به طول مشخص تولید می‌کند.
    """
    characters = string.ascii_lowercase + string.digits
    return ''.join(random.choice(characters) for i in range(length))