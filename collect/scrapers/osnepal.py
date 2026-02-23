#!/usr/bin/env python
"""
OSNepal RSS Feed Scraper - Uses local static image as fallback
"""
import requests
import xml.etree.ElementTree as ET
import json
from datetime import datetime, timedelta
import re
import html
from django.db import transaction
from django.templatetags.static import static

from collect.models import DangerousKeyword, AutoNewsArticle

def keyboard_osnepal_to_json(request):
    """OSNepal RSS scraper - Uses local static image as fallback"""
    
    if not request or not hasattr(request, 'user') or not request.user.is_authenticated:
        return json.dumps({
            "metadata": {
                "status": "error",
                "message": "User authentication required",
                "scraped_at": datetime.now().isoformat()
            },
            "articles": []
        })
    
    feed_url = "https://www.osnepal.com/feed"
    TODAY = datetime.now()
    FOUR_DAYS_AGO = TODAY - timedelta(days=10)
    
    print(f"\n🚀 OSNEPAL SCRAPER - {TODAY.strftime('%Y-%m-%d')} (last {10} days)")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    all_articles = []
    
    # ============ LOCAL DEFAULT IMAGE ============
    # Path to your local default image in static folder
    DEFAULT_IMAGE_PATH = "/static/project_images/osnepal.png"
    
    # Get keywords
    try:
        keywords = DangerousKeyword.objects.filter(is_active=True).values('word', 'category')
        all_keywords_list = []
        keywords_by_category = {}
        
        for kw in keywords:
            word = kw['word'].lower().strip()
            category = kw['category'].strip()
            all_keywords_list.append({'word': word, 'category': category})
            
            if category not in keywords_by_category:
                keywords_by_category[category] = []
            keywords_by_category[category].append(word)
    except Exception:
        all_keywords_list = []
        keywords_by_category = {}
    
    def is_article_within_date_range(pub_date):
        if pub_date:
            return pub_date >= FOUR_DAYS_AGO
        return True
    
    def parse_nepali_date(date_str):
        """Parse date string with Nepali timezone (+0545)"""
        if not date_str:
            return None
        try:
            # Format: Mon, 23 Feb 2026 17:18:13 +0545
            # Remove timezone and parse
            date_str = re.sub(r'\s+\+0545$', '', date_str)
            return datetime.strptime(date_str, '%a, %d %b %Y %H:%M:%S')
        except:
            return TODAY
    
    # Fetch RSS feed
    try:
        print(f"\n📡 Fetching RSS feed...")
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
            'dc': 'http://purl.org/dc/elements/1.1/',
            'atom': 'http://www.w3.org/2005/Atom',
            'media': 'http://search.yahoo.com/mrss/'
        }
        
        # Find all items
        items = root.findall('.//item')
        print(f"📄 Found {len(items)} articles in RSS feed")
        
        # Get channel image if available (for reference)
        channel_img = root.find('.//image/url')
        if channel_img is not None and channel_img.text:
            print(f"🖼️ Channel image available: {channel_img.text.strip()}")
        
        for item in items:
            try:
                title_elem = item.find('title')
                link_elem = item.find('link')
                pubDate_elem = item.find('pubDate')
                guid_elem = item.find('guid')
                
                title = title_elem.text.strip() if title_elem is not None else ""
                url = link_elem.text.strip() if link_elem is not None else ""
                
                if not url and guid_elem is not None:
                    url = guid_elem.text.strip()
                
                # Parse date
                pub_date = None
                date_text = ""
                if pubDate_elem is not None and pubDate_elem.text:
                    date_text = pubDate_elem.text
                    pub_date = parse_nepali_date(date_text)
                
                # Get description
                description_elem = item.find('description')
                summary = title
                if description_elem is not None and description_elem.text:
                    summary = html.unescape(description_elem.text)
                    summary = re.sub(r'<.*?>', '', summary)
                    summary = summary.strip()
                
                # ============ IMAGE EXTRACTION WITH LOCAL FALLBACK ============
                # Try to find an image in the RSS feed
                image_url = None
                image_found = False
                image_source = "none"
                
                # Method 1: Check for enclosure tag (sometimes has images)
                enclosure = item.find('enclosure')
                if enclosure is not None:
                    img_url = enclosure.get('url', '')
                    if img_url and img_url.startswith('http'):
                        # Check if it's an image type
                        img_type = enclosure.get('type', '')
                        if 'image' in img_type or not img_type:  # If no type specified, assume it's image
                            image_url = img_url
                            image_found = True
                            image_source = "enclosure"
                            print(f"   🖼️ Found enclosure image")
                
                # Method 2: Check for media:content tag
                if not image_found:
                    media_content = item.find('media:content', namespaces)
                    if media_content is not None:
                        img_url = media_content.get('url', '')
                        if img_url and img_url.startswith('http'):
                            img_type = media_content.get('type', '')
                            if 'image' in img_type or not img_type:
                                image_url = img_url
                                image_found = True
                                image_source = "media"
                                print(f"   🖼️ Found media image")
                
                # Method 3: Try to extract image from description
                if not image_found and description_elem is not None and description_elem.text:
                    # Look for img tag in description
                    img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', description_elem.text)
                    if img_match:
                        img_url = img_match.group(1)
                        if img_url.startswith('http'):
                            image_url = img_url
                            image_found = True
                            image_source = "description"
                            print(f"   🖼️ Found image in description")
                        elif img_url.startswith('/'):
                            # Convert relative URL to absolute
                            image_url = f"https://www.osnepal.com{img_url}"
                            image_found = True
                            image_source = "description_relative"
                            print(f"   🖼️ Found relative image in description")
                
                # ============ LOCAL FALLBACK ============
                # If no image found, use the local default image
                if not image_found:
                    image_url = DEFAULT_IMAGE_PATH
                    image_source = "local_default"
                    print(f"   🖼️ Using local default image: {DEFAULT_IMAGE_PATH}")
                
                # Try to extract article ID from URL
                article_id = ""
                if url:
                    id_match = re.search(r'/detail/(\d+)', url)
                    if id_match:
                        article_id = id_match.group(1)
                
                article_data = {
                    'title': title[:500],
                    'url': url,
                    'category': 'news',
                    'category_display': 'समाचार',
                    'date_text': date_text,
                    'image_url': image_url,
                    'summary': summary[:1000],
                    'page_found': 1,
                    'all_categories': ['news'],
                    'pub_date': pub_date,
                    'article_id': article_id,
                    'has_image': image_found,
                    'image_source': image_source
                }
                
                if is_article_within_date_range(pub_date):
                    article_data['discovered_at'] = datetime.now().isoformat()
                    all_articles.append(article_data)
                    print(f"   ✅ Added: {title[:50]}... (Image: {image_source})")
                
            except Exception as e:
                print(f"   ⚠️ Error parsing item: {e}")
                continue
        
        print(f"📊 After date filter: {len(all_articles)} articles")
        
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
    
    # Count articles by image source
    local_default_count = len([a for a in unique_articles if a.get('image_source') == 'local_default'])
    rss_image_count = len([a for a in unique_articles if a.get('image_source') != 'local_default' and a.get('has_image')])
    print(f"📊 Images from RSS: {rss_image_count}")
    print(f"📊 Images from local default: {local_default_count}")
    
    # Analyze articles for keywords
    def analyze_article_content(article, keywords_by_category, all_keywords_list):
        matched_keywords = []
        matched_categories = set()
        keywords_found = []
        
        content = f"{article['title']}".lower()
        
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
    
    # Match keywords
    matched_articles = []
    category_stats = {}
    
    for article in unique_articles:
        threat = analyze_article_content(article, keywords_by_category, all_keywords_list)
        if threat['has_match']:
            article['threat_analysis'] = threat
            matched_articles.append(article)
            category_stats['news'] = category_stats.get('news', 0) + 1
    
    print(f"🔴 Matched articles: {len(matched_articles)}")
    
    # Save to database
    saved_count = 0
    updated_count = 0
    error_count = 0
    
    for article in matched_articles[:200]:
        try:
            existing = AutoNewsArticle.objects.filter(
                url=article['url'],
                created_by=request.user
            ).first()
            
            title = article['title'][:500]
            summary = article.get('summary', article['title'])[:1000]
            url = article['url'][:1000]
            
            # ============ IMAGE URL HANDLING ============
            # Keep the image URL as is (local static path or external URL)
            image_url = article.get('image_url', '')
            if image_url:
                image_url = image_url[:1000]
            
            source = 'osnepal'
            date = article.get('pub_date', datetime.now()).strftime('%Y-%m-%d')[:20]
            content_length = len(article.get('summary', ''))
            priority = article['threat_analysis']['priority']
            threat_level = article['threat_analysis']['level']
            keywords = json.dumps(article['threat_analysis']['keywords_found'], ensure_ascii=False)
            categories_json = json.dumps(['news'], ensure_ascii=False)
            
            if existing:
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
            else:
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
                
        except Exception as e:
            error_count += 1
            print(f"   ⚠️ Save error: {e}")
    
    print(f"\n📊 Total RSS articles: {len(unique_articles)}")
    print(f"🔴 Matched articles: {len(matched_articles)}")
    print(f"📊 With RSS images: {len([a for a in matched_articles if a.get('image_source') != 'local_default' and a.get('has_image')])}")
    print(f"📊 With local default images: {len([a for a in matched_articles if a.get('image_source') == 'local_default'])}")
    print(f"💾 Saved: {saved_count} new, {updated_count} updated")
    print(f"{'='*60}")
    
    alert_message = f"✅ OSNepal: Found {len(matched_articles)} matching articles"
    if saved_count > 0 or updated_count > 0:
        alert_message += f" (Saved: {saved_count} new, Updated: {updated_count})"
    
    metadata = {
        "source": "OSNepal",
        "scraped_at": datetime.now().isoformat(),
        "status": "success",
        "user": request.user.username,
        "total_articles_scraped": len(unique_articles),
        "articles_with_keywords": len(matched_articles),
        "articles_with_rss_images": len([a for a in matched_articles if a.get('image_source') != 'local_default' and a.get('has_image')]),
        "articles_with_local_images": len([a for a in matched_articles if a.get('image_source') == 'local_default']),
        "database_save": {
            "new_articles_saved": saved_count,
            "existing_articles_updated": updated_count,
            "errors": error_count
        },
        "date_range": {
            "start": FOUR_DAYS_AGO.strftime('%Y-%m-%d'),
            "end": TODAY.strftime('%Y-%m-%d')
        }
    }
    
    return json.dumps({
        "metadata": metadata,
        "articles": matched_articles[:10],
        "status": "success",
        "alert_message": alert_message
    }, ensure_ascii=False)