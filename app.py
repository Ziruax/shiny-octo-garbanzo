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

# Initialize a global UserAgent object
ua = UserAgent()

# --- Configuration ---
DEFAULT_DELAY_MIN = 1  # Minimum delay in seconds
DEFAULT_DELAY_MAX = 3  # Maximum delay in seconds
DEFAULT_TIMEOUT = 20   # Increased timeout in seconds
MAX_PAGES_DEFAULT = 5  

# Function to get a random header
def get_random_headers(referer=None):
    headers = {
        'User-Agent': ua.random,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    if referer:
        headers['Referer'] = referer
    return headers

# --- Scraping Functions ---

# Function to scrape Groupda.com
def scrape_groupda(category_value="", country_value="", language_value="", max_pages=None):
    """
    Scrapes Groupda.com by replicating its AJAX loading mechanism.
    """
    base_url = "https://groupda.com/add/group/find"
    load_url = "https://groupda.com/add/group/loadresult"
    results = []
    
    session = requests.Session()
    
    try:
        st.write("Initializing Groupda.com session...")
        # 1. Initial GET request to get cookies and session data
        init_response = session.get(base_url, headers=get_random_headers(referer="https://groupda.com/add/"), timeout=DEFAULT_TIMEOUT)
        init_response.raise_for_status()
        st.write("Initial page fetched.")
        
        # --- Crucial Part: Get Country Code/Name from the external API ---
        # The JS calls https://geolocation-db.com/json/geoip.php?jsonp=callback
        # We need to replicate this to get countryCode and countryName
        geo_api_url = "https://geolocation-db.com/json/geoip.php?jsonp=callback"
        geo_response = session.get(geo_api_url, headers=get_random_headers(referer=base_url), timeout=DEFAULT_TIMEOUT)
        geo_response.raise_for_status()
        
        # The response is JSONP: callback({...})
        # Extract JSON part
        geo_text = geo_response.text
        if geo_text.startswith("callback(") and geo_text.endswith(");"):
            json_str = geo_text[9:-2] # Remove 'callback(' and ');'
            geo_data = json.loads(json_str)
            country_code = geo_data.get('country_code', '')
            country_name = geo_data.get('country_name', '')
            st.write(f"Geolocation fetched: {country_code} - {country_name}")
        else:
            st.warning("Could not parse geolocation data. Using empty strings.")
            country_code = ""
            country_name = ""
        # --- End Geolocation ---
        
        # 2. Load initial results (group_no=0) using the geolocation data
        st.write("Loading initial results (page 1)...")
        initial_post_data = {
            'group_no': '0',
            'gcid': category_value,
            'cid': country_value,
            'lid': language_value,
            'findPage': 'true',
            'countryCode': country_code,
            'countryName': country_name
        }
        initial_load_headers = get_random_headers(referer=base_url)
        initial_load_headers.update({
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'
        })
        
        initial_res = session.post(load_url, data=initial_post_data, headers=initial_load_headers, timeout=DEFAULT_TIMEOUT)
        initial_res.raise_for_status()
        
        if initial_res.text.strip():
            initial_soup = BeautifulSoup(initial_res.text, 'html.parser')
            initial_groups = parse_groupda_containers(initial_soup)
            results.extend(initial_groups)
            st.write(f"Found {len(initial_groups)} groups on initial load.")
        else:
            st.warning("Initial AJAX call for Groupda.com returned empty content.")

        # 3. Loop through subsequent pages using AJAX POST
        page_counter = 1 # Start from 1 as 0 is already loaded
        while True: 
            if max_pages is not None and page_counter >= max_pages:
                st.info(f"Reached maximum pages limit ({max_pages}) for Groupda.com.")
                break

            st.write(f"Scraping Groupda.com page {page_counter + 1} (AJAX)...")
            
            post_data = {
                'group_no': str(page_counter),
                'gcid': category_value,
                'cid': country_value,
                'lid': language_value,
                'findPage': 'true',
                'countryCode': country_code, # Include these crucial parameters
                'countryName': country_name
            }
            
            load_headers = get_random_headers(referer=base_url)
            load_headers.update({
                'X-Requested-With': 'XMLHttpRequest',
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'
            })
            
            res = session.post(load_url, data=post_data, headers=load_headers, timeout=DEFAULT_TIMEOUT)
            
            if res.status_code != 200:
                st.warning(f"Groupda.com page {page_counter + 1}: Received status code {res.status_code}. Stopping.")
                break
            
            if not res.text.strip() or res.text.strip() == "":
                st.info(f"No more results found on Groupda.com after page {page_counter + 1}.")
                break 
            
            result_soup = BeautifulSoup(res.text, 'html.parser')
            
            page_groups = parse_groupda_containers(result_soup)
            
            if not page_groups:
                st.info(f"No new groups found on Groupda.com page {page_counter + 1}. Stopping.")
                break 
            
            for group in page_groups:
                group['Category_ID'] = category_value
                group['Country_ID'] = country_value
                group['Language_ID'] = language_value
                results.append(group)
            
            page_counter += 1
            delay = random.uniform(DEFAULT_DELAY_MIN, DEFAULT_DELAY_MAX)
            st.write(f"Waiting for {delay:.2f} seconds...")
            time.sleep(delay)
            
    except requests.exceptions.Timeout:
        st.error("Timeout occurred while scraping Groupda.com.")
        return pd.DataFrame() # Return empty DataFrame on error
    except requests.exceptions.RequestException as e:
        st.error(f"An HTTP error occurred while scraping Groupda.com: {e}")
        return pd.DataFrame() # Return empty DataFrame on error
    except Exception as e:
        st.error(f"An unexpected error occurred while scraping Groupda.com: {e}")
        return pd.DataFrame() # Return empty DataFrame on error
    
    st.success(f"Finished scraping Groupda.com. Total pages scraped: {page_counter}, Links found: {len(results)}")
    return pd.DataFrame(results)

def parse_groupda_containers(soup):
    """Parses group containers from Groupda.com's AJAX response."""
    groups = []
    # Groupda uses <div class="view view-tenth"> for each group item
    group_items = soup.find_all('div', class_='view-tenth')
    
    for item in group_items:
        # Find the WhatsApp link
        link_tag = item.find('a', href=lambda href: href and 'chat.whatsapp.com' in href)
        if not link_tag:
            continue
            
        href = link_tag.get('href', '').strip()
        if not href:
            continue
            
        # Extract title, often from an <h3> or <p> inside the item
        title_tag = item.find('h3') or item.find('p') or item.find('a') # Fallback to link text
        title = title_tag.get_text(strip=True) if title_tag else "No Title"
        
        # Extract image URL if present
        img_tag = item.find('img')
        img_src = img_tag.get('src', '') if img_tag else ''
        
        groups.append({
            'Source': 'Groupda.com',
            'Title': title,
            'Link': href,
            'Image_URL': img_src # Might be useful
        })
    return groups

# Function to scrape Groupsor.link
def scrape_groupsor(category_value="", country_value="", language_value="", max_pages=None):
    """
    Scrapes Groupsor.link by replicating its AJAX loading mechanism.
    """
    base_find_url = "https://groupsor.link/group/find" # URL for the find page
    load_url = "https://groupsor.link/group/indexmore" # URL for loading more results
    join_base_url = "https://chat.whatsapp.com/invite/" # Base URL for actual WhatsApp links
    results = []
    
    session = requests.Session()
    
    try:
        st.write("Initializing Groupsor.link session...")
        # 1. Initial GET request to the find page (might not be strictly necessary for cookies, but good practice)
        init_response = session.get(base_find_url, headers=get_random_headers(referer="https://groupsor.link/"), timeout=DEFAULT_TIMEOUT)
        init_response.raise_for_status()
        st.write("Initial find page fetched.")

        # 2. Load initial results (group_no=0)
        # This is the key call that loads the first batch of groups
        st.write("Loading initial results (page 1)...")
        initial_post_data = {
            'group_no': '0',
            'gcid': category_value,
            'cid': country_value,
            'lid': language_value
            # Note: No 'findPage' flag like Groupda
        }
        initial_load_headers = get_random_headers(referer=base_find_url)
        initial_load_headers.update({
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'
        })
        
        initial_res = session.post(load_url, data=initial_post_data, headers=initial_load_headers, timeout=DEFAULT_TIMEOUT)
        initial_res.raise_for_status()
        
        if initial_res.text.strip():
            initial_soup = BeautifulSoup(initial_res.text, 'html.parser')
            initial_groups = parse_groupsor_containers(initial_soup, join_base_url)
            results.extend(initial_groups)
            st.write(f"Found {len(initial_groups)} groups on initial load.")
        else:
            st.warning("Initial AJAX call for Groupsor.link returned empty content.")

        # 3. Loop through subsequent pages using AJAX POST
        page_counter = 1 # Start from 1
        while True: 
            if max_pages is not None and page_counter >= max_pages:
                st.info(f"Reached maximum pages limit ({max_pages}) for Groupsor.link.")
                break

            st.write(f"Scraping Groupsor.link page {page_counter + 1}...")
            
            post_data = {
                'group_no': str(page_counter),
                'gcid': category_value,
                'cid': country_value,
                'lid': language_value
            }
            
            load_headers = get_random_headers(referer=base_find_url)
            load_headers.update({
                'X-Requested-With': 'XMLHttpRequest',
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'
            })
            
            res = session.post(load_url, data=post_data, headers=load_headers, timeout=DEFAULT_TIMEOUT)
            
            if res.status_code != 200:
                st.warning(f"Groupsor.link page {page_counter + 1}: Received status code {res.status_code}. Stopping.")
                break
            
            if not res.text.strip() or res.text.strip() == "":
                st.info(f"No more results found on Groupsor.link after page {page_counter + 1}.")
                break 
            
            result_soup = BeautifulSoup(res.text, 'html.parser')
            
            page_groups = parse_groupsor_containers(result_soup, join_base_url)
            
            if not page_groups:
                 st.info(f"No new groups found on Groupsor.link page {page_counter + 1}. Stopping.")
                 break 
            
            for group in page_groups:
                group['Category_ID'] = category_value
                group['Country_ID'] = country_value
                group['Language_ID'] = language_value
                results.append(group)
                
            page_counter += 1
            delay = random.uniform(DEFAULT_DELAY_MIN, DEFAULT_DELAY_MAX)
            st.write(f"Waiting for {delay:.2f} seconds...")
            time.sleep(delay)
            
    except requests.exceptions.Timeout:
        st.error("Timeout occurred while scraping Groupsor.link.")
        return pd.DataFrame() # Return empty DataFrame on error
    except requests.exceptions.RequestException as e:
        st.error(f"An HTTP error occurred while scraping Groupsor.link: {e}")
        return pd.DataFrame() # Return empty DataFrame on error
    except Exception as e:
        st.error(f"An unexpected error occurred while scraping Groupsor.link: {e}")
        return pd.DataFrame() # Return empty DataFrame on error
        
    st.success(f"Finished scraping Groupsor.link. Total pages scraped: {page_counter}, Links found: {len(results)}")
    return pd.DataFrame(results)

def parse_groupsor_containers(soup, join_base_url):
    """Parses group containers from Groupsor.link's AJAX response and transforms links."""
    groups = []
    # Groupsor uses <div class="view view-tenth"> for each group item, similar to Groupda
    group_items = soup.find_all('div', class_='view-tenth')
    
    for item in group_items:
        # Find the Groupsor join link (e.g., /group/join/ID)
        join_link_tag = item.find('a', href=lambda href: href and '/group/join/' in href)
        if not join_link_tag:
            # Fallback: look for any WhatsApp-like link directly
            direct_link_tag = item.find('a', href=lambda href: href and 'chat.whatsapp.com' in href)
            if direct_link_tag:
                 href = direct_link_tag.get('href', '').strip()
                 title_tag = item.find('h3') or item.find('p') or item.find('a')
                 title = title_tag.get_text(strip=True) if title_tag else "No Title"
                 img_tag = item.find('img')
                 img_src = img_tag.get('src', '') if img_tag else ''
                 groups.append({
                    'Source': 'Groupsor.link',
                    'Title': title,
                    'Link': href,
                    'Image_URL': img_src
                 })
            continue # Skip if no join link or direct link found
            
        join_href = join_link_tag.get('href', '').strip()
        if not join_href:
            continue
            
        # --- Transform the link ---
        # Input: /group/join/ExP5H8aG1vU1ptQk3IGgbX
        # Output: https://chat.whatsapp.com/invite/ExP5H8aG1vU1ptQk3IGgbX
        path = urlparse(join_href).path
        if path.startswith("/group/join/"):
            group_id = path.split("/group/join/")[-1]
            actual_whatsapp_link = urljoin(join_base_url, group_id)
        else:
            actual_whatsapp_link = join_href # Fallback if format is unexpected
        # --- End Transform ---
        
        # Extract title
        title_tag = item.find('h3') or item.find('p') or item.find('a') # Fallback to link text if needed
        title = title_tag.get_text(strip=True) if title_tag else "No Title"
        
        # Extract image URL
        img_tag = item.find('img')
        img_src = img_tag.get('src', '') if img_tag else ''
        
        groups.append({
            'Source': 'Groupsor.link',
            'Title': title,
            'Link': actual_whatsapp_link, # Use the transformed link
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

# Simplified options for demonstration
category_options_groupda = {
    "Any Category": "", "18_Adult_Hot_Babes": "3", "Girls_Group": "2", "Gaming_Apps": "7", "Health_Beauty_Fitness": "8"
}
category_options_groupsor = {
    "Any Category": "", "Adult/18+/Hot": "7", "Gaming/Apps": "18", "Health/Beauty/Fitness": "19", "Sports/Games": "28"
}

country_options_simple = {"Any Country": "", "India": "99", "USA": "223", "UK": "222"}
language_options_simple = {"Any Language": "", "English": "17", "Hindi": "26", "Spanish": "51"}

# Initialize variables
selected_category_value_gd = ""
selected_country_value_gd = ""
selected_language_value_gd = ""
selected_category_value_gs = ""
selected_country_value_gs = ""
selected_language_value_gs = ""

if site_choice in ["Groupda.com", "Both"]:
    selected_category_name_gd = st.sidebar.selectbox("Category (Groupda.com):", list(category_options_groupda.keys()), key="gd_cat")
    selected_category_value_gd = category_options_groupda[selected_category_name_gd]
    selected_country_name_gd = st.sidebar.selectbox("Country (Groupda.com):", list(country_options_simple.keys()), key="gd_country")
    selected_country_value_gd = country_options_simple[selected_country_name_gd]
    selected_language_name_gd = st.sidebar.selectbox("Language (Groupda.com):", list(language_options_simple.keys()), key="gd_lang")
    selected_language_value_gd = language_options_simple[selected_language_name_gd]

if site_choice in ["Groupsor.link", "Both"]:
    selected_category_name_gs = st.sidebar.selectbox("Category (Groupsor.link):", list(category_options_groupsor.keys()), key="gs_cat")
    selected_category_value_gs = category_options_groupsor[selected_category_name_gs]
    selected_country_name_gs = st.sidebar.selectbox("Country (Groupsor.link):", list(country_options_simple.keys()), key="gs_country")
    selected_country_value_gs = country_options_simple[selected_country_name_gs]
    selected_language_name_gs = st.sidebar.selectbox("Language (Groupsor.link):", list(language_options_simple.keys()), key="gs_lang")
    selected_language_value_gs = language_options_simple[selected_language_name_gs]

max_pages_input = st.sidebar.number_input("Max Pages per Site (0 for many):", min_value=0, max_value=100, value=5, step=1)
max_pages = None if max_pages_input == 0 else max_pages_input

if st.sidebar.button("Start Scraping"):
    all_data = []
    
    if site_choice in ["Groupda.com", "Both"]:
        with st.spinner(f"Scraping Groupda.com..."):
            df_groupda = scrape_groupda(
                category_value=selected_category_value_gd, 
                country_value=selected_country_value_gd, 
                language_value=selected_language_value_gd, 
                max_pages=max_pages
            )
            if not df_groupda.empty:
                all_data.append(df_groupda)

    if site_choice in ["Groupsor.link", "Both"]:
        with st.spinner(f"Scraping Groupsor.link..."):
            df_groupsor = scrape_groupsor(
                category_value=selected_category_value_gs, 
                country_value=selected_country_value_gs, 
                language_value=selected_language_value_gs, 
                max_pages=max_pages
            )
            if not df_groupsor.empty:
                all_data.append(df_groupsor)

    # Corrected line: Added the missing colon ':'
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
        st.info("No data was scraped.")

st.markdown("---")
st.subheader("How it works:")
st.markdown("""
1.  Select the website(s) to scrape.
2.  Choose filters (category, country, language).
3.  Set the number of pages to scrape (0 means scrape a lot until no more are found).
4.  Click "Start Scraping".
5.  View results and download as CSV.
""")
