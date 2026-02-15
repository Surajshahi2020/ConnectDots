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


def keyboard_kantipur_to_json(request):
    base_url = "https://www.kantipurdaily.com"
    send_to_websocket(f"🌐 Visiting site: {base_url}")
    
    # --------------------------------------------------------------------------Change fetching time----------------------------------------------------------------
    TODAY = datetime.now()
    TWO_DAYS_AGO = TODAY - timedelta(days=4)  # Increased to 4 days for more articles
    
    # Settings
    DELAY = 3
    MAX_WORKERS = 4
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
            # Fallback keywords if DB fails - Nepali keywords for Kantipur
            fallback = {
                'चुनाव': 'Election', 'मतदान': 'Election', 'राजनीति': 'Politics',
                'सरकार': 'Government', 'प्रधानमन्त्री': 'Government', 'मन्त्री': 'Government',
                'सेना': 'Army', 'प्रहरी': 'Police', 'अदालत': 'Legal',
                'आर्थिक': 'Economic', 'बजेट': 'Economic', 'मुद्रा': 'Economic',
                'शिक्षा': 'Education', 'विद्यालय': 'Education', 'विश्वविद्यालय': 'Education',
                'स्वास्थ्य': 'Health', 'अस्पताल': 'Health', 'डाक्टर': 'Health',
                'खेल': 'Sports', 'क्रिकेट': 'Sports', 'फुटबल': 'Sports',
                'मनोरञ्जन': 'Entertainment', 'चलचित्र': 'Entertainment', 'गायक': 'Entertainment',
                'प्रदूषण': 'Environment', 'वातावरण': 'Environment', 'जलवायु': 'Environment'
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
            "Accept-Language": "en-US,en;q=0.9,ne;q=0.8",
            "Referer": base_url,
        })
        return session
    
    def find_article_links(session):
        """Find article links from various sections of Kantipur"""
        nonlocal current_step
        update_progress("Finding articles", 0, 1, "🔍 Searching for articles in Kantipur sections...")
        
        # Kantipur specific categories and sections
        categories = [
            "/news", "/politics", "/economy", "/sports", "/entertainment",
            "/opinion", "/blog", "/photo-feature", "/health", "/education",
            "/technology", "/national", "/international", "/lifestyle"
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
                response = session.get(url, timeout=15)
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'html.parser')
                    
                    # Find article links - Kantipur specific selectors
                    article_selectors = [
                        "article", ".article-item", ".news-item", ".post-item",
                        "div.article", "div.news-block", "div.post-block",
                        ".featured-news", ".main-news", ".trending-news"
                    ]
                    
                    for selector in article_selectors:
                        for element in soup.select(selector):
                            # Find link within the article element
                            link_elem = element.find('a', href=True)
                            if not link_elem:
                                continue
                            
                            href = link_elem.get('href', '').strip()
                            if not href:
                                continue
                            
                            # Normalize URL
                            if href.startswith('//'):
                                href = 'https:' + href
                            elif href.startswith('/'):
                                href = base_url + href
                            
                            # Filter URLs
                            if ('kantipurdaily.com' not in href or
                                any(x in href.lower() for x in ['category', 'tag', 'author', 'page', '?']) or
                                href in seen_urls or '#' in href):
                                continue
                            
                            # Get title
                            title = ""
                            title_elem = element.find(['h1', 'h2', 'h3', 'h4', 'h5'])
                            if title_elem:
                                title = title_elem.get_text(strip=True)
                            if not title or len(title) < 10:
                                title = link_elem.get_text(strip=True)
                            
                            if len(title) >= 10 and href.startswith('http'):
                                articles.append({'url': href, 'title': title[:250]})
                                seen_urls.add(href)
                                
                                if len(articles) >= 80:  # Increase limit for Kantipur
                                    time_taken = time.time() - start_time
                                    update_progress("Finding articles", len(categories), len(categories), 
                                                  f"✅ Found {len(articles)} articles in {time_taken:.1f}s")
                                    current_step += 1
                                    return articles
                
            except Exception as e:
                print(f"Error in category {category}: {str(e)[:100]}")
                continue
        
        time_taken = time.time() - start_time
        update_progress("Finding articles", len(categories), len(categories), 
                       f"✅ Found {len(articles)} articles in {time_taken:.1f}s")
        current_step += 1
        return articles
    
    def check_duplicates(articles, request):
        """Check for existing articles in database"""
        nonlocal current_step
        update_progress("Checking duplicates", 0, 1, "🔍 Checking for duplicate articles in database...")
        
        try:
            from collect.models import AutoNewsArticle
            
            urls_to_check = [a['url'] for a in articles]
            duplicate_urls = []
            
            # Check in batches
            total_batches = (len(urls_to_check) + 9) // 10  # Ceiling division
            for i in range(0, len(urls_to_check), 10):
                batch_num = i // 10 + 1
                batch = urls_to_check[i:i+10]
                
                batch_progress = (batch_num / total_batches) * 100
                update_progress("Checking duplicates", batch_num, total_batches,
                               f"📋 Checking batch {batch_num}/{total_batches} ({batch_progress:.1f}%)")
                
                existing = AutoNewsArticle.objects.filter(
                    url__in=batch,
                    created_by=request.user
                ).values_list('url', flat=True)
                
                duplicate_urls.extend(existing)
            
            if duplicate_urls:
                update_progress("Checking duplicates", total_batches, total_batches,
                               f"⏭️ Found {len(duplicate_urls)} duplicates in database")
            else:
                update_progress("Checking duplicates", total_batches, total_batches,
                               "✅ No duplicates found")
            
            current_step += 1
            return duplicate_urls
            
        except Exception as e:
            update_progress("Checking duplicates", 1, 1, f"⚠️ Skipping duplicate check: {str(e)[:50]}")
            current_step += 1
            return []
    
    def fetch_article_content(article, session, article_num, total_articles):
        """Fetch content for a single Kantipur article"""
        try:
            time.sleep(DELAY * 0.5)  # Reduced delay
            response = session.get(article['url'], timeout=12)
            
            if response.status_code != 200:
                return None
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Get date - Kantipur specific date selectors
            pub_date = None
            date_selectors = [
                "meta[property='article:published_time']",
                "meta[name='publish-date']",
                "meta[name='date']",
                ".date-published",
                ".article-date",
                ".post-date",
                "time",
                "span.date"
            ]
            
            for selector in date_selectors:
                elem = soup.select_one(selector)
                if elem:
                    date_str = elem.get('content', '') or elem.get('datetime', '') or elem.get_text(strip=True)
                    if date_str:
                        try:
                            # Try to extract date from various formats
                            date_patterns = [
                                r'(\d{4}-\d{2}-\d{2})',
                                r'(\d{2}-\d{2}-\d{4})',
                                r'(\d{4}/\d{2}/\d{2})',
                                r'(\d{2}/\d{2}/\d{4})',
                                r'(\d{1,2}\s+[जनवरी|फेब्रुअरी|मार्च|अप्रिल|मे|जुन|जुलाई|अगस्ट|सेप्टेम्बर|अक्टोबर|नोभेम्बर|डिसेम्बर]\s+\d{4})',
                            ]
                            
                            for pattern in date_patterns:
                                match = re.search(pattern, date_str)
                                if match:
                                    try:
                                        pub_date = datetime.strptime(match.group(1), '%Y-%m-%d')
                                        break
                                    except:
                                        try:
                                            pub_date = datetime.strptime(match.group(1), '%d-%m-%Y')
                                            break
                                        except:
                                            continue
                            
                            if pub_date and pub_date < TWO_DAYS_AGO:
                                return None
                            break
                        except:
                            continue
            
            # Get content - Kantipur specific content selectors
            content = ""
            content_selectors = [
                "div.news-content",
                "div.article-content",
                "div.post-content",
                "article div.content",
                ".detail-box",
                ".editor-box",
                "div.description"
            ]
            
            for selector in content_selectors:
                elem = soup.select_one(selector)
                if elem:
                    # Remove unwanted elements
                    for unwanted in elem.select('.advertisement, .related-news, .comments-section, script, style'):
                        unwanted.decompose()
                    
                    paragraphs = elem.find_all('p')
                    if paragraphs:
                        text_parts = []
                        for p in paragraphs[:25]:  # Increased limit for Kantipur
                            text = p.get_text(strip=True)
                            if len(text) > 30 and not text.startswith(('ADVERTISEMENT', 'SPONSORED', 'Related')):
                                text_parts.append(text)
                        
                        if text_parts:
                            content = ' '.join(text_parts)[:3000]  # Increased content limit
                            break
            
            if not content or len(content) < 150:  # Increased minimum content length
                return None
            
            # Get image - Kantipur specific image selectors
            image_url = ""
            img_selectors = [
                "meta[property='og:image']",
                "meta[name='twitter:image']",
                "img.featured-image",
                "img.article-image",
                ".main-image img",
                "figure img"
            ]
            
            for selector in img_selectors:
                elem = soup.select_one(selector)
                if elem:
                    src = elem.get('content', '') or elem.get('src', '') or elem.get('data-src', '')
                    if src and 'http' in src:
                        image_url = src
                        if '300x0' in image_url:
                            image_url = image_url.replace('300x0', '800x0')
                        break
            
            # Generate content hash for duplicate checking
            content_hash = hashlib.md5(content[:1500].encode()).hexdigest()
            
            # Get category from URL or content
            category = "General"
            if 'kantipurdaily.com' in article['url']:
                url_parts = article['url'].split('/')
                if len(url_parts) >= 4:
                    possible_category = url_parts[3]
                    # --------------------------------------------------------------------------Change fetching category-------------------------------------------------------------
                    if possible_category in ['national', 'news', 'politics', 'economy', 'opinion', 'health', 'education', 'technology', 'national']:
                        category = possible_category.capitalize()
            
            return {
                'url': article['url'],
                'title': article['title'],
                'content': content,
                'image_url': image_url,
                'date': pub_date.strftime('%Y-%m-%d') if pub_date else TODAY.strftime('%Y-%m-%d'),
                'category': category,  # Added category
                'content_hash': content_hash
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
            
            # Determine threat level based on categories and content
            threat_level = "low"
            priority = "low"
            
            # Check for urgent categories
            urgent_categories = ['Violence', 'Terrorism', 'Emergency', 'Crime']
            high_categories = ['Politics', 'Government', 'Protest', 'Economic']
            medium_categories = ['Education', 'Health', 'Environment', 'Legal']
            
            if any(cat in urgent_categories for cat in categories):
                threat_level = "high"
                priority = "high"
            elif any(cat in high_categories for cat in categories):
                threat_level = "medium"
                priority = "medium"
            elif any(cat in medium_categories for cat in categories):
                threat_level = "low"
                priority = "medium"
            
            # Also check content for emergency keywords
            content_lower = article['content'].lower()
            emergency_keywords = ['आपतकाल', 'आपदा', 'दुर्घटना', 'हत्या', 'आक्रमण', 'बम', 'विस्फोट']
            if any(kw in content_lower for kw in emergency_keywords):
                threat_level = "high"
                priority = "high"
            
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
                       f"✅ Keyword matches: {len(filtered)} articles in {time_taken:.1f}s")
        current_step += 1
        return filtered
    
    def save_to_database(articles, request):
        """Save articles to database with duplicate prevention"""
        nonlocal current_step
        try:
            from collect.models import AutoNewsArticle  # Changed to AutoNewsArticle
            
            update_progress("Saving to DB", 0, len(articles), 
                           f"💾 Saving {len(articles)} articles to database...")
            
            saved_count = 0
            duplicate_count = 0
            error_count = 0
            start_time = time.time()
            
            for idx, article in enumerate(articles):
                try:
                    # Check by content hash first (most reliable)
                    exists = AutoNewsArticle.objects.filter(
                        content_hash=article['content_hash'],
                        created_by=request.user
                    ).exists()
                    
                    if exists:
                        duplicate_count += 1
                        continue
                    
                    # Also check by URL
                    exists = AutoNewsArticle.objects.filter(
                        url=article['url'],
                        created_by=request.user
                    ).exists()
                    
                    if exists:
                        duplicate_count += 1
                        continue
                    
                    # Save article with keyword analysis
                    news_article = AutoNewsArticle(
                        title=article['title'],
                        summary=article['content'][:500],
                        content=article['content'],
                        url=article['url'],
                        image_url=article.get('image_url', ''),
                        source="kantipur",  # Changed source name
                        category=article.get('category', 'General'),  # Added category
                        publish_date=datetime.strptime(article['date'], '%Y-%m-%d'),
                        threat_level=article.get('threat_level', 'low'),
                        priority=article.get('priority', 'medium'),
                        categories=",".join(article.get('categories', [])[:5]),
                        keywords_found=",".join(article.get('found_keywords', [])[:10]),
                        content_hash=article['content_hash'],
                        created_by=request.user,
                        is_active=True,
                        metadata=json.dumps({
                            'original_title': article['title'],
                            'content_length': len(article['content']),
                            'image_url': article.get('image_url', ''),
                            'scraped_at': datetime.now().isoformat()
                        }, ensure_ascii=False)
                    )
                    
                    news_article.save()
                    saved_count += 1
                    
                    # Update progress every 3 articles
                    if (idx + 1) % 3 == 0 or (idx + 1) == len(articles):
                        progress_percent = ((idx + 1) / len(articles)) * 100
                        update_progress("Saving to DB", idx + 1, len(articles),
                                       f"💾 Saved {saved_count}/{len(articles)} articles ({progress_percent:.1f}%)")
                        
                except Exception as e:
                    error_count += 1
                    print(f"Error saving article {idx}: {str(e)[:100]}")
                    continue
            
            time_taken = time.time() - start_time
            update_progress("Saving to DB", len(articles), len(articles),
                           f"✅ Saved {saved_count}/{len(articles)} articles in {time_taken:.1f}s "
                           f"(Skipped {duplicate_count} duplicates, Errors: {error_count})")
            current_step += 1
            return saved_count, duplicate_count
            
        except Exception as e:
            update_progress("Saving to DB", 1, 1, f"❌ Database error: {str(e)[:50]}")
            current_step += 1
            return 0, len(articles)
    
    # MAIN EXECUTION
    try:
        print("Kantipur news fetching started")
        send_to_websocket("=" * 60)
        send_to_websocket("🚀 STARTING KANTIPUR DAILY SCRAPER")
        send_to_websocket(f"👤 User: {request.user.username if request.user.is_authenticated else 'Unknown'}")
        send_to_websocket(f"📅 Date range: Last 4 days")
        send_to_websocket(f"⏳ Estimated steps: {TOTAL_STEPS}")
        send_to_websocket(f"🌐 Target: {base_url}")
        send_to_websocket("=" * 60)
        
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
        
        # 4. Check for duplicates in DB
        duplicate_urls = check_duplicates(article_links, request)
        
        # Remove duplicates
        articles_to_fetch = [a for a in article_links if a['url'] not in duplicate_urls]
        if duplicate_urls:
            send_to_websocket(f"📊 After duplicate removal: {len(articles_to_fetch)}/{len(article_links)} articles")
        
        # 5. Fetch article content
        articles_with_content = fetch_all_articles(articles_to_fetch, session)
        if not articles_with_content:
            send_to_websocket("❌ No articles with content found")
            return json.dumps({
                "metadata": {"status": "success", "message": "No valid articles found"},
                "articles": []
            })
        
        # 6. Filter and analyze by keywords
        filtered_articles = filter_by_keywords(articles_with_content, keyword_dict)
        
        # 7. Save to database
        saved_count, duplicate_count = save_to_database(filtered_articles, request)
        
        # Prepare final response
        final_articles = []
        for idx, article in enumerate(filtered_articles):
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
        send_to_websocket(f"📊 After filtering: {len(filtered_articles)}")
        send_to_websocket(f"💾 Saved to DB: {saved_count}")
        send_to_websocket(f"⏭️ Duplicates skipped: {duplicate_count}")
        send_to_websocket(f"🔑 Keywords used: {len(keyword_dict)}")
        
        if filtered_articles:
            total_keywords = sum(len(a.get('found_keywords', [])) for a in filtered_articles)
            avg_keywords = total_keywords / len(filtered_articles) if filtered_articles else 0
            
            # Category distribution
            categories_count = {}
            for article in filtered_articles:
                category = article.get('category', 'General')
                categories_count[category] = categories_count.get(category, 0) + 1
            
            send_to_websocket(f"🔍 Avg keywords/article: {avg_keywords:.1f}")
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
                "duplicates_skipped": len(duplicate_urls),
                "articles_with_content": len(articles_with_content),
                "keyword_matches": len(filtered_articles),
                "saved_to_db": saved_count,
                "db_duplicates": duplicate_count,
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
                "source": "kantipur",
                "message": str(e),
                "time_taken": round(time.time() - global_start_time, 2),
                "scraped_at": datetime.now().isoformat()
            },
            "articles": []
        })


# Function to integrate with your existing fetch system
def fetch_kantipur_news(request):
    """
    Main function to call from your keyboard view
    """
    try:
        # Call the scraper function
        result_json = keyboard_kantipur_to_json(request)
        result_data = json.loads(result_json)
        
        return {
            "status": result_data["metadata"]["status"],
            "message": result_data["metadata"].get("message", "Kantipur fetch completed"),
            "stats": {
                "saved": result_data["metadata"].get("saved_to_db", 0),
                "skipped": result_data["metadata"].get("db_duplicates", 0),
                "total_processed": result_data["metadata"].get("articles_with_content", 0)
            },
            "data": result_data
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error in fetch_kantipur_news: {str(e)}"
        }