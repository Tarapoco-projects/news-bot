import os
import asyncio
import httpx
import google.generativeai as genai
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Securely load API keys from environment variables
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
NEWS_API_KEY = os.environ.get("NEWS_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not all([TELEGRAM_TOKEN, NEWS_API_KEY, GEMINI_API_KEY]):
    raise ValueError("Missing one or more API keys in environment variables!")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

seen_articles = set()

async def fetch_and_summarize(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    url = f"https://newsapi.org/v2/top-headlines?country=us&apiKey={NEWS_API_KEY}"
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        data = response.json()

    if data.get("status") != "ok" or not data.get("articles"):
        return

    for article in data["articles"]:
        article_url = article.get("url")
        if article_url in seen_articles:
            continue

        seen_articles.add(article_url)
        title = article.get("title", "No Title")
        date_published = article.get("publishedAt", "Unknown Date")[:10]
        
        raw_text = f"Description: {article.get('description', '')}\nContent: {article.get('content', '')}"
        prompt = f"You are a concise news editor. Summarize the following news article in 2 to 3 bullet points. Keep it factual and brief.\n\nTitle: {title}\nText: {raw_text}"
        
        try:
            summary_response = await model.generate_content_async(prompt)
            summary = summary_response.text
        except Exception:
            summary = "Summary generation failed."

        message = f"📰 *{title}*\n📅 {date_published}\n\n📝 *Summary:*\n{summary}\n\n🔗 [Read Full Article]({article_url})"
        
        await context.bot.send_message(
            chat_id=chat_id, text=message, parse_mode="Markdown", disable_web_page_preview=True
        )
        break 

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text("News Summary Bot is now active! 🗞️\nI will check for breaking news every 15 minutes.")
    
    current_jobs = context.job_queue.get_jobs_by_name(str(chat_id))
    for job in current_jobs:
        job.schedule_removal()

    context.job_queue.run_repeating(
        fetch_and_summarize, interval=900, first=5, chat_id=chat_id, name=str(chat_id)
    )

if __name__ == '__main__':
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    print("Bot is starting in the cloud...")
    app.run_polling(allowed_updates=Update.ALL)