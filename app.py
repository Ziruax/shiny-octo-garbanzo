# app.py
import streamlit as st
import requests
from bs4 import BeautifulSoup
import time
import random
from fake_useragent import UserAgent
import pandas as pd

# Initialize a global UserAgent object
ua = UserAgent()

# --- Configuration ---
DEFAULT_DELAY_MIN = 1  # Minimum delay in seconds
DEFAULT_DELAY_MAX = 3  # Maximum delay in seconds
DEFAULT_TIMEOUT = 15   # Request timeout in seconds
MAX_PAGES_DEFAULT = 5  # Default max pages in UI (user can increase)

# Function to get a random header
def get_random_headers():
    return {
        'User-Agent': ua.random,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }

# --- Scraping Functions ---

# Function to scrape Groupda.com
def scrape_groupda(category_value="", country_value="", language_value="", max_pages=None):
    """
    Scrapes Groupda.com.
    Note: The site uses a geolocation API call which is hard to replicate perfectly.
    We will try to mimic the initial page load and subsequent POST requests.
    """
    base_url = "https://groupda.com/add/group/find"
    load_url = "https://groupda.com/add/group/loadresult"
    results = []
    
    session = requests.Session()
    
    try:
        st.write("Initializing Groupda.com session...")
        # 1. Initial GET request to the find page to get cookies/session and initial content
        init_headers = get_random_headers()
        init_headers['Referer'] = 'https://groupda.com/add/'
        response = session.get(base_url, headers=init_headers, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()
        st.write("Initial page loaded.")
        
        # Parse initial page to get the initial set of groups (group_no=0)
        initial_soup = BeautifulSoup(response.text, 'html.parser')
        initial_results_div = initial_soup.find('div', id='results')
        if initial_results_div:
            initial_groups = parse_group_containers(initial_results_div, "Groupda.com")
            results.extend(initial_groups)
            st.write(f"Found {len(initial_groups)} groups on initial load.")
        else:
            st.warning("Could not find initial results div on Groupda.com")

        # 2. Loop through subsequent pages using AJAX POST
        page_counter = 1 # Start from 1 as 0 is already loaded
        while True: # Infinite loop, break on no results or max_pages
            if max_pages is not None and page_counter >= max_pages:
                st.info(f"Reached maximum pages limit ({max_pages}) for Groupda.com.")
                break

            st.write(f"Scraping Groupda.com page {page_counter + 1} (AJAX)...")
            
            # POST data for loading results
            # Based on the JS, we should include countryCode and countryName if possible,
            # but since we can't easily get them, we'll omit them and see if it works.
            post_data = {
                'group_no': str(page_counter),
                'gcid': category_value,
                'cid': country_value,
                'lid': language_value,
                'findPage': 'true'
                # countryCode and countryName omitted
            }
            
            # Make POST request to load results
            load_headers = get_random_headers()
            load_headers['Referer'] = base_url
            load_headers['X-Requested-With'] = 'XMLHttpRequest'
            load_headers['Content-Type'] = 'application/x-www-form-urlencoded; charset=UTF-8'
            
            res = session.post(load_url, data=post_data, headers=load_headers, timeout=DEFAULT_TIMEOUT)
            
            # Check for specific error responses or empty content
            if res.status_code != 200:
                st.warning(f"Groupda.com page {page_counter + 1}: Received status code {res.status_code}. Stopping.")
                break
            
            # Check if response content indicates no more results
            if not res.text.strip() or "<!-- No results -->" in res.text or res.text.strip() == "":
                st.info(f"No more results found on Groupda.com after page {page_counter + 1}.")
                break # Likely no more results
            
            # Parse the returned HTML snippet
            result_soup = BeautifulSoup(res.text, 'html.parser')
            
            # Extract groups
            page_groups = parse_group_containers(result_soup, "Groupda.com")
            
            if not page_groups:
                st.warning(f"No group links found in parsed content of Groupda.com page {page_counter + 1}.")
                # Decide whether to break or continue. Let's break as it likely means no more results.
                break 
            
            for group in page_groups:
                group['Category'] = category_value
                group['Country'] = country_value
                group['Language'] = language_value
                results.append(group)
            
            page_counter += 1
            # Add a delay to be respectful
            delay = random.uniform(DEFAULT_DELAY_MIN, DEFAULT_DELAY_MAX)
            st.write(f"Waiting for {delay:.2f} seconds...")
            time.sleep(delay)
            
    except requests.exceptions.Timeout:
        st.error("Timeout occurred while scraping Groupda.com. The site might be slow or unresponsive.")
        return pd.DataFrame() # Return empty DataFrame on error
    except requests.exceptions.RequestException as e:
        st.error(f"An HTTP error occurred while scraping Groupda.com: {e}")
        return pd.DataFrame() # Return empty DataFrame on error
    except Exception as e:
        st.error(f"An unexpected error occurred while scraping Groupda.com: {e}")
        return pd.DataFrame()
    
    st.success(f"Finished scraping Groupda.com. Total pages scraped: {page_counter}, Links found: {len(results)}")
    df = pd.DataFrame(results)
    # Reorder columns if needed
    if not df.empty:
        df = df[['Source', 'Title', 'Link', 'Category', 'Country', 'Language']]
    return df

# Function to scrape Groupsor.link
def scrape_groupsor(category_value="", country_value="", language_value="", max_pages=None):
    """
    Scrapes Groupsor.link.
    """
    base_url = "https://groupsor.link/group/find"
    load_url = "https://groupsor.link/group/indexmore"
    results = []
    
    session = requests.Session()
    
    try:
        st.write("Initializing Groupsor.link session...")
        # 1. Initial GET request to load the first set of results (group_no=0)
        init_headers = get_random_headers()
        init_headers['Referer'] = 'https://groupsor.link/'
        # The initial load happens via JS: $('#results').load("...", {'group_no': 0})
        # We need to replicate this initial AJAX call.
        initial_post_data = {'group_no': '0'}
        initial_headers_ajax = get_random_headers()
        initial_headers_ajax['Referer'] = base_url
        initial_headers_ajax['X-Requested-With'] = 'XMLHttpRequest'
        initial_headers_ajax['Content-Type'] = 'application/x-www-form-urlencoded; charset=UTF-8'
        
        initial_res = session.post(load_url, data=initial_post_data, headers=initial_headers_ajax, timeout=DEFAULT_TIMEOUT)
        initial_res.raise_for_status()
        
        if initial_res.text.strip():
            initial_soup = BeautifulSoup(initial_res.text, 'html.parser')
            initial_groups = parse_group_containers(initial_soup, "Groupsor.link")
            results.extend(initial_groups)
            st.write(f"Found {len(initial_groups)} groups on initial load.")
        else:
            st.warning("Initial AJAX call for Groupsor.link returned empty content.")
        st.write("Initial page loaded.")
        
        # 2. Loop through subsequent pages
        page_counter = 1 # Start from 1
        while True: # Infinite loop, break on no results or max_pages
            if max_pages is not None and page_counter >= max_pages:
                st.info(f"Reached maximum pages limit ({max_pages}) for Groupsor.link.")
                break

            st.write(f"Scraping Groupsor.link page {page_counter + 1}...")
            
            # POST data for loading more results
            post_data = {
                'group_no': str(page_counter),
                'gcid': category_value,
                'cid': country_value,
                'lid': language_value
            }
            
            load_headers = get_random_headers()
            load_headers['Referer'] = base_url
            load_headers['X-Requested-With'] = 'XMLHttpRequest'
            load_headers['Content-Type'] = 'application/x-www-form-urlencoded; charset=UTF-8'
            
            res = session.post(load_url, data=post_data, headers=load_headers, timeout=DEFAULT_TIMEOUT)
            
            # Check for specific error responses or empty content
            if res.status_code != 200:
                st.warning(f"Groupsor.link page {page_counter + 1}: Received status code {res.status_code}. Stopping.")
                break
            
            # Check if response content indicates no more results
            if not res.text.strip() or "<!-- No results -->" in res.text or res.text.strip() == "":
                st.info(f"No more results found on Groupsor.link after page {page_counter + 1}.")
                break # Likely no more results
            
            result_soup = BeautifulSoup(res.text, 'html.parser')
            
            # Extract groups
            page_groups = parse_group_containers(result_soup, "Groupsor.link")
            
            if not page_groups:
                st.warning(f"No group links found in parsed content of Groupsor.link page {page_counter + 1}.")
                break # Likely no more results
            
            for group in page_groups:
                group['Category'] = category_value
                group['Country'] = country_value
                group['Language'] = language_value
                results.append(group)
                
            page_counter += 1
            delay = random.uniform(DEFAULT_DELAY_MIN, DEFAULT_DELAY_MAX)
            st.write(f"Waiting for {delay:.2f} seconds...")
            time.sleep(delay)
            
    except requests.exceptions.Timeout:
        st.error("Timeout occurred while scraping Groupsor.link. The site might be slow or unresponsive.")
        return pd.DataFrame()
    except requests.exceptions.RequestException as e:
        st.error(f"An HTTP error occurred while scraping Groupsor.link: {e}")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"An unexpected error occurred while scraping Groupsor.link: {e}")
        return pd.DataFrame()
        
    st.success(f"Finished scraping Groupsor.link. Total pages scraped: {page_counter}, Links found: {len(results)}")
    df = pd.DataFrame(results)
    # Reorder columns if needed
    if not df.empty:
        df = df[['Source', 'Title', 'Link', 'Category', 'Country', 'Language']]
    return df

def parse_group_containers(soup, source_name):
    """Helper function to parse group containers from a BeautifulSoup object."""
    groups = []
    # Based on the HTML structure, look for containers. The class might vary or be absent.
    # Let's try a common pattern or just look for <a> tags directly.
    
    # Attempt 1: Look for common container classes (this might need adjustment based on actual rendered HTML)
    # group_containers = soup.find_all('div', class_='view-group') 
    
    # Attempt 2: Look for <a> tags directly containing the WhatsApp links
    group_links = soup.find_all('a', href=lambda href: href and 'chat.whatsapp.com' in href)
    
    if not group_links:
        # If no links found directly, return empty list
        return groups

    for link_tag in group_links:
        href = link_tag.get('href', '').strip()
        if not href:
            continue
            
        # Try to get a title
        # Option 1: Text inside the <a> tag
        title_from_link = link_tag.get_text(strip=True)
        
        # Option 2: Look for a nearby title element (this is heuristic and might need refinement)
        title = "No Title Found"
        parent = link_tag.parent
        if parent:
            # Look for a heading tag sibling or parent
            title_tag = parent.find_previous_sibling(['h3', 'h4', 'h5', 'h6', 'p', 'div'])
            if title_tag and title_tag.get_text(strip=True):
                title = title_tag.get_text(strip=True)
            elif title_from_link:
                title = title_from_link
            # Add more heuristics if needed
            
        groups.append({
            'Source': source_name,
            'Title': title,
            'Link': href,
            # Category, Country, Language will be added by the caller
        })
        
    return groups


# --- Streamlit App ---
st.title("WhatsApp Group Scraper")
st.write("Scrape WhatsApp group links from competitor websites.")
st.warning("**Disclaimer:** This tool is for educational/research purposes only. Respect the target websites' `robots.txt` and terms of service. Use responsibly to avoid overloading their servers.")

# --- Sidebar for Inputs ---
st.sidebar.header("Scraper Settings")

# Site Selection
site_choice = st.sidebar.selectbox(
    "Select Website to Scrape:",
    ("Groupda.com", "Groupsor.link", "Both")
)

# Category, Country, Language Selection (based on analysis)
# Using simplified options for demonstration. You can expand these.
category_options_groupda = {
    "Any Category": "",
    "Girls_Group": "2",
    "18_Adult_Hot_Babes": "3",
    "Art_Design_Photography": "4",
    "Auto_Vehicle": "5",
    "Business_Advertising_Marketing": "6",
    "Gaming_Apps": "7",
    "Health_Beauty_Fitness": "8",
    "Comedy_Funny": "9",
    "Dating_Flirting_Chatting": "10",
    "Educational_Schooling_Collage": "11",
    "Entertainment_Masti": "12",
    "Family_Relationships": "13",
    "Fan_Club_Celebrities": "14",
    "Fashion_Style_Clothing": "15",
    "Earn_Money_Online": "16",
    "MLM_Group_Joining": "17",
    "Film_Animation": "18",
    "Spiritual_Devotional": "19",
    "Cricket_Kabadi_FC": "20",
    "Sports_Other_Games": "21",
    "Food_Drinks_Recipe": "22",
    "Crypto_Bitcoin_Betting": "23",
    "Any_Category": "24",
    # Add more as needed
}
category_options_groupsor = {
    "Any Category": "",
    "Adult/18+/Hot": "7",
    "Art/Design/Photography": "5",
    "Auto/Vehicle": "6",
    "Business/Advertising/Marketing": "8",
    "Comedy/Funny": "9",
    "Dating/Flirting/Chatting": "10",
    "Education/School": "11",
    "Entertainment/Masti": "12",
    "Family/Relationships": "13",
    "Fan Club/Celebrities": "14",
    "Fashion/Style/Clothing": "15",
    "Film/Animation": "16",
    "Food/Drinks": "17",
    "Gaming/Apps": "18",
    "Health/Beauty/Fitness": "19",
    "Jobs/Career": "20",
    "Money/Earning": "22",
    "Music/Audio/Songs": "21",
    "News/Magazines/Politics": "23",
    "Pets/Animals/Nature": "24",
    "Roleplay/Comics": "25",
    "Science/Technology": "26",
    "Shopping/Buy/Sell": "27",
    "Social/Friendship/Community": "30",
    "Spiritual/Devotional": "29",
    "Sports/Games": "28",
    "Thoughts/Quotes/Jokes": "31",
    "Travel/Local/Place": "32",
}

# Country and Language options are large. For simplicity, we'll define a small subset.
# You can expand this or use a library like `pycountry` if needed.
country_options_simple = {"Any Country": "", "India": "99", "USA": "223", "UK": "222", "Canada": "38", "Australia": "13"}
language_options_simple = {"Any Language": "", "English": "17", "Hindi": "26", "Spanish": "51", "French": "20", "German": "23"}

selected_category_name_gd = ""
selected_category_value_gd = ""
selected_country_value_gd = ""
selected_language_value_gd = ""

selected_category_name_gs = ""
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

# Number of Pages (Set to None for unlimited, or a high default)
max_pages_input = st.sidebar.number_input("Max Pages per Site (0 for unlimited):", min_value=0, max_value=1000, value=0, step=1)
max_pages = None if max_pages_input == 0 else max_pages_input

# Scrape Button
if st.sidebar.button("Start Scraping"):
    all_data = []
    
    if site_choice in ["Groupda.com", "Both"]:
        with st.spinner(f"Scraping data from Groupda.com (Category: {selected_category_name_gd})..."):
            df_groupda = scrape_groupda(
                category_value=selected_category_value_gd, 
                country_value=selected_country_value_gd, 
                language_value=selected_language_value_gd, 
                max_pages=max_pages
            )
            if not df_groupda.empty:
                all_data.append(df_groupda)

    if site_choice in ["Groupsor.link", "Both"]:
        with st.spinner(f"Scraping data from Groupsor.link (Category: {selected_category_name_gs})..."):
            df_groupsor = scrape_groupsor(
                category_value=selected_category_value_gs, 
                country_value=selected_country_value_gs, 
                language_value=selected_language_value_gs, 
                max_pages=max_pages
            )
            if not df_groupsor.empty:
                all_data.append(df_groupsor)

    # Combine and Display Results
    if all_data:
        final_df = pd.concat(all_data, ignore_index=True)
        st.subheader("Scraped Results")
        st.dataframe(final_df)
        
        # Download Button
        csv = final_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="Download data as CSV",
            data=csv,
            file_name='whatsapp_groups.csv',
            mime='text/csv',
        )
    else:
        st.info("No data was scraped. Please check the settings, network connection, or try again later. The site structure might have changed.")

# --- Information Section ---
st.markdown("---")
st.subheader("How it works:")
st.markdown("""
1.  **Select Website:** Choose which competitor site(s) to scrape.
2.  **Choose Filters:** Select categories, countries, and languages (based on site options).
3.  **Set Pages:** Define how many pages of results to fetch per site (0 means unlimited until no more results are found).
4.  **Start Scraping:** Click the button to begin the process. The scraper will load the initial page and then make requests to load subsequent pages of results.
5.  **View & Download:** See the results in a table and download them as a CSV file.
""")

st.info("**Note on Limitations:**")
st.markdown("""
*   **Dynamic Content:** `Groupda.com` uses a JavaScript call to determine your country (`countryCode`, `countryName`). This scraper omits these parameters in POST requests, which might affect results if the server strictly filters by detected location.
*   **Site Changes:** If the target websites change their HTML structure or request parameters, the scraper will need to be updated.
*   **Rate Limiting/Blocking:** Sending too many requests too quickly can lead to your IP being blocked. The scraper includes random delays.
*   **Respectful Scraping:** Always ensure your usage complies with the websites' terms of service and is respectful of their resources.
""")
