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


def keyboard_nagariknews_to_json(request):
    base_url = "https://nagariknews.nagariknetwork.com"
    send_to_websocket(f"🌐 Visiting site: {base_url}")
    
    # --------------------------------------------------------------------------Change fetching time-------------------------------------------------------------
    TODAY = datetime.now()
    TWO_DAYS_AGO = TODAY - timedelta(days=2)
    
    # Settings
    DELAY = 4
    MAX_WORKERS = 3
    TOTAL_STEPS = 7  # Total steps in the scraping process
    
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
        step_progress = (current_step / TOTAL_STEPS) * 100
        
        if total and current > 0:
            item_progress = (current / total) * 100
            message = f"📊 Step {current_step}/{TOTAL_STEPS}: {step_name} ({current}/{total} - {item_progress:.1f}%)"
        else:
            message = f"📊 Step {current_step}/{TOTAL_STEPS}: {step_name}"
        
        message += f" | Total progress: {step_progress:.1f}% | Elapsed: {elapsed:.1f}s"
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
            update_progress("Keywords loaded", 1, 1, f"✅ Loaded {len(keyword_list)} keywords for user")
            return keyword_list, keyword_dict
            
        except Exception as e:
            update_progress("Keywords error", 1, 1, f"⚠️ Using fallback keywords: {str(e)[:50]}")
            # Fallback keywords if DB fails
            fallback = {
                'चुनाव': 'Election', 'मतदान': 'Election', 'राजनीति': 'Politics',
                'election': 'Election', 'vote': 'Election', 'politics': 'Politics'
            }
            return list(fallback.keys()), fallback
    
    def create_session():
        """Create HTTP session"""
        session = requests.Session()
        retry = Retry(total=2, backoff_factor=1)
        adapter = HTTPAdapter(max_retries=retry, pool_connections=10)
        session.mount('https://', adapter)
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
            "Accept": "text/html,application/xhtml+xml",
        })
        return session
    
    def find_article_links(session):
        """Find article links from political sections"""
        nonlocal current_step
        update_progress("Finding articles", 0, 1, "🔍 Searching for articles in political sections...")
        # --------------------------------------------------------------------------Change fetching category-------------------------------------------------------------
        categories = [
            "/politics", "/trending/election-nepal", "/trending/Chunabi-Charcha", 
            "/main-news", "/photo-feature", "/blog", "/interview", "/opinion", "cartoon", "Bazar", "others"
        ]
        
        articles = []
        seen_urls = set()
        start_time = time.time()
        
        for idx, category in enumerate(categories):
            try:
                # Update category progress
                cat_progress = ((idx + 1) / len(categories)) * 100
                update_progress(
                    "Finding articles", 
                    idx + 1, 
                    len(categories),
                    f"📂 Checking category {idx+1}/{len(categories)}: {category} ({cat_progress:.1f}%)"
                )
                
                url = base_url + category
                time.sleep(DELAY)
                response = session.get(url, timeout=10)
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'html.parser')
                    
                    for link in soup.find_all('a', href=True):
                        href = link.get('href', '').strip()
                        if not href:
                            continue
                        
                        # Normalize URL
                        if href.startswith('//'):
                            href = 'https:' + href
                        elif href.startswith('/'):
                            href = base_url + href
                        
                        # Filter URLs
                        if ('nagariknetwork.com' not in href or
                            any(x in href.lower() for x in ['category', 'tag', 'author']) or
                            href in seen_urls):
                            continue
                        
                        # Get title
                        title = link.get_text(strip=True)
                        if len(title) < 10:
                            parent = link.find_parent(['h1', 'h2', 'h3', 'h4'])
                            if parent:
                                title = parent.get_text(strip=True)
                        
                        if len(title) >= 10:
                            articles.append({'url': href, 'title': title[:200]})
                            seen_urls.add(href)
                            
                            if len(articles) >= 50:  # Limit
                                time_taken = time.time() - start_time
                                update_progress("Finding articles", len(categories), len(categories), 
                                              f"✅ Found {len(articles)} articles in {time_taken:.1f}s")
                                return articles
                
            except Exception:
                continue
        
        time_taken = time.time() - start_time
        update_progress("Finding articles", len(categories), len(categories), 
                       f"✅ Found {len(articles)} articles in {time_taken:.1f}s")
        current_step += 1
        return articles
    
    def check_duplicates(articles, request):
        """Check for existing articles in database and return existing IDs"""
        nonlocal current_step
        update_progress("Checking duplicates", 0, 1, "🔍 Checking for duplicate articles in database...")
        
        try:
            from collect.models import AutoNewsArticle
            
            urls_to_check = [a['url'] for a in articles]
            duplicate_urls = []
            existing_articles = {}
            
            # Check in batches
            total_batches = (len(urls_to_check) + 9) // 10
            for i in range(0, len(urls_to_check), 10):
                batch_num = i // 10 + 1
                batch = urls_to_check[i:i+10]
                
                batch_progress = (batch_num / total_batches) * 100
                update_progress("Checking duplicates", batch_num, total_batches,
                               f"📋 Checking batch {batch_num}/{total_batches} ({batch_progress:.1f}%)")
                
                existing = AutoNewsArticle.objects.filter(
                    url__in=batch,
                    created_by=request.user
                ).values('url', 'id')
                
                for item in existing:
                    duplicate_urls.append(item['url'])
                    existing_articles[item['url']] = item['id']
            
            if duplicate_urls:
                update_progress("Checking duplicates", total_batches, total_batches,
                               f"⏭️ Found {len(duplicate_urls)} duplicates in database")
            else:
                update_progress("Checking duplicates", total_batches, total_batches,
                               "✅ No duplicates found")
            
            current_step += 1
            return duplicate_urls, existing_articles
            
        except Exception as e:
            update_progress("Checking duplicates", 1, 1, f"⚠️ Skipping duplicate check: {str(e)[:50]}")
            current_step += 1
            return [], {}
    
    def fetch_article_content(article, session, article_num, total_articles):
        """Fetch content for a single article"""
        try:
            time.sleep(DELAY * 0.7)
            response = session.get(article['url'], timeout=10)
            
            if response.status_code != 200:
                return None
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Get date
            pub_date = None
            for selector in ["meta[property='article:published_time']", "time[datetime]"]:
                elem = soup.select_one(selector)
                if elem:
                    date_str = elem.get('content', '') or elem.get('datetime', '')
                    if date_str:
                        try:
                            match = re.search(r'(\d{4}-\d{2}-\d{2})', date_str)
                            if match:
                                pub_date = datetime.strptime(match.group(1), '%Y-%m-%d')
                                if pub_date < TWO_DAYS_AGO:
                                    return None
                                break
                        except:
                            continue
            
            # Get content
            content = ""
            for selector in ["div.news-content", "div.article-content", "article"]:
                elem = soup.select_one(selector)
                if elem:
                    paragraphs = elem.find_all('p')
                    if paragraphs:
                        text_parts = [p.get_text(strip=True) for p in paragraphs[:15] 
                                     if len(p.get_text(strip=True)) > 30]
                        if text_parts:
                            content = ' '.join(text_parts)[:2000]
                            break
            
            if not content or len(content) < 100:
                return None
            
            # Get image
            image_url = ""
            for selector in ["meta[property='og:image']", "img.wp-post-image"]:
                elem = soup.select_one(selector)
                if elem:
                    src = elem.get('content', '') or elem.get('src', '')
                    if src and 'http' in src:
                        image_url = src
                        break
            
            # Generate content hash for duplicate checking
            content_hash = hashlib.md5(content[:1000].encode()).hexdigest()
            
            # Get category from URL or content
            category = "General"
            url_parts = article['url'].split('/')
            if len(url_parts) >= 4:
                possible_category = url_parts[3]
                if possible_category in ['politics', 'main-news', 'opinion', 'blog', 'interview']:
                    category = possible_category.capitalize()
            
            return {
                'url': article['url'],
                'title': article['title'],
                'content': content,
                'image_url': image_url,
                'date': pub_date.strftime('%Y-%m-%d') if pub_date else TODAY.strftime('%Y-%m-%d'),
                'category': category,
                'content_hash': content_hash
            }
            
        except Exception:
            return None
    
    def fetch_all_articles(articles, session):
        """Fetch all articles in parallel"""
        nonlocal current_step
        if not articles:
            current_step += 1
            return []
        
        update_progress("Fetching content", 0, len(articles), 
                       f"📥 Fetching content for {len(articles)} articles...")
        
        results = []
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {}
            for idx, article in enumerate(articles):
                future = executor.submit(fetch_article_content, article, session, idx + 1, len(articles))
                futures[future] = article
            
            completed = 0
            for future in as_completed(futures):
                completed += 1
                
                # Calculate progress
                progress_percent = (completed / len(articles)) * 100
                elapsed_batch = time.time() - start_time
                avg_time_per_article = elapsed_batch / completed if completed > 0 else 0
                articles_left = len(articles) - completed
                est_time_left = avg_time_per_article * articles_left
                
                if completed % 5 == 0 or completed == len(articles):
                    update_progress(
                        "Fetching content", 
                        completed, 
                        len(articles),
                        f"📄 Article {completed}/{len(articles)} ({progress_percent:.1f}%) | "
                        f"ETA: {est_time_left:.1f}s remaining"
                    )
                
                result = future.result()
                if result:
                    results.append(result)
        
        time_taken = time.time() - start_time
        update_progress("Fetching content", len(articles), len(articles),
                       f"✅ Fetched {len(results)}/{len(articles)} articles in {time_taken:.1f}s")
        current_step += 1
        return results
    
    def analyze_keywords_in_article(article, keyword_dict):
        """Find which keywords match in the article"""
        text = (article['title'] + ' ' + article['content']).lower()
        found_keywords = []
        found_categories = set()
        
        for keyword, category in keyword_dict.items():
            if keyword in text:
                found_keywords.append(keyword)
                found_categories.add(category)
                if len(found_keywords) >= 10:  # Limit
                    break
        
        return found_keywords, list(found_categories)
    
    def filter_by_keywords(articles, keyword_dict):
        """Filter articles by keywords and return analyzed results"""
        nonlocal current_step
        if not keyword_dict:
            update_progress("Keyword analysis", 1, 1, "⚠️ No keywords found - returning all articles")
            current_step += 1
            # If no keywords, return all articles with empty analysis
            for article in articles:
                article['found_keywords'] = []
                article['categories'] = []
                article['threat_level'] = "low"
                article['priority'] = "low"
            return articles
        
        update_progress("Keyword analysis", 0, len(articles), 
                       f"🔍 Analyzing {len(articles)} articles for keyword matches...")
        
        filtered = []
        start_time = time.time()
        
        for idx, article in enumerate(articles):
            found_keywords, categories = analyze_keywords_in_article(article, keyword_dict)
            
            if found_keywords:  # Only include if keywords matched
                # Determine threat level
                threat_level = "low"
                if any(cat in ['Violence', 'Terrorism'] for cat in categories):
                    threat_level = "high"
                elif any(cat in ['Crime', 'Political_Unrest'] for cat in categories):
                    threat_level = "medium"
                
                # Determine priority
                priority = "medium" if threat_level == "low" else "high"
                
                article['found_keywords'] = found_keywords
                article['categories'] = categories
                article['threat_level'] = threat_level
                article['priority'] = priority
                filtered.append(article)
            
            # Update progress every 5 articles
            if (idx + 1) % 5 == 0 or (idx + 1) == len(articles):
                progress_percent = ((idx + 1) / len(articles)) * 100
                update_progress("Keyword analysis", idx + 1, len(articles),
                               f"🔑 Analyzed {idx + 1}/{len(articles)} articles ({progress_percent:.1f}%)")
        
        time_taken = time.time() - start_time
        update_progress("Keyword analysis", len(articles), len(articles),
                       f"✅ Keyword matches: {len(filtered)}/{len(articles)} in {time_taken:.1f}s")
        current_step += 1
        return filtered
    
    def save_to_database(articles, request, existing_articles=None):
        """Save articles to database with duplicate prevention - CORRECTED FOR YOUR MODEL"""
        nonlocal current_step
        if existing_articles is None:
            existing_articles = {}
            
        try:
            from collect.models import AutoNewsArticle
            
            update_progress("Saving to DB", 0, len(articles), 
                           f"💾 Saving {len(articles)} articles to database...")
            
            saved_count = 0
            updated_count = 0
            error_count = 0
            errors = []
            start_time = time.time()
            
            for idx, article in enumerate(articles):
                try:
                    # Get user for created_by field
                    user = request.user if request.user.is_authenticated else None
                    
                    # Prepare data according to your model
                    title = article['title'][:500]  # max_length=500
                    summary = article['content'][:1000]  # TextField
                    url = article['url'][:1000]  # max_length=1000
                    image_url = article.get('image_url', '')[:1000] if article.get('image_url') else None
                    source = "nagariknews"[:100]  # max_length=100
                    date = article.get('date', TODAY.strftime('%Y-%m-%d'))[:20]  # max_length=20
                    
                    # Store analysis data
                    content_length = len(article['content'])
                    priority = article.get('priority', 'medium')[:10]  # max_length=10
                    threat_level = article.get('threat_level', 'low')[:10]  # max_length=10
                    
                    # Store keywords and categories as JSON strings
                    keywords = json.dumps(article.get('found_keywords', []), ensure_ascii=False)
                    categories = json.dumps(article.get('categories', []), ensure_ascii=False)
                    
                    # Check if article exists
                    if article['url'] in existing_articles:
                        # Update existing article
                        article_id = existing_articles[article['url']]
                        existing = AutoNewsArticle.objects.get(id=article_id)
                        
                        existing.title = title
                        existing.summary = summary
                        existing.url = url
                        existing.image_url = image_url
                        existing.source = source
                        existing.date = date
                        existing.content_length = content_length
                        existing.priority = priority
                        existing.threat_level = threat_level
                        existing.keywords = keywords
                        existing.categories = categories
                        
                        existing.save()
                        updated_count += 1
                        
                        if updated_count <= 5 or len(articles) <= 20:
                            print(f"      🔄 Updated: {article['title'][:50]}...")
                    else:
                        # Check by content hash (optional, not required for your model)
                        # You can add this if you want, but not necessary
                        
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
                    import traceback
                    traceback.print_exc()
                
                # Update progress every 3 articles
                if (idx + 1) % 3 == 0 or (idx + 1) == len(articles):
                    progress_percent = ((idx + 1) / len(articles)) * 100
                    update_progress("Saving to DB", idx + 1, len(articles),
                                   f"💾 New: {saved_count} | Updated: {updated_count} | Total: {idx + 1}/{len(articles)} ({progress_percent:.1f}%)")
            
            time_taken = time.time() - start_time
            update_progress("Saving to DB", len(articles), len(articles),
                           f"✅ New: {saved_count} | Updated: {updated_count} | Errors: {error_count} | Total: {saved_count + updated_count}/{len(articles)} in {time_taken:.1f}s")
            current_step += 1
            return saved_count, updated_count, error_count, errors
            
        except Exception as e:
            update_progress("Saving to DB", 1, 1, f"❌ Database error: {str(e)[:50]}")
            current_step += 1
            return 0, 0, len(articles), [str(e)]
    
    # MAIN EXECUTION
    try:
        print("Nagarik news fetching started")
        send_to_websocket("=" * 50)
        send_to_websocket("🚀 STARTING NAGARIK NEWS SCRAPER")
        send_to_websocket(f"👤 User: {request.user.username if request.user.is_authenticated else 'Unknown'}")
        send_to_websocket(f"📅 Date range: Last 2 days")
        send_to_websocket(f"⏳ Estimated steps: {TOTAL_STEPS}")
        send_to_websocket("=" * 50)
        
        # Track total progress
        overall_start = time.time()
        
        # 1. Get user's keywords
        keyword_list, keyword_dict = get_user_keywords(request)
        
        # 2. Create session
        update_progress("Creating session", 1, 1, "🔧 Creating HTTP session...")
        session = create_session()
        current_step += 1
        
        # 3. Find article links
        article_links = find_article_links(session)
        if not article_links:
            send_to_websocket("❌ No articles found")
            return json.dumps({
                "metadata": {"status": "success", "message": "No articles found"},
                "articles": []
            })
        
        # 4. Check for duplicates in DB and get existing article IDs
        duplicate_urls, existing_articles = check_duplicates(article_links, request)
        
        # Remove duplicates from fetch list
        articles_to_fetch = [a for a in article_links if a['url'] not in duplicate_urls]
        if duplicate_urls:
            send_to_websocket(f"📊 After duplicate removal: {len(articles_to_fetch)} new + {len(duplicate_urls)} existing = {len(article_links)} total")
        
        # 5. Fetch article content (only new articles)
        articles_with_content = fetch_all_articles(articles_to_fetch, session)
        
        if not articles_with_content and not duplicate_urls:
            send_to_websocket("❌ No articles with content found")
            return json.dumps({
                "metadata": {"status": "success", "message": "No valid articles found"},
                "articles": []
            })
        
        # 6. Filter and analyze by keywords
        filtered_articles = []
        if articles_with_content:
            filtered_articles = filter_by_keywords(articles_with_content, keyword_dict)
        
        # 7. Save to database (only new articles with keyword matches)
        saved_count = 0
        updated_count = 0
        error_count = 0
        errors = []
        
        if filtered_articles:
            saved_count, updated_count, error_count, errors = save_to_database(filtered_articles, request, existing_articles)
        else:
            send_to_websocket("⚠️ No articles with keyword matches found")
        
        # Prepare final response
        final_articles = []
        for idx, article in enumerate(filtered_articles):
            final_articles.append({
                'id': idx + 1,
                'title': article['title'],
                'url': article['url'],
                'summary': article['content'][:300] + "..." if len(article['content']) > 300 else article['content'],
                'date': article['date'],
                'image_url': article.get('image_url', ''),
                'content_length': len(article['content']),
                'keywords': article.get('found_keywords', [])[:5],
                'categories': article.get('categories', [])[:3],
                'threat_level': article.get('threat_level', 'low'),
                'priority': article.get('priority', 'medium'),
                'source': 'Nagarik News',
                'has_keywords': len(article.get('found_keywords', [])) > 0,
                'keyword_count': len(article.get('found_keywords', [])),
                'category_count': len(article.get('categories', []))
            })
        
        # FINAL SUMMARY
        total_time = round(time.time() - overall_start, 2)
        
        send_to_websocket("=" * 50)
        send_to_websocket("🎯 SCRAPING COMPLETE - FINAL SUMMARY")
        send_to_websocket(f"⏱️ Total time: {total_time}s")
        send_to_websocket(f"📊 Articles found: {len(article_links)}")
        send_to_websocket(f"📊 Existing in DB: {len(duplicate_urls)}")
        send_to_websocket(f"📊 New articles fetched: {len(articles_with_content)}")
        send_to_websocket(f"📊 After filtering: {len(filtered_articles)}")
        send_to_websocket(f"💾 New saves: {saved_count}")
        send_to_websocket(f"🔄 Updates: {updated_count}")
        send_to_websocket(f"❌ Errors: {error_count}")
        send_to_websocket(f"🔑 Keywords used: {len(keyword_dict)}")
        
        if filtered_articles:
            total_keywords = sum(len(a.get('found_keywords', [])) for a in filtered_articles)
            avg_keywords = total_keywords / len(filtered_articles) if filtered_articles else 0
            send_to_websocket(f"🔍 Avg keywords/article: {avg_keywords:.1f}")
        
        send_to_websocket("✅ All steps completed successfully!")
        send_to_websocket("=" * 50)
        
        return json.dumps({
            "metadata": {
                "status": "success",
                "source": "nagariknews",
                "total_links": len(article_links),
                "existing_in_db": len(duplicate_urls),
                "articles_with_content": len(articles_with_content),
                "keyword_matches": len(filtered_articles),
                "saved_to_db": saved_count,
                "updated_in_db": updated_count,
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
                "source": "nagariknews",
                "message": str(e),
                "time_taken": round(time.time() - global_start_time, 2),
                "scraped_at": datetime.now().isoformat()
            },
            "articles": []
        })