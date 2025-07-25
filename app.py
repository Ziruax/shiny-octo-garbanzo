# app.py
import streamlit as st
import requests
from bs4 import BeautifulSoup
import time
import random
from fake_useragent import UserAgent
import pandas as pd
from urllib.parse import urljoin, urlparse
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
    group_items = soup.find_all('div', class_=lambda x: x and ('view-tenth' in x or 'group-container' in x))
    
    for item in group_items:
        try:
            link_tag = item.find('a', href=lambda href: href and 'chat.whatsapp.com' in href)
            if not link_tag:
                continue
                
            href = link_tag.get('href', '').strip()
            if not href:
                continue
                
            title_tag = (item.find('h3') or 
                        item.find('p', class_=lambda x: x and 'title' in x) or 
                        item.find('div', class_=lambda x: x and 'title' in x) or 
                        link_tag)
            
            title = title_tag.get_text(strip=True) if title_tag else "No Title"
            
            img_tag = item.find('img')
            img_src = img_tag.get('src', '') if img_tag else ''
            
            groups.append({
                'Source': 'Groupda.com',
                'Title': title,
                'Link': href,
                'Image_URL': img_src
            })
        except:
            continue
            
    return groups

def scrape_groupda(category_value="3", country_value="", language_value="", max_pages=None):
    """Improved Groupda.com scraper with better error handling"""
    find_url = "https://groupda.com/add/group/find"
    load_url = "https://groupda.com/add/group/loadresult"
    results = []
    page_counter = 0  # Initialize counter
    
    session = requests.Session()
    
    try:
        st.write("🚀 Initializing Groupda.com session...")
        
        # 1. Initial GET request
        init_headers = get_random_headers(referer="https://groupda.com/add/")
        init_response = session.get(find_url, headers=init_headers, timeout=DEFAULT_TIMEOUT)
        init_response.raise_for_status()
        st.success("✅ Initial find page fetched successfully")
        
        # 2. Prepare AJAX request
        post_data = {
            'group_no': str(page_counter),
            'gcid': category_value if category_value else '3',
            'cid': country_value,
            'lid': language_value,
            'findPage': 'true',
            'home': 'true',
            '_': str(int(time.time() * 1000))
        }
        
        ajax_headers = get_random_headers(referer=find_url)
        ajax_headers.update({
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Origin': 'https://groupda.com',
        })
        
        st.write("🔍 Loading initial results...")
        response = session.post(load_url, data=post_data, headers=ajax_headers)
        
        if response.status_code != 200 or not response.text.strip():
            st.error(f"❌ AJAX call failed (Status {response.status_code})")
            st.text(f"Response: {response.text[:200]}...")
            return pd.DataFrame()
            
        soup = BeautifulSoup(response.text, 'html.parser')
        initial_groups = parse_groupda_containers(soup)
        
        if not initial_groups:
            st.warning("⚠️ No groups found in initial load")
            return pd.DataFrame()
            
        results.extend(initial_groups)
        page_counter += 1
        st.success(f"✅ Found {len(initial_groups)} groups on initial load")
        
        # Pagination
        while True:
            if max_pages and page_counter >= max_pages:
                st.info(f"ℹ️ Reached maximum pages limit ({max_pages})")
                break
                
            delay = random.uniform(DEFAULT_DELAY_MIN, DEFAULT_DELAY_MAX)
            st.write(f"⏳ Waiting {delay:.1f} seconds...")
            time.sleep(delay)
            
            st.write(f"🔍 Scraping page {page_counter + 1}...")
            post_data['group_no'] = str(page_counter)
            
            try:
                response = session.post(load_url, data=post_data, headers=ajax_headers)
                if response.status_code != 200 or not response.text.strip():
                    st.info("ℹ️ No more results found")
                    break
                    
                soup = BeautifulSoup(response.text, 'html.parser')
                page_groups = parse_groupda_containers(soup)
                
                if not page_groups:
                    st.info("ℹ️ No more groups found")
                    break
                    
                results.extend(page_groups)
                page_counter += 1
            except Exception as e:
                st.error(f"❌ Error loading page: {str(e)}")
                break
                
    except Exception as e:
        st.error(f"❌ Critical error: {str(e)}")
        return pd.DataFrame()
    
    st.success(f"🏁 Finished. Pages: {page_counter}, Groups: {len(results)}")
    return pd.DataFrame(results)

def parse_groupsor_containers(soup):
    """Improved parsing for Groupsor.link containers"""
    groups = []
    join_base_url = "https://chat.whatsapp.com/invite/"
    
    group_items = soup.find_all('div', class_=lambda x: x and ('view-tenth' in x or 'group-item' in x))
    
    for item in group_items:
        try:
            link_tag = (item.find('a', href=lambda href: href and 'chat.whatsapp.com' in href) or 
                       item.find('a', href=lambda href: href and '/group/join/' in href))
            
            if not link_tag:
                continue
                
            href = link_tag.get('href', '').strip()
            if not href:
                continue
                
            if '/group/join/' in href:
                group_id = href.split('/group/join/')[-1]
                href = urljoin(join_base_url, group_id)
                
            title_tag = (item.find('h3') or 
                        item.find('p', class_=lambda x: x and 'title' in x) or 
                        item.find('div', class_=lambda x: x and 'title' in x) or 
                        link_tag)
            
            title = title_tag.get_text(strip=True) if title_tag else "No Title"
            
            img_tag = item.find('img')
            img_src = img_tag.get('src', '') if img_tag else ''
            
            groups.append({
                'Source': 'Groupsor.link',
                'Title': title,
                'Link': href,
                'Image_URL': img_src
            })
        except:
            continue
            
    return groups

def scrape_groupsor(category_value="", country_value="", language_value="", max_pages=None):
    """Improved Groupsor.link scraper with Selenium"""
    find_url = "https://groupsor.link/group/find"
    results = []
    page_counter = 0
    
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument(f'user-agent={ua.random}')
    
    driver = None
    try:
        st.write("🚀 Initializing Groupsor.link with Selenium...")
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        driver.get(find_url)
        
        # Apply filters if specified
        if category_value or country_value or language_value:
            st.write("⚙️ Applying filters...")
            filter_url = f"{find_url}?"
            if category_value:
                filter_url += f"gcid={category_value}&"
            if country_value:
                filter_url += f"cid={country_value}&"
            if language_value:
                filter_url += f"lid={language_value}&"
            driver.get(filter_url.rstrip('&'))
        
        st.write("🌐 Waiting for page to load...")
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".view-tenth, #load_more"))
        )
        
        # Parse initial results
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        initial_groups = parse_groupsor_containers(soup)
        
        if initial_groups:
            results.extend(initial_groups)
            page_counter += 1
            st.success(f"✅ Found {len(initial_groups)} groups on initial load")
            
            # Pagination
            while True:
                if max_pages and page_counter >= max_pages:
                    st.info(f"ℹ️ Reached maximum pages limit ({max_pages})")
                    break
                    
                try:
                    load_more = driver.find_element(By.ID, 'load_more')
                    driver.execute_script("arguments[0].click();", load_more)
                    time.sleep(random.uniform(2, 4))
                    
                    WebDriverWait(driver, 15).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, f".view-tenth:nth-child({len(results) + 1})"))
                    )
                    
                    soup = BeautifulSoup(driver.page_source, 'html.parser')
                    new_groups = parse_groupsor_containers(soup)
                    
                    if not new_groups or len(new_groups) <= len(results):
                        st.info("ℹ️ No more groups found")
                        break
                        
                    results = new_groups
                    page_counter += 1
                    st.write(f"🔍 Found {len(results)} groups so far...")
                except:
                    st.info("ℹ️ No more pages available")
                    break
        else:
            st.warning("⚠️ No groups found initially")
            
    except Exception as e:
        st.error(f"❌ Error: {str(e)}")
    finally:
        if driver:
            driver.quit()
    
    st.success(f"🏁 Finished. Pages: {page_counter}, Groups: {len(results)}")
    return pd.DataFrame(results)

# --- Streamlit UI ---
st.title("🚀 WhatsApp Group Scraper")

# Sidebar filters
site_choice = st.sidebar.selectbox(
    "Select Website:",
    ("Groupda.com", "Groupsor.link", "Both")
)

# Groupda.com filters
if site_choice in ["Groupda.com", "Both"]:
    st.sidebar.subheader("Groupda.com Filters")
    category_gd = st.sidebar.selectbox(
        "Category:",
        ["Default (18+)", "Girls Group", "Gaming/Apps", "Health/Beauty", "Business/Marketing"],
        key="gd_cat"
    )
    country_gd = st.sidebar.selectbox(
        "Country:",
        ["Any Country", "India", "USA", "UK", "Canada"],
        key="gd_country"
    )

# Groupsor.link filters
if site_choice in ["Groupsor.link", "Both"]:
    st.sidebar.subheader("Groupsor.link Filters")
    category_gs = st.sidebar.selectbox(
        "Category:",
        ["Any Category", "Adult/18+", "Gaming/Apps", "Health/Beauty", "Business"],
        key="gs_cat"
    )
    country_gs = st.sidebar.selectbox(
        "Country:",
        ["Any Country", "India", "USA", "UK", "Canada"],
        key="gs_country"
    )

max_pages = st.sidebar.number_input(
    "Max Pages (0 for unlimited):",
    min_value=0,
    max_value=50,
    value=5
)

if st.sidebar.button("🚀 Start Scraping", type="primary"):
    all_data = []
    
    if site_choice in ["Groupda.com", "Both"]:
        with st.spinner("🔍 Scraping Groupda.com..."):
            df_gd = scrape_groupda(
                category_value="3" if category_gd == "Default (18+)" else "",
                country_value="99" if country_gd == "India" else "",
                max_pages=max_pages if max_pages > 0 else None
            )
            if not df_gd.empty:
                all_data.append(df_gd)
    
    if site_choice in ["Groupsor.link", "Both"]:
        with st.spinner("🔍 Scraping Groupsor.link..."):
            df_gs = scrape_groupsor(
                category_value="7" if category_gs == "Adult/18+" else "",
                country_value="29" if country_gs == "India" else "",
                max_pages=max_pages if max_pages > 0 else None
            )
            if not df_gs.empty:
                all_data.append(df_gs)
    
    if all_data:
        final_df = pd.concat(all_data, ignore_index=True)
        st.subheader("📊 Results")
        st.dataframe(final_df)
        
        csv = final_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            "💾 Download CSV",
            csv,
            "whatsapp_groups.csv",
            "text/csv"
        )
    else:
        st.warning("⚠️ No data scraped. Try adjusting filters.")

st.info("💡 Tip: For Groupsor.link, scraping may be slower due to Cloudflare protection.")
