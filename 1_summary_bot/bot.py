import logging
import re
import requests

from bs4 import BeautifulSoup
from openai import OpenAI

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

BOT_TOKEN = "ТОКЕН_БОТА"

GROQ_API_KEY = "КЛЮЧ_ГРОК_АПИ"

client = OpenAI(
    api_key=GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1",
)

logging.basicConfig(level=logging.INFO)

def extract_text_from_url(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=20,
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    for tag in soup([
        "script",
        "style",
        "nav",
        "footer",
        "header",
        "aside",
        "noscript",
        "svg",
    ]):
        tag.decompose()

    text = soup.get_text(separator=" ")

    text = re.sub(r"\s+", " ", text)

    return text.strip()



def summarize_with_ai(text: str) -> str:
    short_text = text[:12000]

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",

        messages=[
            {
                "role": "system",
                "content": (
                    "Ты делаешь качественные "
                    "конспекты статей."
                ),
            },
            {
                "role": "user",
                "content": f"""
Сделай краткий конспект статьи.

Правила:
- 5 пунктов
- только главное
- без воды
- понятным языком
- на русском

Статья:
{short_text}
""",
            },
        ],

        temperature=0.4,
    )

    return response.choices[0].message.content



async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        "👋 Отправь ссылку на статью."
    )

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    url = update.message.text.strip()

    if not url.startswith("http"):
        await update.message.reply_text(
            "❌ Это не ссылка."
        )
        return

    msg = await update.message.reply_text(
        "⏳ Загружаю статью..."
    )

    try:
        article_text = extract_text_from_url(url)

        if len(article_text) < 300:
            await msg.edit_text(
                "❌ Не удалось извлечь текст."
            )
            return

        await msg.edit_text(
            "🤖 Делаю конспект..."
        )

        summary = summarize_with_ai(article_text)

        # лимит Telegram
        if len(summary) > 4000:
            summary = summary[:4000]

        await msg.edit_text(
            f"📝 КОНСПЕКТ:\n\n{summary}"
        )

    except Exception as e:
        await msg.edit_text(
            f"❌ Ошибка:\n\n{str(e)}"
        )



def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message,
        )
    )

    print("Bot started...")

    app.run_polling()

if __name__ == "__main__":
    main()
