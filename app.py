import streamlit as st
import requests
from bs4 import BeautifulSoup
import time
import random
from fake_useragent import UserAgent
import pandas as pd

# Initialize a global UserAgent object
ua = UserAgent()

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

# Function to scrape Groupda.com
def scrape_groupda(category_value="3", max_pages=3):
    base_url = "https://groupda.com/add/group/find"
    results = []
    
    # Initial request to get cookies or session data if needed
    session = requests.Session()
    session.headers.update(get_random_headers())
    
    try:
        # The form submission URL seems to be the same as the base URL
        response = session.get(base_url, headers=get_random_headers(), timeout=10)
        response.raise_for_status()
        
        # Parse initial page to get any hidden form data or tokens if necessary
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Loop through pages
        for page in range(max_pages):
            st.write(f"Scraping Groupda.com page {page + 1}...")
            
            # POST data for pagination/form submission
            data = {
                'gcid': category_value, # Default to "18_Adult_Hot_Babes"
                'group_no': str(page),
                'findPage': 'true'
                # Note: countryCode and countryName are fetched via JS on the site, we might need to simulate this or leave them out
            }
            
            # Make POST request to load results
            result_url = "https://groupda.com/add/group/loadresult"
            res = session.post(result_url, data=data, headers=get_random_headers(), timeout=10)
            res.raise_for_status()
            
            # Parse the returned HTML snippet
            result_soup = BeautifulSoup(res.text, 'html.parser')
            
            # Find group links - based on the structure, they seem to be inside <a> tags with href containing 'chat.whatsapp.com'
            links = result_soup.find_all('a', href=lambda href: href and 'chat.whatsapp.com' in href)
            
            if not links:
                st.warning(f"No links found on Groupda.com page {page + 1}.")
                break # No more results
            
            for link in links:
                href = link.get('href')
                title = link.get_text(strip=True) or "No Title"
                results.append({
                    'Source': 'Groupda.com',
                    'Title': title,
                    'Link': href,
                    'Category': category_value # This is the ID, not the name
                })
            
            # Add a small delay to be respectful
            time.sleep(random.uniform(1, 3))
            
    except requests.exceptions.RequestException as e:
        st.error(f"An error occurred while scraping Groupda.com: {e}")
        return pd.DataFrame() # Return empty DataFrame on error
    
    return pd.DataFrame(results)

# Function to scrape Groupsor.link
def scrape_groupsor(category_value="", max_pages=3):
    base_url = "https://groupsor.link/group/find"
    results = []
    
    session = requests.Session()
    session.headers.update(get_random_headers())
    
    try:
        # Initial request
        response = session.get(base_url, headers=get_random_headers(), timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Loop through pages
        for page in range(max_pages):
            st.write(f"Scraping Groupsor.link page {page + 1}...")
            
            # POST data for pagination
            data = {
                'gcid': category_value, # Default to empty (Any Category)
                'group_no': str(page)
            }
            
            result_url = "https://groupsor.link/group/indexmore"
            res = session.post(result_url, data=data, headers=get_random_headers(), timeout=10)
            res.raise_for_status()
            
            result_soup = BeautifulSoup(res.text, 'html.parser')
            
            # Find group links
            links = result_soup.find_all('a', href=lambda href: href and 'chat.whatsapp.com' in href)
            
            if not links:
                st.warning(f"No links found on Groupsor.link page {page + 1}.")
                break # No more results
            
            for link in links:
                href = link.get('href')
                title = link.get_text(strip=True) or "No Title"
                results.append({
                    'Source': 'Groupsor.link',
                    'Title': title,
                    'Link': href,
                    'Category': category_value
                })
                
            time.sleep(random.uniform(1, 3))
            
    except requests.exceptions.RequestException as e:
        st.error(f"An error occurred while scraping Groupsor.link: {e}")
        return pd.DataFrame()
        
    return pd.DataFrame(results)

# --- Streamlit App ---
st.title("WhatsApp Group Scraper")
st.write("Scrape WhatsApp group links from competitor websites.")

# --- Sidebar for Inputs ---
st.sidebar.header("Scraper Settings")

# Site Selection
site_choice = st.sidebar.selectbox(
    "Select Website to Scrape:",
    ("Groupda.com", "Groupsor.link", "Both")
)

# Category Selection (based on analysis of the provided HTML)
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
    # ... (add more as needed, but 3 is prominent in the JS)
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

selected_category_name = ""
selected_category_value = ""
if site_choice == "Groupda.com":
    selected_category_name = st.sidebar.selectbox("Select Category (Groupda.com):", list(category_options_groupda.keys()))
    selected_category_value = category_options_groupda[selected_category_name]
elif site_choice == "Groupsor.link":
    selected_category_name = st.sidebar.selectbox("Select Category (Groupsor.link):", list(category_options_groupsor.keys()))
    selected_category_value = category_options_groupsor[selected_category_name]
else: # Both
    # For simplicity, let's use Groupda's categories as default for "Both"
    selected_category_name = st.sidebar.selectbox("Select Category (Applied to both sites):", list(category_options_groupda.keys()))
    selected_category_value = category_options_groupda[selected_category_name]

# Number of Pages
max_pages = st.sidebar.number_input("Number of Pages to Scrape:", min_value=1, max_value=10, value=2)

# Scrape Button
if st.sidebar.button("Start Scraping"):
    all_data = []
    
    if site_choice in ["Groupda.com", "Both"]:
        with st.spinner(f"Scraping data from Groupda.com (Category: {selected_category_name})..."):
            df_groupda = scrape_groupda(category_value=selected_category_value, max_pages=max_pages)
            if not df_groupda.empty:
                all_data.append(df_groupda)
            st.success("Finished scraping Groupda.com!")

    if site_choice in ["Groupsor.link", "Both"]:
        with st.spinner(f"Scraping data from Groupsor.link (Category: {selected_category_name})..."):
            df_groupsor = scrape_groupsor(category_value=selected_category_value, max_pages=max_pages)
            if not df_groupsor.empty:
                all_data.append(df_groupsor)
            st.success("Finished scraping Groupsor.link!")

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
        st.info("No data was scraped. Please check the settings or try again later.")

# --- Information Section ---
st.markdown("---")
st.subheader("How it works:")
st.markdown("""
1.  **Select Website:** Choose which competitor site(s) to scrape.
2.  **Choose Category:** Select a category to filter the groups (based on site's dropdown options).
3.  **Set Pages:** Define how many pages of results to fetch.
4.  **Start Scraping:** Click the button to begin the process.
5.  **View & Download:** See the results in a table and download them as a CSV file.
""")

st.info("**Note:** This scraper is designed for educational and research purposes. Please ensure your usage complies with the target websites' `robots.txt` and terms of service. Be respectful of their servers by not making too many rapid requests.")
