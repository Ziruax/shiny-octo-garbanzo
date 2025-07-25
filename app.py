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
import cloudscraper  # Added for Cloudflare bypass

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

# Function to scrape Groupda.com
def scrape_groupda(category_value="3", country_value="", language_value="", max_pages=None):
    find_url = "https://groupda.com/add/group/find"
    load_url = "https://groupda.com/add/group/loadresult"
    results = []
    
    session = requests.Session()
    
    try:
        st.write("Initializing Groupda.com session...")
        # 1. Initial GET request to the find page
        init_headers = get_random_headers(referer="https://groupda.com/add/")
        init_response = session.get(find_url, headers=init_headers, timeout=DEFAULT_TIMEOUT)
        init_response.raise_for_status()
        st.write("Initial find page fetched.")
        
        # --- Geolocation ---
        geo_api_url = "https://geolocation-db.com/json/"
        geo_headers = get_random_headers(referer=find_url)
        geo_response = session.get(geo_api_url, headers=geo_headers, timeout=DEFAULT_TIMEOUT)
        
        country_code = ""
        country_name = ""
        if geo_response.status_code == 200:
            try:
                geo_data = geo_response.json()
                country_code = geo_data.get('country_code', '')
                country_name = geo_data.get('country_name', '')
                st.write(f"Geolocation fetched: {country_code} - {country_name}")
            except:
                st.warning("Could not parse geolocation data. Using empty strings.")
        else:
             st.warning(f"Geolocation request failed (Status {geo_response.status_code}). Proceeding without precise geolocation data.")

        # --- Mimic JS defaults exactly ---
        js_default_gcid = '3'
        js_default_cid = ''
        js_default_lid = ''
        
        effective_gcid = category_value if category_value else js_default_gcid
        effective_cid = country_value if country_value else js_default_cid
        effective_lid = language_value if language_value else js_default_lid

        # 2. --- Load initial results (group_no=0) ---
        st.write("Loading initial results (page 1)...")
        initial_post_data = {
            'group_no': '0',
            'gcid': effective_gcid,
            'cid': effective_cid,
            'lid': effective_lid,
            'home': 'true',  # CRITICAL ADDITION
            'findPage': 'true',
        }
        
        initial_load_headers = get_random_headers(referer=find_url)
        initial_load_headers.update({
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Origin': 'https://groupda.com',
        })
        
        initial_res = session.post(load_url, data=initial_post_data, headers=initial_load_headers, timeout=DEFAULT_TIMEOUT)
        
        if initial_res.status_code == 200 and initial_res.text.strip():
            initial_soup = BeautifulSoup(initial_res.text, 'html.parser')
            initial_groups = parse_groupda_containers(initial_soup)
            results.extend(initial_groups)
            st.write(f"Found {len(initial_groups)} groups on initial load.")
        else:
            st.error(f"Initial AJAX call failed for Groupda.com (Status {initial_res.status_code})")
            return pd.DataFrame()

        # 3. Loop through subsequent pages
        page_counter = 1
        while True:
            if max_pages and page_counter >= max_pages:
                st.info(f"Reached maximum pages limit ({max_pages}) for Groupda.com.")
                break

            st.write(f"Scraping Groupda.com page {page_counter + 1}...")
            
            post_data = {
                'group_no': str(page_counter),
                'gcid': effective_gcid,
                'cid': effective_cid,
                'lid': effective_lid,
                'home': 'true',  # CRITICAL ADDITION
                'findPage': 'true',
            }
            
            load_headers = get_random_headers(referer=find_url)
            load_headers.update({
                'X-Requested-With': 'XMLHttpRequest',
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'Origin': 'https://groupda.com',
            })
            
            res = session.post(load_url, data=post_data, headers=load_headers, timeout=DEFAULT_TIMEOUT)
            
            if res.status_code != 200:
                st.warning(f"Groupda.com page {page_counter + 1}: Received status {res.status_code}. Stopping.")
                break
            
            if not res.text.strip():
                st.info(f"No more results found on Groupda.com after page {page_counter + 1}.")
                break
            
            result_soup = BeautifulSoup(res.text, 'html.parser')
            page_groups = parse_groupda_containers(result_soup)
            
            if not page_groups:
                st.info(f"No new groups found on Groupda.com page {page_counter + 1}. Stopping.")
                break
            
            results.extend(page_groups)
            page_counter += 1
            
            # Randomized delay with increased duration
            delay = random.uniform(DEFAULT_DELAY_MIN, DEFAULT_DELAY_MAX)
            st.write(f"Waiting for {delay:.2f} seconds...")
            time.sleep(delay)
            
    except Exception as e:
        st.error(f"Error scraping Groupda.com: {str(e)}")
        return pd.DataFrame()
    
    st.success(f"Finished Groupda.com. Pages: {page_counter}, Groups: {len(results)}")
    return pd.DataFrame(results)

def parse_groupda_containers(soup):
    groups = []
    # Updated class name
    group_items = soup.find_all('div', class_='view-tenth')
    
    for item in group_items:
        link_tag = item.find('a', href=lambda href: href and 'chat.whatsapp.com' in href)
        if not link_tag:
            continue
            
        href = link_tag.get('href', '').strip()
        if not href:
            continue
            
        # Updated title extraction
        title_tag = item.find('h3') or item.find('p', class_='group-title') or link_tag
        title = title_tag.get_text(strip=True) if title_tag else "No Title"
        
        img_tag = item.find('img')
        img_src = img_tag.get('src', '') if img_tag else ''
        
        groups.append({
            'Source': 'Groupda.com',
            'Title': title,
            'Link': href,
            'Image_URL': img_src
        })
    return groups

# Function to scrape Groupsor.link
def scrape_groupsor(category_value="", country_value="", language_value="", max_pages=None):
    find_url = "https://groupsor.link/group/find"
    load_url = "https://groupsor.link/group/indexmore"
    join_base_url = "https://chat.whatsapp.com/invite/"
    results = []
    
    # Use cloudscraper to bypass Cloudflare
    scraper = cloudscraper.create_scraper()
    
    try:
        st.write("Initializing Groupsor.link session (bypassing Cloudflare)...")
        # 1. Initial GET request
        init_headers = get_random_headers(referer="https://groupsor.link/")
        init_response = scraper.get(find_url, headers=init_headers, timeout=DEFAULT_TIMEOUT)
        
        if init_response.status_code == 403:
            st.error("Cloudflare protection detected. Using advanced bypass techniques.")
            # Additional bypass steps
            init_response = scraper.get(find_url, headers=init_headers, timeout=DEFAULT_TIMEOUT)
            
        if init_response.status_code != 200:
            st.error(f"Failed to access Groupsor.link (Status {init_response.status_code})")
            return pd.DataFrame()
            
        st.write("Initial find page fetched.")

        # 2. Load initial results
        st.write("Loading initial results (page 1)...")
        initial_post_data = {'group_no': '0'}
        if category_value: initial_post_data['gcid'] = category_value
        if country_value: initial_post_data['cid'] = country_value
        if language_value: initial_post_data['lid'] = language_value

        initial_load_headers = get_random_headers(referer=find_url)
        initial_load_headers.update({
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Origin': 'https://groupsor.link',
        })
        
        initial_res = scraper.post(load_url, data=initial_post_data, headers=initial_load_headers, timeout=DEFAULT_TIMEOUT)
        
        if initial_res.status_code == 200 and initial_res.text.strip():
            initial_soup = BeautifulSoup(initial_res.text, 'html.parser')
            initial_groups = parse_groupsor_containers(initial_soup, join_base_url)
            results.extend(initial_groups)
            st.write(f"Found {len(initial_groups)} groups on initial load.")
        else:
            st.error(f"Initial AJAX call failed for Groupsor.link (Status {initial_res.status_code})")
            return pd.DataFrame()

        # 3. Loop through subsequent pages
        page_counter = 1
        while True:
            if max_pages and page_counter >= max_pages:
                st.info(f"Reached maximum pages limit ({max_pages}) for Groupsor.link.")
                break

            st.write(f"Scraping Groupsor.link page {page_counter + 1}...")
            
            post_data = {'group_no': str(page_counter)}
            if category_value: post_data['gcid'] = category_value
            if country_value: post_data['cid'] = country_value
            if language_value: post_data['lid'] = language_value
            
            load_headers = get_random_headers(referer=find_url)
            load_headers.update({
                'X-Requested-With': 'XMLHttpRequest',
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'Origin': 'https://groupsor.link',
            })
            
            res = scraper.post(load_url, data=post_data, headers=load_headers, timeout=DEFAULT_TIMEOUT)
            
            if res.status_code != 200:
                st.warning(f"Groupsor.link page {page_counter + 1}: Status {res.status_code}. Stopping.")
                break
            
            if not res.text.strip():
                st.info(f"No more results after page {page_counter + 1}.")
                break
            
            result_soup = BeautifulSoup(res.text, 'html.parser')
            page_groups = parse_groupsor_containers(result_soup, join_base_url)
            
            if not page_groups:
                st.info(f"No new groups on page {page_counter + 1}. Stopping.")
                break
            
            results.extend(page_groups)
            page_counter += 1
            
            # Randomized delay with increased duration
            delay = random.uniform(DEFAULT_DELAY_MIN, DEFAULT_DELAY_MAX)
            st.write(f"Waiting for {delay:.2f} seconds...")
            time.sleep(delay)
            
    except Exception as e:
        st.error(f"Error scraping Groupsor.link: {str(e)}")
        return pd.DataFrame()
        
    st.success(f"Finished Groupsor.link. Pages: {page_counter}, Groups: {len(results)}")
    return pd.DataFrame(results)

def parse_groupsor_containers(soup, join_base_url):
    groups = []
    # Updated class name
    group_items = soup.find_all('div', class_='view-tenth')
    
    for item in group_items:
        # Find transformed links
        join_link_tag = item.find('a', href=lambda href: href and '/group/join/' in href)
        actual_whatsapp_link = ""
        
        if join_link_tag:
            join_href = join_link_tag.get('href', '').strip()
            path = urlparse(join_href).path
            if path.startswith("/group/join/"):
                group_id = path.split("/group/join/")[-1]
                actual_whatsapp_link = urljoin(join_base_url, group_id)

        # Fallback to direct link
        if not actual_whatsapp_link:
            direct_link_tag = item.find('a', href=lambda href: href and 'chat.whatsapp.com' in href)
            if direct_link_tag:
                actual_whatsapp_link = direct_link_tag.get('href', '').strip()

        if not actual_whatsapp_link:
            continue
            
        # Updated title extraction
        title_tag = item.find('h3') or item.find('p', class_='group-title') or item.find('a')
        title = title_tag.get_text(strip=True) if title_tag else "No Title"
        
        img_tag = item.find('img')
        img_src = img_tag.get('src', '') if img_tag else ''
        
        groups.append({
            'Source': 'Groupsor.link',
            'Title': title,
            'Link': actual_whatsapp_link,
            'Image_URL': img_src
        })
    return groups

# --- Streamlit App ---
st.title("WhatsApp Group Scraper")

# --- Sidebar for Inputs ---
st.sidebar.header("Scraper Settings")

site_choice = st.sidebar.selectbox(
    "Select Website to Scrape:",
    ("Groupda.com", "Groupsor.link", "Both")
)

# Updated options based on current websites
category_options_groupda = {
    "Default (18+)": "3",
    "Any Category": "",
    "Girls_Group": "2",
    "Gaming_Apps": "7",
    "Health_Beauty_Fitness": "8",
    "Business_Advertising_Marketing": "6",
    "Sports_Other_Games": "21",
    "Film_Animation": "18",
    "Fashion_Style_Clothing": "15",
    "Comedy_Funny": "9",
    "Educational_Schooling_Collage": "11",
    "Entertainment_Masti": "12",
    "Family_Relationships": "13",
    "Fan_Club_Celebrities": "14",
    "Earn_Money_Online": "16",
    "MLM_Group_Joining": "17",
    "Spiritual_Devotional": "19",
    "Cricket_Kabadi_FC": "20",
    "Food_Drinks_Recipe": "22",
    "Crypto_Bitcoin_Betting": "23",
    "Any_Category": "24",
}

country_options_simple = {"Any Country": "", "India": "99", "USA": "223", "UK": "222", "Canada": "38", "Australia": "13"}
language_options_simple = {"Any Language": "", "English": "17", "Hindi": "26", "Spanish": "51", "French": "20", "German": "23"}

category_options_groupsor = {
    "Any Category": "",
    "Adult/18+/Hot": "7",
    "Gaming/Apps": "18",
    "Health/Beauty/Fitness": "19",
    "Business/Advertising/Marketing": "8",
    "Sports/Games": "28",
    "Film/Animation": "16",
    "Fashion/Style/Clothing": "15",
    "Comedy/Funny": "9",
    "Education/School": "11",
    "Entertainment/Masti": "12",
    "Family/Relationships": "13",
    "Fan Club/Celebrities": "14",
    "Money/Earning": "22",
    "Music/Audio/Songs": "21",
    "News/Magazines/Politics": "23",
    "Pets/Animals/Nature": "24",
    "Roleplay/Comics": "25",
    "Science/Technology": "26",
    "Shopping/Buy/Sell": "27",
    "Social/Friendship/Community": "30",
    "Spiritual/Devotional": "29",
    "Thoughts/Quotes/Jokes": "31",
    "Travel/Local/Place": "32",
}

country_options_simple_gs = {"Any Country": "", "India": "29", "USA": "87", "UK": "86", "Canada": "12", "Australia": "3"}
language_options_simple_gs = {"Any Language": "", "English": "11", "Hindi": "69", "Spanish": "12", "French": "29", "German": "9"}

# Initialize variables with defaults
selected_category_value_gd = "3"
selected_country_value_gd = ""
selected_language_value_gd = ""
selected_category_value_gs = ""
selected_country_value_gs = ""
selected_language_value_gs = ""

if site_choice in ["Groupda.com", "Both"]:
    selected_category_name_gd = st.sidebar.selectbox("Category (Groupda.com):", list(category_options_groupda.keys()), key="gd_cat", index=0)
    selected_category_value_gd = category_options_groupda[selected_category_name_gd]
    selected_country_name_gd = st.sidebar.selectbox("Country (Groupda.com):", list(country_options_simple.keys()), key="gd_country")
    selected_country_value_gd = country_options_simple[selected_country_name_gd]
    selected_language_name_gd = st.sidebar.selectbox("Language (Groupda.com):", list(language_options_simple.keys()), key="gd_lang")
    selected_language_value_gd = language_options_simple[selected_language_name_gd]

if site_choice in ["Groupsor.link", "Both"]:
    selected_category_name_gs = st.sidebar.selectbox("Category (Groupsor.link):", list(category_options_groupsor.keys()), key="gs_cat")
    selected_category_value_gs = category_options_groupsor[selected_category_name_gs]
    selected_country_name_gs = st.sidebar.selectbox("Country (Groupsor.link):", list(country_options_simple_gs.keys()), key="gs_country")
    selected_country_value_gs = country_options_simple_gs[selected_country_name_gs]
    selected_language_name_gs = st.sidebar.selectbox("Language (Groupsor.link):", list(language_options_simple_gs.keys()), key="gs_lang")
    selected_language_value_gs = language_options_simple_gs[selected_language_name_gs]

max_pages_input = st.sidebar.number_input("Max Pages per Site (0 for many):", min_value=0, max_value=100, value=5, step=1)
max_pages = None if max_pages_input == 0 else max_pages_input

if st.sidebar.button("Start Scraping"):
    all_data = []
    
    if site_choice in ["Groupda.com", "Both"]:
        with st.spinner(f"Scraping Groupda.com (Category: '{selected_category_name_gd}')..."):
            df_groupda = scrape_groupda(
                category_value=selected_category_value_gd,
                country_value=selected_country_value_gd,
                language_value=selected_language_value_gd,
                max_pages=max_pages
            )
            if not df_groupda.empty:
                all_data.append(df_groupda)

    if site_choice in ["Groupsor.link", "Both"]:
        with st.spinner(f"Scraping Groupsor.link (Category: '{selected_category_name_gs}')..."):
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
        st.subheader("Scraped Results")
        st.dataframe(final_df)
        
        csv = final_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="Download data as CSV",
            data=csv,
            file_name='whatsapp_groups.csv',
            mime='text/csv',
        )
    else:
        st.info("No data was scraped. Try adjusting filters or check if sites are blocking requests.")

st.markdown("---")
st.subheader("How it works:")
st.markdown("""
1.  Select the website(s) to scrape.
2.  Choose filters (category, country, language).
3.  Set the number of pages to scrape (0 means scrape until no more are found).
4.  Click "Start Scraping".
5.  View results and download as CSV.
""")
