import os
import feedparser
import google.generativeai as genai
from telegram import Bot
import asyncio
from datetime import datetime, timezone

# Securely load API keys
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# RSS Feed URL (Reuters Top News)
RSS_URL = "https://feeds.reuters.com/reuters/topNews"

async def main():
    bot = Bot(token=TELEGRAM_TOKEN)
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')

    # Parse the RSS feed
    feed = feedparser.parse(RSS_URL)
    
    # We look at the most recent article
    if not feed.entries:
        return

    article = feed.entries[0]
    title = article.title
    link = article.link
    summary_text = article.get('summary', '')

    # Create a prompt for Gemini
    prompt = f"Summarize this news in 2 bullet points: {title}. {summary_text}"
    
    try:
        summary_response = await model.generate_content_async(prompt)
        summary = summary_response.text
    except Exception:
        summary = "Summary generation failed."

    message = f"📰 *{title}*\n\n📝 *Summary:*\n{summary}\n\n🔗 [Read Full]({link})"
    
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode="Markdown")

if __name__ == "__main__":
    asyncio.run(main())
