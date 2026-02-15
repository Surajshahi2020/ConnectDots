import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime, timedelta
import re
import time
import os
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def techpana_to_json():
    base_url = "https://techpana.com/"
    
    # Rotating User-Agents
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15"
    ]
    
    # Enhanced headers
    headers = {
        "User-Agent": random.choice(user_agents),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    }
    
    # Comprehensive Nepali keywords for threat detection
    important_keywords = {
        # Cybersecurity Threats
        "साइबर", "ह्याक", "ह्याकिङ", "साइबर अपराध", "साइबर हमला", "डाटा", "डाटा उल्लंघन",
        "फिसिङ", "मालवेयर", "र्यान्समवेयर", "भाइरस", "ट्रोजन", "स्पाइवेयर",
        "साइबर सुरक्षा", "सूचना सुरक्षा", "नेटवर्क सुरक्षा", "अनलाइन सुरक्षा",
        "पासवर्ड", "एन्क्रिप्सन", "फायरवाल", "एन्टिभाइरस",
        
        # Data Privacy & Breaches
        "डाटा संरक्षण", "गोपनीयता", "व्यक्तिगत डाटा", "निजी जानकारी", "डाटा लिक",
        "गोपनीयता उल्लंघन", "डाटा चोरी", "जानकारी लिक", "प्राइभेसी",
        
        # Financial Cyber Crimes
        "डिजिटल बैंकिङ", "इन्टरनेट बैंकिङ", "मोबाइल बैंकिङ", "क्रेडिट कार्ड", "डेबिट कार्ड",
        "क्रेडिट कार्ड धोका", "बैंकिङ धोका", "अनलाइन धोका", "ई-कॉमर्स धोका",
        "डिजिटल पेमेन्ट", "ई-पेमेन्ट", "मोबाइल पेमेन्ट", "वाल्ट", "सानिमा बैंक", "इन्टरनेट बैंकिङ",
        
        # Social Media & Online Crimes
        "सोशल मिडिया", "फेसबुक", "ट्विटर", "इन्स्टाग्राम", "टिकटक", "युट्युब",
        "सोशल मिडिया अपराध", "अनलाइन उत्पीडन", "साइबर बुलिङ", "अनलाइन धम्की",
        "फेक अकाउन्ट", "नकली प्रोफाइल", "इन्टरनेट धोका",
        
        # Identity Theft & Fraud
        "आइडेन्टिटी चोरी", "पहिचान चोरी", "फरजीवी", "नकली", "घोटाला", "धोका",
        "फिनान्सियल धोका", "इन्भेस्टमेन्ट धोका", "पोन्जी योजना",
        
        # AI & Emerging Tech Threats
        "एआई", "कृत्रिम बुद्धिमत्ता", "मेसिन लर्निङ", "डिप लर्निङ", "न्युरल नेटवर्क",
        "एआई हथियार", "स्वायत्त हथियार", "रोबोटिक्स", "ड्रोन",
        "स्वचालित हमला", "एआई सुरक्षा", "मेसिन इन्टेलिजेन्स",
        
        # Critical Infrastructure
        "स्मार्ट सिटी", "इन्टरनेट अफ थिङ्स", "आइओटी", "स्मार्ट ग्रिड",
        "ऊर्जा प्रणाली", "जलापूर्ति", "यातायात प्रणाली", "स्वास्थ्य प्रणाली",
        "आलोचनात्मक संरचना", "राष्ट्रिय सुरक्षा",
        
        # Government & Politics
        "गृहमन्त्री", "प्रधानमन्त्री", "राष्ट्रपति", "सरकार", "मन्त्री", "संसद",
        "ओली", "प्रचण्ड", "देव", "सौर्य", "नेपाली", "कांग्रेस", "एमाले", "माओवादी",
        
        # Army & Security Forces
        "सेना", "नेपाली सेना", "सैनिक", "सशस्त्र", "सुरक्षा", "जेवी", "जवान",
        "प्रहरी", "नेपाल प्रहरी", "एपीएफ", "सशस्त्र प्रहरी",
        
        # Crime & Violence
        "हत्या", "डकैती", "चोरी", "लुट", "अपहरण", "बलात्कार", "हिंसा",
        "मारपीट", "आक्रमण", "धम्की", "अपराध", "अपराधी",
        
        # Protests & Civil Unrest
        "प्रदर्शन", "आन्दोलन", "धर्ना", "हड्ताल", "भोकहड्ताल", "जुलुस", "रैली",
        
        # Legal & Court
        "अदालत", "सुनुवाइ", "न्याय", "जेल", "कारावास", "मुद्दा", "याचिका",
        
        # Economic Threats
        "मूल्यवृद्धि", "महँगी", "अवरोध", "नाकाबन्दी", "संकट", "मन्दी", "बेरोजगार",
        
        # GenZ & Youth
        "जेनजेड", "जेन जेड", "युवा", "युवती", "युवक", "छात्र", "विद्यार्थी",
        
        # Durga Parsai
        "दुर्गा पार्साई", "पार्साई", "दुर्गा", "पारसाई", "डीपी",
        
        # Esewa & Digital Payments
        "इसेवा", "ई-सेवा", "इसेwa", "डिजिटल लेनदेन", "मोबाइल वाल्ट", "रोहित पौडेल"
    }
    
    # Pre-compile regex patterns
    URL_PATTERN = re.compile(r'/(\d{4})/(\d+)/')
    CONTENT_SELECTORS = [
        "body > main > section.custom-container.mt-10 > div.row > div.col-xl-8 > div > div.col-lg-11 > div > div.content__with-sidebar > div > div.content__desc > div",
        "div.news_detail-para.para.detail-content-paragraph.detail-news-details-paragh",
        "div.content__desc div",
        "div.detail-content-paragraph",
        "div.news_detail-para"
    ]
    
    # Pre-define threat level categories for faster lookup
    CRITICAL_THREAT_TERMS = {
        "ह्याक", "साइबर हमला", "डाटा उल्लंघन", "र्यान्समवेयर", 
        "क्रेडिट कार्ड धोका", "बैंकिङ धोका", "आइडेन्टिटी चोरी",
        "हत्या", "आतंकवाद", "बम", "विस्फोट", "अपहरण", "बलात्कार"
    }
    HIGH_THREAT_TERMS = {
        "साइबर अपराध", "मालवेयर", "फिसिङ", "डाटा लिक", 
        "गोपनीयता उल्लंघन", "सोशल मिडिया अपराध",
        "पक्राउ", "धरौटी", "प्रदर्शन", "हिंसा", "घोटाला", "भ्रष्टाचार"
    }
    MEDIUM_THREAT_TERMS = {
        "साइबर सुरक्षा", "डाटा संरक्षण", "अनलाइन धोका",
        "एआई", "कृत्रिम बुद्धिमत्ता", "डिजिटल अपराध",
        "जेनजेड", "युवा", "दुर्गा पार्साई", "सेना", "प्रहरी"
    }
    
    # Create keyword set for faster lookup
    keyword_set = set(important_keywords)
    
    # Rate limiting class
    class RateLimiter:
        def __init__(self, calls_per_minute=20):
            self.calls_per_minute = calls_per_minute
            self.last_calls = []
            
        def wait_if_needed(self):
            now = datetime.now()
            # Remove calls older than 1 minute
            self.last_calls = [call for call in self.last_calls 
                              if (now - call).seconds < 60]
            
            if len(self.last_calls) >= self.calls_per_minute:
                oldest_call = self.last_calls[0]
                sleep_time = 60 - (now - oldest_call).seconds
                if sleep_time > 0:
                    print(f"⏳ Rate limiting: Sleeping for {sleep_time} seconds...")
                    time.sleep(sleep_time + random.uniform(1, 3))
                
                # Clean up again after sleep
                now = datetime.now()
                self.last_calls = [call for call in self.last_calls 
                                  if (now - call).seconds < 60]
            
            self.last_calls.append(now)
    
    def save_to_debug_file(data, filename="techpana_debug_output.json"):
        """Save the scraped data to a JSON file for debugging"""
        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"💾 Debug data saved to {filename}")
        except Exception as e:
            print(f"❌ Error saving debug file: {e}")
    
    def get_existing_urls_from_database():
        """Get existing article URLs from database to avoid duplicates"""
        try:
            # Import your model here
            from collect.models import AutoNewsArticle
            existing_urls = set(AutoNewsArticle.objects.values_list('url', flat=True))
            print(f"📁 Found {len(existing_urls)} existing articles in database")
            return existing_urls
        except Exception as e:
            print(f"⚠️ Error loading existing articles from database: {e}")
            return set()
    
    def is_recent_article_by_id(article_url):
        """Check if article is from today or yesterday based on article ID pattern"""
        try:
            match = URL_PATTERN.search(article_url)
            if not match:
                return False
            
            year = int(match.group(1))
            article_id = int(match.group(2))
            
            current_year = datetime.now().year
            if year != current_year:
                return False
            
            # Adjust this threshold based on typical article frequency
            # Techpana seems to publish articles with IDs around 155xxx in 2026
            current_max_id = 155000  # Adjust this based on current articles
            
            # Consider articles from the last 1000 IDs as recent
            return article_id >= (current_max_id - 1000)
            
        except Exception as e:
            print(f"⚠️ Error checking article ID for {article_url}: {e}")
            return False

    def extract_article_info(container):
        """Extract title and link from article container"""
        for heading_tag in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            heading = container.find(heading_tag)
            if heading:
                title_link = heading.find('a', href=URL_PATTERN)
                if title_link:
                    title = title_link.get_text(strip=True)
                    link = title_link.get('href')
                    if link and not link.startswith('http'):
                        link = "https://techpana.com" + link
                    return title, link
        
        # Alternative selector
        title_div = container.find("div", class_=re.compile(r"single_row-title|single_grid-title"))
        if title_div:
            title_link = title_div.find('a', href=URL_PATTERN)
            if title_link:
                title = title_link.get_text(strip=True)
                link = title_link.get('href')
                if link and not link.startswith('http'):
                    link = "https://techpana.com" + link
                return title, link
        
        return None, None

    def create_session():
        """Create a session with retry strategy and rate limiting"""
        session = requests.Session()
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )
        
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=10,
            pool_maxsize=10
        )
        
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        
        # Update headers with random User-Agent
        session.headers.update({
            "User-Agent": random.choice(user_agents),
            "Accept": headers["Accept"],
            "Accept-Language": headers["Accept-Language"],
            "Accept-Encoding": headers["Accept-Encoding"],
            "DNT": headers["DNT"],
            "Connection": headers["Connection"],
            "Upgrade-Insecure-Requests": headers["Upgrade-Insecure-Requests"],
        })
        
        return session

    def fetch_single_article_content(url, session, rate_limiter):
        """Fetch content for a single article with rate limiting"""
        try:
            # Apply rate limiting
            rate_limiter.wait_if_needed()
            
            # Add random delay between 3-7 seconds
            time.sleep(random.uniform(3, 7))
            
            response = session.get(url, timeout=15)
            response.raise_for_status()
            
            # Check if we got blocked
            if response.status_code == 429:
                print(f"⏸️ Got 429 for {url}, waiting 30 seconds...")
                time.sleep(30)
                return url, ""
            
            soup = BeautifulSoup(response.content, "lxml")
            full_content = ""
            
            for selector in CONTENT_SELECTORS:
                content_div = soup.select_one(selector)
                if content_div:
                    paragraphs = content_div.find_all("p")
                    for p in paragraphs:
                        text = p.get_text(strip=True)
                        if (text and len(text) > 15 and
                            not text.startswith(("पछिल्लो अध्यावधिक:", "अध्यावधिक:", "Updated:")) and
                            not any(date_term in text for date_term in ["मंसिर", "कार्तिक", "२०८२", "२०८१"]) and
                            "iframe" not in str(p) and
                            "facebook" not in str(p).lower() and
                            "comment" not in str(p).lower()):
                            
                            full_content += text + " "
                    
                    if len(full_content.strip()) > 100:
                        break
            
            return url, full_content.strip()[:2000] if full_content.strip() else ""
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Error fetching {url}: {e}")
            return url, ""
        except Exception as e:
            print(f"❌ Unexpected error fetching {url}: {e}")
            return url, ""

    def get_article_content_batch(urls_to_fetch):
        """Fetch multiple article contents in parallel with better rate limiting"""
        content_map = {}
        rate_limiter = RateLimiter(calls_per_minute=15)  # Be conservative
        
        # Process in small batches with delays between batches
        batch_size = 3  # Very small batch size to avoid detection
        delay_between_batches = 20  # seconds
        
        for i in range(0, len(urls_to_fetch), batch_size):
            batch = urls_to_fetch[i:i+batch_size]
            print(f"📄 Processing batch {i//batch_size + 1}/{(len(urls_to_fetch)-1)//batch_size + 1} ({len(batch)} articles)")
            
            # Create a new session for each batch to rotate User-Agent
            session = create_session()
            
            # Process batch
            with ThreadPoolExecutor(max_workers=2) as executor:  # Only 2 workers!
                future_to_url = {}
                for url in batch:
                    future = executor.submit(fetch_single_article_content, url, session, rate_limiter)
                    future_to_url[future] = url
                
                for future in as_completed(future_to_url):
                    url, content = future.result()
                    content_map[url] = content
            
            # Close session
            session.close()
            
            # Delay between batches
            if i + batch_size < len(urls_to_fetch):
                print(f"⏸️ Waiting {delay_between_batches} seconds before next batch...")
                time.sleep(delay_between_batches)
        
        return content_map

    def analyze_keywords(content):
        """Analyze content for keywords and return matches"""
        # Use list comprehension for faster matching
        found_keywords = [kw for kw in keyword_set if kw in content]
        return found_keywords

    def determine_threat_level(keywords):
        """Determine threat level based on found keywords"""
        if any(term in keywords for term in CRITICAL_THREAT_TERMS):
            return "critical"
        elif any(term in keywords for term in HIGH_THREAT_TERMS):
            return "high"
        elif any(term in keywords for term in MEDIUM_THREAT_TERMS):
            return "medium"
        else:
            return "low"

    def categorize_article(keywords):
        """Categorize article based on keywords"""
        categories = []
        category_mapping = {
            "Cybersecurity": {"साइबर", "ह्याक", "साइबर अपराध", "साइबर हमला", "मालवेयर", "र्यान्समवेयर"},
            "Data_Privacy": {"डाटा", "डाटा उल्लंघन", "गोपनीयता", "डाटा संरक्षण", "व्यक्तिगत डाटा"},
            "Social_Media": {"सोशल मिडिया", "फेसबुक", "ट्विटर", "इन्स्टाग्राम", "टिकटक"},
            "AI_Threats": {"एआई", "कृत्रिम बुद्धिमत्ता", "मेसिन लर्निङ", "डिप लर्निङ"},
            "Financial_Tech": {"डिजिटल बैंकिङ", "क्रेडिट कार्ड", "ई-कॉमर्स धोका", "डिजिटल पेमेन्ट"},
            "GenZ": {"जेनजेड", "जेन जेड", "युवा", "युवती", "युवक"},
            "Durga_Parsai": {"दुर्गा पार्साई", "पार्साई", "दुर्गा", "पारसाई"},
            "Army": {"सेना", "नेपाली सेना", "सैनिक", "सशस्त्र"},
            "Police": {"प्रहरी", "नेपाल प्रहरी", "प्रहरी अधिकारी"},
            "Crime": {"हत्या", "हिंसा", "मारपीट", "आक्रमण"},
            "Protest": {"प्रदर्शन", "आन्दोलन", "धर्ना", "हड्ताल"},
            "Government": {"प्रधानमन्त्री", "राष्ट्रपति", "सरकार", "मन्त्री"}
        }
        
        for cat, terms in category_mapping.items():
            if any(term in keywords for term in terms):
                categories.append(cat)
        
        return categories if categories else ["General"]

    def get_article_date_from_url(article_url):
        """Extract approximate date from article URL for display"""
        try:
            match = URL_PATTERN.search(article_url)
            if match:
                year = match.group(1)
                article_id = match.group(2)
                return f"{year}-{article_id}"
            return "Recent"
        except:
            return "Recent"

    try:
        print(f"🚀 Starting Techpana scraping at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Load existing articles from database
        existing_urls = get_existing_urls_from_database()
        
        # Create session for homepage
        session = create_session()
        
        # Fetch main page with delay
        time.sleep(random.uniform(2, 5))
        print(f"🌐 Fetching homepage: {base_url}")
        response = session.get(base_url, timeout=15)
        response.raise_for_status()
        
        # Check for blocking
        if response.status_code == 429:
            print("❌ Homepage blocked with 429. Waiting 60 seconds...")
            time.sleep(60)
            # Try once more
            response = session.get(base_url, timeout=15)
            response.raise_for_status()
        
        soup = BeautifulSoup(response.content, "lxml")
        session.close()
        
        # Find all article containers
        article_containers = []
        main_articles = soup.select("div.single_grid-wrapper")
        side_articles = soup.select("div.single_row-wrapper")
        grid_articles = soup.select("div.grid_section-content .single_grid-wrapper, div.grid_section-content .single_row-wrapper")
        
        article_containers.extend(main_articles)
        article_containers.extend(side_articles)
        article_containers.extend(grid_articles)
        
        print(f"🔍 Found {len(article_containers)} article containers on homepage")
        
        # First pass: extract basic article info and filter
        candidate_articles = []
        candidate_urls = []
        
        for container in article_containers:
            title, link = extract_article_info(container)
            if not title or not link:
                continue
            
            # Skip existing articles
            if link in existing_urls:
                continue
            
            # Check if recent
            if not is_recent_article_by_id(link):
                continue
            
            # Extract description and image
            description = ""
            desc_p = container.find('p')
            if desc_p:
                description = desc_p.get_text(strip=True)
            
            image_url = None
            img_tag = container.find('img')
            if img_tag and img_tag.get('src'):
                image_url = img_tag.get('src')
                if image_url and not image_url.startswith('http'):
                    image_url = "https://techpana.com" + image_url
            
            candidate_articles.append({
                'title': title,
                'link': link,
                'description': description,
                'image_url': image_url
            })
            candidate_urls.append(link)
        
        print(f"📄 Found {len(candidate_articles)} candidate articles (after filtering)")
        
        # If too many articles, prioritize by URL pattern or title keywords
        if len(candidate_articles) > 50:
            print(f"⚠️ Too many candidate articles ({len(candidate_articles)}). Prioritizing...")
            # Prioritize articles with higher IDs (more recent)
            candidate_articles.sort(key=lambda x: int(URL_PATTERN.search(x['link']).group(2)) if URL_PATTERN.search(x['link']) else 0, reverse=True)
            candidate_articles = candidate_articles[:50]  # Limit to 50
            candidate_urls = [a['link'] for a in candidate_articles]
        
        if not candidate_articles:
            print("📭 No new articles to fetch")
            output = {
                "metadata": {
                    "source": "Techpana",
                    "url": base_url,
                    "scraped_at": datetime.now().isoformat(),
                    "status": "success",
                    "message": "No new articles found",
                    "total_articles_found": len(article_containers)
                },
                "articles": []
            }
            return json.dumps(output, indent=2, ensure_ascii=False)
        
        print(f"📄 Fetching content for {len(candidate_articles)} candidate articles...")
        
        # Batch fetch article contents with rate limiting
        content_map = get_article_content_batch(candidate_urls)
        
        # Process articles
        articles_data = []
        stats = {
            'new_articles': 0,
            'skipped_existing': len(article_containers) - len(candidate_articles),
            'skipped_no_content': 0,
            'skipped_no_keywords': 0,
            'skipped_low_priority': 0
        }
        
        for article_info in candidate_articles:
            title = article_info['title']
            link = article_info['link']
            description = article_info['description']
            image_url = article_info['image_url']
            
            print(f"🔄 Processing: {title[:60]}...")
            
            # Get content
            full_content = content_map.get(link, "")
            summary = full_content if full_content else description
            
            if not summary or len(summary.strip()) < 50:
                stats['skipped_no_content'] += 1
                print(f"  ⏭️ Skipped: No content")
                continue
            
            # Analyze keywords
            content_for_analysis = title + " " + summary
            found_keywords = analyze_keywords(content_for_analysis)
            
            if not found_keywords:
                stats['skipped_no_keywords'] += 1
                print(f"  ⏭️ Skipped: No keywords matched")
                continue
            
            # Determine threat level and priority
            threat_level = determine_threat_level(found_keywords)
            if threat_level == "low":
                stats['skipped_low_priority'] += 1
                print(f"  ⏭️ Skipped: Low priority")
                continue
            
            priority = "high" if threat_level in ["critical", "high"] else "medium"
            categories = categorize_article(found_keywords)
            
            # Create article data
            date_str = get_article_date_from_url(link)
            current_date = datetime.now().strftime("%Y-%m-%d")
            
            article_data = {
                "id": len(articles_data) + 1,
                "title": title,
                "summary": summary,
                "url": link,
                "image_url": image_url if image_url else "",
                "date": f"{current_date} (ID: {date_str})",
                "source": "techpana",
                "threat_analysis": {
                    "level": threat_level,
                    "keywords_found": found_keywords,
                    "total_keywords_matched": len(found_keywords),
                    "categories": categories
                },
                "content_length": len(content_for_analysis),
                "summary_length": len(summary),
                "has_content": bool(summary and len(summary.strip()) >= 50),
                "content_source": "full_article" if full_content else "preview",
                "priority": priority,
                "has_full_content": bool(full_content),
                "scraped_timestamp": datetime.now().isoformat()
            }
            
            articles_data.append(article_data)
            stats['new_articles'] += 1
            print(f"  ✅ Added {priority} priority article with {len(found_keywords)} keywords")
        
        # Final statistics
        print(f"\n📊 SCRAPING SUMMARY:")
        print(f"   Total articles found: {len(article_containers)}")
        print(f"   High/Medium priority articles added: {stats['new_articles']}")
        print(f"   Articles skipped (existing): {stats['skipped_existing']}")
        print(f"   Articles skipped (no content): {stats['skipped_no_content']}")
        print(f"   Articles skipped (no keywords): {stats['skipped_no_keywords']}")
        print(f"   Articles skipped (low priority): {stats['skipped_low_priority']}")
        
        # Create output
        output = {
            "metadata": {
                "source": "Techpana",
                "url": base_url,
                "scraped_at": datetime.now().isoformat(),
                "status": "success",
                "total_articles_found": len(article_containers),
                "high_medium_priority_articles_added": stats['new_articles'],
                "articles_skipped_existing": stats['skipped_existing'],
                "articles_skipped_no_content": stats['skipped_no_content'],
                "articles_skipped_no_keywords": stats['skipped_no_keywords'],
                "articles_skipped_low_priority": stats['skipped_low_priority'],
                "priority_filter": "high_and_medium_only",
                "date_filter": "today_and_yesterday",
                "content_statistics": {
                    "articles_with_full_content": len([a for a in articles_data if a["has_full_content"]]),
                    "articles_with_preview_only": len([a for a in articles_data if not a["has_full_content"]]),
                    "average_summary_length": sum([a["summary_length"] for a in articles_data]) // len(articles_data) if articles_data else 0,
                    "articles_with_adequate_content": len([a for a in articles_data if a["has_content"]])
                },
                "message": f"Found {stats['new_articles']} high/medium priority articles (today/yesterday) from Techpana"
            },
            "articles": articles_data
        }
        
        # Save debug file
        save_to_debug_file(output, "techpana_debug_output.json")
        print(f"💾 Full results saved to techpana_debug_output.json")
        
        return json.dumps(output, indent=2, ensure_ascii=False)
        
    except Exception as e:
        print(f"❌ Critical error: {e}")
        import traceback
        traceback.print_exc()
        
        error_output = {
            "metadata": {
                "source": "Techpana", 
                "url": base_url,
                "scraped_at": datetime.now().isoformat(),
                "status": "error",
                "error": str(e)
            },
            "articles": []
        }
        save_to_debug_file(error_output, "techpana_debug_output.json")
        return json.dumps(error_output, indent=2)

# Run it
if __name__ == "__main__":
    print("🚀 Starting Techpana scraper...")
    start_time = time.time()
    json_data = techpana_to_json()
    end_time = time.time()
    print(f"✅ Techpana scraping completed in {end_time - start_time:.2f} seconds!")
    print(f"📄 Output length: {len(json_data)} characters")