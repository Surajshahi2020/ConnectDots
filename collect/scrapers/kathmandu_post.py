"""
Script to scrape SECURITY-RELATED news from kathmandupost.ekantipur.com
Updated for current website structure
"""

from datetime import datetime
from bs4 import BeautifulSoup as BS
import requests
import json

parser = "lxml"
URL = "https://kathmandupost.com"  # Updated URL

def setup():
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        PAGE = requests.get(URL, headers=HEADERS, timeout=10)
        PAGE.raise_for_status()
        return BS(PAGE.content, parser)
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return None

def format_date_from_url(url):
    """Extract and format date from article URL"""
    try:
        # URL format: /national/2023/12/15/title-slug
        parts = url.split('/')
        year, month, day = parts[2], parts[3], parts[4]
        date_obj = datetime.strptime(f"{year}-{month}-{day}", "%Y-%m-%d")
        return date_obj.strftime("%d %b %Y")
    except:
        return datetime.now().strftime("%d %b %Y")

def is_security_related(content):
    """Check if content is related to Nepal security threats"""
    
    security_keywords = {
        # Military & Defense
        "army", "military", "security", "defense", "soldier", "jawan",
        "army chief", "army officer", "army camp", "army training",
        
        # Police & Law Enforcement
        "police", "police officer", "IGP", "CID", "crime", "investigation",
        "arrest", "detention", "raid", "case", "charge",
        
        # APF & Border Security
        "APF", "Armed Police", "border", "immigration", "customs",
        
        # Weapons & Violence
        "weapon", "gun", "bullet", "rifle", "bomb", "explosion",
        "shooting", "firing", "blast", "violence", "attack", "assault",
        
        # Crime & Threats
        "murder", "killing", "robbery", "theft", "kidnapping", "rape",
        "criminal", "gang", "smuggling", "trafficking",
        
        # Terrorism & Extremism
        "terror", "terrorism", "terrorist", "extremism", "extremist",
        "Maoist", "armed", "conflict", "insurgency",
        
        # Protests & Civil Unrest
        "protest", "demonstration", "strike", "bandh", "rally",
        "unrest", "clash", "riot", "vandalism", "arson",
        
        # Cyber Security
        "cyber", "hack", "hacking", "phishing", "cyber crime", "data breach",
        
        # National Security
        "national security", "treason", "espionage", "intelligence",
        
        # Emergency & Disaster
        "emergency", "disaster", "earthquake", "flood", "landslide", "rescue",
        
        # Political Security
        "government security", "ministry security", "VIP security",
        
        # Economic Security
        "scam", "corruption", "fraud", "financial crime"
    }
    
    content_lower = content.lower()
    
    for keyword in security_keywords:
        if keyword.lower() in content_lower:
            return True
    
    return False

def analyze_security_threat(content):
    """Analyze content for security threat levels"""
    
    security_keywords = {
        "terrorism", "terrorist", "bomb", "explosion", "shooting", "murder", 
        "kidnapping", "hostage", "assassination", "armed attack", "mass violence",
        "protest", "demonstration", "strike", "riot", "clash", "vandalism", 
        "arson", "cyber attack", "hack", "data breach", "fraud", "corruption",
        "army", "police", "APF", "arrest", "raid", "investigation", "crime",
        "weapon", "gun", "ammunition", "explosive", "border", "immigration",
        "security force", "intelligence", "surveillance", "espionage"
    }
    
    found_keywords = []
    threat_level = "low"
    
    content_lower = content.lower()
    
    for keyword in security_keywords:
        if keyword.lower() in content_lower:
            found_keywords.append(keyword)
    
    # Determine threat level
    if found_keywords:
        critical_threat_terms = {"terrorism", "terrorist", "bomb", "explosion", "mass shooting", "assassination"}
        high_threat_terms = {"armed attack", "shooting", "riot", "arson", "cyber attack", "hostage", "kidnapping"}
        medium_threat_terms = {"protest", "demonstration", "strike", "clash", "vandalism", "fraud", "investigation"}
        
        found_terms_lower = [term.lower() for term in found_keywords]
        
        if any(term in found_terms_lower for term in critical_threat_terms):
            threat_level = "critical"
        elif any(term in found_terms_lower for term in high_threat_terms):
            threat_level = "high"
        elif any(term in found_terms_lower for term in medium_threat_terms):
            threat_level = "medium"
        else:
            threat_level = "low"
    
    # Determine categories
    categories = []
    category_mapping = {
        "Terrorism": {"terrorism", "terrorist", "bomb", "explosion"},
        "Violent_Crime": {"murder", "shooting", "armed attack", "hostage", "kidnapping"},
        "Public_Disorder": {"protest", "demonstration", "riot", "strike", "clash"},
        "Cyber_Security": {"cyber attack", "hack", "data breach"},
        "Law_Enforcement": {"police", "arrest", "investigation", "raid", "crime"},
        "Military": {"army", "military", "defense"},
    }
    
    for cat, terms in category_mapping.items():
        if any(term in content_lower for term in terms):
            categories.append(cat)
    
    if not categories and found_keywords:
        categories = ["General_Security"]
    
    return {
        "threat_level": threat_level,
        "keywords_found": found_keywords,
        "categories": categories,
        "priority": "high" if threat_level in ["critical", "high"] else "medium"
    }

def kathmandu_post_security_extractor():
    """Extracts security-related news from Kathmandu Post"""
    soup = setup()
    if soup is None:
        return []
        
    security_news_list = []
    
    try:
        # Try multiple possible article selectors
        articles = soup.find_all('article')
        
        if not articles:
            # Alternative selectors
            articles = soup.find_all('div', class_=['article', 'news-item', 'story'])
        
        for article in articles:
            try:
                # Try to find title and link
                title_elem = article.find(['h2', 'h3', 'h1'])
                if not title_elem:
                    continue
                    
                link_elem = title_elem.find('a') if title_elem else article.find('a')
                if not link_elem or not link_elem.get('href'):
                    continue
                
                # Get article details
                title = title_elem.get_text(strip=True)
                relative_link = link_elem['href']
                
                # Make absolute URL
                if relative_link.startswith('/'):
                    article_link = URL + relative_link
                else:
                    article_link = relative_link
                
                # Get summary
                summary_elem = article.find('p')
                summary = summary_elem.get_text(strip=True) if summary_elem else ""
                
                # Get image
                img_elem = article.find('img')
                image_link = img_elem.get('src') if img_elem else ""
                if image_link and image_link.startswith('//'):
                    image_link = 'https:' + image_link
                elif image_link and image_link.startswith('/'):
                    image_link = URL + image_link
                
                # Get date
                date = format_date_from_url(relative_link)
                
                # Combine content for analysis
                content_for_analysis = title + " " + summary
                
                # Filter for security-related news
                if not is_security_related(content_for_analysis):
                    continue
                
                # Analyze threat level
                threat_analysis = analyze_security_threat(content_for_analysis)
                
                # Only include meaningful security news
                if threat_analysis["threat_level"] in ["critical", "high", "medium"]:
                    news_dict = {
                        "title": title,
                        "source": "kathmandu_post",
                        "news_link": article_link,
                        "raw_date": date,
                        "summary": summary,
                        "image_link": image_link,
                        "threat_analysis": threat_analysis,
                        "content_length": len(content_for_analysis),
                        "priority": threat_analysis["priority"]
                    }
                    
                    security_news_list.append(news_dict)
                    print(f"✅ Added security article: {title[:50]}...")
                    
            except Exception as e:
                print(f"⚠️  Skipping article due to error: {e}")
                continue
                
    except Exception as e:
        print(f"❌ Error processing articles: {e}")
    
    return security_news_list

def kathmandu_post_security_to_json():
    """Returns JSON output with security news"""
    articles = kathmandu_post_security_extractor()
    
    output = {
        "metadata": {
            "source": "Kathmandu Post Security News",
            "url": URL,
            "scraped_at": datetime.now().isoformat(),
            "status": "success",
            "total_articles_found": len(articles),
            "focus": "Nepal Security & Threat Intelligence"
        },
        "articles": articles
    }
    
    return json.dumps(output, indent=2, ensure_ascii=False)

# For backward compatibility
def kathmandu_post_extractor():
    return kathmandu_post_security_extractor()

def kathmandu_post_to_json():
    return kathmandu_post_security_to_json()

if __name__ == "__main__":
    print("🚀 Testing Kathmandu Post Security News Extractor...")
    
    security_news = kathmandu_post_security_extractor()
    print(f"\n📊 RESULTS: Found {len(security_news)} security-related articles")
    
    if security_news:
        threat_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for article in security_news:
            threat_level = article["threat_analysis"]["threat_level"]
            threat_counts[threat_level] += 1
        
        print(f"🛡️  Threat Level Distribution: {threat_counts}")
        
        print("\n🔍 Sample Security Articles:")
        for i, article in enumerate(security_news[:3]):
            print(f"\n{i+1}. {article['title']}")
            print(f"   Threat: {article['threat_analysis']['threat_level']}")
            print(f"   Categories: {', '.join(article['threat_analysis']['categories'])}")
            print(f"   URL: {article['news_link']}")
    else:
        print("❌ No security articles found. The website structure might have changed.")
        print("💡 Try checking the website manually: https://kathmandupost.com")