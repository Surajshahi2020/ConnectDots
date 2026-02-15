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
import hashlib
from utils.websocket_helper import send_to_websocket


def keyboard_kathmandu_post_to_json(request):
    """Main function for Kathmandu Post scraper with WebSocket support"""
    base_url = "https://kathmandupost.com"
    send_to_websocket(f"🌐 Visiting site: {base_url}")
    
    # --------------------------------------------------------------------------
    # Time settings
    TODAY = datetime.now()
    TWO_DAYS_AGO = TODAY - timedelta(days=4)
    
    # Settings
    DELAY = 3
    MAX_WORKERS = 4
    TOTAL_STEPS = 7
    
    # Track overall progress
    global_start_time = time.time()
    current_step = 1
    
    def update_progress(step_name, current, total=None, custom_message=None):
        """Update progress with percentage and time estimation"""
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
        """Get keywords from DangerousKeyword table"""
        try:
            update_progress("Loading keywords", 1, 1, "🔑 Fetching saved keywords from database...")
            
            from collect.models import DangerousKeyword
            
            if not request.user.is_authenticated:
                return [], {}
            
            keywords = DangerousKeyword.objects.filter(
                is_active=True, 
                created_by=request.user
            )
            
            keyword_dict = {}
            for kw in keywords:
                keyword_dict[kw.word.lower().strip()] = kw.category.strip()
            
            keyword_list = list(keyword_dict.keys())
            update_progress("Keywords loaded", 1, 1, f"✅ Loaded {len(keyword_list)} keywords")
            return keyword_list, keyword_dict
            
        except Exception as e:
            update_progress("Keywords error", 1, 1, f"⚠️ Using fallback keywords: {str(e)[:50]}")
            fallback = {
                'security': 'Security', 'army': 'Military', 'military': 'Military', 'police': 'Police',
                'defense': 'Defense', 'terrorism': 'Terrorism', 'attack': 'Violence', 'crime': 'Crime',
                'murder': 'Violence', 'bomb': 'Terrorism', 'protest': 'Protest', 'cyber': 'Cyber_Security'
            }
            return list(fallback.keys()), fallback
    
    def create_session():
        """Create HTTP session"""
        session = requests.Session()
        retry = Retry(total=3, backoff_factor=1)
        adapter = HTTPAdapter(max_retries=retry, pool_connections=10)
        session.mount('https://', adapter)
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        })
        return session
    
    def extract_articles_from_page(soup, category_name):
        """Extract articles from a category page based on Kathmandu Post structure"""
        articles = []
        
        # Look for article containers - Kathmandu Post specific
        article_containers = soup.find_all(['article', 'div'], class_=re.compile(r'card|block|item|article|post', re.I))
        
        for container in article_containers:
            try:
                # Find link
                link = container.find('a', href=True)
                if not link:
                    continue
                
                href = link.get('href', '').strip()
                if not href:
                    continue
                
                # Clean URL
                if href.startswith('//'):
                    href = 'https:' + href
                elif href.startswith('/'):
                    href = base_url + href
                elif not href.startswith('http'):
                    continue
                
                # Filter URLs
                if any(x in href.lower() for x in ['/category/', '/tag/', '/author/', '/page/', '?', '#']):
                    continue
                
                # Get title
                title = link.get_text(strip=True)
                if not title or len(title) < 15:
                    heading = container.find(['h1', 'h2', 'h3', 'h4'])
                    if heading:
                        title = heading.get_text(strip=True)
                
                if title and len(title) >= 15:
                    # Get image if available
                    image_url = ""
                    img = container.find('img')
                    if img:
                        image_url = img.get('src') or img.get('data-src') or ''
                    
                    # Get summary/excerpt
                    summary = ""
                    p_tag = container.find('p')
                    if p_tag:
                        summary = p_tag.get_text(strip=True)[:300]
                    
                    articles.append({
                        'url': href,
                        'title': title[:250],
                        'category': category_name,
                        'image_url': image_url,
                        'summary': summary
                    })
                    
            except Exception:
                continue
        
        return articles
    
    def find_article_links(session):
        """Find article links from Kathmandu Post"""
        nonlocal current_step
        update_progress("Finding articles", 0, 1, "🔍 Searching for articles...")
        
        categories = [
            "/national", "/politics", "/valley", "/crime", "/money",
            "/sports", "/health", "/education", "/science-technology",
            "/art-culture", "/opinion", "/blog", "/interview"
        ]
        
        articles = []
        seen_urls = set()
        start_time = time.time()
        
        for idx, category in enumerate(categories):
            try:
                update_progress(f"Checking {category.strip('/')}", idx + 1, len(categories))
                
                url = base_url + category
                time.sleep(DELAY)
                response = session.get(url, timeout=15)
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'html.parser')
                    page_articles = extract_articles_from_page(soup, category.strip('/'))
                    
                    new_articles = 0
                    for article in page_articles:
                        if article['url'] not in seen_urls:
                            seen_urls.add(article['url'])
                            articles.append(article)
                            new_articles += 1
                    
                    print(f"      Found {new_articles} new articles in {category}")
                    
                    if len(articles) >= 60:
                        break
                
            except Exception as e:
                print(f"Error in category {category}: {str(e)[:100]}")
                continue
        
        time_taken = time.time() - start_time
        update_progress("Finding articles", len(categories), len(categories), 
                       f"✅ Found {len(articles)} articles")
        current_step += 1
        return articles
    
    def check_duplicates(articles, request):
        """Check for existing articles in database and return existing IDs"""
        nonlocal current_step
        update_progress("Checking duplicates", 0, 1, "🔍 Checking for duplicates...")
        
        try:
            from collect.models import AutoNewsArticle
            
            urls_to_check = [a['url'] for a in articles]
            duplicate_urls = []
            existing_articles = {}
            
            # Check in batches
            for i in range(0, len(urls_to_check), 20):
                batch = urls_to_check[i:i+20]
                existing = AutoNewsArticle.objects.filter(
                    url__in=batch,
                    created_by=request.user
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
    
    def format_date_from_url(url):
        """Extract and format date from Kathmandu Post URL"""
        try:
            parts = url.split('/')
            if len(parts) >= 5:
                year, month, day = parts[2], parts[3], parts[4]
                date_obj = datetime.strptime(f"{year}-{month}-{day}", "%Y-%m-%d")
                return date_obj
        except:
            pass
        return None
    
    def fetch_article_content(article, session):
        """Fetch content for a single Kathmandu Post article"""
        try:
            time.sleep(DELAY * 0.5)
            response = session.get(article['url'], timeout=12)
            
            if response.status_code != 200:
                return None
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Get date from URL or page
            pub_date = format_date_from_url(article['url'])
            
            if not pub_date:
                date_elem = soup.select_one('time, .published-date, .article-date, meta[property="article:published_time"]')
                if date_elem:
                    date_str = date_elem.get('datetime', '') or date_elem.get('content', '') or date_elem.get_text(strip=True)
                    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', date_str)
                    if date_match:
                        try:
                            pub_date = datetime.strptime(date_match.group(1), '%Y-%m-%d')
                        except:
                            pass
            
            # Filter by date
            if pub_date and pub_date < TWO_DAYS_AGO:
                return None
            
            # Get content
            content = ""
            content_selectors = [
                "div[class*='content']", "article div.text", ".description",
                ".article-content", ".story-content", ".news-content",
                "div.detail-content", ".main-content", "article"
            ]
            
            for selector in content_selectors:
                elem = soup.select_one(selector)
                if elem:
                    # Remove unwanted elements
                    for unwanted in elem.select('.advertisement, .related-news, .comments, script, style, .social-share'):
                        unwanted.decompose()
                    
                    paragraphs = elem.find_all('p')
                    if paragraphs:
                        text_parts = []
                        for p in paragraphs[:20]:
                            text = p.get_text(strip=True)
                            if len(text) > 30 and not text.startswith(('ADVERTISEMENT', 'SPONSORED')):
                                text_parts.append(text)
                        
                        if text_parts:
                            content = ' '.join(text_parts)[:2500]
                            break
            
            if not content or len(content) < 150:
                return None
            
            # Get image
            image_url = article.get('image_url', '')
            if not image_url:
                img_selectors = [
                    "meta[property='og:image']",
                    "meta[name='twitter:image']",
                    ".article-image img",
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
                'date': pub_date.strftime('%Y-%m-%d') if pub_date else TODAY.strftime('%Y-%m-%d'),
                'category': article.get('category', 'General'),
                'summary': article.get('summary', '')
            }
            
        except Exception as e:
            print(f"Error fetching article {article['url'][:50]}: {str(e)[:100]}")
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
        
        update_progress("Fetching content", len(articles), len(articles), 
                       f"✅ Fetched {len(results)} articles")
        current_step += 1
        return results
    
    def analyze_security_threat(content, keyword_dict):
        """Analyze security threat level based on content and user keywords"""
        content_lower = content.lower()
        
        # Security keywords
        security_keywords = {
            'terrorism': 'Terrorism', 'terrorist': 'Terrorism', 'bomb': 'Terrorism', 'explosion': 'Terrorism',
            'murder': 'Violence', 'killing': 'Violence', 'shooting': 'Violence', 'attack': 'Violence',
            'police': 'Police', 'arrest': 'Police', 'investigation': 'Police',
            'army': 'Military', 'military': 'Military', 'soldier': 'Military',
            'protest': 'Protest', 'strike': 'Protest', 'riot': 'Protest',
            'cyber': 'Cyber_Security', 'hack': 'Cyber_Security', 'breach': 'Cyber_Security'
        }
        
        found_keywords = []
        found_categories = set()
        
        # Check security keywords
        for keyword, category in security_keywords.items():
            if keyword in content_lower:
                found_keywords.append(keyword)
                found_categories.add(category)
        
        # Check user keywords
        if keyword_dict:
            for keyword, category in keyword_dict.items():
                if keyword.lower() in content_lower:
                    found_keywords.append(keyword)
                    found_categories.add(category)
        
        # Determine threat level
        threat_level = "low"
        priority = "low"
        
        critical_terms = {'terrorism', 'bomb', 'explosion', 'mass shooting', 'assassination'}
        high_terms = {'murder', 'killing', 'shooting', 'attack', 'kidnapping', 'hostage', 'riot'}
        
        if any(term in content_lower for term in critical_terms):
            threat_level = "critical"
            priority = "high"
        elif any(term in content_lower for term in high_terms):
            threat_level = "high"
            priority = "high"
        elif found_keywords:
            threat_level = "medium"
            priority = "medium"
        
        return {
            'found_keywords': list(set(found_keywords))[:10],
            'categories': list(found_categories)[:5],
            'threat_level': threat_level,
            'priority': priority
        }
    
    def filter_by_keywords(articles, keyword_dict):
        """Filter articles by keywords and security analysis"""
        nonlocal current_step
        update_progress("Keyword analysis", 0, len(articles))
        
        filtered = []
        
        for idx, article in enumerate(articles):
            full_text = article['title'] + ' ' + article['content']
            analysis = analyze_security_threat(full_text, keyword_dict)
            
            if analysis['found_keywords']:
                article['found_keywords'] = analysis['found_keywords']
                article['categories'] = analysis['categories']
                article['threat_level'] = analysis['threat_level']
                article['priority'] = analysis['priority']
                filtered.append(article)
            
            if (idx + 1) % 5 == 0:
                update_progress("Keyword analysis", idx + 1, len(articles))
        
        update_progress("Keyword analysis", len(articles), len(articles), 
                       f"✅ Keyword matches: {len(filtered)} articles")
        current_step += 1
        return filtered
    
    def save_to_database(articles, request, existing_articles=None):
        """Save articles to database with duplicate prevention"""
        nonlocal current_step
        if existing_articles is None:
            existing_articles = {}
            
        try:
            from collect.models import AutoNewsArticle
            
            update_progress("Saving to DB", 0, len(articles))
            
            saved_count = 0
            updated_count = 0
            error_count = 0
            errors = []
            
            for idx, article in enumerate(articles):
                try:
                    user = request.user if request.user.is_authenticated else None
                    
                    # Prepare data according to your model
                    title = article['title'][:500]
                    summary = article['content'][:1000]  # Use content as summary
                    url = article['url'][:1000]
                    image_url = article.get('image_url', '')[:1000] if article.get('image_url') else None
                    source = "kathmandu_post"[:100]
                    date = article.get('date', TODAY.strftime('%Y-%m-%d'))[:20]
                    
                    content_length = len(article['content'])
                    priority = article.get('priority', 'medium')[:10]
                    threat_level = article.get('threat_level', 'low')[:10]
                    
                    # Store as JSON strings
                    keywords = json.dumps(article.get('found_keywords', []), ensure_ascii=False)
                    categories = json.dumps(article.get('categories', []), ensure_ascii=False)
                    
                    # Check if exists
                    if article['url'] in existing_articles:
                        # Update existing
                        article_id = existing_articles[article['url']]
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
                
                if (idx + 1) % 3 == 0:
                    update_progress("Saving to DB", idx + 1, len(articles))
            
            update_progress("Saving to DB", len(articles), len(articles), 
                           f"✅ New: {saved_count} | Updated: {updated_count} | Errors: {error_count}")
            current_step += 1
            return saved_count, updated_count, error_count, errors
            
        except Exception as e:
            update_progress("Saving to DB", 1, 1, f"❌ Database error: {str(e)[:50]}")
            current_step += 1
            return 0, 0, len(articles), [str(e)]
    
    # MAIN EXECUTION
    try:
        print("\n" + "=" * 60)
        send_to_websocket("🚀 STARTING KATHMANDU POST SCRAPER")
        send_to_websocket(f"👤 User: {request.user.username if request.user.is_authenticated else 'Unknown'}")
        send_to_websocket(f"📅 Date range: Last 4 days")
        send_to_websocket("=" * 60)
        
        overall_start = time.time()
        
        # 1. Get keywords
        keyword_list, keyword_dict = get_user_keywords(request)
        
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
        
        # 4. Check duplicates
        duplicate_urls, existing_articles = check_duplicates(article_links, request)
        
        # 5. Fetch content
        articles_to_fetch = [a for a in article_links if a['url'] not in duplicate_urls]
        articles_with_content = fetch_all_articles(articles_to_fetch, session)
        
        # 6. Filter by keywords
        filtered_articles = filter_by_keywords(articles_with_content, keyword_dict) if articles_with_content else []
        
        # 7. Save to database
        saved_count, updated_count, error_count, errors = save_to_database(
            filtered_articles, request, existing_articles
        ) if filtered_articles else (0, 0, 0, [])
        
        # Prepare final response
        final_articles = []
        for idx, article in enumerate(filtered_articles):
            final_articles.append({
                'id': idx + 1,
                'title': article['title'],
                'url': article['url'],
                'summary': article['content'][:300] + "...",
                'date': article['date'],
                'category': article.get('category', 'General'),
                'image_url': article.get('image_url', ''),
                'content_length': len(article['content']),
                'keywords': article.get('found_keywords', [])[:5],
                'categories': article.get('categories', [])[:3],
                'threat_level': article.get('threat_level', 'low'),
                'priority': article.get('priority', 'medium'),
                'source': 'Kathmandu Post'
            })
        
        # Final summary
        total_time = round(time.time() - overall_start, 2)
        
        send_to_websocket("=" * 60)
        send_to_websocket("🎯 KATHMANDU POST SCRAPING COMPLETE")
        send_to_websocket(f"⏱️ Total time: {total_time}s")
        send_to_websocket(f"📊 Articles found: {len(article_links)}")
        send_to_websocket(f"📊 Existing in DB: {len(duplicate_urls)}")
        send_to_websocket(f"📊 New articles fetched: {len(articles_with_content)}")
        send_to_websocket(f"🔒 Security articles: {len(filtered_articles)}")
        send_to_websocket(f"💾 New saves: {saved_count}")
        send_to_websocket(f"🔄 Updates: {updated_count}")
        send_to_websocket(f"❌ Errors: {error_count}")
        send_to_websocket(f"🔑 Keywords used: {len(keyword_dict)}")
        send_to_websocket("=" * 60)
        
        return json.dumps({
            "metadata": {
                "status": "success",
                "source": "kathmandu_post",
                "total_links": len(article_links),
                "existing_in_db": len(duplicate_urls),
                "articles_with_content": len(articles_with_content),
                "security_articles": len(filtered_articles),
                "saved_to_db": saved_count,
                "updated_in_db": updated_count,
                "errors": error_count,
                "time_taken": total_time,
                "user_keywords_count": len(keyword_dict),
                "user": request.user.username if request.user.is_authenticated else "unknown",
                "scraped_at": datetime.now().isoformat()
            },
            "articles": final_articles
        }, ensure_ascii=False)
        
    except Exception as e:
        send_to_websocket(f"❌ CRITICAL ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return json.dumps({
            "metadata": {
                "status": "error",
                "source": "kathmandu_post",
                "message": str(e),
                "time_taken": round(time.time() - global_start_time, 2)
            },
            "articles": []
        })


def fetch_kathmandu_post_news(request):
    """Main function to call from your keyboard view"""
    try:
        result_json = keyboard_kathmandu_post_to_json(request)
        result_data = json.loads(result_json)
        
        return {
            "status": result_data["metadata"]["status"],
            "message": result_data["metadata"].get("message", "Kathmandu Post fetch completed"),
            "stats": {
                "saved": result_data["metadata"].get("saved_to_db", 0),
                "updated": result_data["metadata"].get("updated_in_db", 0),
                "skipped": result_data["metadata"].get("existing_in_db", 0),
                "errors": result_data["metadata"].get("errors", 0),
                "security_articles": result_data["metadata"].get("security_articles", 0),
                "total_processed": result_data["metadata"].get("articles_with_content", 0)
            },
            "data": result_data
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error in fetch_kathmandu_post_news: {str(e)}"
        }