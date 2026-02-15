import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime, timedelta
import re
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib.parse
import os
from utils.websocket_helper import send_to_websocket
from django.contrib.auth.models import User
from django.db import models, transaction
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

# Import your models from collect app
from collect.models import DangerousKeyword, AutoNewsArticle


def keyboard_techpana_to_json(request):
    # Check if request has user
    if not request or not hasattr(request, 'user'):
        return json.dumps({
            "metadata": {
                "status": "error",
                "message": "User authentication required",
                "scraped_at": datetime.now().isoformat()
            },
            "articles": []
        })
    
    base_url = "https://techpana.com"
    
    # ============ ADJUSTED DELAYS ============
    DISCOVERY_DELAY = 2
    ARTICLE_DELAY = 2
    CATEGORY_DELAY = 3
    
    # ============ PAGINATION LIMIT ============
    MAX_PAGES_PER_CATEGORY = 4  # Only scrape first 4 pages
    
    # ============ DATE RANGE ============
    # Only get articles from last 4 days
    TODAY = datetime.now()
    FOUR_DAYS_AGO = TODAY - timedelta(days=4)
    
    print(f"\n📅 DATE FILTER: Only articles from {FOUR_DAYS_AGO.strftime('%Y-%m-%d')} to {TODAY.strftime('%Y-%m-%d')} will be kept")
    
    # User-Agents
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ]
    
    # ============ RELEVANT CATEGORIES FOR TECHPANA ============
    RELEVANT_CATEGORIES = [
        # Fact Check & Verification
        "/factcheck", 
        "/category/viral",   
        "/category/facebook",
        "/category/cyber-crime",
        "/category/cyber-attack",
        # "/category/twitter",
        # "/category/youtube",
        # "/category/law",
        # "category/news",
        
        # Data & Privacy
        # "/category/data-breach",
        # "/category/data-privacy",
        # "/category/cyber-laws",
        
        # Scams & Fraud
        # "/category/tiktok",
        # "/category/whatsapp",
    ]
    
    # ============ FETCH DANGEROUS KEYWORDS FROM DB ============
    def fetch_dangerous_keywords():
        """Fetch all active dangerous keywords from collect app database"""
        try:
            keywords = DangerousKeyword.objects.filter(is_active=True).values('word', 'category')
            
            # Organize keywords by category
            keywords_by_category = {}
            all_keywords_list = []
            
            for kw in keywords:
                word = kw['word'].lower().strip()
                category = kw['category'].strip()
                
                # Add to category-specific list
                if category not in keywords_by_category:
                    keywords_by_category[category] = []
                keywords_by_category[category].append(word)
                
                # Add to master list
                all_keywords_list.append({
                    'word': word,
                    'category': category
                })
            
            print(f"\n📋 LOADED DANGEROUS KEYWORDS FROM COLLECT APP:")
            for category, words in keywords_by_category.items():
                print(f"   • {category}: {len(words)} keywords")
            print(f"   TOTAL: {len(all_keywords_list)} keywords")
            
            return keywords_by_category, all_keywords_list
            
        except Exception as e:
            print(f"⚠️ Error fetching keywords from database: {str(e)}")
            return {}, []
    
    # ============ KEYWORD MATCHING FUNCTION ============
    def analyze_article_content(article, keywords_by_category, all_keywords_list):
        """
        Analyze article title and summary against dangerous keywords
        Returns matched keywords by category and threat analysis
        """
        matched_keywords = []
        matched_categories = set()
        keywords_found = []
        
        # Combine title and summary for analysis
        content_to_analyze = f"{article['title']} {article.get('summary', '')}".lower()
        
        # Remove special characters for better matching
        content_to_analyze = re.sub(r'[^\w\s]', ' ', content_to_analyze)
        words_in_content = set(content_to_analyze.split())
        
        # Check each keyword against the content
        for keyword_info in all_keywords_list:
            keyword = keyword_info['word']
            category = keyword_info['category']
            
            # Check for exact match or as part of words
            if keyword in words_in_content or keyword in content_to_analyze:
                matched_keywords.append({
                    'word': keyword,
                    'category': category
                })
                matched_categories.add(category)
                keywords_found.append(keyword)
        
        # Remove duplicates while preserving order
        unique_keywords_found = []
        seen = set()
        for kw in keywords_found:
            if kw not in seen:
                seen.add(kw)
                unique_keywords_found.append(kw)
        
        # Determine threat level based on matches
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
            "keywords_found": unique_keywords_found[:20],
            "total_keywords_matched": total_matches,
            "categories": list(matched_categories),
            "matched_keywords_detail": matched_keywords[:30],
            "has_match": total_matches > 0
        }
    
    # ============ DATE PARSING FUNCTION ============
    def parse_article_date(date_text):
        """Parse date from Techpana article to check if it's within last 4 days"""
        if not date_text:
            return None
        
        date_text = date_text.lower().strip()
        
        try:
            # Try to parse various date formats
            # Format: "January 15, 2025" or "Jan 15, 2025" or "15 Jan 2025"
            for fmt in ["%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y", "%Y-%m-%d"]:
                try:
                    parsed_date = datetime.strptime(date_text, fmt)
                    return parsed_date
                except:
                    continue
            
            # Handle relative dates like "2 days ago", "yesterday", etc.
            if 'day' in date_text or 'yesterday' in date_text:
                if 'yesterday' in date_text:
                    return TODAY - timedelta(days=1)
                
                days_match = re.search(r'(\d+)\s+day', date_text)
                if days_match:
                    days = int(days_match.group(1))
                    return TODAY - timedelta(days=days)
            
            # Handle "2025-01-15" format
            if re.match(r'\d{4}-\d{2}-\d{2}', date_text):
                return datetime.strptime(date_text[:10], "%Y-%m-%d")
                
        except Exception as e:
            pass
        
        return None
    
    def is_article_within_date_range(article):
        """Check if article is from last 4 days"""
        # If we have date_text, try to parse it
        if article.get('date_text'):
            article_date = parse_article_date(article['date_text'])
            if article_date:
                # Remove time component for date comparison
                article_date = article_date.replace(hour=0, minute=0, second=0, microsecond=0)
                cutoff_date = FOUR_DAYS_AGO.replace(hour=0, minute=0, second=0, microsecond=0)
                
                if article_date >= cutoff_date:
                    return True
                else:
                    print(f"      ⏰ Skipping article from {article_date.strftime('%Y-%m-%d')} (older than 4 days)")
                    return False
        
        # If we can't determine date, assume it's recent (keep it)
        return True
    
    # ============ SESSION SETUP ============
    def create_protected_session():
        session = requests.Session()
        
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
            raise_on_status=False
        )
        
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=10,
            pool_maxsize=10
        )
        
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        
        session.headers.update({
            "User-Agent": random.choice(user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache"
        })
        
        return session
    
    def safe_decode_html(content):
        if isinstance(content, bytes):
            try:
                return content.decode('utf-8')
            except:
                return content.decode('utf-8', errors='replace')
        return content
    
    # ============ PAGINATION HANDLING ============
    def get_next_page_url(soup, current_url):
        """Find next page URL from pagination"""
        pagination = soup.find('ul', class_=re.compile(r'pagination|pager|pages'))
        if pagination:
            next_link = pagination.find('a', text=re.compile(r'next|»|›|>|→', re.I))
            if not next_link:
                next_link = soup.find('link', rel='next')
            if not next_link:
                next_link = soup.find('a', class_=re.compile(r'next|older'))
            
            if next_link and next_link.get('href'):
                next_url = next_link['href']
                if next_url.startswith('/'):
                    next_url = base_url + next_url
                return next_url
        
        page_links = soup.find_all('a', href=re.compile(r'page[/=]\d+'))
        if page_links:
            current_page = 1
            page_match = re.search(r'page[/=](\d+)', current_url)
            if page_match:
                current_page = int(page_match.group(1))
            
            for link in page_links:
                href = link['href']
                page_match = re.search(r'page[/=](\d+)', href)
                if page_match:
                    page_num = int(page_match.group(1))
                    if page_num == current_page + 1:
                        if href.startswith('/'):
                            href = base_url + href
                        return href
        
        return None
    
    # ============ ARTICLE EXTRACTION ============
    def extract_articles_from_category_page(html_content, category_url, category_name):
        """Extract articles from category listing page"""
        soup = BeautifulSoup(html_content, 'html.parser')
        articles = []
        
        print(f"\n   🔍 Extracting articles from {category_name}...")
        
        # Try multiple selectors for Techpana's actual structure
        selectors = [
            ('div', 'col-sm-6 col-md-4'),
            ('div', 'single_grid-wrapper'),
            ('article', None),
            ('div', 'post'),
            ('div', 'entry'),
            ('div', 'news-item'),
            ('div', 'card'),
            ('div', 'item'),
            ('div', 'blog-post'),
            ('div', 'latest-post'),
            ('div', 'grid-item'),
            ('div', 'post-item'),
            ('div', 'news-grid'),
            ('div', 'article-card'),
            ('div', 'story-card'),
            ('div', 'content-card'),
        ]
        
        for tag, class_name in selectors:
            containers = soup.find_all(tag, class_=class_name) if class_name else soup.find_all(tag)
            
            for container in containers:
                try:
                    # Find title and link
                    title_elem = container.find(['h1', 'h2', 'h3', 'h4', 'h5']) or container.find('div', class_=re.compile(r'title|heading|name|post-title|entry-title|article-title'))
                    
                    if title_elem:
                        link = title_elem.find('a', href=True) or container.find('a', href=True)
                        
                        if link and link.get('href'):
                            title = link.get_text(strip=True) or title_elem.get_text(strip=True)
                            url = link['href']
                            
                            # Clean URL
                            if url.startswith('/'):
                                url = base_url + url
                            elif not url.startswith('http'):
                                url = base_url + '/' + url.lstrip('/')
                            
                            # Skip non-article links
                            if any(skip in url.lower() for skip in ['category', 'tag', 'author', '#', 'login', 'register', 'profile', 'account']):
                                continue
                            
                            # Get date if available
                            date_text = ""
                            date_elem = container.find('time') or container.find('span', class_=re.compile(r'date|time|published|post-date|entry-date'))
                            if date_elem:
                                date_text = date_elem.get_text(strip=True)
                            
                            # Get image if available
                            image_url = ""
                            img_elem = container.find('img')
                            if img_elem:
                                image_url = img_elem.get('src') or img_elem.get('data-src') or img_elem.get('data-lazy-src') or ''
                                if image_url and not image_url.startswith('http'):
                                    image_url = base_url + image_url if image_url.startswith('/') else image_url
                            
                            # Get excerpt/summary
                            summary = ""
                            summary_elem = container.find('p', class_=re.compile(r'excerpt|summary|description|post-excerpt|entry-summary')) or container.find('div', class_=re.compile(r'excerpt|summary|description'))
                            if summary_elem:
                                summary = summary_elem.get_text(strip=True)
                            
                            articles.append({
                                'title': title,
                                'url': url,
                                'category': category_name,
                                'date_text': date_text,
                                'image_url': image_url,
                                'summary': summary[:500] if summary else title[:300],
                                'method': f'{tag}.{class_name if class_name else "no-class"}'
                            })
                except Exception as e:
                    continue
            
            if articles:
                print(f"      Found {len(articles)} articles using {tag}.{class_name if class_name else 'no-class'}")
                break
        
        # If no articles found with specific selectors, try direct link extraction
        if not articles:
            print(f"      No articles found with selectors, trying direct link extraction...")
            all_links = soup.find_all('a', href=True)
            for link in all_links:
                href = link['href']
                title = link.get_text(strip=True)
                
                # Check if this looks like an article link
                if (title and len(title) > 25 and 
                    ('/202' in href or '/story' in href or '/post' in href or '/article' in href or '/news' in href) and 
                    not any(x in href.lower() for x in ['category', 'tag', 'author', 'page', '#', 'login', 'register'])):
                    
                    if not href.startswith('http'):
                        href = base_url + href if href.startswith('/') else href
                    
                    articles.append({
                        'title': title,
                        'url': href,
                        'category': category_name,
                        'date_text': '',
                        'image_url': '',
                        'summary': title[:300],
                        'method': 'direct'
                    })
        
        # Remove duplicates while preserving order
        unique_articles = []
        seen_urls = set()
        for article in articles:
            if article['url'] not in seen_urls:
                seen_urls.add(article['url'])
                unique_articles.append(article)
        
        print(f"      ✅ Total unique articles found on this page: {len(unique_articles)}")
        return unique_articles
    
    # ============ MAIN EXTRACTION WITH PAGINATION LIMIT ============
    def extract_all_articles():
        """Extract articles from all relevant categories with max 4 pages per category"""
        all_articles = []
        processed_urls = set()
        
        session = create_protected_session()
        
        print(f"\n🔍 Processing {len(RELEVANT_CATEGORIES)} Techpana categories...")
        print(f"   📄 Max pages per category: {MAX_PAGES_PER_CATEGORY}")
        print(f"   📅 Date filter: Keeping only articles from {FOUR_DAYS_AGO.strftime('%Y-%m-%d')} onwards")
        
        # Filter to only include categories that exist on Techpana
        working_categories = []
        
        for category_path in RELEVANT_CATEGORIES:
            # Skip empty or malformed paths
            if not category_path:
                continue
                
            # Ensure category_path starts with /
            if not category_path.startswith('/'):
                category_path = '/' + category_path
                
            category_url = base_url + category_path
            category_name = category_path.replace('/category/', '').replace('/', '')
            
            # Test if category exists
            try:
                test_response = session.get(category_url, timeout=15)
                if test_response.status_code == 200:
                    working_categories.append(category_path)
                    print(f"\n   ✅ Category exists: {category_name}")
                else:
                    print(f"\n   ⚠️ Category not found (HTTP {test_response.status_code}): {category_name}")
                    continue
            except Exception as e:
                print(f"\n   ⚠️ Cannot access category {category_name}: {str(e)[:50]}")
                continue
            
            page_num = 1
            
            print(f"\n   📂 Scraping category: {category_name}")
            print(f"      URL: {category_url}")
            
            # Only scrape up to MAX_PAGES_PER_CATEGORY
            while page_num <= MAX_PAGES_PER_CATEGORY:
                current_url = category_url
                if page_num > 1:
                    if '?' in current_url:
                        current_url = f"{current_url}&page={page_num}"
                    else:
                        current_url = f"{current_url}?page={page_num}"
                
                print(f"      📄 Page {page_num}/{MAX_PAGES_PER_CATEGORY}: {current_url}")
                
                try:
                    time.sleep(CATEGORY_DELAY + random.uniform(1, 3))
                    
                    response = session.get(current_url, timeout=30)
                    
                    if response.status_code != 200:
                        print(f"      ⚠️ HTTP {response.status_code} - stopping pagination for this category")
                        break
                    
                    html_content = safe_decode_html(response.content)
                    articles = extract_articles_from_category_page(html_content, current_url, category_name)
                    
                    if not articles:
                        print(f"      📭 No articles found on page {page_num}")
                        break
                    
                    new_articles = []
                    date_filtered_count = 0
                    
                    for article in articles:
                        # Check if article is within date range
                        if is_article_within_date_range(article):
                            if article['url'] not in processed_urls:
                                article['discovered_at'] = datetime.now().isoformat()
                                article['page_found'] = page_num
                                article['category_url'] = category_url
                                all_articles.append(article)
                                processed_urls.add(article['url'])
                                new_articles.append(article)
                        else:
                            date_filtered_count += 1
                    
                    if date_filtered_count > 0:
                        print(f"      ⏰ Filtered out {date_filtered_count} articles older than 4 days")
                    
                    print(f"      ✅ Page {page_num}: +{len(new_articles)} new articles within date range")
                    
                    # Check if we've reached max pages
                    if page_num >= MAX_PAGES_PER_CATEGORY:
                        print(f"      🏁 Reached max pages limit ({MAX_PAGES_PER_CATEGORY}) for {category_name}")
                        break
                    
                    # Check for next page URL
                    soup = BeautifulSoup(response.content, 'html.parser')
                    next_url = get_next_page_url(soup, current_url)
                    
                    if not next_url or next_url == current_url:
                        print(f"      🏁 No more pages available for {category_name}")
                        break
                    
                    page_num += 1
                    
                except Exception as e:
                    print(f"      ⚠️ Error on page {page_num}: {str(e)[:50]}...")
                    break
            
            category_articles = [a for a in all_articles if a.get('category') == category_name]
            print(f"      📊 Total articles from {category_name} (last 4 days): {len(category_articles)}")
        
        print(f"\n📊 WORKING CATEGORIES FOUND: {len(working_categories)} out of {len(RELEVANT_CATEGORIES)}")
        print(f"📊 TOTAL ARTICLES WITHIN DATE RANGE: {len(all_articles)}")
        return all_articles, working_categories
    
    # ============ PROCESS ARTICLES WITH KEYWORD MATCHING ============
    def process_articles_with_keywords(articles, request, keywords_by_category, all_keywords_list):
        """Process articles and match with dangerous keywords - ONLY KEEP MATCHES"""
        print(f"\n📊 Processing {len(articles)} articles with keyword matching...")
        print(f"   🔴 Will ONLY keep articles that match dangerous keywords")
        
        processed_articles = []
        matched_articles_count = 0
        keyword_match_stats = {}
        
        for i, article in enumerate(articles):
            # Analyze article content against keywords
            threat_analysis = analyze_article_content(article, keywords_by_category, all_keywords_list)
            
            # ONLY KEEP ARTICLES THAT HAVE KEYWORD MATCHES
            if threat_analysis['has_match']:
                # Update statistics
                categories_matched = threat_analysis['categories']
                for category in categories_matched:
                    if category not in keyword_match_stats:
                        keyword_match_stats[category] = 0
                    keyword_match_stats[category] += 1
                
                matched_articles_count += 1
                
                article_data = {
                    "id": len(processed_articles) + 1,
                    "title": article['title'],
                    "summary": article.get('summary', article['title'][:300]),
                    "url": article['url'],
                    "source": "techpana",
                    "category": article.get('category', 'general'),
                    "date_text": article.get('date_text', ''),
                    "image_url": article.get('image_url', ''),
                    "page_found": article.get('page_found', 1),
                    "threat_analysis": threat_analysis,
                    "publish_date": datetime.now().strftime('%Y-%m-%d'),
                    "scraped_at": datetime.now().isoformat(),
                    "discovered_at": article.get('discovered_at', datetime.now().isoformat()),
                    "has_dangerous_keywords": True,
                    "matched_categories": threat_analysis['categories'],
                    "matched_keywords": threat_analysis['keywords_found'],
                    "threat_level": threat_analysis['level'],
                    "threat_priority": threat_analysis['priority']
                }
                
                processed_articles.append(article_data)
                
                # Show progress
                if len(processed_articles) % 10 == 0 or len(processed_articles) == 1:
                    print(f"      ✅ Found match #{len(processed_articles)}: +{threat_analysis['total_keywords_matched']} keywords in '{article['title'][:50]}...'")
            else:
                # Skip articles without keyword matches
                if i < 5:  # Show first few skips only
                    print(f"      ⏭️  Skipping article (no keyword matches): {article['title'][:50]}...")
        
        print(f"\n✅ KEYWORD MATCHING COMPLETE:")
        print(f"   • Total articles analyzed: {len(articles)}")
        print(f"   • Articles WITH dangerous keywords: {matched_articles_count} (KEPT)")
        print(f"   • Articles WITHOUT keywords: {len(articles) - matched_articles_count} (FILTERED OUT)")
        
        if keyword_match_stats:
            print(f"\n   📊 Matches by category:")
            for category, count in sorted(keyword_match_stats.items(), key=lambda x: x[1], reverse=True):
                print(f"      • {category}: {count} articles")
        
        return processed_articles, {
            'matched': matched_articles_count,
            'total': len(articles),
            'filtered_out': len(articles) - matched_articles_count,
            'category_stats': keyword_match_stats
        }
    
    # ============ SAVE TO DATABASE FUNCTION - CORRECTED FOR YOUR MODEL ============
    @transaction.atomic
    def save_articles_to_database(articles, request):
        """
        Save scraped articles to AutoNewsArticle model in collect app
        Only saves articles with keyword matches
        """
        saved_count = 0
        updated_count = 0
        error_count = 0
        errors = []
        
        print(f"\n💾 SAVING {len(articles)} MATCHED ARTICLES TO DATABASE...")
        
        # Get user for created_by field
        user = request.user if request.user.is_authenticated else None
        
        for article in articles:
            try:
                # Check if article already exists for this user (unique_together = ['url', 'created_by'])
                existing_article = AutoNewsArticle.objects.filter(
                    url=article['url'],
                    created_by=user
                ).first()
                
                # Prepare data according to your model
                title = article['title'][:500]  # max_length=500
                summary = article.get('summary', article['title'])[:1000]  # TextField
                url = article['url'][:1000]  # max_length=1000
                image_url = article.get('image_url', '')[:1000] if article.get('image_url') else None
                source = article.get('source', 'techpana')[:100]  # max_length=100
                date = article.get('date_text', '')[:20] or datetime.now().strftime('%Y-%m-%d')[:20]  # max_length=20
                
                # Store threat analysis data in appropriate fields
                content_length = len(article.get('summary', ''))
                priority = article.get('threat_analysis', {}).get('priority', 'medium')[:10]  # max_length=10
                threat_level = article.get('threat_analysis', {}).get('level', 'low')[:10]  # max_length=10
                
                # Store keywords and categories as JSON strings in TextFields
                keywords = json.dumps(article.get('threat_analysis', {}).get('keywords_found', []), ensure_ascii=False)
                categories = json.dumps(article.get('threat_analysis', {}).get('categories', []), ensure_ascii=False)
                
                if existing_article:
                    # Update existing article
                    existing_article.title = title
                    existing_article.summary = summary
                    existing_article.url = url
                    existing_article.image_url = image_url
                    existing_article.source = source
                    existing_article.date = date
                    existing_article.content_length = content_length
                    existing_article.priority = priority
                    existing_article.threat_level = threat_level
                    existing_article.keywords = keywords
                    existing_article.categories = categories
                    
                    existing_article.save()
                    updated_count += 1
                    if updated_count <= 5 or len(articles) <= 20:
                        print(f"      🔄 Updated: {article['title'][:50]}...")
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
                        categories=categories,
                        created_by=user
                    )
                    saved_count += 1
                    if saved_count <= 5 or len(articles) <= 20:
                        print(f"      ✅ Saved: {article['title'][:50]}...")
                
            except Exception as e:
                error_count += 1
                error_msg = f"Error saving {article['url'][:50]}: {str(e)[:100]}"
                errors.append(error_msg)
                print(f"      ❌ {error_msg}")
                
                # Print more details for debugging
                import traceback
                traceback.print_exc()
        
        print(f"\n   ✅ New articles saved: {saved_count}")
        print(f"   🔄 Existing articles updated: {updated_count}")
        print(f"   ❌ Errors: {error_count}")
        print(f"   📊 TOTAL MATCHED ARTICLES IN DATABASE: {saved_count + updated_count}")
        
        if errors and error_count <= 5:
            for error in errors:
                print(f"      • {error[:100]}...")
        
        return saved_count, updated_count, error_count, errors
    
    # ============ MAIN EXECUTION ============
    try:
        start_time = time.time()
        print("=" * 80)
        print("🚀 TECHPANA SCRAPER - KEYWORD MATCHING ONLY MODE")
        print("=" * 80)
        print(f"📋 Total categories to check: {len(RELEVANT_CATEGORIES)}")
        print(f"📄 MAX PAGES PER CATEGORY: {MAX_PAGES_PER_CATEGORY}")
        print(f"📅 DATE RANGE: Last 4 days ({FOUR_DAYS_AGO.strftime('%Y-%m-%d')} to {TODAY.strftime('%Y-%m-%d')})")
        print(f"🔴 FILTER: ONLY articles with dangerous keyword matches will be saved")
        print("=" * 80)
        
        # Step 1: Fetch dangerous keywords from collect app database
        print("\n📚 Loading dangerous keywords from collect app...")
        keywords_by_category, all_keywords_list = fetch_dangerous_keywords()
        
        if not all_keywords_list:
            print("⚠️ No dangerous keywords found in database. No articles will be saved.")
            return json.dumps({
                "metadata": {
                    "status": "warning",
                    "message": "No dangerous keywords found in database",
                    "scraped_at": datetime.now().isoformat()
                },
                "articles": []
            }, ensure_ascii=False)
        
        # Step 2: Test connection
        print("\n🌐 Testing connection to Techpana...")
        test_session = create_protected_session()
        try:
            test_response = test_session.get("https://techpana.com", timeout=30)
            print(f"   ✅ Techpana homepage: {test_response.status_code}")
        except Exception as e:
            print(f"   ❌ Cannot access Techpana: {str(e)}")
            return json.dumps({
                "metadata": {
                    "status": "error",
                    "message": f"Cannot access Techpana: {str(e)}",
                    "scraped_at": datetime.now().isoformat()
                },
                "articles": []
            }, ensure_ascii=False)
        
        # Step 3: Extract articles from all relevant categories
        all_articles, working_categories = extract_all_articles()
        
        if not all_articles:
            print("\n❌ No articles found within date range!")
            return json.dumps({
                "metadata": {
                    "status": "success",
                    "message": "No articles found in last 4 days",
                    "total_articles_found": 0,
                    "scraped_at": datetime.now().isoformat(),
                    "source": "Techpana"
                },
                "articles": []
            }, ensure_ascii=False)
        
        # Step 4: Process articles with keyword matching - ONLY KEEP MATCHES
        matched_articles, stats = process_articles_with_keywords(
            all_articles, 
            request, 
            keywords_by_category, 
            all_keywords_list
        )
        
        if not matched_articles:
            print("\n📭 No articles with dangerous keyword matches found in last 4 days!")
            
            metadata = {
                "source": "Techpana",
                "scraped_at": datetime.now().isoformat(),
                "status": "success",
                "user": request.user.username if request.user.is_authenticated else "anonymous",
                "total_categories_checked": len(RELEVANT_CATEGORIES),
                "working_categories_found": len(working_categories),
                "total_articles_scraped": len(all_articles),
                "articles_with_keywords": 0,
                "articles_filtered_out": len(all_articles),
                "date_range": {
                    "start": FOUR_DAYS_AGO.strftime('%Y-%m-%d'),
                    "end": TODAY.strftime('%Y-%m-%d')
                },
                "message": "No keyword matches found in last 4 days"
            }
            
            return json.dumps({
                "metadata": metadata,
                "articles": [],
                "stats": stats
            }, ensure_ascii=False)
        
        # Step 5: Save only matched articles to database
        saved, updated, errors_count, errors_list = save_articles_to_database(matched_articles, request)
        
        # Step 6: Prepare metadata
        exec_time = round(time.time() - start_time, 2)
        
        metadata = {
            "source": "Techpana",
            "scraped_at": datetime.now().isoformat(),
            "status": "success",
            "user": request.user.username if request.user.is_authenticated else "anonymous",
            "total_categories_checked": len(RELEVANT_CATEGORIES),
            "working_categories_found": len(working_categories),
            "max_pages_per_category": MAX_PAGES_PER_CATEGORY,
            "total_articles_scraped": len(all_articles),
            "articles_with_keywords": len(matched_articles),
            "articles_filtered_out_by_date": len([a for a in all_articles if not is_article_within_date_range(a)]),
            "articles_filtered_out_by_keywords": len(all_articles) - len(matched_articles),
            "database_save": {
                "new_articles_saved": saved,
                "existing_articles_updated": updated,
                "errors": errors_count,
                "total_matched_articles_in_db": saved + updated
            },
            "date_range": {
                "start": FOUR_DAYS_AGO.strftime('%Y-%m-%d'),
                "end": TODAY.strftime('%Y-%m-%d')
            },
            "execution_time_seconds": exec_time,
            "execution_time_formatted": f"{exec_time:.2f}s",
            "articles_per_category": {},
            "keyword_matches_by_category": stats.get('category_stats', {}),
            "dangerous_keywords_loaded": len(all_keywords_list)
        }
        
        # Add category counts to metadata
        for category_path in working_categories:
            cat_name = category_path.replace('/category/', '').replace('/', '')
            count = len([a for a in matched_articles if a.get('category') == cat_name])
            metadata["articles_per_category"][cat_name] = count
        
        print("\n" + "=" * 80)
        print(f"✅ TECHPANA SCRAPING COMPLETED SUCCESSFULLY!")
        print(f"   📊 CATEGORIES: {len(working_categories)} working out of {len(RELEVANT_CATEGORIES)} checked")
        print(f"   📄 PAGES PER CATEGORY: First {MAX_PAGES_PER_CATEGORY} pages")
        print(f"   📅 DATE RANGE: Last 4 days")
        print(f"   📊 TOTAL ARTICLES SCRAPED: {len(all_articles)}")
        print(f"   🔴 ARTICLES WITH KEYWORD MATCHES: {len(matched_articles)} (SAVED)")
        print(f"   ⏭️  ARTICLES WITHOUT MATCHES: {len(all_articles) - len(matched_articles)} (FILTERED)")
        print(f"   📚 DANGEROUS KEYWORDS LOADED: {len(all_keywords_list)}")
        print(f"   💾 DATABASE: {saved} new, {updated} updated, {errors_count} errors")
        print(f"   ⏱️  EXECUTION TIME: {exec_time:.2f} seconds")
        print("=" * 80)
        
        # Print working categories with match counts
        if matched_articles:
            print("\n📋 MATCHED ARTICLES BY CATEGORY:")
            cat_counts = {}
            for article in matched_articles:
                cat = article.get('category', 'general')
                cat_counts[cat] = cat_counts.get(cat, 0) + 1
            
            for i, (cat, count) in enumerate(sorted(cat_counts.items(), key=lambda x: x[1], reverse=True)[:20], 1):
                print(f"   {i}. {cat}: {count} matched articles")
        
        # Send to websocket if available
        try:
            send_to_websocket({
                "type": "scraping_complete",
                "source": "techpana",
                "metadata": metadata,
                "stats": stats
            })
        except:
            pass
        
        # Return ONLY matched articles
        return json.dumps({
            "metadata": metadata,
            "articles": matched_articles,
            "stats": stats,
            "database_results": {
                "saved": saved,
                "updated": updated,
                "errors": errors_list[:5] if errors_list else []
            },
            "working_categories": working_categories,
            "dangerous_keywords_summary": {
                "total_keywords": len(all_keywords_list),
                "categories": list(keywords_by_category.keys()),
                "keywords_by_category": {k: len(v) for k, v in keywords_by_category.items()}
            },
            "summary": {
                "total_categories_checked": len(RELEVANT_CATEGORIES),
                "working_categories_found": len(working_categories),
                "max_pages_per_category": MAX_PAGES_PER_CATEGORY,
                "total_articles_scraped": len(all_articles),
                "articles_with_keywords": len(matched_articles),
                "date_filter_applied": f"Last 4 days ({FOUR_DAYS_AGO.strftime('%Y-%m-%d')} to {TODAY.strftime('%Y-%m-%d')})",
                "keyword_match_rate": f"{round((len(matched_articles) / len(all_articles) * 100), 2) if all_articles else 0}%"
            }
        }, ensure_ascii=False)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        
        error_response = {
            "metadata": {
                "status": "error", 
                "error": str(e),
                "error_type": type(e).__name__,
                "scraped_at": datetime.now().isoformat(),
                "source": "Techpana"
            },
            "articles": []
        }
        
        # Try to send error to websocket
        try:
            send_to_websocket({
                "type": "scraping_error",
                "source": "techpana",
                "error": str(e)
            })
        except:
            pass
        
        return json.dumps(error_response, ensure_ascii=False)


# ============ TESTING FUNCTION ============
def test_techpana_scraper():
    """Test function with debug output"""
    print("🧪 TECHPANA SCRAPER - KEYWORD MATCHING ONLY MODE")
    print("=" * 80)
    print("🔴 ONLY articles with dangerous keyword matches from last 4 days will be saved")
    print("=" * 80)
    
    class MockUser:
        def __init__(self):
            self.username = "debug_user"
            self.is_authenticated = True
    
    class MockRequest:
        def __init__(self):
            self.user = MockUser()
    
    # Run the scraper
    result = keyboard_techpana_to_json(MockRequest())
    
    # Parse and display results
    try:
        parsed = json.loads(result)
        
        print(f"\n📋 FINAL RESULTS SUMMARY:")
        print(f"   Status: {parsed['metadata'].get('status', 'unknown')}")
        print(f"   Categories checked: {parsed['metadata'].get('total_categories_checked', 0)}")
        print(f"   Working categories: {parsed['metadata'].get('working_categories_found', 0)}")
        print(f"   Total articles scraped: {parsed['metadata'].get('total_articles_scraped', 0)}")
        print(f"   Articles with keyword matches: {parsed['metadata'].get('articles_with_keywords', 0)}")
        print(f"   Articles filtered out: {parsed['metadata'].get('articles_filtered_out_by_keywords', 0)}")
        print(f"   Dangerous keywords loaded: {parsed['metadata'].get('dangerous_keywords_loaded', 0)}")
        print(f"   Database - New: {parsed['metadata'].get('database_save', {}).get('new_articles_saved', 0)}")
        print(f"   Database - Updated: {parsed['metadata'].get('database_save', {}).get('existing_articles_updated', 0)}")
        print(f"   Database - Errors: {parsed['metadata'].get('database_save', {}).get('errors', 0)}")
        print(f"   Execution time: {parsed['metadata'].get('execution_time_formatted', 'N/A')}")
        
        if parsed.get('articles'):
            print(f"\n🔴 MATCHED ARTICLES ({len(parsed['articles'])} total):")
            for i, article in enumerate(parsed['articles'][:10], 1):
                print(f"   {i}. {article['title'][:80]}...")
                print(f"      URL: {article['url']}")
                print(f"      Threat Level: {article['threat_analysis']['level']}")
                print(f"      Keywords Found: {article['threat_analysis']['keywords_found'][:5]}")
                print(f"      Categories: {article['threat_analysis']['categories']}")
        else:
            print(f"\n📭 No matching articles found in last 4 days")
        
    except json.JSONDecodeError:
        print(f"❌ Failed to parse JSON response")
        print(f"Raw response: {result[:500]}...")
    
    return result


# ============ SCHEDULED TASK FUNCTION ============
def run_techpana_scraper_scheduled():
    """Function to be called by Celery or cron jobs"""
    print(f"🕐 Starting scheduled Techpana scraper at {datetime.now()}")
    print(f"🔴 Mode: Keyword matches only, Last 4 days")
    
    class SystemUser:
        def __init__(self):
            self.username = "system"
            self.is_authenticated = True
    
    class ScheduledRequest:
        def __init__(self):
            self.user = SystemUser()
    
    try:
        result = keyboard_techpana_to_json(ScheduledRequest())
        parsed = json.loads(result)
        
        if parsed['metadata']['status'] == 'success':
            matched_count = parsed['metadata'].get('articles_with_keywords', 0)
            print(f"✅ Scheduled Techpana scraper completed successfully")
            print(f"   Categories found: {parsed['metadata'].get('working_categories_found', 0)}")
            print(f"   Articles scraped: {parsed['metadata'].get('total_articles_scraped', 0)}")
            print(f"   🔴 Keyword matches found: {matched_count}")
            print(f"   New to database: {parsed['metadata'].get('database_save', {}).get('new_articles_saved', 0)}")
            return matched_count
        else:
            print(f"❌ Scheduled Techpana scraper failed: {parsed['metadata'].get('error', 'Unknown error')}")
            return 0
            
    except Exception as e:
        print(f"❌ Scheduled Techpana scraper exception: {str(e)}")
        return 0


if __name__ == "__main__":
    result = test_techpana_scraper()
    print("\n✨ Techpana scraping complete - Only keyword matching articles from last 4 days saved!")