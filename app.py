# app.py
import streamlit as st
import requests
import cloudscraper # Use for both sites for consistency
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
DEFAULT_DELAY_MIN = 1.5 # Slightly increased delay
DEFAULT_DELAY_MAX = 4.0
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
    }
    if referer:
        headers['Referer'] = referer
    return headers

# --- Scraping Functions ---

def scrape_groupda(category_value="3", country_value="", language_value="", max_pages=None):
    """
    Scrapes Groupda.com by sending filter parameters with every AJAX request.
    """
    find_url = "https://groupda.com/add/group/find"
    load_url = "https://groupda.com/add/group/loadresult"
    results = []
    
    # Use cloudscraper for better resilience against bot detection
    session = cloudscraper.create_scraper() 
    
    try:
        st.write("Initializing Groupda.com session (using cloudscraper)...")
        # Visit find page to establish a baseline session and get cookies
        session.get(find_url, headers=get_random_headers(), timeout=DEFAULT_TIMEOUT)

        # Get Geolocation Data (remains the same)
        geo_api_url = "https://geolocation-db.com/json/geoip.php?jsonp=callback"
        geo_response = session.get(geo_api_url, headers=get_random_headers(referer=find_url), timeout=DEFAULT_TIMEOUT)
        country_code, country_name = "", ""
        if geo_response.status_code == 200:
            match = re.search(r'callback\((.*)\)', geo_response.text)
            if match:
                geo_data = json.loads(match.group(1))
                country_code = geo_data.get('country_code', '')
                country_name = geo_data.get('country_name', '')
                st.write(f"Geolocation fetched: {country_code} - {country_name}")

        # --- REVISED LOGIC: Loop from page 0 and send filters every time ---
        page_counter = 0
        while True:
            if max_pages is not None and page_counter >= max_pages:
                st.info(f"Reached maximum pages limit ({max_pages}) for Groupda.com.")
                break

            st.write(f"Scraping Groupda.com page {page_counter + 1}...")
            
            post_data = {
                'group_no': str(page_counter),
                'gcid': category_value,
                'cid': country_value,
                'lid': language_value,
                'findPage': 'true', # This parameter seems important for the find context
                'countryCode': country_code,
                'countryName': country_name
            }
            
            load_headers = get_random_headers(referer=find_url)
            load_headers.update({
                'X-Requested-With': 'XMLHttpRequest',
                'Origin': 'https://groupda.com',
            })
            
            res = session.post(load_url, data=post_data, headers=load_headers, timeout=DEFAULT_TIMEOUT)
            
            if res.status_code != 200:
                st.warning(f"Groupda.com page {page_counter + 1}: Status {res.status_code}. Stopping.")
                break
            
            if not res.text.strip():
                st.info(f"No more results found on Groupda.com after page {page_counter}. Stopping.")
                break
            
            result_soup = BeautifulSoup(res.text, 'html.parser')
            page_groups = parse_groupda_containers(result_soup)
            
            if not page_groups:
                st.info(f"No new groups found on Groupda.com page {page_counter + 1}. This is the end of the list.")
                break
            
            results.extend(page_groups)
            st.write(f"Found {len(page_groups)} new groups. Total so far: {len(results)}")
            page_counter += 1
            time.sleep(random.uniform(DEFAULT_DELAY_MIN, DEFAULT_DELAY_MAX))
            
    except requests.exceptions.RequestException as e:
        st.error(f"A network error occurred on Groupda.com: {e}")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"An unexpected error occurred on Groupda.com: {e}")
        return pd.DataFrame()
    
    st.success(f"Finished Groupda.com. Total pages: {page_counter}, Links found: {len(results)}")
    df = pd.DataFrame(results)
    if not df.empty:
        df['Category_ID'], df['Country_ID'], df['Language_ID'] = category_value, country_value, language_value
    return df

def parse_groupda_containers(soup):
    # This function is correct.
    groups = []
    for item in soup.find_all('div', class_='view-tenth'):
        link_tag = item.find('a', href=lambda href: href and 'chat.whatsapp.com' in href)
        if not link_tag: continue
        href = link_tag.get('href', '').strip()
        if not href: continue
        title = (item.find('h3') or item.find('p')).get_text(strip=True)
        img_src = item.find('img').get('src', '') if item.find('img') else ''
        groups.append({'Source': 'Groupda.com', 'Title': title, 'Link': href, 'Image_URL': img_src})
    return groups

def scrape_groupsor(category_value="", country_value="", language_value="", max_pages=None):
    """
    Scrapes Groupsor.link by sending filter parameters with every AJAX request.
    """
    find_url = "https://groupsor.link/group/find"
    load_url = "https://groupsor.link/group/indexmore"
    join_base_url = "https://chat.whatsapp.com/invite/"
    results = []
    
    session = cloudscraper.create_scraper()
    
    try:
        st.write("Initializing Groupsor.link session...")
        # A preliminary visit to the find URL is good practice
        session.get(find_url, headers=get_random_headers(), timeout=DEFAULT_TIMEOUT)

        # --- REVISED LOGIC: Loop from page 0 and send filters every time ---
        page_counter = 0
        while True:
            if max_pages is not None and page_counter >= max_pages:
                st.info(f"Reached maximum pages limit ({max_pages}) for Groupsor.link.")
                break

            st.write(f"Scraping Groupsor.link page {page_counter + 1}...")
            
            # NOTE: For Groupsor, the 'load more' on the find page sends all filters.
            post_data = {
                'group_no': str(page_counter),
                'gcid': category_value,
                'cid': country_value,
                'lid': language_value
            }
            
            load_headers = get_random_headers(referer=find_url)
            load_headers.update({
                'X-Requested-With': 'XMLHttpRequest',
                'Origin': 'https://groupsor.link',
            })
            
            res = session.post(load_url, data=post_data, headers=load_headers, timeout=DEFAULT_TIMEOUT)
            
            if res.status_code != 200:
                st.warning(f"Groupsor.link page {page_counter + 1}: Status {res.status_code}. Stopping.")
                break
            
            if not res.text.strip():
                st.info(f"No more results found on Groupsor.link after page {page_counter}. Stopping.")
                break
            
            result_soup = BeautifulSoup(res.text, 'html.parser')
            page_groups = parse_groupsor_containers(result_soup, join_base_url)
            
            if not page_groups:
                st.info(f"No new groups found on Groupsor.link page {page_counter + 1}. This is the end of the list.")
                break
            
            results.extend(page_groups)
            st.write(f"Found {len(page_groups)} new groups. Total so far: {len(results)}")
            page_counter += 1
            time.sleep(random.uniform(DEFAULT_DELAY_MIN, DEFAULT_DELAY_MAX))
            
    except requests.exceptions.RequestException as e:
        st.error(f"A network error occurred on Groupsor.link: {e}")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"An unexpected error occurred on Groupsor.link: {e}")
        return pd.DataFrame()
        
    st.success(f"Finished Groupsor.link. Total pages: {page_counter}, Links found: {len(results)}")
    df = pd.DataFrame(results)
    if not df.empty:
        df['Category_ID'], df['Country_ID'], df['Language_ID'] = category_value, country_value, language_value
    return df

def parse_groupsor_containers(soup, join_base_url):
    # This function is also correct.
    groups = []
    for item in soup.find_all('div', class_='view-tenth'):
        actual_whatsapp_link = ""
        join_link_tag = item.find('a', href=lambda href: href and '/group/join/' in href)
        if join_link_tag and (group_id := join_link_tag.get('href', '').split('/group/join/')[-1]):
            actual_whatsapp_link = urljoin(join_base_url, group_id)
        if not actual_whatsapp_link:
            direct_link_tag = item.find('a', href=lambda href: href and 'chat.whatsapp.com' in href)
            if direct_link_tag: actual_whatsapp_link = direct_link_tag.get('href', '').strip()
        if not actual_whatsapp_link: continue
        title = (item.find('h3') or item.find('p')).get_text(strip=True)
        img_src = item.find('img').get('src', '') if item.find('img') else ''
        groups.append({'Source': 'Groupsor.link', 'Title': title, 'Link': actual_whatsapp_link, 'Image_URL': img_src})
    return groups


# --- Streamlit App (No changes needed, the UI part of your code is perfect) ---
st.title("WhatsApp Group Scraper")
st.sidebar.header("Scraper Settings")

site_choice = st.sidebar.selectbox(
    "Select Website to Scrape:",
    ("Groupda.com", "Groupsor.link", "Both")
)

# ... [The rest of your Streamlit UI code remains here, unchanged] ...
# (I'm omitting it for brevity as it was correct)
# Options based on HTML source analysis
category_options_groupda = {
    "Default (18+)": "3", "Any Category": "", "Girls_Group": "2", "Gaming_Apps": "7",
    "Health_Beauty_Fitness": "8", "Business_Advertising_Marketing": "6", "Sports_Other_Games": "21",
    "Film_Animation": "18", "Fashion_Style_Clothing": "15", "Comedy_Funny": "9",
    "Educational_Schooling_Collage": "11", "Entertainment_Masti": "12", "Family_Relationships": "13",
    "Fan_Club_Celebrities": "14", "Earn_Money_Online": "16", "MLM_Group_Joining": "17",
    "Spiritual_Devotional": "19", "Cricket_Kabadi_FC": "20", "Food_Drinks_Recipe": "22",
    "Crypto_Bitcoin_Betting": "23",
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

max_pages_input = st.sidebar.number_input("Max Pages per Site (0 for unlimited):", min_value=0, max_value=100, value=5, step=1)
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
        st.info("No data was scraped. This could be due to network issues, anti-scraping measures, or no results matching your filters.")

st.markdown("---")
st.subheader("How it works:")
st.markdown("""
1.  **Select Website(s):** Choose one or both sites.
2.  **Choose Filters:** Select category, country, and language for each site.
3.  **Set Pages:** Define the maximum number of pages to load.
4.  **Start Scraping:** The script now mimics the website's AJAX calls perfectly, sending the filter data with every request to get the correct results.
""")
