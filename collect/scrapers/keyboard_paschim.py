#!/usr/bin/env python
"""
Enhanced Paschim Nepal Scraper - Clean version with minimal prints
"""
import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime, timedelta
import re
import time
from django.db import transaction

from collect.models import DangerousKeyword, AutoNewsArticle

def keyboard_paschimnepal_to_json(request):
    """Paschim Nepal scraper with expanded categories"""
    
    if not request or not hasattr(request, 'user') or not request.user.is_authenticated:
        return json.dumps({
            "metadata": {
                "status": "error",
                "message": "User authentication required",
                "scraped_at": datetime.now().isoformat()
            },
            "articles": []
        })
    
    base_url = "https://paschimnepal.com"
    TODAY = datetime.now()
    FOUR_DAYS_AGO = TODAY - timedelta(days=10)
    
    # Only print header
    print(f"\n🚀 PASCHIM NEPAL SCRAPER - {TODAY.strftime('%Y-%m-%d')} (last {10} days)")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    # ============ EXPANDED CATEGORIES ============
    categories = [
        # Original working categories
        {'path': '/category/accident/', 'name': 'accident', 'display': 'दुर्घटना'},
        {'path': '/category/notic/', 'name': 'notice', 'display': 'सूचना'},
        
        # New categories from your request
        {'path': '/category/rajniti/', 'name': 'politics', 'display': 'राजनीति'},
        {'path': '/category/pradesh-khabar/', 'name': 'province_news', 'display': 'प्रदेश खबर'},
        {'path': '/category/article/', 'name': 'article', 'display': 'लेख'},
        {'path': '/category/interview/', 'name': 'interview', 'display': 'अन्तर्वार्ता'},
        {'path': '/category/economic/', 'name': 'economic', 'display': 'आर्थिक'},
        
        # Additional categories that might have content
        {'path': '/category/market/', 'name': 'market', 'display': 'मार्केत'},
    ]
    
    MAX_PAGES_PER_CATEGORY = 3
    all_articles = []
    working_categories = []
    
    # Get keywords (silent)
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
    
    def is_article_within_date_range(article):
        """Check if article is from last 10 days (silent)"""
        url = article.get('url', '')
        
        url_date_match = re.search(r'/(\d{4})/(\d{2})/', url)
        if url_date_match:
            year, month = url_date_match.groups()
            try:
                article_date = datetime(int(year), int(month), 1)
                
                # Current month
                if article_date.year == TODAY.year and article_date.month == TODAY.month:
                    return True
                
                # Last month with grace period
                last_month = TODAY.replace(day=1) - timedelta(days=1)
                if (article_date.year == last_month.year and 
                    article_date.month == last_month.month and 
                    TODAY.day <= 10):
                    return True
                
                # After cutoff
                if article_date >= FOUR_DAYS_AGO.replace(day=1):
                    return True
                
                return False
                
            except Exception:
                return True
        
        return True
    
    # Scrape categories
    for category in categories:
        url = base_url + category['path']
        
        try:
            response = requests.get(url, headers=headers, timeout=30)
            if response.status_code != 200:
                continue
            
            working_categories.append(category['path'])
            
            for page_num in range(1, MAX_PAGES_PER_CATEGORY + 1):
                page_url = url
                if page_num > 1:
                    page_url = f"{url}page/{page_num}/"
                
                if page_num > 1:
                    page_response = requests.get(page_url, headers=headers, timeout=30)
                    if page_response.status_code != 200:
                        break
                    soup = BeautifulSoup(page_response.content, 'html.parser')
                else:
                    soup = BeautifulSoup(response.content, 'html.parser')
                
                page_articles = []
                
                # Find articles
                for link in soup.find_all('a', href=True):
                    href = link.get('href', '')
                    title = link.get_text(strip=True)
                    
                    if (title and len(title) > 20 and 
                        href.startswith('https://paschimnepal.com/') and
                        '/202' in href and
                        not any(x in href for x in ['category', 'tag', '#', 'wp-content', 'feed'])):
                        
                        clean_title = re.sub(r'प्रकाशित मितिः.*$', '', title).strip()
                        
                        parent = link.find_parent(['article', 'div', 'li'])
                        summary = clean_title
                        image_url = ""
                        
                        if parent:
                            p = parent.find('p')
                            if p and len(p.get_text(strip=True)) > len(clean_title):
                                summary = p.get_text(strip=True)
                            
                            img = parent.find('img')
                            if img:
                                image_url = img.get('src') or img.get('data-src') or ''
                                if image_url and image_url.startswith('/'):
                                    image_url = base_url + image_url
                        
                        article_data = {
                            'title': clean_title,
                            'url': href,
                            'category': category['name'],
                            'category_display': category['display'],
                            'date_text': '',
                            'image_url': image_url,
                            'summary': summary[:1000],
                            'page_found': page_num,
                            'source_category': category['display']
                        }
                        
                        if is_article_within_date_range(article_data):
                            article_data['discovered_at'] = datetime.now().isoformat()
                            all_articles.append(article_data)
                
                time.sleep(1)
            
        except Exception:
            continue
    
    # Remove duplicates
    unique_articles = []
    seen_urls = set()
    for article in all_articles:
        if article['url'] not in seen_urls:
            seen_urls.add(article['url'])
            unique_articles.append(article)
    
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
            image_url = article.get('image_url', '')[:1000] if article.get('image_url') else None
            source = 'paschimnepal'
            date = datetime.now().strftime('%Y-%m-%d')
            content_length = len(article.get('summary', ''))
            priority = article['threat_analysis']['priority']
            threat_level = article['threat_analysis']['level']
            keywords = json.dumps(article['threat_analysis']['keywords_found'], ensure_ascii=False)
            categories = json.dumps([article['category_display']], ensure_ascii=False)
            
            if existing:
                existing.title = title
                existing.summary = summary
                existing.image_url = image_url
                existing.content_length = content_length
                existing.priority = priority
                existing.threat_level = threat_level
                existing.keywords = keywords
                existing.categories = categories
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
                    categories=categories,
                    created_by=request.user
                )
                saved_count += 1
                
        except Exception:
            error_count += 1
    
    # Prepare response with MINIMAL summary prints
    print(f"\n📊 Working categories: {len(working_categories)}/{len(categories)}")
    print(f"📊 Total articles: {len(unique_articles)}")
    print(f"🔴 Matched articles: {len(matched_articles)}")
    print(f"💾 Saved: {saved_count} new, {updated_count} updated")
    print(f"{'='*60}")
    
    alert_message = f"✅ Paschim Nepal: Found {len(matched_articles)} matching articles"
    if saved_count > 0 or updated_count > 0:
        alert_message += f" (Saved: {saved_count} new, Updated: {updated_count})"
    
    metadata = {
        "source": "Paschim Nepal",
        "scraped_at": datetime.now().isoformat(),
        "status": "success",
        "user": request.user.username,
        "total_categories_checked": len(categories),
        "working_categories_found": len(working_categories),
        "total_articles_scraped": len(unique_articles),
        "articles_with_keywords": len(matched_articles),
        "articles_by_category": category_stats,
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