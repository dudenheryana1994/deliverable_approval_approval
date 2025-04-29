import requests
import json
import os
from dotenv import load_dotenv
from datetime import datetime
import logging

# Konfigurasi logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
logger.debug("Starting script at " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

# Muat variabel lingkungan dari file .env
load_dotenv()

NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
NOTION_API_KEY = os.getenv("NOTION_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
SENT_IDS_FILE = "id_sent.json"

def get_notion_data():
    url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    try:
        response = requests.post(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching Notion data: {e}")
        return None

def send_to_telegram(chat_id, message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        logger.info(f"Message sent to Telegram ID {chat_id}")
        logger.debug(f"Telegram response: {response.text}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Error sending message to {chat_id}: {e}")

def read_sent_ids():
    if os.path.exists(SENT_IDS_FILE):
        with open(SENT_IDS_FILE, "r") as f:
            return json.load(f)
    return []

def save_sent_ids(sent_ids):
    with open(SENT_IDS_FILE, "w") as f:
        json.dump(sent_ids, f, indent=4)

def extract_text(rich_text_list, default="Tidak ada data"):
    if not rich_text_list:
        return default
    return " ".join([text.get("plain_text", "") for text in rich_text_list if "plain_text" in text])

def extract_date(prop):
    """Ambil isi tanggal dari field date biasa"""
    if isinstance(prop, dict):
        date_data = prop.get("date")
        if date_data and isinstance(date_data, dict):
            return date_data.get("start", "Tidak ada data")
    return "Tidak ada data"

def format_approval_date(date_str):
    """Format tanggal ISO8601 ke DD/MM/YYYY HH:MM"""
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception as e:
        logger.error(f"Error formatting date {date_str}: {e}")
        return date_str  # fallback tampilkan apa adanya

def extract_formula(prop):
    """Ambil nilai dari properti formula Notion dengan tepat"""
    if not isinstance(prop, dict):
        return "Tidak ada data"

    formula_result = prop.get("formula")
    if not formula_result:
        return "Tidak ada data"

    # Cek tipe hasil formula dan ambil isinya sesuai tipe
    if formula_result.get("type") == "string" and formula_result.get("string") is not None:
        return formula_result["string"]
    if formula_result.get("type") == "number" and formula_result.get("number") is not None:
        return str(formula_result["number"])
    if formula_result.get("type") == "boolean" and formula_result.get("boolean") is not None:
        return str(formula_result["boolean"])
    if formula_result.get("type") == "date" and formula_result.get("date") is not None:
        return formula_result["date"].get("start", "Tidak ada data")

    return "Tidak ada data"

def main():
    notion_data = get_notion_data()
    if not notion_data:
        return

    results = notion_data.get("results", [])
    if not results:
        logger.info("No data found.")
        return

    sent_ids = read_sent_ids()

    for item in results:
        item_id = item.get("id")
        properties = item.get("properties", {})

        # Ambil data dari properti
        activities_name = extract_text(properties.get("Activities Name", {}).get("title", []))
        user_name = extract_text(properties.get("User Name", {}).get("rich_text", []))

        approve_decline_prop = properties.get("Approve / Decline")
        approve_decline = "Tidak ada data"
        if approve_decline_prop:
            select_data = approve_decline_prop.get("select")
            if select_data:
                approve_decline = select_data.get("name", "Tidak ada data")

        approval_date_raw = extract_date(properties.get("Approval Date"))
        approval_date = format_approval_date(approval_date_raw) if approval_date_raw != "Tidak ada data" else "Tidak ada data"

        no_id = extract_text(properties.get("ID Activities", {}).get("rich_text", []))
        project_name = extract_text(properties.get("Project Name", {}).get("rich_text", []), default="-")
        work_package_name = extract_text(properties.get("Work Package Name", {}).get("rich_text", []))
        act_duration = extract_text(properties.get("Act. Duration", {}).get("rich_text", []))

        # Ambil nilai ID Kirim FB dan ID Telegram (U)
        id_kirim_fb = extract_text(properties.get("ID Kirim FB", {}).get("rich_text", []))
        tele_id_u = extract_text(properties.get("ID Telegram (As)", {}).get("rich_text", []))

        logger.debug(f"ID Telegram (As) for item {item_id}: {tele_id_u}")
        logger.debug(f"ID Kirim FB: {id_kirim_fb}")
        logger.debug(f"ID Activities for item {item_id}: {no_id}")

        if item_id not in sent_ids and id_kirim_fb != "Tidak ada data" and tele_id_u != "Tidak ada data":
            message = (
                f"*STATUS APPROVAL DELIVERABLE*\n\n"
                f"📅 *Tanggal Approve:* {approval_date}\n"
                f"🏗 *Nama Project:* {project_name}\n"
                f"📦 *Work Package:* {work_package_name}\n"
                f"📄 *Nama Activity:* {activities_name}\n"
                f"🆔 *ID Activity:* {no_id}\n"
                f"✅ *Status:* {approve_decline}\n"
                f"👤 *Di approve oleh:* {user_name}\n"
                f"⏳ *Durasi Pekerjaan:* {act_duration}"

            )
            logger.debug(f"Sending message: {message}")
            send_to_telegram(tele_id_u, message)
            sent_ids.append(item_id)
            save_sent_ids(sent_ids)

if __name__ == "__main__":
    main()
