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
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import os

# Configuration
DEFAULT_DELAY_MIN = 3
DEFAULT_DELAY_MAX = 7
DEFAULT_TIMEOUT = 30
MAX_PAGES_DEFAULT = 5

# Initialize UserAgent
ua = UserAgent()

def get_random_headers(referer=None):
    headers = {
        'User-Agent': ua.random,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    if referer:
        headers['Referer'] = referer
    return headers

def parse_groupda_containers(soup):
    groups = []
    containers = soup.find_all('div', class_=lambda x: x and ('view-tenth' in x or 'group-container' in x))
    
    for item in containers:
        try:
            link = item.find('a', href=lambda href: href and 'chat.whatsapp.com' in href)
            if not link:
                continue
                
            groups.append({
                'Source': 'Groupda.com',
                'Title': link.get_text(strip=True) or "No Title",
                'Link': link['href'],
                'Image_URL': item.find('img')['src'] if item.find('img') else ''
            })
        except:
            continue
    return groups

def scrape_groupda(category_value="3", country_value="", language_value="", max_pages=None):
    find_url = "https://groupda.com/add/group/find"
    load_url = "https://groupda.com/add/group/loadresult"
    results = []
    page_counter = 0
    
    session = requests.Session()
    
    try:
        st.write("🚀 Initializing Groupda.com session...")
        
        # First make a GET request to get cookies
        init_response = session.get(find_url, headers=get_random_headers(), timeout=DEFAULT_TIMEOUT)
        init_response.raise_for_status()
        
        # Prepare AJAX request
        post_data = {
            'group_no': '0',
            'gcid': category_value,
            'cid': country_value,
            'lid': language_value,
            'findPage': 'true',
            'home': 'true',
            '_': str(int(time.time() * 1000))
        }
        
        headers = get_random_headers(referer=find_url)
        headers.update({
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Origin': 'https://groupda.com'
        })
        
        st.write("🔍 Loading initial results...")
        response = session.post(load_url, data=post_data, headers=headers)
        
        if response.status_code == 200 and response.text.strip():
            soup = BeautifulSoup(response.text, 'html.parser')
            groups = parse_groupda_containers(soup)
            
            if groups:
                results.extend(groups)
                page_counter = 1
                st.success(f"✅ Found {len(groups)} groups on initial load")
                
                # Pagination
                while True:
                    if max_pages and page_counter >= max_pages:
                        break
                        
                    time.sleep(random.uniform(DEFAULT_DELAY_MIN, DEFAULT_DELAY_MAX))
                    
                    post_data['group_no'] = str(page_counter)
                    response = session.post(load_url, data=post_data, headers=headers)
                    
                    if response.status_code != 200 or not response.text.strip():
                        break
                        
                    soup = BeautifulSoup(response.text, 'html.parser')
                    new_groups = parse_groupda_containers(soup)
                    
                    if not new_groups:
                        break
                        
                    results.extend(new_groups)
                    page_counter += 1
            else:
                st.warning("⚠️ No groups found in initial load")
        else:
            st.error(f"❌ AJAX call failed (Status {response.status_code})")
            st.text(f"Response: {response.text[:200]}...")
            
    except Exception as e:
        st.error(f"❌ Error: {str(e)}")
    
    st.success(f"🏁 Finished Groupda.com. Pages: {page_counter}, Groups: {len(results)}")
    return pd.DataFrame(results)

def setup_selenium():
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument(f'user-agent={ua.random}')
    
    # Fix for ChromeDriver in Linux environments
    chrome_options.binary_location = os.getenv('GOOGLE_CHROME_BIN', '/usr/bin/google-chrome')
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def scrape_groupsor(category_value="", country_value="", language_value="", max_pages=None):
    find_url = "https://groupsor.link/group/find"
    results = []
    page_counter = 0
    
    try:
        st.write("🚀 Initializing Groupsor.link with Selenium...")
        driver = setup_selenium()
        driver.get(find_url)
        
        # Wait for page to load
        time.sleep(5)  # Increased wait time for Cloudflare
        
        # Parse initial results
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        groups = parse_groupsor_containers(soup)
        
        if groups:
            results.extend(groups)
            page_counter = 1
            st.success(f"✅ Found {len(groups)} groups on initial load")
            
            # Pagination
            while True:
                if max_pages and page_counter >= max_pages:
                    break
                    
                try:
                    load_button = driver.find_element('id', 'load_more')
                    driver.execute_script("arguments[0].click();", load_button)
                    time.sleep(random.uniform(3, 5))  # Wait for content to load
                    
                    soup = BeautifulSoup(driver.page_source, 'html.parser')
                    new_groups = parse_groupsor_containers(soup)
                    
                    if not new_groups or len(new_groups) <= len(results):
                        break
                        
                    results = new_groups
                    page_counter += 1
                except:
                    break
        else:
            st.warning("⚠️ No groups found initially")
            
    except Exception as e:
        st.error(f"❌ Error: {str(e)}")
    finally:
        if 'driver' in locals():
            driver.quit()
    
    st.success(f"🏁 Finished Groupsor.link. Pages: {page_counter}, Groups: {len(results)}")
    return pd.DataFrame(results)

def parse_groupsor_containers(soup):
    groups = []
    join_base = "https://chat.whatsapp.com/invite/"
    
    for item in soup.find_all('div', class_='view-tenth'):
        try:
            link = item.find('a', href=lambda href: href and ('chat.whatsapp.com' in href or '/group/join/' in href))
            if not link:
                continue
                
            href = link['href']
            if '/group/join/' in href:
                href = join_base + href.split('/group/join/')[-1]
                
            title = item.find('h3').get_text(strip=True) if item.find('h3') else "No Title"
            img = item.find('img')['src'] if item.find('img') else ''
            
            groups.append({
                'Source': 'Groupsor.link',
                'Title': title,
                'Link': href,
                'Image_URL': img
            })
        except:
            continue
    return groups

# Streamlit UI
st.title("WhatsApp Group Scraper")

site_choice = st.sidebar.selectbox(
    "Select Website:",
    ["Groupda.com", "Groupsor.link", "Both"]
)

max_pages = st.sidebar.number_input(
    "Max Pages (0 for unlimited):",
    min_value=0,
    max_value=50,
    value=5
)

if st.sidebar.button("Start Scraping"):
    all_data = []
    
    if site_choice in ["Groupda.com", "Both"]:
        with st.spinner("Scraping Groupda.com..."):
            df_gd = scrape_groupda(max_pages=max_pages if max_pages > 0 else None)
            if not df_gd.empty:
                all_data.append(df_gd)
    
    if site_choice in ["Groupsor.link", "Both"]:
        with st.spinner("Scraping Groupsor.link..."):
            df_gs = scrape_groupsor(max_pages=max_pages if max_pages > 0 else None)
            if not df_gs.empty:
                all_data.append(df_gs)
    
    if all_data:
        final_df = pd.concat(all_data, ignore_index=True)
        st.dataframe(final_df)
        
        csv = final_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            "Download CSV",
            csv,
            "whatsapp_groups.csv",
            "text/csv"
        )
    else:
        st.warning("No data scraped. Try adjusting filters.")
