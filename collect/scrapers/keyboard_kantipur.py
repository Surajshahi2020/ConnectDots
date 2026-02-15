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
from utils.websocket_helper import send_to_websocket


def keyboard_kantipur_to_json(request):
    # Try both possible domains
    base_urls = ["https://ekantipur.com", "https://www.kantipurdaily.com"]
    base_url = base_urls[0]  # Start with ekantipur.com
    
    send_to_websocket(f"🌐 Attempting to connect to: {base_url}")
    
    # Settings
    TODAY = datetime.now()
    TWO_DAYS_AGO = TODAY - timedelta(days=4)
    
    DELAY = 2
    MAX_WORKERS = 4
    TOTAL_STEPS = 7
    
    global_start_time = time.time()
    current_step = 1
    
    def update_progress(step_name, current, total=None, custom_message=None):
        nonlocal current_step
        if custom_message:
            send_to_websocket(custom_message)
            return
        elapsed = time.time() - global_start_time
        if total and current > 0:
            message = f"📊 {step_name}: {current}/{total} ({elapsed:.1f}s)"
        else:
            message = f"📊 {step_name} ({elapsed:.1f}s)"
        send_to_websocket(message)
    
    def get_user_keywords(request):
        try:
            from collect.models import DangerousKeyword
            if not request.user.is_authenticated:
                return [], {}
            keywords = DangerousKeyword.objects.filter(is_active=True, created_by=request.user)
            keyword_dict = {kw.word.lower().strip(): kw.category.strip() for kw in keywords}
            return list(keyword_dict.keys()), keyword_dict
        except Exception as e:
            print(f"⚠️ Keyword error: {e}")
            return [], {}
    
    def create_session():
        session = requests.Session()
        retry = Retry(total=3, backoff_factor=1)
        adapter = HTTPAdapter(max_retries=retry, pool_connections=10)
        session.mount('https://', adapter)
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml",
        })
        return session
    
    def find_article_links(session):
        """Find article links using the actual HTML structure"""
        nonlocal current_step, base_url
        update_progress("Finding articles", 0, 1, "🔍 Searching for articles...")
        
        # Try to determine which base URL works
        working_base = None
        for url in base_urls:
            try:
                test_response = session.get(url, timeout=10)
                if test_response.status_code == 200:
                    working_base = url
                    base_url = url
                    send_to_websocket(f"✅ Connected to: {url}")
                    break
            except:
                continue
        
        if not working_base:
            send_to_websocket("❌ Cannot connect to Kantipur")
            return []
        
        # Categories to check - REMOVED /economy
        categories = [
            "/news", "/politics", "/sports", "/entertainment",
        ]
        
        articles = []
        seen_urls = set()
        start_time = time.time()
        working_categories = 0
        
        for idx, category in enumerate(categories):
            try:
                cat_name = category.strip('/')
                update_progress(f"Checking {cat_name}", idx + 1, len(categories))
                
                url = working_base + category
                print(f"\n   📄 Fetching {url}")
                
                time.sleep(DELAY)
                response = session.get(url, timeout=15)
                
                if response.status_code != 200:
                    print(f"   ⚠️ HTTP {response.status_code} - Skipping")
                    continue
                
                working_categories += 1
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # 🔍 FIND ARTICLES USING ACTUAL HTML STRUCTURE
                found_on_page = 0
                
                # Look for category-description divs (from your HTML)
                description_divs = soup.find_all('div', class_='category-description')
                print(f"      Found {len(description_divs)} category-description divs")
                
                for desc in description_divs:
                    try:
                        h2 = desc.find('h2')
                        if not h2:
                            continue
                        
                        link = h2.find('a', href=True)
                        if not link:
                            continue
                        
                        href = link.get('href', '').strip()
                        title = link.get_text(strip=True)
                        
                        # Clean URL
                        if href.startswith('/'):
                            href = working_base + href
                        elif href.startswith('//'):
                            href = 'https:' + href
                        
                        if title and len(title) > 15 and href not in seen_urls:
                            articles.append({
                                'url': href,
                                'title': title[:250],
                                'category': cat_name
                            })
                            seen_urls.add(href)
                            found_on_page += 1
                            
                    except Exception as e:
                        continue
                
                # If no articles found with specific class, try general headlines
                if found_on_page == 0:
                    headlines = soup.find_all(['h2', 'h3'])
                    for h in headlines[:30]:
                        link = h.find('a', href=True)
                        if link:
                            href = link.get('href', '')
                            title = link.get_text(strip=True)
                            
                            if href.startswith('/'):
                                href = working_base + href
                            
                            if title and len(title) > 15 and href not in seen_urls:
                                articles.append({
                                    'url': href,
                                    'title': title[:250],
                                    'category': cat_name
                                })
                                seen_urls.add(href)
                                found_on_page += 1
                
                print(f"      ✅ Found {found_on_page} articles")
                
                if len(articles) >= 100:
                    break
                    
            except Exception as e:
                print(f"   ⚠️ Error: {str(e)[:100]}")
                continue
        
        time_taken = time.time() - start_time
        update_progress("Finding articles", len(categories), len(categories), 
                       f"✅ Found {len(articles)} articles from {working_categories} working categories")
        current_step += 1
        
        send_to_websocket(f"📊 Working categories: {working_categories}/{len(categories)}")
        return articles
    
    def check_duplicates(articles, request):
        """Check for existing articles"""
        nonlocal current_step
        try:
            from collect.models import AutoNewsArticle
            urls_to_check = [a['url'] for a in articles]
            duplicate_urls = []
            existing_articles = {}
            
            user = request.user if request.user.is_authenticated else None
            
            for i in range(0, len(urls_to_check), 20):
                batch = urls_to_check[i:i+20]
                existing = AutoNewsArticle.objects.filter(
                    url__in=batch,
                    created_by=user
                ).values('url', 'id')
                
                for item in existing:
                    duplicate_urls.append(item['url'])
                    existing_articles[item['url']] = item['id']
            
            if duplicate_urls:
                update_progress("Checking duplicates", 1, 1, f"⏭️ Found {len(duplicate_urls)} duplicates")
            else:
                update_progress("Checking duplicates", 1, 1, "✅ No duplicates found")
            
            current_step += 1
            return duplicate_urls, existing_articles
        except Exception as e:
            update_progress("Checking duplicates", 1, 1, f"⚠️ Skipping duplicate check: {str(e)[:50]}")
            current_step += 1
            return [], {}
    
    def fetch_article_content(article, session):
        """Fetch full article content"""
        try:
            time.sleep(DELAY * 0.5)
            response = session.get(article['url'], timeout=15)
            
            if response.status_code != 200:
                return None
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Get date
            pub_date = TODAY
            date_selectors = [
                "meta[property='article:published_time']",
                "meta[name='publish-date']",
                "time[datetime]",
                ".published-date",
                ".article-date",
                "span.date"
            ]
            
            for selector in date_selectors:
                elem = soup.select_one(selector)
                if elem:
                    date_str = elem.get('content', '') or elem.get('datetime', '') or elem.get_text(strip=True)
                    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', date_str)
                    if date_match:
                        try:
                            pub_date = datetime.strptime(date_match.group(1), '%Y-%m-%d')
                            if pub_date < TWO_DAYS_AGO:
                                return None
                            break
                        except:
                            pass
            
            # Get content
            content = ""
            content_selectors = [
                "div.news-content", "div.article-content", "article",
                ".main-content", ".story-content", "div[class*='content']",
                ".description", ".detail-box", ".editor-box"
            ]
            
            for selector in content_selectors:
                elem = soup.select_one(selector)
                if elem:
                    # Remove unwanted elements
                    for unwanted in elem.select('script, style, .ad, .advertisement, .related, .comments, .social-share, iframe'):
                        unwanted.decompose()
                    
                    paragraphs = elem.find_all('p')
                    if paragraphs:
                        text_parts = []
                        for p in paragraphs[:20]:
                            text = p.get_text(strip=True)
                            if len(text) > 30 and not text.startswith(('ADVERTISEMENT', 'SPONSORED', 'Related', 'Also read')):
                                text_parts.append(text)
                        
                        if text_parts:
                            content = ' '.join(text_parts)[:3000]
                            break
            
            if not content or len(content) < 200:
                # Try to get all paragraphs from the page
                all_paragraphs = soup.find_all('p')
                text_parts = [p.get_text(strip=True) for p in all_paragraphs[:30] 
                             if len(p.get_text(strip=True)) > 30]
                if text_parts:
                    content = ' '.join(text_parts)[:3000]
            
            if not content or len(content) < 200:
                return None
            
            # Get image
            image_url = ""
            img_selectors = [
                "meta[property='og:image']",
                "meta[name='twitter:image']",
                ".featured-image img",
                "article img",
                ".main-image img",
                "figure img"
            ]
            
            for selector in img_selectors:
                elem = soup.select_one(selector)
                if elem:
                    src = elem.get('content', '') or elem.get('src', '') or elem.get('data-src', '')
                    if src and 'http' in src:
                        image_url = src
                        break
            
            return {
                'url': article['url'],
                'title': article['title'],
                'content': content,
                'image_url': image_url,
                'date': pub_date.strftime('%Y-%m-%d'),
                'category': article.get('category', 'General')
            }
            
        except Exception as e:
            print(f"Error fetching {article['url'][:50]}: {str(e)[:100]}")
            return None
    
    def fetch_all_articles(articles, session):
        """Fetch all articles in parallel"""
        nonlocal current_step
        if not articles:
            current_step += 1
            return []
        
        update_progress("Fetching content", 0, len(articles))
        
        results = []
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_article = {executor.submit(fetch_article_content, article, session): article 
                               for article in articles}
            
            completed = 0
            for future in as_completed(future_to_article):
                completed += 1
                
                if completed % 5 == 0:
                    update_progress("Fetching content", completed, len(articles))
                
                result = future.result()
                if result:
                    results.append(result)
        
        time_taken = time.time() - start_time
        update_progress("Fetching content", len(articles), len(articles), 
                       f"✅ Fetched {len(results)} articles")
        current_step += 1
        return results
    
    def analyze_keywords_in_article(article, keyword_dict):
        """Find which keywords match in the article"""
        if not keyword_dict:
            return [], []
        
        text = (article['title'] + ' ' + article['content']).lower()
        found_keywords = []
        found_categories = set()
        
        for keyword, category in keyword_dict.items():
            if keyword.lower() in text:
                found_keywords.append(keyword)
                found_categories.add(category)
        
        return found_keywords[:10], list(found_categories)[:5]
    
    def filter_by_keywords(articles, keyword_dict):
        """Process ALL articles - KEEP EVERYTHING, just add keyword analysis"""
        nonlocal current_step
        update_progress("Keyword analysis", 0, len(articles))
        
        processed_articles = []
        start_time = time.time()
        keyword_match_count = 0
        
        for idx, article in enumerate(articles):
            found_keywords, categories = analyze_keywords_in_article(article, keyword_dict)
            
            # Set threat level based on keywords found
            if found_keywords:
                threat_level = "medium" if len(found_keywords) > 2 else "low"
                priority = "medium"
                keyword_match_count += 1
            else:
                # Default values for articles without keywords
                threat_level = "low"
                priority = "low"
            
            article['found_keywords'] = found_keywords
            article['categories'] = categories
            article['threat_level'] = threat_level
            article['priority'] = priority
            processed_articles.append(article)  # ← KEEP ALL ARTICLES
            
            if (idx + 1) % 10 == 0:
                update_progress("Keyword analysis", idx + 1, len(articles))
        
        time_taken = time.time() - start_time
        update_progress("Keyword analysis", len(articles), len(articles), 
                       f"✅ Processed {len(processed_articles)} articles ({keyword_match_count} with keywords)")
        current_step += 1
        return processed_articles
    
    def save_to_database(articles, request, existing_articles=None):
        """Save articles to database - CORRECTED FOR YOUR MODEL"""
        nonlocal current_step
        if existing_articles is None:
            existing_articles = {}
            
        try:
            from collect.models import AutoNewsArticle
            
            update_progress("Saving to DB", 0, len(articles), 
                           f"💾 Saving {len(articles)} articles to database...")
            
            saved_count = 0
            updated_count = 0
            duplicate_count = 0
            error_count = 0
            errors = []
            start_time = time.time()
            
            for idx, article in enumerate(articles):
                try:
                    user = request.user if request.user.is_authenticated else None
                    
                    # ✅ USE ONLY FIELDS THAT EXIST IN YOUR MODEL
                    title = article['title'][:500]
                    summary = article['content'][:1000] if article.get('content') else ""
                    url = article['url'][:1000]
                    image_url = article.get('image_url', '')[:1000] if article.get('image_url') else None
                    source = "kantipur"[:100]
                    date = article.get('date', TODAY.strftime('%Y-%m-%d'))[:20]
                    
                    content_length = len(article['content']) if article.get('content') else 0
                    priority = article.get('priority', 'medium')[:10]
                    threat_level = article.get('threat_level', 'low')[:10]
                    
                    # Store as JSON strings
                    keywords = json.dumps(article.get('found_keywords', []), ensure_ascii=False)
                    categories = json.dumps(article.get('categories', []), ensure_ascii=False)
                    
                    # Check if exists by URL
                    if url in existing_articles:
                        # Update existing
                        article_id = existing_articles[url]
                        existing = AutoNewsArticle.objects.get(id=article_id)
                        
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
                            
                    elif AutoNewsArticle.objects.filter(url=url, created_by=user).exists():
                        # Duplicate found via direct check
                        duplicate_count += 1
                        
                    else:
                        # Create new
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
                    
                except Exception as e:
                    error_count += 1
                    errors.append(str(e)[:100])
                
                # Update progress every 3 articles
                if (idx + 1) % 3 == 0 or (idx + 1) == len(articles):
                    progress_percent = ((idx + 1) / len(articles)) * 100
                    update_progress("Saving to DB", idx + 1, len(articles),
                                   f"💾 New: {saved_count} | Updated: {updated_count} | Duplicates: {duplicate_count} | Errors: {error_count}")
            
            time_taken = time.time() - start_time
            update_progress("Saving to DB", len(articles), len(articles),
                           f"✅ New: {saved_count} | Updated: {updated_count} | Duplicates: {duplicate_count} | Errors: {error_count} | Total: {saved_count + updated_count}/{len(articles)} in {time_taken:.1f}s")
            current_step += 1
            return saved_count, updated_count, duplicate_count, error_count, errors
            
        except Exception as e:
            update_progress("Saving to DB", 1, 1, f"❌ Database error: {str(e)[:50]}")
            current_step += 1
            return 0, 0, 0, len(articles), [str(e)]
    
    # MAIN EXECUTION
    try:
        overall_start = time.time()
        
        send_to_websocket("=" * 60)
        send_to_websocket("🚀 STARTING KANTIPUR DAILY SCRAPER")
        send_to_websocket(f"👤 User: {request.user.username if request.user.is_authenticated else 'Unknown'}")
        send_to_websocket(f"📅 Date range: Last 4 days")
        send_to_websocket("=" * 60)
        
        # 1. Get keywords
        keyword_list, keyword_dict = get_user_keywords(request)
        send_to_websocket(f"🔑 Loaded {len(keyword_dict)} keywords")
        
        # 2. Create session
        update_progress("Creating session", 1, 1)
        session = create_session()
        current_step += 1
        
        # 3. Find articles
        article_links = find_article_links(session)
        if not article_links:
            send_to_websocket("❌ No articles found")
            return json.dumps({
                "metadata": {"status": "success", "message": "No articles found"},
                "articles": []
            })
        
        send_to_websocket(f"📊 Found {len(article_links)} total articles")
        
        # 4. Check duplicates
        duplicate_urls, existing_articles = check_duplicates(article_links, request)
        
        # 5. Fetch content (only new articles)
        articles_to_fetch = [a for a in article_links if a['url'] not in duplicate_urls]
        send_to_websocket(f"📊 Fetching {len(articles_to_fetch)} new articles...")
        
        articles_with_content = fetch_all_articles(articles_to_fetch, session)
        send_to_websocket(f"📊 Successfully fetched {len(articles_with_content)} articles with content")
        
        # 6. Process ALL articles (keep everything, just add keyword analysis)
        processed_articles = filter_by_keywords(articles_with_content, keyword_dict) if articles_with_content else []
        
        # Count articles with keywords for reporting
        articles_with_keywords = sum(1 for a in processed_articles if a.get('found_keywords'))
        
        # 7. Save to database
        saved_count = 0
        updated_count = 0
        duplicate_count = 0
        error_count = 0
        errors = []
        
        if processed_articles:
            saved_count, updated_count, duplicate_count, error_count, errors = save_to_database(
                processed_articles, request, existing_articles
            )
        else:
            send_to_websocket("⚠️ No articles to save")
        
        # Prepare final response
        final_articles = []
        for idx, article in enumerate(processed_articles):
            final_articles.append({
                'id': idx + 1,
                'title': article['title'],
                'url': article['url'],
                'summary': article['content'][:300] + "..." if len(article['content']) > 300 else article['content'],
                'date': article['date'],
                'category': article.get('category', 'General'),
                'image_url': article.get('image_url', ''),
                'content_length': len(article['content']),
                'keywords': article.get('found_keywords', [])[:5],
                'categories': article.get('categories', [])[:3],
                'threat_level': article.get('threat_level', 'low'),
                'priority': article.get('priority', 'medium'),
                'source': 'Kantipur Daily',
                'has_keywords': len(article.get('found_keywords', [])) > 0,
                'keyword_count': len(article.get('found_keywords', [])),
                'category_count': len(article.get('categories', []))
            })
        
        # FINAL SUMMARY
        total_time = round(time.time() - overall_start, 2)
        
        send_to_websocket("=" * 60)
        send_to_websocket("🎯 KANTIPUR SCRAPING COMPLETE - FINAL SUMMARY")
        send_to_websocket(f"⏱️ Total time: {total_time}s")
        send_to_websocket(f"📊 Articles found: {len(article_links)}")
        send_to_websocket(f"📊 Existing in DB: {len(duplicate_urls)}")
        send_to_websocket(f"📊 New articles fetched: {len(articles_with_content)}")
        send_to_websocket(f"📊 Total processed: {len(processed_articles)}")
        send_to_websocket(f"🔑 Articles WITH keywords: {articles_with_keywords}")
        send_to_websocket(f"📄 Articles WITHOUT keywords: {len(processed_articles) - articles_with_keywords}")
        send_to_websocket(f"💾 New saves: {saved_count}")
        send_to_websocket(f"🔄 Updates: {updated_count}")
        send_to_websocket(f"⏭️ Duplicates skipped: {duplicate_count}")
        send_to_websocket(f"❌ Errors: {error_count}")
        send_to_websocket(f"🔑 Keywords used: {len(keyword_dict)}")
        
        if processed_articles:
            # Category distribution
            categories_count = {}
            for article in processed_articles:
                category = article.get('category', 'General')
                categories_count[category] = categories_count.get(category, 0) + 1
            
            send_to_websocket(f"📑 Categories found: {len(categories_count)}")
            
            # Show top 5 categories
            top_categories = sorted(categories_count.items(), key=lambda x: x[1], reverse=True)[:5]
            for cat, count in top_categories:
                send_to_websocket(f"   - {cat}: {count} articles")
        
        send_to_websocket("✅ All steps completed successfully!")
        send_to_websocket("=" * 60)
        
        return json.dumps({
            "metadata": {
                "status": "success",
                "source": "kantipur",
                "total_links": len(article_links),
                "existing_in_db": len(duplicate_urls),
                "articles_with_content": len(articles_with_content),
                "total_processed": len(processed_articles),
                "articles_with_keywords": articles_with_keywords,
                "articles_without_keywords": len(processed_articles) - articles_with_keywords,
                "saved_to_db": saved_count,
                "updated_in_db": updated_count,
                "duplicates_skipped": duplicate_count,
                "errors": error_count,
                "time_taken": total_time,
                "user_keywords_count": len(keyword_dict),
                "user": request.user.username if request.user.is_authenticated else "unknown",
                "scraped_at": datetime.now().isoformat()
            },
            "articles": final_articles,
            "database_results": {
                "saved": saved_count,
                "updated": updated_count,
                "duplicates": duplicate_count,
                "errors": errors[:5] if errors else []
            }
        }, ensure_ascii=False)
        
    except Exception as e:
        send_to_websocket(f"❌ CRITICAL ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return json.dumps({
            "metadata": {
                "status": "error",
                "source": "kantipur",
                "message": str(e),
                "time_taken": round(time.time() - global_start_time, 2),
                "scraped_at": datetime.now().isoformat()
            },
            "articles": []
        })


def fetch_kantipur_news(request):
    """
    Main function to call from your keyboard view
    """
    try:
        result_json = keyboard_kantipur_to_json(request)
        result_data = json.loads(result_json)
        
        return {
            "status": result_data["metadata"]["status"],
            "message": result_data["metadata"].get("message", "Kantipur fetch completed"),
            "stats": {
                "saved": result_data["metadata"].get("saved_to_db", 0),
                "updated": result_data["metadata"].get("updated_in_db", 0),
                "skipped": result_data["metadata"].get("existing_in_db", 0),
                "duplicates": result_data["metadata"].get("duplicates_skipped", 0),
                "errors": result_data["metadata"].get("errors", 0),
                "articles_with_keywords": result_data["metadata"].get("articles_with_keywords", 0),
                "articles_without_keywords": result_data["metadata"].get("articles_without_keywords", 0),
                "total_processed": result_data["metadata"].get("total_processed", 0)
            },
            "data": result_data
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error in fetch_kantipur_news: {str(e)}"
        }