#!/usr/bin/env python
"""
Shilapaper RSS Feed Scraper - शिलापेपर
"""
import requests
import xml.etree.ElementTree as ET
import json
from datetime import datetime, timedelta
import re
import html
from django.db import transaction
from django.conf import settings
import os

from collect.models import DangerousKeyword, AutoNewsArticle

def keyboard_shilapaper_to_json(request):
    """Shilapaper RSS scraper"""

    if not request or not hasattr(request, 'user') or not request.user.is_authenticated:
        return json.dumps({
            "metadata": {
                "status": "error",
                "message": "User authentication required",
                "scraped_at": datetime.now().isoformat()
            },
            "articles": []
        })

    feed_url = "https://shilapaper.com/feed"
    TODAY = datetime.now()
    FOUR_DAYS_AGO = TODAY - timedelta(days=30)

    print(f"\n🚀 SHILAPAPER SCRAPER - {TODAY.strftime('%Y-%m-%d')} (last {4} days)")
    print(f"📡 RSS Feed URL: {feed_url}")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/rss+xml, application/xml, text/xml, */*'
    }

    all_articles = []

    # ============ DEFAULT IMAGE HANDLING ============
    DEFAULT_IMAGE_PATH = "/static/project_images/shilapaper.png"
    print(f"🖼️ Using default image for all articles: {DEFAULT_IMAGE_PATH}")

    # Get keywords
    try:
        keywords = DangerousKeyword.objects.filter(
            is_active=True,
            created_by=request.user
        ).values('word', 'category')
        all_keywords_list = []
        keywords_by_category = {}

        for kw in keywords:
            word = kw['word'].lower().strip()
            category = kw['category'].strip()
            all_keywords_list.append({'word': word, 'category': category})

            if category not in keywords_by_category:
                keywords_by_category[category] = []
            keywords_by_category[category].append(word)

        print(f"🔑 Loaded {len(all_keywords_list)} keywords")
    except Exception as e:
        print(f"⚠️ Keyword fetch error: {e}")
        all_keywords_list = []
        keywords_by_category = {}

    def is_article_within_date_range(pub_date):
        if pub_date:
            return pub_date >= FOUR_DAYS_AGO
        return True

    def parse_date(date_str):
        """Parse date from RSS feed"""
        if not date_str:
            return TODAY

        try:
            # Format: Mon, 09 Feb 2026 05:09:16 +0000
            date_str = re.sub(r'\s+\+\d{4}$', '', date_str)
            return datetime.strptime(date_str, '%a, %d %b %Y %H:%M:%S')
        except Exception as e:
            print(f"Date parse error for '{date_str[:30]}': {e}")
            return TODAY

    def clean_summary(text):
        """Clean HTML and extra whitespace from summary"""
        if not text:
            return ""

        # Remove HTML tags but keep content
        text = re.sub(r'<.*?>', ' ', text)

        # Remove "The post ... appeared first on ..." pattern
        text = re.sub(r'The post.*?appeared first on.*?\.', '', text, flags=re.DOTALL)

        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)

        return text.strip()

    def extract_clean_text_from_content(content):
        """Extract clean text from content, removing HTML"""
        if not content:
            return ""

        # Remove HTML tags
        text = re.sub(r'<.*?>', ' ', content)

        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)

        return text.strip()

    def extract_post_id_from_url(url):
        """Extract post ID from Shilapaper URL pattern"""
        if not url:
            return ""
        # Pattern: https://shilapaper.com/2026/02/16310.html
        id_match = re.search(r'/(\d+)\.html$', url)
        if id_match:
            return id_match.group(1)
        return ""

    def analyze_article_content(article, keywords_by_category, all_keywords_list):
        """Analyze article content for keywords and return threat analysis"""
        matched_keywords = []
        matched_categories = set()
        keywords_found = []

        content = f"{article['title']} {article.get('summary', '')}".lower()

        for keyword_info in all_keywords_list:
            keyword = keyword_info['word']
            category = keyword_info['category']

            if keyword in content:
                matched_keywords.append({'word': keyword, 'category': category})
                matched_categories.add(category)
                keywords_found.append(keyword)

        unique_keywords = list(set(keywords_found))
        total_matches = len(matched_keywords)

        if total_matches >= 5:
            threat_level = "high"
            priority = "high"
        elif total_matches >= 2:
            threat_level = "medium"
            priority = "medium"
        elif total_matches >= 1:
            threat_level = "low"
            priority = "low"
        else:
            threat_level = "none"
            priority = "none"

        return {
            "level": threat_level,
            "priority": priority,
            "keywords_found": unique_keywords[:20],
            "total_keywords_matched": total_matches,
            "categories": list(matched_categories),
            "has_match": total_matches > 0
        }

    # Fetch RSS feed
    try:
        print(f"\n📡 Fetching RSS feed from Shilapaper...")
        response = requests.get(feed_url, headers=headers, timeout=30)

        if response.status_code != 200:
            return json.dumps({
                "metadata": {
                    "status": "error",
                    "message": f"Failed to fetch RSS feed: HTTP {response.status_code}",
                    "scraped_at": datetime.now().isoformat()
                },
                "articles": []
            })

        # Parse XML
        root = ET.fromstring(response.content)

        # Handle namespaces
        namespaces = {
            'content': 'http://purl.org/rss/1.0/modules/content/',
            'dc': 'http://purl.org/dc/elements/1.1/',
            'media': 'http://search.yahoo.com/mrss/',
            'feed-additions': 'com-wordpress:feed-additions:1'
        }

        # Find channel
        channel = root.find('channel')
        if channel is None:
            channel = root

        # Find all items
        items = channel.findall('item')
        print(f"📄 Found {len(items)} articles in RSS feed")

        for idx, item in enumerate(items):
            try:
                print(f"\n   📄 Processing article {idx+1}/{len(items)}")

                # Title
                title_elem = item.find('title')
                title = html.unescape(title_elem.text).strip() if title_elem is not None else ""
                title = clean_summary(title)

                # Link
                link_elem = item.find('link')
                url = link_elem.text.strip() if link_elem is not None else ""

                # Publication date
                pubDate_elem = item.find('pubDate')
                pub_date = TODAY
                date_text = ""
                if pubDate_elem is not None and pubDate_elem.text:
                    date_text = pubDate_elem.text
                    pub_date = parse_date(date_text)

                # Creator/Author
                creator_elem = item.find('dc:creator', namespaces)
                author = "शिलापेपर"
                if creator_elem is not None and creator_elem.text:
                    author = html.unescape(creator_elem.text).strip()
                    author = clean_summary(author)

                # Description
                description_elem = item.find('description')
                summary = title

                if description_elem is not None and description_elem.text:
                    desc_text = html.unescape(description_elem.text)

                    # Clean summary
                    clean_desc = clean_summary(desc_text)
                    if clean_desc and len(clean_desc) > len(summary):
                        summary = clean_desc[:1000]

                # Get full content for better summary
                content_elem = item.find('content:encoded', namespaces)
                if content_elem is not None and content_elem.text:
                    full_content = html.unescape(content_elem.text)

                    # Extract clean text from content
                    clean_content = extract_clean_text_from_content(full_content)
                    if len(clean_content) > len(summary):
                        summary = clean_content[:1000]

                # Get categories
                categories = []
                for cat in item.findall('category'):
                    if cat.text:
                        cat_text = html.unescape(cat.text).strip()
                        cat_text = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', cat_text)
                        cat_text = clean_summary(cat_text)
                        if cat_text:
                            categories.append(cat_text)

                # Get post ID from URL
                post_id = extract_post_id_from_url(url)

                # Determine main category
                main_category = categories[0] if categories else 'समाचार'

                # Use default image for ALL articles
                image_url = DEFAULT_IMAGE_PATH
                image_source = "default_static"

                # Create base article data
                article_data = {
                    'title': title[:500],
                    'url': url,
                    'post_id': post_id,
                    'author': author,
                    'category': main_category,
                    'category_display': main_category,
                    'date_text': date_text,
                    'image_url': image_url,
                    'summary': summary[:1000],
                    'page_found': 1,
                    'all_categories': categories,
                    'pub_date': pub_date,
                    'has_image': True,
                    'image_source': image_source,
                    'image_optimized': False,
                    'source': 'shilapaper'
                }

                # Add to collection if within date range
                if is_article_within_date_range(pub_date):
                    article_data['discovered_at'] = datetime.now().isoformat()
                    all_articles.append(article_data)
                    preview_title = title[:50] if title else "No title"
                    print(f"   ✅ Added: {preview_title}... (Date: {pub_date.strftime('%Y-%m-%d')})")
                else:
                    preview = title[:30] if title else "No title"
                    print(f"   ⏭️ Skipped old: {preview}... ({pub_date.strftime('%Y-%m-%d')})")

            except Exception as e:
                print(f"   ⚠️ Error parsing item: {e}")
                continue

        print(f"\n📊 After date filter: {len(all_articles)} articles")

    except ET.ParseError as e:
        print(f"❌ XML Parse Error: {e}")
        return json.dumps({
            "metadata": {
                "status": "error",
                "message": f"XML Parse Error: {str(e)}",
                "scraped_at": datetime.now().isoformat()
            },
            "articles": []
        })
    except Exception as e:
        print(f"❌ Error fetching RSS feed: {e}")
        return json.dumps({
            "metadata": {
                "status": "error",
                "message": f"Error fetching RSS feed: {str(e)}",
                "scraped_at": datetime.now().isoformat()
            },
            "articles": []
        })

    # Remove duplicates
    unique_articles = []
    seen_urls = set()
    for article in all_articles:
        if article['url'] not in seen_urls:
            seen_urls.add(article['url'])
            unique_articles.append(article)

    print(f"📊 Unique articles: {len(unique_articles)}")

    # Analyze ALL articles for keywords and prepare for database
    processed_articles = []
    keyword_match_count = 0

    for article in unique_articles:
        # Analyze content for keywords
        threat = analyze_article_content(article, keywords_by_category, all_keywords_list)

        # Add threat analysis to article
        article['threat_analysis'] = threat

        if threat['has_match']:
            keyword_match_count += 1

        processed_articles.append(article)

    print(f"🔴 Articles with keyword matches: {keyword_match_count} out of {len(processed_articles)}")

    # Save ALL articles to database (both matched and unmatched)
    saved_count = 0
    updated_count = 0
    error_count = 0

    for article in processed_articles[:200]:  # Limit to 200 articles
        try:
            existing = AutoNewsArticle.objects.filter(
                url=article['url'],
                created_by=request.user
            ).first()

            title = article['title'][:500]
            summary = article.get('summary', article['title'])[:1000]
            url = article['url'][:1000]

            # Use default image for all articles
            image_url = DEFAULT_IMAGE_PATH

            source = 'shilapaper'
            date = article.get('pub_date', datetime.now()).strftime('%Y-%m-%d')[:20]
            content_length = len(article.get('summary', ''))
            priority = article['threat_analysis']['priority']
            threat_level = article['threat_analysis']['level']
            keywords = json.dumps(article['threat_analysis']['keywords_found'], ensure_ascii=False)
            all_cats = article.get('all_categories', [article['category_display']])
            categories_json = json.dumps(all_cats[:10], ensure_ascii=False)

            if existing:
                # Update existing article
                existing.title = title
                existing.summary = summary
                existing.image_url = image_url
                existing.content_length = content_length
                existing.priority = priority
                existing.threat_level = threat_level
                existing.keywords = keywords
                existing.categories = categories_json
                existing.save()
                updated_count += 1
                print(f"   🔄 Updated: {title[:30]}... (Threat: {threat_level})")
            else:
                # Create new article
                AutoNewsArticle.objects.create(
                    title=title,
                    summary=summary,
                    url=url,
                    image_url=image_url,
                    source=source,
                    date=date,
                    content_length=content_length,
                    priority=priority,
                    threat_level=threat_level,
                    keywords=keywords,
                    categories=categories_json,
                    created_by=request.user
                )
                saved_count += 1
                print(f"   ✅ Saved: {title[:30]}... (Threat: {threat_level})")

        except Exception as e:
            error_count += 1
            print(f"   ⚠️ Save error: {e}")

    print(f"\n📊 Total RSS articles: {len(unique_articles)}")
    print(f"🔴 Articles with keyword matches: {keyword_match_count}")
    print(f"📊 All articles use default image: {DEFAULT_IMAGE_PATH}")
    print(f"💾 Saved: {saved_count} new, {updated_count} updated")
    print(f"❌ Errors: {error_count}")
    print(f"📅 Date range: {FOUR_DAYS_AGO.strftime('%Y-%m-%d')} to {TODAY.strftime('%Y-%m-%d')}")
    print(f"{'='*60}")

    alert_message = f"✅ Shilapaper: Processed {len(unique_articles)} articles ({keyword_match_count} with keyword matches)"
    if saved_count > 0 or updated_count > 0:
        alert_message += f" (Saved: {saved_count} new, Updated: {updated_count})"

    metadata = {
        "source": "Shilapaper",
        "scraped_at": datetime.now().isoformat(),
        "status": "success",
        "user": request.user.username,
        "total_articles_scraped": len(unique_articles),
        "articles_with_keywords": keyword_match_count,
        "articles_without_keywords": len(unique_articles) - keyword_match_count,
        "articles_with_default_image": len(unique_articles),
        "database_save": {
            "new_articles_saved": saved_count,
            "existing_articles_updated": updated_count,
            "errors": error_count
        },
        "date_range": {
            "start": FOUR_DAYS_AGO.strftime('%Y-%m-%d'),
            "end": TODAY.strftime('%Y-%m-%d')
        },
        "default_image_path": DEFAULT_IMAGE_PATH
    }

    return json.dumps({
        "metadata": metadata,
        "articles": processed_articles[:10],  # Return first 10 processed articles
        "status": "success",
        "alert_message": alert_message
    }, ensure_ascii=False)


def fetch_shilapaper_news(request):
    """Main function to call from your keyboard view"""
    try:
        result_json = keyboard_shilapaper_to_json(request)
        result_data = json.loads(result_json)

        return {
            "status": result_data["metadata"]["status"],
            "message": result_data.get("alert_message", "Shilapaper fetch completed"),
            "stats": {
                "saved": result_data["metadata"]["database_save"]["new_articles_saved"],
                "updated": result_data["metadata"]["database_save"]["existing_articles_updated"],
                "errors": result_data["metadata"]["database_save"]["errors"],
                "security_articles": result_data["metadata"]["articles_with_keywords"],
                "total_processed": result_data["metadata"]["total_articles_scraped"]
            },
            "data": result_data
        }

    except Exception as e:
        return {
            "status": "error",
            "message": f"Error in fetch_shilapaper_news: {str(e)}"
        }