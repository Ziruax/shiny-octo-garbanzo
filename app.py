# app.py
import streamlit as st
import requests
from bs4 import BeautifulSoup
import time
import random
from fake_useragent import UserAgent
import pandas as pd
from urllib.parse import urljoin, urlparse
import json
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# Initialize a global UserAgent object
ua = UserAgent()

# --- Configuration ---
DEFAULT_DELAY_MIN = 3  # Increased to avoid blocking
DEFAULT_DELAY_MAX = 7
DEFAULT_TIMEOUT = 30
MAX_PAGES_DEFAULT = 5

# Function to get a random header
def get_random_headers(referer=None):
    headers = {
        'User-Agent': ua.random,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'same-origin',
    }
    if referer:
        headers['Referer'] = referer
    return headers

# --- Scraping Functions ---

def parse_groupda_containers(soup):
    """Improved parsing for Groupda.com containers"""
    groups = []
    # Multiple possible selectors for robustness
    group_items = soup.find_all('div', class_=lambda x: x and ('view-tenth' in x or 'group-container' in x))
    
    for item in group_items:
        try:
            # Find WhatsApp link - checking multiple possible locations
            link_tag = (item.find('a', href=lambda href: href and 'chat.whatsapp.com' in href) or 
                       item.find('a', class_=lambda x: x and 'group-link' in x))
            
            if not link_tag:
                continue
                
            href = link_tag.get('href', '').strip()
            if not href:
                continue
                
            # Improved title extraction
            title_tag = (item.find('h3') or 
                        item.find('p', class_=lambda x: x and 'title' in x) or 
                        item.find('div', class_=lambda x: x and 'title' in x) or 
                        link_tag)
            
            title = title_tag.get_text(strip=True) if title_tag else "No Title"
            
            # Improved image extraction
            img_tag = item.find('img')
            img_src = img_tag.get('src', '') if img_tag else ''
            
            groups.append({
                'Source': 'Groupda.com',
                'Title': title,
                'Link': href,
                'Image_URL': img_src
            })
        except Exception as e:
            continue
            
    return groups

def scrape_groupda(category_value="3", country_value="", language_value="", max_pages=None):
    """Improved Groupda.com scraper with better parameter handling"""
    find_url = "https://groupda.com/add/group/find"
    load_url = "https://groupda.com/add/group/loadresult"
    results = []
    
    session = requests.Session()
    
    try:
        st.write("🚀 Initializing Groupda.com session...")
        
        # 1. Initial GET request with proper headers
        init_headers = get_random_headers(referer="https://groupda.com/add/")
        init_response = session.get(find_url, headers=init_headers, timeout=DEFAULT_TIMEOUT)
        init_response.raise_for_status()
        st.success("✅ Initial find page fetched successfully")
        
        # 2. Prepare AJAX request with all required parameters
        post_data = {
            'group_no': '0',
            'gcid': category_value if category_value else '3',  # Default to 18+ category
            'cid': country_value,
            'lid': language_value,
            'findPage': 'true',
            'home': 'true',  # Critical parameter
            '_': str(int(time.time() * 1000))  # Timestamp
        }
        
        ajax_headers = get_random_headers(referer=find_url)
        ajax_headers.update({
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Origin': 'https://groupda.com',
        })
        
        st.write("🔍 Loading initial results...")
        response = session.post(load_url, data=post_data, headers=ajax_headers)
        
        if response.status_code == 200 and response.text.strip():
            soup = BeautifulSoup(response.text, 'html.parser')
            initial_groups = parse_groupda_containers(soup)
            
            if initial_groups:
                results.extend(initial_groups)
                st.success(f"✅ Found {len(initial_groups)} groups on initial load")
                
                # Pagination logic
                page_counter = 1
                while True:
                    if max_pages and page_counter >= max_pages:
                        st.info(f"ℹ️ Reached maximum pages limit ({max_pages})")
                        break
                        
                    delay = random.uniform(DEFAULT_DELAY_MIN, DEFAULT_DELAY_MAX)
                    st.write(f"⏳ Waiting {delay:.1f} seconds before next page...")
                    time.sleep(delay)
                    
                    st.write(f"🔍 Scraping page {page_counter + 1}...")
                    post_data['group_no'] = str(page_counter)
                    
                    response = session.post(load_url, data=post_data, headers=ajax_headers)
                    
                    if response.status_code != 200:
                        st.warning(f"⚠️ Page {page_counter + 1} failed (Status {response.status_code})")
                        break
                        
                    if not response.text.strip():
                        st.info("ℹ️ No more results found")
                        break
                        
                    soup = BeautifulSoup(response.text, 'html.parser')
                    page_groups = parse_groupda_containers(soup)
                    
                    if not page_groups:
                        st.info("ℹ️ No more groups found")
                        break
                        
                    results.extend(page_groups)
                    page_counter += 1
            else:
                st.warning("⚠️ No groups found in initial load - check filters")
        else:
            st.error(f"❌ AJAX call failed (Status {response.status_code})")
            st.text(f"Response snippet: {response.text[:200]}...")
            
    except Exception as e:
        st.error(f"❌ Error scraping Groupda.com: {str(e)}")
        return pd.DataFrame()
    
    st.success(f"🏁 Finished Groupda.com. Pages: {page_counter}, Groups: {len(results)}")
    return pd.DataFrame(results)

def parse_groupsor_containers(soup):
    """Improved parsing for Groupsor.link containers"""
    groups = []
    join_base_url = "https://chat.whatsapp.com/invite/"
    
    # Multiple possible selectors for robustness
    group_items = soup.find_all('div', class_=lambda x: x and ('view-tenth' in x or 'group-item' in x))
    
    for item in group_items:
        try:
            # Try multiple link locations
            link_tag = (item.find('a', href=lambda href: href and 'chat.whatsapp.com' in href) or 
                       item.find('a', href=lambda href: href and '/group/join/' in href) or
                       item.find('a', class_=lambda x: x and 'group-link' in x))
            
            if not link_tag:
                continue
                
            href = link_tag.get('href', '').strip()
            if not href:
                continue
                
            # Transform join links to WhatsApp links
            if '/group/join/' in href:
                group_id = href.split('/group/join/')[-1]
                href = urljoin(join_base_url, group_id)
                
            # Improved title extraction
            title_tag = (item.find('h3') or 
                        item.find('p', class_=lambda x: x and 'title' in x) or 
                        item.find('div', class_=lambda x: x and 'title' in x) or 
                        link_tag)
            
            title = title_tag.get_text(strip=True) if title_tag else "No Title"
            
            # Improved image extraction
            img_tag = item.find('img')
            img_src = img_tag.get('src', '') if img_tag else ''
            
            groups.append({
                'Source': 'Groupsor.link',
                'Title': title,
                'Link': href,
                'Image_URL': img_src
            })
        except Exception as e:
            continue
            
    return groups

def scrape_groupsor(category_value="", country_value="", language_value="", max_pages=None):
    """Improved Groupsor.link scraper with Selenium"""
    find_url = "https://groupsor.link/group/find"
    load_url = "https://groupsor.link/group/indexmore"
    results = []
    
    # Set up Selenium options
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument(f'user-agent={ua.random}')
    
    # Initialize driver
    driver = None
    try:
        st.write("🚀 Initializing Groupsor.link with Selenium...")
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        
        # Load initial page
        driver.get(find_url)
        st.write("🌐 Waiting for page to load...")
        
        # Wait for either groups to load or the "Load more" button
        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".view-tenth, #load_more"))
            )
        except:
            st.warning("⚠️ Timed out waiting for page elements")
        
        # Parse initial results
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        initial_groups = parse_groupsor_containers(soup)
        
        if initial_groups:
            results.extend(initial_groups)
            st.success(f"✅ Found {len(initial_groups)} groups on initial load")
            
            # Pagination logic
            page_counter = 1
            while True:
                if max_pages and page_counter >= max_pages:
                    st.info(f"ℹ️ Reached maximum pages limit ({max_pages})")
                    break
                    
                # Try to click "Load more" button
                try:
                    load_more = driver.find_element(By.ID, 'load_more')
                    driver.execute_script("arguments[0].click();", load_more)
                    
                    # Wait for new content to load
                    time.sleep(random.uniform(2, 4))
                    WebDriverWait(driver, 15).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, f".view-tenth:nth-child({len(results) + 1})"))
                    )
                    
                    # Parse new results
                    soup = BeautifulSoup(driver.page_source, 'html.parser')
                    new_groups = parse_groupsor_containers(soup)
                    
                    if not new_groups or len(new_groups) <= len(results):
                        st.info("ℹ️ No more groups found")
                        break
                        
                    results = new_groups  # Replace with all current groups
                    page_counter += 1
                    st.write(f"🔍 Found {len(results)} groups so far...")
                    
                except Exception as e:
                    st.info("ℹ️ No more pages available")
                    break
        else:
            st.warning("⚠️ No groups found initially - check if filters are needed")
            
    except Exception as e:
        st.error(f"❌ Error scraping Groupsor.link: {str(e)}")
    finally:
        if driver:
            driver.quit()
    
    st.success(f"🏁 Finished Groupsor.link. Pages: {page_counter}, Groups: {len(results)}")
    return pd.DataFrame(results)

# --- Streamlit UI ---
st.title("🚀 WhatsApp Group Scraper")
st.markdown("Scrape WhatsApp group links from Groupda.com and Groupsor.link")

# --- Sidebar for Inputs ---
st.sidebar.header("⚙️ Scraper Settings")

site_choice = st.sidebar.selectbox(
    "Select Website to Scrape:",
    ("Groupda.com", "Groupsor.link", "Both"),
    index=0
)

# Updated options based on current websites
category_options_groupda = {
    "Default (18+)": "3",
    "Any Category": "",
    "Girls Group": "2",
    "Gaming/Apps": "7",
    "Health/Beauty": "8",
    "Business/Marketing": "6",
    "Sports/Games": "21",
    "Film/Animation": "18",
    "Fashion/Style": "15",
    "Comedy/Funny": "9",
    "Education": "11",
    "Entertainment": "12",
    "Family": "13",
    "Celebrities": "14",
    "Money Online": "16",
    "MLM Groups": "17",
    "Spiritual": "19",
    "Cricket": "20",
    "Food/Recipes": "22",
    "Crypto/Betting": "23"
}

country_options_simple = {
    "Any Country": "",
    "India": "99",
    "USA": "223",
    "UK": "222",
    "Canada": "38",
    "Australia": "13"
}

language_options_simple = {
    "Any Language": "",
    "English": "17",
    "Hindi": "26",
    "Spanish": "51",
    "French": "20",
    "German": "23"
}

category_options_groupsor = {
    "Any Category": "",
    "Adult/18+": "7",
    "Gaming/Apps": "18",
    "Health/Beauty": "19",
    "Business": "8",
    "Sports": "28",
    "Film": "16",
    "Fashion": "15",
    "Comedy": "9",
    "Education": "11",
    "Entertainment": "12",
    "Family": "13",
    "Celebrities": "14",
    "Money": "22",
    "Music": "21",
    "News": "23",
    "Pets": "24",
    "Roleplay": "25",
    "Tech": "26",
    "Shopping": "27",
    "Social": "30",
    "Spiritual": "29",
    "Quotes": "31",
    "Travel": "32"
}

country_options_simple_gs = {
    "Any Country": "",
    "India": "29",
    "USA": "87",
    "UK": "86",
    "Canada": "12",
    "Australia": "3"
}

language_options_simple_gs = {
    "Any Language": "",
    "English": "11",
    "Hindi": "69",
    "Spanish": "12",
    "French": "29",
    "German": "9"
}

# Initialize variables
selected_category_value_gd = "3"
selected_country_value_gd = ""
selected_language_value_gd = ""
selected_category_value_gs = ""
selected_country_value_gs = ""
selected_language_value_gs = ""

if site_choice in ["Groupda.com", "Both"]:
    st.sidebar.subheader("Groupda.com Filters")
    selected_category_name_gd = st.sidebar.selectbox(
        "Category (Groupda):",
        list(category_options_groupda.keys()),
        key="gd_cat",
        index=0
    )
    selected_category_value_gd = category_options_groupda[selected_category_name_gd]
    
    selected_country_name_gd = st.sidebar.selectbox(
        "Country (Groupda):",
        list(country_options_simple.keys()),
        key="gd_country"
    )
    selected_country_value_gd = country_options_simple[selected_country_name_gd]
    
    selected_language_name_gd = st.sidebar.selectbox(
        "Language (Groupda):",
        list(language_options_simple.keys()),
        key="gd_lang"
    )
    selected_language_value_gd = language_options_simple[selected_language_name_gd]

if site_choice in ["Groupsor.link", "Both"]:
    st.sidebar.subheader("Groupsor.link Filters")
    selected_category_name_gs = st.sidebar.selectbox(
        "Category (Groupsor):",
        list(category_options_groupsor.keys()),
        key="gs_cat"
    )
    selected_category_value_gs = category_options_groupsor[selected_category_name_gs]
    
    selected_country_name_gs = st.sidebar.selectbox(
        "Country (Groupsor):",
        list(country_options_simple_gs.keys()),
        key="gs_country"
    )
    selected_country_value_gs = country_options_simple_gs[selected_country_name_gs]
    
    selected_language_name_gs = st.sidebar.selectbox(
        "Language (Groupsor):",
        list(language_options_simple_gs.keys()),
        key="gs_lang"
    )
    selected_language_value_gs = language_options_simple_gs[selected_language_name_gs]

max_pages_input = st.sidebar.number_input(
    "Max Pages per Site (0 for unlimited):",
    min_value=0,
    max_value=50,
    value=5,
    step=1
)
max_pages = None if max_pages_input == 0 else max_pages_input

if st.sidebar.button("🚀 Start Scraping", type="primary"):
    all_data = []
    
    if site_choice in ["Groupda.com", "Both"]:
        with st.spinner(f"🔍 Scraping Groupda.com (Category: {selected_category_name_gd})..."):
            df_groupda = scrape_groupda(
                category_value=selected_category_value_gd,
                country_value=selected_country_value_gd,
                language_value=selected_language_value_gd,
                max_pages=max_pages
            )
            if not df_groupda.empty:
                all_data.append(df_groupda)

    if site_choice in ["Groupsor.link", "Both"]:
        with st.spinner(f"🔍 Scraping Groupsor.link (Category: {selected_category_name_gs})..."):
            df_groupsor = scrape_groupsor(
                category_value=selected_category_value_gs,
                country_value=selected_country_value_gs,
                language_value=selected_language_value_gs,
                max_pages=max_pages
            )
            if not df_groupsor.empty:
                all_data.append(df_groupsor)

    if all_data:
        final_df = pd.concat(all_data, ignore_index=True)
        st.subheader("📊 Scraped Results")
        st.dataframe(final_df)
        
        # Add download button
        csv = final_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="💾 Download as CSV",
            data=csv,
            file_name='whatsapp_groups.csv',
            mime='text/csv',
        )
        
        # Show stats
        st.success(f"✅ Successfully scraped {len(final_df)} groups!")
    else:
        st.warning("⚠️ No data was scraped. Try adjusting filters or check if sites are blocking requests.")

# Add instructions
st.markdown("---")
st.subheader("📖 How To Use")
st.markdown("""
1. Select website(s) to scrape from the sidebar
2. Choose filters (category, country, language)
3. Set maximum pages to scrape (0 for unlimited)
4. Click "Start Scraping" button
5. View results and download as CSV
""")

st.subheader("⚠️ Important Notes")
st.markdown("""
- Groupsor.link uses Cloudflare protection and may be slower
- Some sites may block scrapers - try again later if it fails
- For best results, don't scrape too many pages at once
""")
