import os
import httpx
import google.generativeai as genai
from telegram import Bot
import asyncio
from datetime import datetime, timezone, timedelta

# Securely load API keys
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
NEWS_API_KEY = os.environ.get("NEWS_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

async def main():
    bot = Bot(token=TELEGRAM_TOKEN)
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')

    # Calculate the time 15 minutes ago
    fifteen_mins_ago = datetime.now(timezone.utc) - timedelta(minutes=15)

    url = f"https://newsapi.org/v2/top-headlines?country=us&apiKey={NEWS_API_KEY}"
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        data = response.json()

    if data.get("status") != "ok" or not data.get("articles"):
        return

    # Find articles published strictly in the last 15 minutes
    new_articles = []
    for article in data["articles"]:
        pub_str = article.get("publishedAt")
        if not pub_str: continue
        
        # Convert NewsAPI time format to Python format
        pub_time = datetime.strptime(pub_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        if pub_time >= fifteen_mins_ago:
            new_articles.append(article)

    if not new_articles:
        print("No new articles published in the last 15 minutes.")
        return

    # Grab the most recent new article to summarize
    article = new_articles[0]
    title = article.get("title", "No Title")
    article_url = article.get("url")
    raw_text = f"Description: {article.get('description', '')}\nContent: {article.get('content', '')}"
    
    prompt = f"You are a concise news editor. Summarize the following news article in 2 to 3 bullet points. Keep it factual and brief.\n\nTitle: {title}\nText: {raw_text}"
    
    try:
        summary_response = await model.generate_content_async(prompt)
        summary = summary_response.text
    except Exception:
        summary = "Summary generation failed."

    message = f"📰 *{title}*\n\n📝 *Summary:*\n{summary}\n\n🔗 [Read Full Article]({article_url})"
    
    # Send directly to your Chat ID
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode="Markdown", disable_web_page_preview=True)

if __name__ == "__main__":
    asyncio.run(main())
