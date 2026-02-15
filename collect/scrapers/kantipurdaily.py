import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime

def kantipur_to_json():
    url = "https://www.kantipurdaily.com/news"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    # Comprehensive Nepali keywords for threat detection
    important_keywords = {
        # Government & Politics
        "गृहमन्त्री", "प्रधानमन्त्री", "राष्ट्रपति", "सरकार", "मन्त्री", "संसद", "संविधान",
        "ओली", "प्रचण्ड", "देव", "सौर्य", "नेपाली", "कांग्रेस", "एमाले", "माओवादी",
        
        # GenZ & Youth Movements
        "जेनजेड", "जेन जेड", "युवा", "युवती", "युवक", "छात्र", "विद्यार्थी", "युवा आन्दोलन",
        "टिकटक", "सोशल मिडिया", "फेसबुक", "इन्स्टाग्राम", "युट्युब", "युट्युबर", "भ्लग",
        "डिजिटल", "अनलाइन", "ट्रेन्डिङ", "भाइरल", "मेम", "रील", "स्टोरी",
        "युवा मञ्च", "युवा संगठन", "युवा नेतृत्व", "युवा अधिकार",
        
        # Durga Parsai & Specific Personalities
        "दुर्गा पार्साई", "पार्साई", "दुर्गा", "पारसाई", "डीपी", "दुर्गा भाई",
        "कमेडी", "व्यङ्ग्य", "सामाजिक मिडिया", "युट्युब च्यानल",
        
        # Army & Military
        "सेना", "नेपाली सेना", "सैनिक", "सशस्त्र", "सुरक्षा", "जेवी", "जवान",
        "सैन्य", "सेना प्रमुख", "सेना अधिकारी", "सेना क्वाटर", "सेना क्याम्प",
        "सेना तालिम", "सेना अभ्यास", "सैन्य अभियान", "सेना टुकडी",
        "सेना हेलिकप्टर", "सेना वाहन", "सेना ब्यारक", "सेना नियुक्ति",
        
        # Police & Law Enforcement
        "प्रहरी", "नेपाल प्रहरी", "प्रहरी अधिकारी", "प्रहरी महानिरीक्षक", "आइजीपी",
        "प्रहरी कार्यालय", "प्रहरी टुकडी", "प्रहरी चौकी", "प्रहरी जवान",
        "सीआईडी", "अपराध अनुसन्धान", "फोरेन्सिक", "खुफिया", "गुप्तचर",
        "ट्राफिक", "यातायात", "सवारी", "प्रहरी अभियान",
        
        # APF & Armed Police
        "एपीएफ", "सशस्त्र प्रहरी", "सशस्त्र प्रहरी बल", "आर्म्ड पुलिस",
        "एपीएफ क्याम्प", "एपीएफ जवान", "सीमा", "बोर्डर",
        
        # Security Forces Combined
        "सुरक्षा बल", "सुरक्षा अंग", "सुरक्षा निकाय", "सुरक्षा योजना",
        "सुरक्षा चौकी", "सुरक्षा तैनाथी", "सुरक्षा अभियान",
        
        # Weapons & Equipment
        "अस्त्र", "शस्त्र", "गोली", "बन्दुक", "पिस्तौल", "राइफल", "बम", "विस्फोट",
        "ग्रेनेड", "एके-४७", "एम-१६", "पिस्टल", "रिवल्बर", "कार्बाइन",
        "गोलाबारी", "गोली चल्ने", "गोली हान्ने", "गोली लागेको",
        "बम पeltos", "बम निस्कासन", "विस्फोटक", "आगजनी",
        
        # Crime & Violence
        "हत्या", "हत्या", "डकैती", "चोरी", "लुट", "अपहरण", "बलात्कार", "हिंसा",
        "मारपीट", "आक्रमण", "धम्की", "अपराध", "अपराधी", "आरोप", "दोषी",
        
        # Terrorism & Extremism
        "आतंक", "आतंकवाद", "आतंकी", "उग्रवाद", "उग्र", "चरमपन्थी", "जिहाद",
        "माओवाद", "माओवादी", "सशस्त्र", "संघर्ष", "युद्ध", "लडाइ",
        
        # Protests & Civil Unrest
        "प्रदर्शन", "आन्दोलन", "धर्ना", "हड्ताल", "भोकहड्ताल", "जुलुस", "रैली",
        "नारा", "दबाब", "माग", "असन्तुष्ट", "विरोध", "आक्रोश", "अशान्ति",
        
        # Legal & Court
        "अदालत", "सुनुवाइ", "न्याय", "जेल", "कारावास", "मुद्दा", "याचिका", "निर्णय",
        "अपील", "जमानत", "हिरासत", "जुरी", "कैद", "सजाय",
        
        # National Security
        "राष्ट्रिय सुरक्षा", "राष्ट्रिय झन्डा", "राष्ट्रगान", "राष्ट्रियता",
        "देश", "राष्ट्र", "सार्वभौम", "सीमा सुरक्षा", "राजद्रोह",
        
        # Cyber & Digital Threats
        "साइबर", "ह्याक", "फिसिङ", "क्रेडिट कार्ड", "बैंक", "घोटाला", "भ्रष्टाचार",
        "कालोधन", "करचोरी", "नकली", "डाटा", "सूचना", "गोपनीय",
        "साइबर अपराध", "डिजिटल अपराध", "अनलाइन धोका", "इन्टरनेट", "साइबर अपराध",
        
        # Emergency & Disasters
        "आपतकाल", "आपदा", "भूकम्प", "बाढी", "पहिरो", "दुर्घटना", "आकस्मिक",
        "उद्धार", "बचाव", "राहत", "आपतकालीन", "इमर्जेन्सी",
        
        # International & Border
        "विदेश", "राजदूत", "दूतावास", "सीमा", "भारत", "चीन", "अमेरिका",
        "सन्धि", "सम्झौता", "वार्ता", "कूटनीति", "अन्तर्राष्ट्रिय",
        
        # Social & Community Threats
        "जातीय", "सामुदायिक", "धार्मिक", "समुदाय", "दंगा", "टकराव", "विवाद",
        "अशान्ति", "उग्र", "आक्रोश", "सम्प्रदाय", "धर्म", "जात",
        
        # Economic Threats
        "मूल्यवृद्धि", "महँगी", "अवरोध", "नाकाबन्दी", "संकट", "मन्दी", "बेरोजगार",
        "आर्थिक", "बजेट", "कर", "रोजगार", "उद्योग",
        
        # Health Emergencies
        "महामारी", "कोरोना", "कोभिड", "संक्रमण", "लकडाउन", "स्वास्थ्य", "अस्पताल",
        "संक्रमित", "कोरेन्टिन", "आइसोलेसन",
        
        # Environmental Threats
        "प्रदूषण", "वातावरण", "जलवायु", "अवनति", "वन", "जंगल", "आगलागी",
        "पर्यावरण", "जल", "वायु", "ध्वनि",
        
        # Specific Threat Types
        "तस्करी", "मानव तस्करी", "नशा", "ड्रग", "मादक", "अफिम", "हेरोइन",
        "करिबा", "चरस", "गांजा", "नशावाद",
        
        # Kidnapping & Hostage
        "बन्धक", "होस्टेज", "फिरौती", "अपहरण", "अगवा", "बन्दी",
        
        # Surveillance & Intelligence
        "नजर", "निगरानी", "खुफिया", "गुप्त", "जासुस", "जासुसी", "सीसीटिभी",
        "क्यामेरा", "मोनिटर", "अवलोकन"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, "lxml")
        
        # Final structured JSON output
        output = {
            "metadata": {
                "source": "Kantipur Daily",
                "url": url,
                "scraped_at": datetime.now().isoformat(),
                "status": "success",
                "keywords_monitored": len(important_keywords),
                "threat_categories": ["GenZ", "Durga_Parsai", "Army", "Police", "Cyber", "Violence", "Protest", "Terrorism"]
            },
            "articles": []
        }
        
        articles = soup.find_all("article", class_="normal")
        
        for i, article in enumerate(articles):
            try:
                # Title and link
                title_elem = article.find("h2")
                if not title_elem:
                    continue
                    
                title = title_elem.get_text(strip=True)
                link_elem = title_elem.find("a")
                relative_link = link_elem["href"] if link_elem and link_elem.get("href") else ""
                full_link = "https://www.kantipurdaily.com" + relative_link
                
                # Summary
                summary_elem = article.find("p")
                summary = summary_elem.get_text(strip=True) if summary_elem else ""
                
                # Combine title and summary for keyword analysis
                content_for_analysis = title + " " + summary
                
                # Find matching keywords
                found_keywords = []
                threat_level = "low"
                
                for keyword in important_keywords:
                    if keyword in content_for_analysis:
                        found_keywords.append(keyword)
                
                # Determine threat level based on keywords found
                if found_keywords:
                    critical_threat_terms = {"हत्या", "आतंकवाद", "बम", "विस्फोट", "अपहरण", "बलात्कार", "आगजनी", "गोली"}
                    high_threat_terms = {"पक्राउ", "धरौटी", "प्रदर्शन", "हिंसा", "घोटाला", "भ्रष्टाचार", "सेना", "प्रहरी"}
                    medium_threat_terms = {"जेनजेड", "युवा", "दुर्गा पार्साई", "साइबर", "अदालत", "मुद्दा"}
                    
                    if any(term in found_keywords for term in critical_threat_terms):
                        threat_level = "critical"
                    elif any(term in found_keywords for term in high_threat_terms):
                        threat_level = "high"
                    elif any(term in found_keywords for term in medium_threat_terms):
                        threat_level = "medium"
                    else:
                        threat_level = "low"
                
                # Determine specific categories
                categories = []
                category_mapping = {
                    "GenZ": {"जेनजेड", "जेन जेड", "युवा", "युवती", "युवक", "छात्र", "टिकटक", "सोशल मिडिया"},
                    "Durga_Parsai": {"दुर्गा पार्साई", "पार्साई", "दुर्गा", "पारसाई", "डीपी"},
                    "Army": {"सेना", "नेपाली सेना", "सैनिक", "सशस्त्र", "जेवी", "सेना प्रमुख"},
                    "Police": {"प्रहरी", "नेपाल प्रहरी", "प्रहरी अधिकारी", "आइजीपी", "सीआईडी"},
                    "APF": {"एपीएफ", "सशस्त्र प्रहरी", "आर्म्ड पुलिस"},
                    "Cyber_Crime": {"साइबर", "ह्याक", "फिसिङ", "डाटा", "अनलाइन"},
                    "Violence": {"हत्या", "हिंसा", "मारपीट", "आक्रमण", "गोली", "बम"},
                    "Protest": {"प्रदर्शन", "आन्दोलन", "धर्ना", "हड्ताल", "रैली"},
                    "Terrorism": {"आतंकवाद", "आतंकी", "उग्रवाद", "माओवादी"},
                    "Government": {"प्रधानमन्त्री", "राष्ट्रपति", "सरकार", "मन्त्री"},
                    "Legal": {"अदालत", "सुनुवाइ", "न्याय", "जेल", "मुद्दा"}
                }
                
                for cat, terms in category_mapping.items():
                    if any(term in found_keywords for term in terms):
                        categories.append(cat)
                
                if not categories:
                    categories = ["Other"]
                
                # Image
                img_elem = article.find("img")
                image_url = ""
                if img_elem and img_elem.get("data-src"):
                    image_url = img_elem["data-src"]
                    image_url = image_url.replace("-lowquality", "").replace("300x0", "1000x0")
                
                # Date from URL
                date_str = "Unknown"
                if relative_link:
                    parts = [p for p in relative_link.split("/") if p]
                    if len(parts) >= 4 and parts[0] == "news":
                        try:
                            year, month, day = parts[1], parts[2], parts[3]
                            date_str = f"{day} {month} {year}"
                        except:
                            pass
                
                article_data = {
                    "id": i + 1,
                    "title": title,
                    "summary": summary,
                    "url": full_link,
                    "image_url": image_url,
                    "date": date_str,
                    "source": "ekantipur",
                    "threat_analysis": {
                        "level": threat_level,
                        "keywords_found": found_keywords,
                        "total_keywords_matched": len(found_keywords),
                        "categories": categories
                    },
                    "content_length": len(content_for_analysis),
                    "priority": "high" if threat_level in ["critical", "high"] else "normal"
                }
                
                output["articles"].append(article_data)
                
            except Exception as e:
                print(f"Skipping article {i} due to error: {e}")
                continue
        
        # Calculate statistics
        total_articles = len(output["articles"])
        articles_with_threats = len([a for a in output["articles"] if a["threat_analysis"]["keywords_found"]])
        
        output["metadata"]["articles_found"] = total_articles
        output["metadata"]["articles_with_threats"] = articles_with_threats
        output["metadata"]["threat_coverage"] = f"{(articles_with_threats/total_articles)*100:.1f}%" if total_articles > 0 else "0%"
        
        # Threat level distribution
        threat_distribution = {}
        for article in output["articles"]:
            level = article["threat_analysis"]["level"]
            threat_distribution[level] = threat_distribution.get(level, 0) + 1
        output["metadata"]["threat_distribution"] = threat_distribution
        
        # Convert to JSON string
        json_output = json.dumps(output, indent=2, ensure_ascii=False)
        return json_output
        
    except Exception as e:
        error_output = {
            "metadata": {
                "source": "Kantipur Daily", 
                "url": url,
                "scraped_at": datetime.now().isoformat(),
                "status": "error",
                "error": str(e)
            },
            "articles": []
        }
        return json.dumps(error_output, indent=2)

# Run it
if __name__ == "__main__":
    json_data = kantipur_to_json()
    # # Save to file
    # with open("kantipur_threat_analysis.json", "w", encoding="utf-8") as f:
    #     f.write(json_data)
    # print("✅ Saved to kantipur_threat_analysis.json")