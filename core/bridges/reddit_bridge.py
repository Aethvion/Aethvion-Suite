import requests
from typing import Dict, Any
from core.utils import get_logger

logger = get_logger(__name__)

HEADERS = {
    "User-Agent": "AethvionSuite/1.0 (Local AI Connector Hub)"
}


def get_top_posts(args: Dict[str, Any]) -> str:
    """
    Fetch hot/top posts from a subreddit (defaults to 'technology' or configured default).
    Optional args:
        - subreddit (str): Subreddit name without r/ (e.g. 'LocalLLaMA', 'programming')
        - limit (int): Number of posts (default 5, max 10)
    """
    sub = (args.get("subreddit") or args.get("query") or "LocalLLaMA").strip().lstrip("r/").strip("/")
    if not sub:
        sub = "LocalLLaMA"
    try:
        limit = min(max(int(args.get("limit", 5)), 1), 10)
    except (ValueError, TypeError):
        limit = 5

    try:
        url = f"https://www.reddit.com/r/{sub}/hot.json?limit={limit + 2}"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        children = resp.json().get("data", {}).get("children", [])
        posts = []
        for item in children:
            d = item.get("data", {})
            if d.get("stickied"):
                continue
            title = d.get("title", "Untitled")
            score = d.get("score", 0)
            comments = d.get("num_comments", 0)
            permalink = f"https://reddit.com{d.get('permalink', '')}"
            selftext = (d.get("selftext") or "").strip()
            snippet = f" — {selftext[:140]}..." if len(selftext) > 140 else (f" — {selftext}" if selftext else "")
            posts.append(f"• [{score}↑ | {comments} comments] {title}{snippet}\n  {permalink}")
            if len(posts) >= limit:
                break

        if not posts:
            return f"No posts found in r/{sub}."
        return f"Top posts in r/{sub}:\n" + "\n".join(posts)
    except Exception as e:
        logger.error(f"Reddit Connector Error: {e}")
        return f"Reddit Connector Error: Could not fetch r/{sub}. ({e})"


def search_reddit(args: Dict[str, Any]) -> str:
    """
    Search Reddit posts across all subreddits or a specific subreddit.
    Args:
        - query (str): Search query
        - subreddit (str, optional): Restrict search to a subreddit
    """
    query = (args.get("query") or "").strip()
    if not query:
        return get_top_posts(args)

    sub = (args.get("subreddit") or "").strip().lstrip("r/").strip("/")
    try:
        if sub:
            url = f"https://www.reddit.com/r/{sub}/search.json"
            params = {"q": query, "restrict_sr": "on", "sort": "relevance", "limit": 5}
        else:
            url = "https://www.reddit.com/search.json"
            params = {"q": query, "sort": "relevance", "limit": 5}

        resp = requests.get(url, headers=HEADERS, params=params, timeout=10)
        resp.raise_for_status()
        children = resp.json().get("data", {}).get("children", [])
        if not children:
            return f"No Reddit results found for '{query}'."

        lines = [f"Reddit search results for '{query}':"]
        for item in children[:5]:
            d = item.get("data", {})
            sub_name = d.get("subreddit_name_prefixed", "r/reddit")
            title = d.get("title", "Untitled")
            score = d.get("score", 0)
            permalink = f"https://reddit.com{d.get('permalink', '')}"
            lines.append(f"• [{sub_name} · {score}↑] {title}\n  {permalink}")
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"Reddit Search Error: {e}")
        return f"Reddit Connector Error: Search failed for '{query}'. ({e})"
