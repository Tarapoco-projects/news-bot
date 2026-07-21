import os
import json
import html  # Add this import
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
    """
    Fetches, parses, summarizes, and sends updates for a single RSS feed.
    """
    print(f"Parsing feed: {feed_url}")
    try:
        feed = feedparser.parse(feed_url)
    except Exception as e:
        print(f"Failed to parse feed {feed_url}: {e}")
        return []

    if not feed.entries:
        return []

    new_articles = []
    # Inspect the top 3 most recent articles from this feed to check for new content
    for entry in feed.entries[:3]:
        link = entry.get('link')
        if not link:
            continue
        if link in cache:
            continue
        new_articles.append(entry)

    sent_links = []
    for article in new_articles:
        # Wrap title and summary in html.unescape to convert entities like &#8217; to normal apostrophes
        title = html.unescape(article.get('title', 'No Title Specified'))
        link = article.get('link')
        summary_text = html.unescape(article.get('summary', ''))

        print(f"New article found: '{title}'")

        # Create a clean, direct prompt for the model
        prompt = f"Summarize this news article in exactly 2 bullet points:\n\nTitle: {title}\nContent: {summary_text}"
        
        try:
            # Generate summary synchronously to prevent asyncio event-loop conflicts
            summary_response = model.generate_content(
                prompt,
                safety_settings={
                    "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
                    "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
                    "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
                    "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE",
                }
            )
            
            if summary_response.text:
                raw_summary = summary_response.text
                
                # --- Post-Processing / Output Cleanup ---
                # 1. Split into lines and strip all leading/trailing whitespaces from each line
                lines = [line.strip() for line in raw_summary.split("\n") if line.strip()]
                
                cleaned_lines = []
                for line in lines:
                    lower_line = line.lower()
                    # 2. Skip any common introductory phrases if they slip past the model
                    if lower_line.startswith(("here is", "here are", "summary of", "this is a", "the following is")) and line.endswith(":"):
                        continue
                    cleaned_lines.append(line)
                
                # Reconstruct summary with single newline separations and no leading indents
                summary = "\n".join(cleaned_lines)
            else:
                summary = "Could not generate summary (empty response)."
                
        except Exception as e:
            print(f"Gemini API error for '{title}': {e}")
            summary = "Summary generation failed due to an API error."

        message = f"📰 *{title}*\n\n📝 *Summary:*\n{summary}\n\n🔗 [Read Full]({link})"
        
        try:
            # Attempt to send with markdown styling
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode="Markdown")
            sent_links.append(link)
        except Exception as e:
            print(f"Markdown send failed ({e}), attempting fallback plain text delivery.")
            try:
                # Fallback to plain text if the AI summary included unescaped Markdown syntax
                await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
                sent_links.append(link)
            except Exception as e_inner:
                print(f"Failed to send message entirely: {e_inner}")

        # Minor cooldown to avoid Telegram bot API rate limits
        await asyncio.sleep(1.5)

    return sent_links


async def main():
    """
    Main orchestrator of the bot execution.
    """
    if not all([TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, GEMINI_API_KEY]):
        print("Required environment keys are missing. Exiting run.")
        return

    bot = Bot(token=TELEGRAM_TOKEN)
    genai.configure(api_key=GEMINI_API_KEY)
    
    # Initialize the Gemini 3.1 Flash-Lite model with direct system instruction
    model = genai.GenerativeModel(
        'gemini-3.1-flash-lite',
        system_instruction=(
            "You are a precise news summarizer. Output ONLY the requested bullet points. "
            "Never include introductory text, conversational filler (such as 'Here is a summary:'), "
            "or wrap-up sentences. Start immediately with the first bullet point. "
            "Use a standard hyphen (-) or bullet (•) with no leading spaces or indentation."
        )
    )

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
