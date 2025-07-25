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

# Initialize a global UserAgent object
ua = UserAgent()

# --- Configuration ---
DEFAULT_DELAY_MIN = 1
DEFAULT_DELAY_MAX = 3
DEFAULT_TIMEOUT = 20
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
        'DNT': '1', # Do Not Track
    }
    if referer:
        headers['Referer'] = referer
    return headers

# --- Scraping Functions ---

# Function to scrape Groupda.com
def scrape_groupda(category_value="3", country_value="", language_value="", max_pages=None):
    """
    Scrapes Groupda.com/find by replicating its AJAX loading mechanism with geolocation.
    """
    find_url = "https://groupda.com/add/group/find"
    load_url = "https://groupda.com/add/group/loadresult"
    results = []
    
    session = requests.Session()
    
    try:
        st.write("Initializing Groupda.com session...")
        # 1. Initial GET request to the find page to get session/cookies
        init_headers = get_random_headers(referer="https://groupda.com/add/")
        init_response = session.get(find_url, headers=init_headers, timeout=DEFAULT_TIMEOUT)
        init_response.raise_for_status()
        st.write("Initial find page fetched.")
        
        # --- Crucial: Get Country Code/Name from the external API ---
        # Replicate the JS: var script = document.createElement('script'); script.src = 'https://geolocation-db.com/json/geoip.php?jsonp=callback';
        geo_api_url = "https://geolocation-db.com/json/geoip.php?jsonp=callback"
        geo_headers = get_random_headers(referer=find_url) # Important: Referer is the find page
        geo_response = session.get(geo_api_url, headers=geo_headers, timeout=DEFAULT_TIMEOUT)
        # geo_response.raise_for_status() # Don't raise, handle gracefully
        
        country_code = ""
        country_name = ""
        if geo_response.status_code == 200:
            geo_text = geo_response.text.strip()
            # Parse JSONP: callback({...})
            match = re.search(r'^callback\s*\(\s*({.*?})\s*\)\s*;?$', geo_text)
            if match:
                try:
                    json_str = match.group(1)
                    geo_data = json.loads(json_str)
                    country_code = geo_data.get('country_code', '')
                    country_name = geo_data.get('country_name', '')
                    st.write(f"Geolocation fetched: {country_code} - {country_name}")
                except json.JSONDecodeError:
                    st.warning("Could not decode geolocation JSON. Using empty strings.")
            else:
                st.warning("Could not parse geolocation data format. Using empty strings.")
        else:
             st.warning(f"Geolocation request failed (Status {geo_response.status_code}). Proceeding without it.")
        # --- End Geolocation ---

        # 2. --- Load initial results (group_no=0) explicitly ---
        # This mimics the JS after geolocation callback
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
        # Crucial headers for AJAX POST to loadresult
        initial_load_headers = get_random_headers(referer=find_url) # Referer is find page
        initial_load_headers.update({
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Origin': 'https://groupda.com', # Add Origin
        })
        
        initial_res = session.post(load_url, data=initial_post_data, headers=initial_load_headers, timeout=DEFAULT_TIMEOUT)
        # Handle response
        if initial_res.status_code == 200:
            if initial_res.text.strip():
                initial_soup = BeautifulSoup(initial_res.text, 'html.parser')
                initial_groups = parse_groupda_containers(initial_soup)
                results.extend(initial_groups)
                st.write(f"Found {len(initial_groups)} groups on initial load.")
            else:
                st.info("Initial AJAX call returned empty content for Groupda.com.")
        else:
            st.error(f"Initial AJAX call failed for Groupda.com (Status {initial_res.status_code}): {initial_res.reason}")

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
                'countryCode': country_code,
                'countryName': country_name
            }
            
            load_headers = get_random_headers(referer=find_url)
            load_headers.update({
                'X-Requested-With': 'XMLHttpRequest',
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'Origin': 'https://groupda.com',
            })
            
            res = session.post(load_url, data=post_data, headers=load_headers, timeout=DEFAULT_TIMEOUT)
            
            if res.status_code != 200:
                st.warning(f"Groupda.com page {page_counter + 1}: Received status code {res.status_code} ({res.reason}). Stopping.")
                break
            
            if not res.text.strip():
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
        return pd.DataFrame()
    except requests.exceptions.RequestException as e:
        st.error(f"An HTTP error occurred while scraping Groupda.com: {e}")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"An unexpected error occurred while scraping Groupda.com: {e}")
        return pd.DataFrame()
    
    st.success(f"Finished scraping Groupda.com. Total pages scraped: {page_counter}, Links found: {len(results)}")
    return pd.DataFrame(results)

def parse_groupda_containers(soup):
    """Parses group containers from Groupda.com's AJAX response."""
    groups = []
    # Based on HTML structure, groups are likely in <div class="view view-tenth">
    group_items = soup.find_all('div', class_='view-tenth')
    
    for item in group_items:
        # Find the WhatsApp link directly within the item
        link_tag = item.find('a', href=lambda href: href and 'chat.whatsapp.com' in href)
        if not link_tag:
            continue
            
        href = link_tag.get('href', '').strip()
        if not href:
            continue
            
        # Extract title
        title_tag = item.find('h3') or item.find('p') or link_tag # Fallback to link text
        title = title_tag.get_text(strip=True) if title_tag else "No Title"
        
        # Extract image URL
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
    """
    Scrapes Groupsor.link/find by replicating its AJAX loading mechanism.
    """
    find_url = "https://groupsor.link/group/find" # The page with the filter form and initial results
    load_url = "https://groupsor.link/group/indexmore" # The endpoint for loading more
    join_base_url = "https://chat.whatsapp.com/invite/" # For transforming /group/join/ links
    results = []
    
    session = requests.Session()
    
    try:
        st.write("Initializing Groupsor.link session...")
        # 1. Initial GET request to the find page to get session/cookies
        init_headers = get_random_headers(referer="https://groupsor.link/")
        # Add specific headers that might be checked
        init_headers.update({
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Cache-Control': 'max-age=0'
        })
        init_response = session.get(find_url, headers=init_headers, timeout=DEFAULT_TIMEOUT)
        init_response.raise_for_status()
        st.write("Initial find page fetched.")

        # 2. --- Load initial results (group_no=0) ---
        # Mimic the initial load, sending filter params like the JS might on subsequent loads
        st.write("Loading initial results (page 1)...")
        initial_post_data = {
            'group_no': '0',
            'gcid': category_value, # Send filter params
            'cid': country_value,
            'lid': language_value
        }
        # Crucial headers for AJAX POST to indexmore
        initial_load_headers = get_random_headers(referer=find_url) # Referer is the find page
        initial_load_headers.update({
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'Origin': 'https://groupsor.link', # Add Origin header
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
        })
        
        initial_res = session.post(load_url, data=initial_post_data, headers=initial_load_headers, timeout=DEFAULT_TIMEOUT)
        # Handle response
        if initial_res.status_code == 200:
            if initial_res.text.strip():
                initial_soup = BeautifulSoup(initial_res.text, 'html.parser')
                initial_groups = parse_groupsor_containers(initial_soup, join_base_url)
                results.extend(initial_groups)
                st.write(f"Found {len(initial_groups)} groups on initial load.")
            else:
               st.info("Initial AJAX call returned empty content for Groupsor.link.")
        else:
            st.error(f"Initial AJAX call failed for Groupsor.link (Status {initial_res.status_code}): {initial_res.reason}. Response snippet: {initial_res.text[:150]}")

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
            
            load_headers = get_random_headers(referer=find_url)
            load_headers.update({
                'X-Requested-With': 'XMLHttpRequest',
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'Origin': 'https://groupsor.link',
                'Sec-Fetch-Dest': 'empty',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'same-origin',
            })
            
            res = session.post(load_url, data=post_data, headers=load_headers, timeout=DEFAULT_TIMEOUT)
            
            if res.status_code != 200:
                st.warning(f"Groupsor.link page {page_counter + 1}: Received status code {res.status_code} ({res.reason}). Stopping.")
                if res.status_code == 403:
                    st.write(f"403 response snippet: {res.text[:200]}")
                break
            
            if not res.text.strip():
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
        return pd.DataFrame()
    except requests.exceptions.RequestException as e:
        st.error(f"An HTTP error occurred while scraping Groupsor.link: {e}")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"An unexpected error occurred while scraping Groupsor.link: {e}")
        return pd.DataFrame()
        
    st.success(f"Finished scraping Groupsor.link. Total pages scraped: {page_counter}, Links found: {len(results)}")
    return pd.DataFrame(results)

def parse_groupsor_containers(soup, join_base_url):
    """Parses group containers from Groupsor.link's AJAX response and transforms links."""
    groups = []
    # Based on HTML structure, groups are likely in <div class="view view-tenth">
    group_items = soup.find_all('div', class_='view-tenth')
    
    for item in group_items:
        actual_whatsapp_link = ""
        # 1. Try to find the Groupsor join link (e.g., /group/join/ID) and transform it
        join_link_tag = item.find('a', href=lambda href: href and '/group/join/' in href)
        if join_link_tag:
            join_href = join_link_tag.get('href', '').strip()
            if join_href:
                # Transform the link: /group/join/ID -> https://chat.whatsapp.com/invite/ID
                path = urlparse(join_href).path
                if path.startswith("/group/join/"):
                    group_id = path.split("/group/join/")[-1]
                    actual_whatsapp_link = urljoin(join_base_url, group_id)
                else:
                    actual_whatsapp_link = join_href # Fallback

        # 2. If no join link, fallback to finding a direct WhatsApp link
        if not actual_whatsapp_link:
            direct_link_tag = item.find('a', href=lambda href: href and 'chat.whatsapp.com' in href)
            if direct_link_tag:
                actual_whatsapp_link = direct_link_tag.get('href', '').strip()

        # If still no link, skip this item
        if not actual_whatsapp_link:
            continue
            
        # Extract title
        title_tag = item.find('h3') or item.find('p') or (join_link_tag if join_link_tag else (direct_link_tag if direct_link_tag else None))
        title = title_tag.get_text(strip=True) if title_tag else "No Title"
        
        # Extract image URL
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

# Options based on HTML source analysis
category_options_groupda = {
    "Any Category": "",
    "18_Adult_Hot_Babes": "3", # Default selected in HTML find page
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
# Note: Country/Language IDs for Groupsor might differ from Groupda
country_options_simple_gs = {"Any Country": "", "India": "29", "USA": "87", "UK": "86", "Canada": "12", "Australia": "3"}
language_options_simple_gs = {"Any Language": "", "English": "11", "Hindi": "69", "Spanish": "12", "French": "29", "German": "9"}

# Initialize variables
selected_category_value_gd = "3" # Default to 18_Adult_Hot_Babes
selected_country_value_gd = ""
selected_language_value_gd = ""
selected_category_value_gs = ""
selected_country_value_gs = ""
selected_language_value_gs = ""

if site_choice in ["Groupda.com", "Both"]:
    selected_category_name_gd = st.sidebar.selectbox("Category (Groupda.com):", list(category_options_groupda.keys()), key="gd_cat", index=1) # Index 1 for "18_Adult_Hot_Babes"
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
        with st.spinner(f"Scraping Groupda.com (Category ID: {selected_category_value_gd})..."):
            df_groupda = scrape_groupda(
                category_value=selected_category_value_gd,
                country_value=selected_country_value_gd,
                language_value=selected_language_value_gd,
                max_pages=max_pages
            )
            if not df_groupda.empty:
                all_data.append(df_groupda)

    if site_choice in ["Groupsor.link", "Both"]:
        with st.spinner(f"Scraping Groupsor.link (Category ID: {selected_category_value_gs})..."):
            df_groupsor = scrape_groupsor(
                category_value=selected_category_value_gs,
                country_value=selected_country_value_gs,
                language_value=selected_language_value_gs,
                max_pages=max_pages
            )
            if not df_groupsor.empty:
                all_data.append(df_groupsor)

    # Corrected line: Added the missing colon ':'
    if all_data: # This was the line with the syntax error
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
