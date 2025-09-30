# utils/notifier.py
import os
import requests
from dotenv import load_dotenv
from .constants import ENV_FILE

load_dotenv(dotenv_path=ENV_FILE)

def send_telegram_message(message):
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    if not bot_token or not chat_id:
        print("CẢNH BÁO: Biến môi trường Telegram chưa được thiết lập. Bỏ qua gửi thông báo.")
        return

    print("Đang gửi báo cáo tới Telegram...")
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            data={'chat_id': chat_id, 'text': message, 'parse_mode': 'Markdown'},
            timeout=10
        )
        if response.status_code == 200:
            print("✅ Đã gửi báo cáo thành công tới Telegram.")
        else:
            print(f"❌ Lỗi khi gửi báo cáo Telegram: {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Lỗi kết nối tới Telegram API: {e}")