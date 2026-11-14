"""
News and Event Collectors for God's Eye Market Intelligence
Fetches financial news, corporate announcements, and regulatory updates
from Indian market RSS feeds and web endpoints.
"""

from __future__ import annotations
import hashlib
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Curated, reliable Indian financial RSS endpoints
DEFAULT_INDIAN_RSS_FEEDS = [
    {
        "source": "Economic Times - Markets",
        "url": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    },
    {
        "source": "Economic Times - Stocks",
        "url": "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms",
    },
    {
        "source": "Moneycontrol - Markets",
        "url": "https://www.moneycontrol.com/rss/marketreports.xml",
    },
    {
        "source": "Moneycontrol - Top News",
        "url": "https://www.moneycontrol.com/rss/MCtopnews.xml",
    },
    {
        "source": "Livemint - Markets",
        "url": "https://www.livemint.com/rss/markets",
    },
    {
        "source": "RBI - Press Releases",
        "url": "https://www.rbi.org.in/pressreleases_rss.xml",
    },
]


class RSSNewsCollector:
    """
    Fetches raw financial news from RSS feeds for Indian equity markets.
    """

    def __init__(
        self,
        feeds: Optional[List[Dict[str, str]]] = None,
        timeout: int = 10,
        user_agent: Optional[str] = None,
    ):
        self.feeds = feeds or DEFAULT_INDIAN_RSS_FEEDS
        self.timeout = timeout
        self.headers = {
            "User-Agent": user_agent
            or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        }

    def _generate_id(self, url: str, title: str) -> str:
        """Deterministically hashes URL and title to create a unique ID."""
        key = f"{url.strip()}|{title.strip()}".encode("utf-8")
        return hashlib.sha256(key).hexdigest()[:16]

    def _parse_published_date(self, date_str: Optional[str]) -> str:
        """Parses various RSS date formats into ISO 8601 UTC string."""
        if not date_str:
            return datetime.now(timezone.utc).isoformat()
        try:
            dt = parsedate_to_datetime(date_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt.isoformat()
        except Exception:
            # Fallback parsing
            formats = [
                "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%d %H:%M:%S",
                "%d %b %Y %H:%M:%S",
                "%a, %d %b %Y %H:%M:%S %Z",
            ]
            for fmt in formats:
                try:
                    dt = datetime.strptime(date_str[:25], fmt)
                    return dt.replace(tzinfo=timezone.utc).isoformat()
                except Exception:
                    continue
            return datetime.now(timezone.utc).isoformat()

    def parse_rss_content(self, content: str | bytes, source_name: str = "RSS") -> List[Dict[str, Any]]:
        """Parses raw XML string or bytes directly into normalized article dicts."""
        articles = []
        if isinstance(content, str):
            content = content.encode("utf-8")
        try:
            root = ET.fromstring(content)
            items = root.findall(".//item")
            is_atom = False
            if not items:
                items = root.findall(".//{http://www.w3.org/2005/Atom}entry")
                is_atom = bool(items)

            collected_at = datetime.now(timezone.utc).isoformat()
            for item in items:
                if not is_atom:
                    title_elem = item.find("title")
                    link_elem = item.find("link")
                    desc_elem = item.find("description")
                    pub_elem = item.find("pubDate")

                    title = title_elem.text.strip() if title_elem is not None and title_elem.text else ""
                    url = link_elem.text.strip() if link_elem is not None and link_elem.text else ""
                    raw_desc = desc_elem.text if desc_elem is not None and desc_elem.text else ""
                    pub_date = pub_elem.text.strip() if pub_elem is not None and pub_elem.text else None
                else:
                    ns = {"atom": "http://www.w3.org/2005/Atom"}
                    title_elem = item.find("atom:title", ns)
                    link_elem = item.find("atom:link", ns)
                    desc_elem = item.find("atom:summary", ns) or item.find("atom:content", ns)
                    pub_elem = item.find("atom:published", ns) or item.find("atom:updated", ns)

                    title = title_elem.text.strip() if title_elem is not None and title_elem.text else ""
                    url = link_elem.attrib.get("href", "").strip() if link_elem is not None else ""
                    raw_desc = desc_elem.text if desc_elem is not None and desc_elem.text else ""
                    pub_date = pub_elem.text.strip() if pub_elem is not None and pub_elem.text else None

                desc = BeautifulSoup(raw_desc, "html.parser").get_text(separator=" ").strip() if raw_desc else ""
                if not title and not desc:
                    continue

                article_id = self._generate_id(url, title)
                published_at = self._parse_published_date(pub_date)
                articles.append({
                    "article_id": article_id,
                    "title": title,
                    "description": desc,
                    "source": source_name,
                    "url": url,
                    "published_at": published_at,
                    "collected_at": collected_at,
                })
        except Exception as e:
            logger.warning(f"Error parsing RSS XML content: {e}")

        return articles

    def fetch_all(self) -> List[Dict[str, Any]]:
        """Alias for collect_all."""
        return self.collect_all()

    def fetch_feed(self, source_name: str, feed_url: str) -> List[Dict[str, Any]]:
        """Fetch and parse a single RSS feed."""
        try:
            resp = requests.get(feed_url, headers=self.headers, timeout=self.timeout)
            if resp.status_code != 200:
                logger.warning(f"Failed to fetch feed {source_name}: HTTP {resp.status_code}")
                return []
            return self.parse_rss_content(resp.content, source_name)
        except Exception as e:
            logger.warning(f"Error fetching feed {source_name} ({feed_url}): {e}")
            return []

    def collect_all(self) -> List[Dict[str, Any]]:
        """Collects articles across all configured Indian financial RSS feeds."""
        all_articles: List[Dict[str, Any]] = []
        seen_ids = set()

        for feed in self.feeds:
            articles = self.fetch_feed(feed["source"], feed["url"])
            for a in articles:
                if a["article_id"] not in seen_ids:
                    seen_ids.add(a["article_id"])
                    all_articles.append(a)

        logger.info(f"Collected {len(all_articles)} raw news articles across {len(self.feeds)} feeds.")
        return all_articles
