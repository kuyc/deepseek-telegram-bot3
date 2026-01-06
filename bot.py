import os
import time
import requests
from io import BytesIO
from openai import OpenAI
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters
)

# ================== ENV ==================

BOT_TOKEN = os.getenv("BOT_TOKEN")
MS_API_KEY = os.getenv("MS_API_KEY")

# ================== LLM (DeepSeek) ==================

llm_client = None
if MS_API_KEY:
    llm_client = OpenAI(
        base_url="https://api-inference.modelscope.ai/v1",
        api_key=MS_API_KEY,
    )

def ask_deepseek(prompt: str) -> str:
    if not llm_client:
        return "❌ DeepSeek недоступен (проверь MS_API_KEY)."

    try:
        response = llm_client.chat.completions.create(
            model="deepseek-ai/DeepSeek-V3.2",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Отвечай кратко, красиво и по делу. "
                        "Без оправданий и лишних объяснений. "
                        "Если нужен prompt — дай готовый аккуратный prompt."
                    )
                },
                {"role": "user", "content": prompt}
            ],
            extra_body={"enable_thinking": False}
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Ошибка DeepSeek: {e}"

# ================== IMAGE (ModelScope) ==================

async def generate_image(prompt: str, update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not MS_API_KEY:
        await context.bot.send_message(
            chat_id=update.channel_post.chat_id,
            text="❌ Генерация изображений недоступна (нет MS_API_KEY)."
        )
        return

    base_url = "https://api-inference.modelscope.ai/"
    headers = {
        "Authorization": f"Bearer {MS_API_KEY}",
        "Content-Type": "application/json",
    }

    # запуск задачи
    r = requests.post(
        f"{base_url}v1/images/generations",
        headers={**headers, "X-ModelScope-Async-Mode": "true"},
        json={
            "model": "ChenkinNoob/ChenkinNoob-XL-V0.2",
            "prompt": prompt
        }
    )

    if r.status_code != 200:
        await context.bot.send_message(
            chat_id=update.channel_post.chat_id,
            text="❌ Не удалось запустить генерацию изображения."
        )
        return

    task_id = r.json().get("task_id")

    # ожидание результата
    for _ in range(20):  # ~100 секунд максимум
        time.sleep(5)

        status = requests.get(
            f"{base_url}v1/tasks/{task_id}",
            headers={**headers, "X-ModelScope-Task-Type": "image_generation"},
        ).json()

        if status.get("task_status") == "SUCCEED":
            img_url = status["output_images"][0]
            img_bytes = requests.get(img_url).content

            await context.bot.send_photo(
                chat_id=update.channel_post.chat_id,
                photo=BytesIO(img_bytes),
                caption=f"🖼 {prompt}",
                reply_to_message_id=update.channel_post.message_id
            )
            return

        if status.get("task_status") == "FAILED":
            await context.bot.send_message(
                chat_id=update.channel_post.chat_id,
                text="❌ Генерация изображения не удалась."
            )
            return

    await context.bot.send_message(
        chat_id=update.channel_post.chat_id,
        text="⏳ Генерация изображения заняла слишком много времени."
    )

# ================== PRIVATE ==================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        await update.message.reply_text(
            "✅ Бот работает.\n\n"
            "В канале используй:\n"
            "@deepseek вопрос\n"
            "@image описание картинки"
        )

# ================== CHANNEL ==================

async def channel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.channel_post
    if not msg or not msg.text:
        return

    text = msg.text.strip()

    # DeepSeek
    if text.lower().startswith("@deepseek"):
        query = text[len("@deepseek"):].strip()
        if not query:
            return
        answer = ask_deepseek(query)
        await context.bot.send_message(
            chat_id=msg.chat_id,
            text=answer,
            reply_to_message_id=msg.message_id
        )

    # Image
    elif text.lower().startswith("@image"):
        query = text[len("@image"):].strip()
        if not query:
            return
        await generate_image(query, update, context)

# ================== MAIN ==================

def main():
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN не найден.")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL, channel_handler))

    print("Бот запущен")
    app.run_polling()

if __name__ == "__main__":
    main()
