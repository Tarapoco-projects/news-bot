import os
import json
import feedparser
import google.generativeai as genai
from telegram import Bot
import asyncio

# Securely load API keys
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Local cache settings to prevent duplicates
CACHE_FILE = "processed_urls.json"
MAX_CACHE_SIZE = 100

# Multi-Feed aggregation target list
RSS_FEEDS = [
    "http://feeds.bbci.co.uk/news/rss.xml",     # BBC News
    "https://techcrunch.com/feed/",             # TechCrunch
    "https://www.theverge.com/rss/index.xml"    # The Verge
]

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error reading cache file, starting fresh: {e}")
            return []
    return []

def save_cache(cache):
    try:
        # Keep only the last N items to keep the repository commit footprint small
        with open(CACHE_FILE, "w") as f:
            json.dump(cache[-MAX_CACHE_SIZE:], f, indent=4)
    except Exception as e:
        print(f"Error saving cache file: {e}")

async def process_feed(feed_url, cache, bot, model):
    print(f"Parsing feed: {feed_url}")
    try:
        feed = feedparser.parse(feed_url)
    except Exception as e:
        print(f"Failed to parse feed {feed_url}: {e}")
        return []

    if not feed.entries:
        return []

    new_articles = []
    for entry in feed.entries[:3]:
        link = entry.get('link')
        if not link:
            continue
        if link in cache:
            continue
        new_articles.append(entry)

    sent_links = []
    for article in new_articles:
        title = article.get('title', 'No Title Specified')
        link = article.get('link')
        summary_text = article.get('summary', '')

        print(f"New article found: '{title}'")

        # Create the prompt
        prompt = f"Summarize this news in 2 bullet points: {title}. {summary_text}"
        
        try:
            # 1. Switch to sync generation to prevent asyncio event-loop conflicts.
            # 2. Relax safety filters so real-world news is not blocked.
            summary_response = model.generate_content(
                prompt,
                safety_settings={
                    "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
                    "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
                    "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
                    "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE",
                }
            )
            
            # Check if the response contains text before accessing it
            if summary_response.text:
                summary = summary_response.text
            else:
                summary = "Could not generate summary (empty response)."
                
        except Exception as e:
            # This will print the precise error details to your GitHub Action/Local console
            print(f"Gemini API error for '{title}': {e}")
            summary = "Summary generation failed due to an API error."

        message = f"📰 *{title}*\n\n📝 *Summary:*\n{summary}\n\n🔗 [Read Full]({link})"
        
        try:
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode="Markdown")
            sent_links.append(link)
        except Exception as e:
            print(f"Markdown send failed ({e}), attempting fallback plain text delivery.")
            try:
                await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
                sent_links.append(link)
            except Exception as e_inner:
                print(f"Failed to send message entirely: {e_inner}")

        await asyncio.sleep(1.5)

    return sent_links

async def main():
    if not all([TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, GEMINI_API_KEY]):
        print("Required environment keys are missing. Exiting run.")
        return

    bot = Bot(token=TELEGRAM_TOKEN)
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')

    cache = load_cache()
    new_cache_entries = []

    for feed_url in RSS_FEEDS:
        sent_links = await process_feed(feed_url, cache, bot, model)
        new_cache_entries.extend(sent_links)
        await asyncio.sleep(2)

    if new_cache_entries:
        cache.extend(new_cache_entries)
        save_cache(cache)
        print(f"Run completed. Cached {len(new_cache_entries)} new articles.")
    else:
        print("Run completed. No new articles found.")

if __name__ == "__main__":
    asyncio.run(main())
