#!/usr/bin/env python
"""
Hetauda Today RSS Feed Scraper - हेटौंडा टुडे
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

def keyboard_hetaudatoday_to_json(request):
    """Hetauda Today RSS scraper"""
    
    if not request or not hasattr(request, 'user') or not request.user.is_authenticated:
        return json.dumps({
            "metadata": {
                "status": "error",
                "message": "User authentication required",
                "scraped_at": datetime.now().isoformat()
            },
            "articles": []
        })
    
    feed_url = "https://www.hetaudatoday.com/feed/"
    TODAY = datetime.now()
    FOUR_DAYS_AGO = TODAY - timedelta(days=4)
    
    print(f"\n🚀 HETAUDA TODAY SCRAPER - {TODAY.strftime('%Y-%m-%d')} (last {4} days)")
    print(f"📡 RSS Feed URL: {feed_url}")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/rss+xml, application/xml, text/xml, */*'
    }
    
    all_articles = []
    
    # ============ DEFAULT IMAGE HANDLING ============
    DEFAULT_IMAGE_PATH = "/static/project_images/hetauda.jpg"
    print(f"🖼️ Default image path: {DEFAULT_IMAGE_PATH}")
    
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
            # Format: Sun, 01 Mar 2026 09:21:38 +0000
            # Remove timezone info
            date_str = re.sub(r'\s+\+\d{4}$', '', date_str)
            return datetime.strptime(date_str, '%a, %d %b %Y %H:%M:%S')
        except Exception as e:
            print(f"Date parse error for '{date_str[:30]}': {e}")
            return TODAY
    
    def extract_image_from_content(content):
        """Extract image URL from content with multiple methods"""
        if not content:
            return None
        
        # Method 1: Look for wp-post-image class (featured image)
        wp_img_pattern = r'<img[^>]+class="[^"]*wp-post-image[^"]*"[^>]+src="([^">]+)"'
        img_match = re.search(wp_img_pattern, content, re.IGNORECASE)
        if img_match:
            img_url = img_match.group(1)
            # Clean up URL
            if img_url.startswith('//'):
                img_url = 'https:' + img_url
            return img_url
        
        # Method 2: Look for any img tag
        img_pattern = r'<img[^>]+src="([^">]+)"'
        img_match = re.search(img_pattern, content, re.IGNORECASE)
        if img_match:
            img_url = img_match.group(1)
            if img_url.startswith('//'):
                img_url = 'https:' + img_url
            return img_url
        
        # Method 3: Look for image in figure
        figure_img_pattern = r'<figure[^>]*>.*?<img[^>]+src="([^">]+)".*?</figure>'
        img_match = re.search(figure_img_pattern, content, re.IGNORECASE | re.DOTALL)
        if img_match:
            img_url = img_match.group(1)
            if img_url.startswith('//'):
                img_url = 'https:' + img_url
            return img_url
        
        return None
    
    def clean_summary(text):
        """Clean HTML and extra whitespace from summary"""
        if not text:
            return ""
        # Remove HTML tags
        text = re.sub(r'<.*?>', '', text)
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        # Remove "The post ... appeared first on ..." pattern
        text = re.sub(r'The post.*?appeared first on.*?\.', '', text, flags=re.DOTALL)
        # Remove "Read more..." patterns
        text = re.sub(r'\[\&hellip;\]', '', text)
        text = re.sub(r'Continue reading.*$', '', text)
        return text.strip()
    
    def extract_nepali_text(content):
        """Extract Nepali text from content (prioritize Nepali)"""
        if not content:
            return ""
        
        # Remove HTML tags
        text = re.sub(r'<.*?>', ' ', content)
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Look for Nepali text (Unicode range)
        nepali_pattern = r'[\u0900-\u097F]{10,}'
        nepali_matches = re.findall(nepali_pattern, text)
        
        if nepali_matches:
            # Return first substantial Nepali text
            for match in nepali_matches:
                if len(match) > 50:
                    return match
        
        return text[:500]
    
    def make_absolute_url(img_url):
        """Convert relative URLs to absolute"""
        if not img_url:
            return None
        
        if img_url.startswith('//'):
            return 'https:' + img_url
        elif img_url.startswith('/'):
            return f"https://www.hetaudatoday.com{img_url}"
        elif not img_url.startswith('http'):
            return f"https://www.hetaudatoday.com/{img_url.lstrip('/')}"
        return img_url
    
    def extract_post_id_from_url(url):
        """Extract post ID from Hetauda Today URL pattern"""
        if not url:
            return ""
        # Pattern: https://www.hetaudatoday.com/2026/03/47923/
        id_match = re.search(r'/(\d+)/?$', url)
        if id_match:
            return id_match.group(1)
        return ""
    
    # Fetch RSS feed
    try:
        print(f"\n📡 Fetching RSS feed from Hetauda Today...")
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
        
        # Try to get channel image
        channel_image = DEFAULT_IMAGE_PATH
        try:
            image_elem = channel.find('image')
            if image_elem is not None:
                url_elem = image_elem.find('url')
                if url_elem is not None and url_elem.text:
                    channel_image = url_elem.text.strip()
                    print(f"🖼️ Channel image found: {channel_image[:50]}...")
        except:
            pass
        
        for item in items:
            try:
                # Title
                title_elem = item.find('title')
                title = html.unescape(title_elem.text).strip() if title_elem is not None else ""
                
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
                author = creator_elem.text.strip() if creator_elem is not None and creator_elem.text else "हेटौंडा टुडे"
                
                # Description
                description_elem = item.find('description')
                summary = title
                image_url = None
                image_found = False
                image_source = "none"
                
                if description_elem is not None and description_elem.text:
                    desc_text = html.unescape(description_elem.text)
                    
                    # Extract image from description
                    img_url = extract_image_from_content(desc_text)
                    if img_url:
                        image_url = make_absolute_url(img_url)
                        image_found = True
                        image_source = "description"
                        print(f"   🖼️ Found image in description: {image_url[:50]}...")
                    
                    # Clean summary
                    clean_desc = clean_summary(desc_text)
                    if clean_desc and len(clean_desc) > len(summary):
                        summary = clean_desc[:1000]
                
                # Get full content for more images and better summary
                content_elem = item.find('content:encoded', namespaces)
                if content_elem is not None and content_elem.text and not image_found:
                    full_content = html.unescape(content_elem.text)
                    
                    # Extract image from content
                    img_url = extract_image_from_content(full_content)
                    if img_url:
                        image_url = make_absolute_url(img_url)
                        image_found = True
                        image_source = "content"
                        print(f"   🖼️ Found image in content: {image_url[:50]}...")
                    
                    # Use content for summary if better
                    clean_content = clean_summary(full_content)
                    if len(clean_content) > len(summary):
                        summary = clean_content[:1000]
                
                # If still no image, try to get from media:content (Hetauda Today uses this)
                if not image_found:
                    media_content = item.find('media:content', namespaces)
                    if media_content is not None and media_content.get('url'):
                        image_url = make_absolute_url(media_content.get('url'))
                        image_found = True
                        image_source = "media"
                        print(f"   🖼️ Found image in media:content")
                    
                    # Also check enclosure tag
                    if not image_found:
                        enclosure = item.find('enclosure')
                        if enclosure is not None and enclosure.get('url'):
                            image_url = make_absolute_url(enclosure.get('url'))
                            image_found = True
                            image_source = "enclosure"
                            print(f"   🖼️ Found image in enclosure")
                
                # Use default if no image
                if not image_found:
                    image_url = DEFAULT_IMAGE_PATH
                    image_source = "local_default"
                    print(f"   🖼️ Using default image")
                
                # Get categories
                categories = []
                for cat in item.findall('category'):
                    if cat.text:
                        cat_text = html.unescape(cat.text).strip()
                        # Remove CDATA if present
                        cat_text = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', cat_text)
                        categories.append(cat_text)
                
                # Get post ID from URL
                post_id = extract_post_id_from_url(url)
                
                # Determine main category (prioritize Nepali categories)
                main_category = categories[0] if categories else 'समाचार'
                
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
                    'has_image': image_found,
                    'image_source': image_source,
                    'source': 'hetaudatoday'
                }
                
                if is_article_within_date_range(pub_date):
                    article_data['discovered_at'] = datetime.now().isoformat()
                    all_articles.append(article_data)
                    print(f"   ✅ Added: {title[:50]}... (Date: {pub_date.strftime('%Y-%m-%d')}, Image: {image_source})")
                else:
                    print(f"   ⏭️ Skipped old: {title[:30]}... ({pub_date.strftime('%Y-%m-%d')})")
                
            except Exception as e:
                print(f"   ⚠️ Error parsing item: {e}")
                continue
        
        print(f"📊 After date filter: {len(all_articles)} articles")
        
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
    
    # Image stats
    local_default_count = len([a for a in unique_articles if a.get('image_source') == 'local_default'])
    rss_image_count = len([a for a in unique_articles if a.get('image_source') != 'local_default' and a.get('has_image')])
    print(f"📊 Images from RSS: {rss_image_count}")
    print(f"📊 Images from local default: {local_default_count}")
    
    # Analyze articles for keywords
    def analyze_article_content(article, keywords_by_category, all_keywords_list):
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
    
    # Match keywords
    matched_articles = []
    category_stats = {}
    
    for article in unique_articles:
        threat = analyze_article_content(article, keywords_by_category, all_keywords_list)
        if threat['has_match']:
            article['threat_analysis'] = threat
            matched_articles.append(article)
            
            cat = article['category_display']
            category_stats[cat] = category_stats.get(cat, 0) + 1
    
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
            
            # Handle image URL
            image_url = article.get('image_url', '')
            
            # Don't modify the image URL if it's already a full URL
            if image_url and not image_url.startswith(('http://', 'https://', '/static/', '/media/')):
                if image_url.startswith('//'):
                    image_url = 'https:' + image_url
                elif image_url.startswith('/'):
                    # For local paths, keep as is
                    pass
                else:
                    # Assume it's a full URL missing protocol
                    image_url = 'https://' + image_url
            
            # Truncate if needed
            if image_url and len(image_url) > 1000:
                image_url = image_url[:1000]
            
            source = 'hetaudatoday'
            date = article.get('pub_date', datetime.now()).strftime('%Y-%m-%d')[:20]
            content_length = len(article.get('summary', ''))
            priority = article['threat_analysis']['priority']
            threat_level = article['threat_analysis']['level']
            keywords = json.dumps(article['threat_analysis']['keywords_found'], ensure_ascii=False)
            all_cats = article.get('all_categories', [article['category_display']])
            categories_json = json.dumps(all_cats[:10], ensure_ascii=False)
            
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
                print(f"   🔄 Updated: {title[:30]}...")
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
                print(f"   ✅ Saved: {title[:30]}...")
                
        except Exception as e:
            error_count += 1
            print(f"   ⚠️ Save error: {e}")
    
    print(f"\n📊 Total RSS articles: {len(unique_articles)}")
    print(f"🔴 Matched articles: {len(matched_articles)}")
    print(f"📊 With RSS images: {len([a for a in matched_articles if a.get('image_source') != 'local_default' and a.get('has_image')])}")
    print(f"📊 With local default images: {len([a for a in matched_articles if a.get('image_source') == 'local_default'])}")
    print(f"💾 Saved: {saved_count} new, {updated_count} updated")
    print(f"📅 Date range: {FOUR_DAYS_AGO.strftime('%Y-%m-%d')} to {TODAY.strftime('%Y-%m-%d')}")
    print(f"{'='*60}")
    
    # Verify images in final articles
    final_articles_with_images = []
    for article in matched_articles[:10]:
        if article.get('image_url'):
            final_articles_with_images.append({
                'title': article['title'][:50],
                'image_url': article['image_url'],
                'image_source': article.get('image_source', 'unknown')
            })
    
    if final_articles_with_images:
        print("\n📸 Sample images in final output:")
        for fa in final_articles_with_images:
            print(f"   - {fa['title']}: {fa['image_url'][:60]}... ({fa['image_source']})")
    
    alert_message = f"✅ Hetauda Today: Found {len(matched_articles)} matching articles"
    if saved_count > 0 or updated_count > 0:
        alert_message += f" (Saved: {saved_count} new, Updated: {updated_count})"
    
    metadata = {
        "source": "Hetauda Today",
        "scraped_at": datetime.now().isoformat(),
        "status": "success",
        "user": request.user.username,
        "total_articles_scraped": len(unique_articles),
        "articles_with_keywords": len(matched_articles),
        "articles_with_rss_images": len([a for a in matched_articles if a.get('image_source') != 'local_default' and a.get('has_image')]),
        "articles_with_local_images": len([a for a in matched_articles if a.get('image_source') == 'local_default']),
        "articles_by_category": category_stats,
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
        "articles": matched_articles[:10],
        "status": "success",
        "alert_message": alert_message
    }, ensure_ascii=False)


def fetch_hetaudatoday_news(request):
    """Main function to call from your keyboard view"""
    try:
        result_json = keyboard_hetaudatoday_to_json(request)
        result_data = json.loads(result_json)
        
        return {
            "status": result_data["metadata"]["status"],
            "message": result_data.get("alert_message", "Hetauda Today fetch completed"),
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
            "message": f"Error in fetch_hetaudatoday_news: {str(e)}"
        }