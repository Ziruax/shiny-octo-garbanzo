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
DEFAULT_TIMEOUT = 25
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
    }
    if referer:
        headers['Referer'] = referer
    return headers

# --- Scraping Functions ---

# Function to scrape Groupda.com
def scrape_groupda(category_value="3", country_value="", language_value="", max_pages=None):
    """
    Scrapes Groupda.com/find by replicating its form submission and AJAX loading.
    """
    find_url = "https://groupda.com/add/group/find"
    load_url = "https://groupda.com/add/group/loadresult"
    results = []
    
    session = requests.Session()
    
    try:
        # NOTE: Get a base header and cookie by visiting the base URL first.
        session.get("https://groupda.com/add/", headers=get_random_headers(), timeout=DEFAULT_TIMEOUT)
        st.write("Initializing Groupda.com session...")

        # --- Crucial: Get Country Code/Name from the external API ---
        geo_api_url = "https://geolocation-db.com/json/geoip.php?jsonp=callback"
        geo_headers = get_random_headers(referer="https://groupda.com/add/")
        geo_response = session.get(geo_api_url, headers=geo_headers, timeout=DEFAULT_TIMEOUT)
        
        country_code, country_name = "", ""
        if geo_response.status_code == 200:
            match = re.search(r'callback\((.*)\)', geo_response.text)
            if match:
                try:
                    geo_data = json.loads(match.group(1))
                    country_code = geo_data.get('country_code', '')
                    country_name = geo_data.get('country_name', '')
                    st.write(f"Geolocation fetched: {country_code} - {country_name}")
                except json.JSONDecodeError:
                    st.warning("Could not decode geolocation JSON.")
        else:
            st.warning(f"Geolocation request failed (Status {geo_response.status_code}).")

        # --- CHANGED: Simulate form POST to get the first page of results ---
        st.write("Submitting search form to get initial results (Page 1)...")
        form_data = {
            'gcid': category_value,
            'cid': country_value,
            'lid': language_value,
        }
        form_headers = get_random_headers(referer="https://groupda.com/add/")
        form_headers['Origin'] = 'https://groupda.com'

        initial_page_response = session.post(find_url, headers=form_headers, data=form_data, timeout=DEFAULT_TIMEOUT)
        initial_page_response.raise_for_status()
        
        initial_soup = BeautifulSoup(initial_page_response.content, 'html.parser')
        # NOTE: The results from the form POST are inside a div with id 'results'.
        results_div = initial_soup.find('div', id='results')
        if results_div:
            initial_groups = parse_groupda_containers(results_div)
            results.extend(initial_groups)
            st.write(f"Found {len(initial_groups)} groups on initial page load.")
        else:
            st.warning("Could not find the results container on the initial page for Groupda.com.")

        # --- CHANGED: Loop through subsequent pages starting from page 1 ---
        page_counter = 1
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
                st.warning(f"Groupda.com page {page_counter + 1}: Received status code {res.status_code}. Stopping.")
                break
            
            if not res.text.strip():
                st.info(f"No more results found on Groupda.com after page {page_counter}.")
                break
            
            result_soup = BeautifulSoup(res.text, 'html.parser')
            page_groups = parse_groupda_containers(result_soup)
            
            if not page_groups:
                st.info(f"No new groups found on Groupda.com page {page_counter + 1}. Stopping.")
                break
            
            results.extend(page_groups)
            
            page_counter += 1
            delay = random.uniform(DEFAULT_DELAY_MIN, DEFAULT_DELAY_MAX)
            st.write(f"Waiting for {delay:.2f} seconds...")
            time.sleep(delay)
            
    except requests.exceptions.RequestException as e:
        st.error(f"An HTTP error occurred while scraping Groupda.com: {e}")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"An unexpected error occurred while scraping Groupda.com: {e}")
        return pd.DataFrame()
    
    st.success(f"Finished scraping Groupda.com. Total pages scraped: {page_counter}, Links found: {len(results)}")
    df = pd.DataFrame(results)
    # Add submitted filter values to the DataFrame
    if not df.empty:
        df['Category_ID'] = category_value
        df['Country_ID'] = country_value
        df['Language_ID'] = language_value
    return df

def parse_groupda_containers(soup):
    """Parses group containers from Groupda.com's response."""
    groups = []
    group_items = soup.find_all('div', class_='view-tenth')
    
    for item in group_items:
        link_tag = item.find('a', href=lambda href: href and 'chat.whatsapp.com' in href)
        if not link_tag:
            continue
            
        href = link_tag.get('href', '').strip()
        if not href:
            continue
            
        title_tag = item.find('h3') or item.find('p') or link_tag
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
    """
    Scrapes Groupsor.link. NOTE: This site uses strong anti-bot protection.
    This script may fail with a 403 error.
    """
    find_url = "https://groupsor.link/group/find"
    load_url = "https://groupsor.link/group/indexmore" # NOTE: AJAX endpoint for 'load more'.
    join_base_url = "https://chat.whatsapp.com/invite/"
    results = []
    
    session = requests.Session()
    
    try:
        st.write("Initializing Groupsor.link session...")
        # NOTE: A simple GET to the homepage to get initial cookies might help.
        session.get("https://groupsor.link/", headers=get_random_headers(), timeout=DEFAULT_TIMEOUT)

        # --- CHANGED: Simulate form POST to get the first page of results ---
        st.write("Submitting search form to Groupsor.link to get initial results (Page 1)...")
        form_data = {
            'gcid': category_value,
            'cid': country_value,
            'lid': language_value,
        }
        form_headers = get_random_headers(referer="https://groupsor.link/")
        form_headers['Origin'] = 'https://groupsor.link'

        initial_page_response = session.post(find_url, headers=form_headers, data=form_data, timeout=DEFAULT_TIMEOUT)
        
        if initial_page_response.status_code == 403:
             st.error("403 Forbidden: Groupsor.link has blocked the request. This is likely due to anti-bot protection (like Cloudflare) that the 'requests' library cannot bypass. Consider using a library like 'cloudscraper' or 'selenium'.")
             return pd.DataFrame()
        
        initial_page_response.raise_for_status()
        
        initial_soup = BeautifulSoup(initial_page_response.content, 'html.parser')
        # NOTE: Find the results container from the initial page load.
        results_div = initial_soup.find('div', id='results') 
        if results_div:
            initial_groups = parse_groupsor_containers(results_div, join_base_url)
            results.extend(initial_groups)
            st.write(f"Found {len(initial_groups)} groups on initial page load.")
        else:
             st.warning("Could not find results container on initial page for Groupsor.link.")

        # --- CHANGED: Loop through subsequent pages starting from page 1 ---
        page_counter = 1
        while True:
            if max_pages is not None and page_counter >= max_pages:
                st.info(f"Reached maximum pages limit ({max_pages}) for Groupsor.link.")
                break

            st.write(f"Scraping Groupsor.link page {page_counter + 1} (AJAX)...")
            
            # NOTE: The AJAX call might only need the page number, as the filters
            # could be tracked by the server-side session initiated by the form POST.
            # Including filters again might also work, but this is a safer bet.
            post_data = {
                'group_no': str(page_counter)
            }
            # If the simple post_data fails, you can try sending all filters again.
            # if category_value: post_data['gcid'] = category_value
            # if country_value: post_data['cid'] = country_value
            # if language_value: post_data['lid'] = language_value
            
            load_headers = get_random_headers(referer=find_url)
            load_headers.update({
                'X-Requested-With': 'XMLHttpRequest',
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'Origin': 'https://groupsor.link',
            })
            
            res = session.post(load_url, data=post_data, headers=load_headers, timeout=DEFAULT_TIMEOUT)
            
            if res.status_code != 200:
                st.warning(f"Groupsor.link page {page_counter + 1}: Received status code {res.status_code}. Stopping.")
                break
            
            if not res.text.strip():
                st.info(f"No more results found on Groupsor.link after page {page_counter}.")
                break
            
            result_soup = BeautifulSoup(res.text, 'html.parser')
            page_groups = parse_groupsor_containers(result_soup, join_base_url)
            
            if not page_groups:
                 st.info(f"No new groups found on Groupsor.link page {page_counter + 1}. Stopping.")
                 break
            
            results.extend(page_groups)
            page_counter += 1
            delay = random.uniform(DEFAULT_DELAY_MIN, DEFAULT_DELAY_MAX)
            st.write(f"Waiting for {delay:.2f} seconds...")
            time.sleep(delay)
            
    except requests.exceptions.RequestException as e:
        st.error(f"An HTTP error occurred while scraping Groupsor.link: {e}")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"An unexpected error occurred while scraping Groupsor.link: {e}")
        return pd.DataFrame()
        
    st.success(f"Finished scraping Groupsor.link. Total pages scraped: {page_counter}, Links found: {len(results)}")
    df = pd.DataFrame(results)
    # Add submitted filter values to the DataFrame
    if not df.empty:
        df['Category_ID'] = category_value
        df['Country_ID'] = country_value
        df['Language_ID'] = language_value
    return df

def parse_groupsor_containers(soup, join_base_url):
    """Parses group containers from Groupsor.link's response and transforms links."""
    groups = []
    group_items = soup.find_all('div', class_='view-tenth')
    
    for item in group_items:
        actual_whatsapp_link = ""
        # 1. Prioritize the Groupsor join link and transform it
        join_link_tag = item.find('a', href=lambda href: href and '/group/join/' in href)
        if join_link_tag:
            join_href = join_link_tag.get('href', '').strip()
            if join_href:
                try:
                    group_id = join_href.split('/group/join/')[-1]
                    if group_id:
                        actual_whatsapp_link = urljoin(join_base_url, group_id)
                except (IndexError, TypeError):
                    pass # Continue to the next check

        # 2. Fallback to a direct WhatsApp link
        if not actual_whatsapp_link:
            direct_link_tag = item.find('a', href=lambda href: href and 'chat.whatsapp.com' in href)
            if direct_link_tag:
                actual_whatsapp_link = direct_link_tag.get('href', '').strip()

        if not actual_whatsapp_link:
            continue
            
        title_tag = item.find('h3') or item.find('p')
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
# NOTE: The Streamlit UI code remains largely the same but I have fixed a syntax error.
st.title("WhatsApp Group Scraper")

# --- Sidebar for Inputs ---
st.sidebar.header("Scraper Settings")

site_choice = st.sidebar.selectbox(
    "Select Website to Scrape:",
    ("Groupda.com", "Groupsor.link", "Both")
)

# Options based on HTML source analysis (Your existing dictionaries are great)
category_options_groupda = {
    "Default (18+)": "3", "Any Category": "", "Girls_Group": "2", "Gaming_Apps": "7",
    "Health_Beauty_Fitness": "8", "Business_Advertising_Marketing": "6", "Sports_Other_Games": "21",
    "Film_Animation": "18", "Fashion_Style_Clothing": "15", "Comedy_Funny": "9",
    "Educational_Schooling_Collage": "11", "Entertainment_Masti": "12", "Family_Relationships": "13",
    "Fan_Club_Celebrities": "14", "Earn_Money_Online": "16", "MLM_Group_Joining": "17",
    "Spiritual_Devotional": "19", "Cricket_Kabadi_FC": "20", "Food_Drinks_Recipe": "22",
    "Crypto_Bitcoin_Betting": "23", "Any_Category": "24",
}
country_options_simple = {"Any Country": "", "India": "99", "USA": "223", "UK": "222", "Canada": "38", "Australia": "13"}
language_options_simple = {"Any Language": "", "English": "17", "Hindi": "26", "Spanish": "51", "French": "20", "German": "23"}

category_options_groupsor = {
    "Any Category": "", "Adult/18+/Hot": "7", "Gaming/Apps": "18", "Health/Beauty/Fitness": "19",
    "Business/Advertising/Marketing": "8", "Sports/Games": "28", "Film/Animation": "16",
    "Fashion/Style/Clothing": "15", "Comedy/Funny": "9", "Education/School": "11",
    "Entertainment/Masti": "12", "Family/Relationships": "13", "Fan Club/Celebrities": "14",
    "Money/Earning": "22", "Music/Audio/Songs": "21", "News/Magazines/Politics": "23",
    "Pets/Animals/Nature": "24", "Roleplay/Comics": "25", "Science/Technology": "26",
    "Shopping/Buy/Sell": "27", "Social/Friendship/Community": "30", "Spiritual/Devotional": "29",
    "Thoughts/Quotes/Jokes": "31", "Travel/Local/Place": "32",
}
country_options_simple_gs = {"Any Country": "", "India": "29", "USA": "87", "UK": "86", "Canada": "12", "Australia": "3"}
language_options_simple_gs = {"Any Language": "", "English": "11", "Hindi": "69", "Spanish": "12", "French": "29", "German": "9"}

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
        with st.spinner(f"Scraping Groupda.com (Category ID: '{selected_category_value_gd}')..."):
            df_groupda = scrape_groupda(
                category_value=selected_category_value_gd,
                country_value=selected_country_value_gd,
                language_value=selected_language_value_gd,
                max_pages=max_pages
            )
            if not df_groupda.empty:
                all_data.append(df_groupda)

    if site_choice in ["Groupsor.link", "Both"]:
        with st.spinner(f"Scraping Groupsor.link (Category ID: '{selected_category_value_gs}')..."):
            df_groupsor = scrape_groupsor(
                category_value=selected_category_value_gs,
                country_value=selected_country_value_gs,
                language_value=selected_language_value_gs,
                max_pages=max_pages
            )
            if not df_groupsor.empty:
                all_data.append(df_groupsor)
    
    # FIXED: The original code was missing a colon ':' on the next line
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
        st.info("No data was scraped. This could be due to network issues, anti-scraping measures on the websites, or no results matching your filters.")

st.markdown("---")
st.subheader("How it works:")
st.markdown("""
1.  Select the website(s) to scrape.
2.  Choose filters (category, country, language).
3.  Set the number of pages to scrape.
4.  Click "Start Scraping".
5.  View results and download as CSV.
**Note:** Web scraping can be unreliable. If a site stops working, it may have updated its anti-bot protections.
""")
