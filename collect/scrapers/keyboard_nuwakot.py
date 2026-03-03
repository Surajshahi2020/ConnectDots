#!/usr/bin/env python
"""
Online Nuwakot RSS Feed Scraper - अनलाइन नुवाकोट
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

def keyboard_onlinenuwakot_to_json(request):
    """Online Nuwakot RSS scraper"""
    
    if not request or not hasattr(request, 'user') or not request.user.is_authenticated:
        return json.dumps({
            "metadata": {
                "status": "error",
                "message": "User authentication required",
                "scraped_at": datetime.now().isoformat()
            },
            "articles": []
        })
    
    feed_url = "https://www.onlinenuwakot.com/feed/"
    TODAY = datetime.now()
    FOUR_DAYS_AGO = TODAY - timedelta(days=4)
    
    print(f"\n🚀 ONLINE NUWAKOT SCRAPER - {TODAY.strftime('%Y-%m-%d')} (last {4} days)")
    print(f"📡 RSS Feed URL: {feed_url}")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/rss+xml, application/xml, text/xml, */*'
    }
    
    all_articles = []
    
    # ============ DEFAULT IMAGE HANDLING ============
    DEFAULT_IMAGE_PATH = "/static/project_images/chitwan.png"
    # Site logo as fallback
    SITE_LOGO = "/static/project_images/chitwan.png"
    print(f"🖼️ Default image path: {DEFAULT_IMAGE_PATH}")
    print(f"🖼️ Site logo fallback: {SITE_LOGO}")
    
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
            # Format: Tue, 03 Mar 2026 01:03:29 +0000
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
        
        # Method 1: Look for wp-image class (WordPress featured image)
        wp_img_pattern = r'<img[^>]+class="[^"]*wp-image-\d+[^"]*"[^>]+src="([^">]+)"'
        img_match = re.search(wp_img_pattern, content, re.IGNORECASE)
        if img_match:
            img_url = img_match.group(1)
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
        
        # Method 3: Look for srcset (contains multiple image sizes)
        srcset_pattern = r'<img[^>]+srcset="([^">]+)"'
        img_match = re.search(srcset_pattern, content, re.IGNORECASE)
        if img_match:
            srcset = img_match.group(1)
            parts = srcset.split(',')
            if parts:
                first_part = parts[0].strip().split(' ')[0]
                if first_part:
                    if first_part.startswith('//'):
                        first_part = 'https:' + first_part
                    return first_part
        
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
        # Remove source attribution
        text = re.sub(r'Source :-.*$', '', text, flags=re.MULTILINE)
        return text.strip()
    
    def extract_nepali_text(content):
        """Extract Nepali text from content"""
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
            return f"https://www.onlinenuwakot.com{img_url}"
        elif not img_url.startswith('http'):
            return f"https://www.onlinenuwakot.com/{img_url.lstrip('/')}"
        return img_url
    
    def extract_post_id_from_url(url):
        """Extract post ID from Online Nuwakot URL pattern"""
        if not url:
            return ""
        # Pattern: https://www.onlinenuwakot.com/news/28075/
        id_match = re.search(r'/(\d+)/?$', url)
        if id_match:
            return id_match.group(1)
        return ""
    
    # Fetch RSS feed
    try:
        print(f"\n📡 Fetching RSS feed from Online Nuwakot...")
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
                author = "अनलाइन नुवाकोट"
                if creator_elem is not None and creator_elem.text:
                    author = html.unescape(creator_elem.text).strip()
                
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
                        print(f"      🖼️ Found image in description")
                    
                    # Clean summary
                    clean_desc = clean_summary(desc_text)
                    if clean_desc and len(clean_desc) > len(summary):
                        summary = clean_desc[:1000]
                
                # Get full content for more images
                content_elem = item.find('content:encoded', namespaces)
                if content_elem is not None and content_elem.text:
                    full_content = html.unescape(content_elem.text)
                    
                    # Extract image from content if not found yet
                    if not image_found:
                        img_url = extract_image_from_content(full_content)
                        if img_url:
                            image_url = make_absolute_url(img_url)
                            image_found = True
                            image_source = "content"
                            print(f"      🖼️ Found image in content")
                    
                    # Use content for summary if better
                    clean_content = clean_summary(full_content)
                    if len(clean_content) > len(summary):
                        summary = clean_content[:1000]
                
                # Use site logo as fallback if no image found
                if not image_found:
                    image_url = SITE_LOGO
                    image_source = "site_logo"
                    print(f"      🖼️ Using site logo as fallback")
                
                # Get categories
                categories = []
                for cat in item.findall('category'):
                    if cat.text:
                        cat_text = html.unescape(cat.text).strip()
                        cat_text = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', cat_text)
                        categories.append(cat_text)
                
                # Get post ID from URL
                post_id = extract_post_id_from_url(url)
                
                # Determine main category
                main_category = categories[0] if categories else 'समाचार'
                
                # Determine section (news/blog)
                section = "news"
                if "/blog/" in url:
                    section = "blog"
                
                article_data = {
                    'title': title[:500],
                    'url': url,
                    'post_id': post_id,
                    'author': author,
                    'category': main_category,
                    'category_display': main_category,
                    'section': section,
                    'date_text': date_text,
                    'image_url': image_url,
                    'summary': summary[:1000],
                    'page_found': 1,
                    'all_categories': categories,
                    'pub_date': pub_date,
                    'has_image': image_found,
                    'image_source': image_source,
                    'source': 'onlinenuwakot'
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
    
    # Image stats
    site_logo_count = len([a for a in unique_articles if a.get('image_source') == 'site_logo'])
    rss_image_count = len([a for a in unique_articles if a.get('image_source') in ['description', 'content']])
    print(f"📊 Images from RSS content: {rss_image_count}")
    print(f"📊 Images from site logo: {site_logo_count}")
    
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
    
    # Debug: Print all image URLs being saved
    print("\n📸 Image URLs being saved:")
    for article in matched_articles[:5]:
        print(f"   - {article['title'][:30]}: {article.get('image_url', 'NO IMAGE')} (source: {article.get('image_source', 'unknown')})")
    
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
            
            if image_url and not image_url.startswith(('http://', 'https://', '/static/', '/media/')):
                if image_url.startswith('//'):
                    image_url = 'https:' + image_url
                elif image_url.startswith('/'):
                    pass
                else:
                    image_url = 'https://' + image_url
            
            if image_url and len(image_url) > 1000:
                image_url = image_url[:1000]
            
            source = 'onlinenuwakot'
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
    print(f"📊 Images from RSS content: {len([a for a in matched_articles if a.get('image_source') in ['description', 'content']])}")
    print(f"📊 Images from site logo: {len([a for a in matched_articles if a.get('image_source') == 'site_logo'])}")
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
    else:
        print("\n❌ No images found in final output!")
    
    alert_message = f"✅ Online Nuwakot: Found {len(matched_articles)} matching articles"
    if saved_count > 0 or updated_count > 0:
        alert_message += f" (Saved: {saved_count} new, Updated: {updated_count})"
    
    metadata = {
        "source": "Online Nuwakot",
        "scraped_at": datetime.now().isoformat(),
        "status": "success",
        "user": request.user.username,
        "total_articles_scraped": len(unique_articles),
        "articles_with_keywords": len(matched_articles),
        "articles_with_rss_images": len([a for a in matched_articles if a.get('image_source') in ['description', 'content']]),
        "articles_with_site_logo": len([a for a in matched_articles if a.get('image_source') == 'site_logo']),
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
        "default_image_path": DEFAULT_IMAGE_PATH,
        "site_logo": SITE_LOGO
    }
    
    return json.dumps({
        "metadata": metadata,
        "articles": matched_articles[:10],
        "status": "success",
        "alert_message": alert_message
    }, ensure_ascii=False)


def fetch_onlinenuwakot_news(request):
    """Main function to call from your keyboard view"""
    try:
        result_json = keyboard_onlinenuwakot_to_json(request)
        result_data = json.loads(result_json)
        
        return {
            "status": result_data["metadata"]["status"],
            "message": result_data.get("alert_message", "Online Nuwakot fetch completed"),
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
            "message": f"Error in fetch_onlinenuwakot_news: {str(e)}"
        }