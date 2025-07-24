# groupsor_scraper_app.py
import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import time
import logging
from urllib.parse import urljoin, quote_plus
import pandas as pd
import io

# --- Configuration ---
BASE_URL = "https://groupsor.link"
SEARCH_ENDPOINT = "/group/search"
AJAX_ENDPOINT = "/group/findmore"
TIMEOUT = 15  # seconds
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds
REQUEST_DELAY = 0.5  # seconds, delay between requests to be respectful
# --- End Configuration ---

# --- Logging Setup ---
# Adjust level as needed (DEBUG for more details, WARNING to reduce spam)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Session State Initialization ---
if 'scraping_state' not in st.session_state:
    st.session_state.scraping_state = 'idle'  # 'idle', 'running', 'paused', 'stopped'
if 'scraped_data' not in st.session_state:
    st.session_state.scraped_data = [] # Stores final results [{'Source': ..., 'Link': ...}, ...]
if 'scraping_progress' not in st.session_state:
    st.session_state.scraping_progress = 0.0
if 'scraping_message' not in st.session_state:
    st.session_state.scraping_message = "Ready to start."
if 'current_task' not in st.session_state:
    st.session_state.current_task = ""
if 'session_object' not in st.session_state:
    st.session_state.session_object = None
if 'intermediate_links_found' not in st.session_state: # Track links found during scraping
     st.session_state.intermediate_links_found = []
if 'intermediate_links_processed' not in st.session_state: # Track links processed during resolution
     st.session_state.intermediate_links_processed = 0

# --- Helper Functions ---

def create_session():
    """Creates a requests session with headers to mimic a real browser."""
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Referer': '',
        'DNT': '1',
        # 'Upgrade-Insecure-Requests': '1', # Can sometimes help
    })
    return session

def safe_request(session, method, url, **kwargs):
    """Makes a request with retries and delays."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            logger.debug(f"Attempt {attempt + 1} - {method} request to {url}")
            response = session.request(method, url, timeout=TIMEOUT, **kwargs)
            logger.debug(f"Response Status Code: {response.status_code}")

            if response.status_code == 403:
                logger.warning(f"403 Forbidden for {url}. Retrying...")
                st.session_state.scraping_message = f"⚠️ 403 Forbidden for {url[:50]}... Retrying ({attempt + 1}/{MAX_RETRIES + 1})"
                st.rerun()
            elif response.status_code == 429:
                logger.warning(f"429 Too Many Requests for {url}. Waiting longer...")
                st.session_state.scraping_message = f"⏳ 429 Rate Limited for {url[:50]}... Waiting..."
                st.rerun()
                time.sleep(RETRY_DELAY * 2)
            elif response.status_code >= 400:
                logger.error(f"HTTP Error {response.status_code} for {url}")
                st.session_state.scraping_message = f"❌ HTTP {response.status_code} Error for {url[:50]}..."
                st.rerun()
            else:
                response.raise_for_status()
                return response
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed (attempt {attempt + 1}): {e}")
            st.session_state.scraping_message = f"⚠️ Request Error for {url[:50]}... Retrying ({attempt + 1}/{MAX_RETRIES + 1})"
            st.rerun()
        except Exception as e:
            logger.error(f"Unexpected error during request (attempt {attempt + 1}): {e}")
            st.session_state.scraping_message = f"💥 Unexpected Error for {url[:50]}... Retrying ({attempt + 1}/{MAX_RETRIES + 1})"
            st.rerun()

        if attempt < MAX_RETRIES:
            logger.info(f"Retrying in {RETRY_DELAY} seconds...")
            time.sleep(RETRY_DELAY)
        else:
            logger.error(f"Failed to fetch {url} after {MAX_RETRIES + 1} attempts.")
            st.session_state.scraping_message = f"❌ Failed to fetch {url[:50]}... after retries."
            st.rerun()
    return None

def get_final_whatsapp_url(session, join_url):
    """
    Fetches the intermediate join page and extracts the final WhatsApp URL.
    Handles retries.
    """
    logger.info(f"Fetching join page: {join_url}")
    st.session_state.current_task = f"Resolving: ...{join_url[-40:]}"
    st.rerun()

    response = safe_request(session, 'GET', join_url)
    if not response:
        return None

    try:
        soup = BeautifulSoup(response.content, 'html.parser')

        # --- 1. Look for direct links ---
        whatsapp_links = soup.find_all('a', href=re.compile(r'chat\.whatsapp\.com'))
        for link_tag in whatsapp_links:
            href = link_tag.get('href')
            if href and 'chat.whatsapp.com' in href:
                logger.info(f"Found final URL (direct link): {href}")
                return href

        # --- 2. Look in JavaScript for window.location or window.open ---
        scripts = soup.find_all('script')
        for script in scripts:
            if script.string:
                loc_match = re.search(r"window\.location\.href\s*=\s*['\"](https?://chat\.whatsapp\.com/[^'\"]*)['\"]", script.string, re.IGNORECASE)
                if loc_match:
                    final_url = loc_match.group(1)
                    logger.info(f"Found final URL in JS (window.location): {final_url}")
                    return final_url
                open_match = re.search(r"window\.open\(['\"](https?://chat\.whatsapp\.com/[^'\"]*)['\"]", script.string, re.IGNORECASE)
                if open_match:
                    final_url = open_match.group(1)
                    logger.info(f"Found final URL in JS (window.open): {final_url}")
                    return final_url

        logger.warning(f"Final URL not found on join page {join_url}")
        return None

    except Exception as e:
        logger.error(f"Error parsing join page {join_url}: {e}")
        return None

def scrape_search_results_step(session, keyword, page_counter, search_url, gcid="", cid="", lid=""):
    """
    Performs one step of scraping GroupSor search results.
    Returns (new_join_links, next_page_counter, is_finished).
    """
    logger.info(f"Fetching AJAX page {page_counter} for keyword '{keyword}'...")
    st.session_state.current_task = f"Scraping Page {page_counter}..."
    st.rerun()

    ajax_params = {
        'group_no': page_counter,
        'keyword': keyword,
        'gcid': gcid,
        'cid': cid,
        'lid': lid
    }
    headers = {'Referer': search_url}

    # Update session headers temporarily
    original_headers = session.headers.copy()
    session.headers.update(headers)
    ajax_response = safe_request(session, 'POST', urljoin(BASE_URL, AJAX_ENDPOINT), data=ajax_params)
    # Restore original headers
    session.headers.clear()
    session.headers.update(original_headers)

    if not ajax_response:
        st.session_state.scraping_message = f"❌ AJAX request failed for page {page_counter}. Stopping."
        st.rerun()
        return [], page_counter, True # Stop scraping

    ajax_html = ajax_response.text.strip()

    # Check for end condition
    if not ajax_html or "<div id=\"no\" style=\"display: none;color: #555\">No More groups</div>" in ajax_html:
        st.session_state.scraping_message = f"✅ Reached end of results at page {page_counter}."
        st.rerun()
        return [], page_counter + 1, True # Finished

    # --- Extract Join Links from AJAX Response ---
    soup = BeautifulSoup(ajax_html, 'html.parser')
    join_links_on_page = []
    join_link_tags = soup.find_all('a', href=re.compile(r'^/group/join/[A-Za-z0-9]+$'))
    for tag in join_link_tags:
        href = tag.get('href')
        if href:
            full_url = urljoin(BASE_URL, href)
            join_links_on_page.append(full_url)

    if not join_links_on_page:
        st.session_state.scraping_message = f"⚠️ No links found on page {page_counter}. Assuming end."
        st.rerun()
        return [], page_counter + 1, True # Finished

    st.session_state.scraping_message = f"📄 Page {page_counter}: Found {len(join_links_on_page)} links."
    st.session_state.intermediate_links_found.extend(join_links_on_page) # Update found links
    st.rerun()
    return join_links_on_page, page_counter + 1, False # Not finished

# --- Streamlit App ---

def main():
    st.set_page_config(page_title="GroupSor Scraper", page_icon="🔍")
    st.title("🔍 GroupSor.link WhatsApp Group Scraper")
    st.markdown("Scrape final WhatsApp group links using keywords.")

    # --- Configuration ---
    st.sidebar.header("Configuration")
    keyword = st.sidebar.text_input("Search Keyword", value="girls")
    # Optional: Add delay control
    # request_delay = st.sidebar.slider("Delay between requests (s)", 0.0, 2.0, REQUEST_DELAY, 0.1)

    # --- Control Buttons ---
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("▶️ Start Scraping"):
            if st.session_state.scraping_state in ['idle', 'stopped']:
                if not keyword.strip():
                    st.sidebar.error("Please enter a search keyword.")
                    return
                # Reset state for a new run
                st.session_state.scraped_data = []
                st.session_state.intermediate_links_found = []
                st.session_state.intermediate_links_processed = 0
                st.session_state.scraping_state = 'running'
                st.session_state.scraping_message = "Initializing scraper..."
                st.session_state.current_task = "Setting up..."
                st.session_state.scraping_progress = 0.0
                if not st.session_state.session_object:
                    st.session_state.session_object = create_session()
                st.rerun()
    with col2:
        if st.button("⏸️ Pause"):
            if st.session_state.scraping_state == 'running':
                st.session_state.scraping_state = 'paused'
                st.session_state.scraping_message = "⏸️ Paused. Click 'Resume' to continue."
                st.rerun()
    with col3:
        if st.button("⏹️ Stop"):
            if st.session_state.scraping_state in ['running', 'paused']:
                st.session_state.scraping_state = 'stopped'
                st.session_state.scraping_message = "⏹️ Stopped by user."
                st.session_state.current_task = "Stopped."
                # Optionally close session
                # if st.session_state.session_object:
                #     st.session_state.session_object.close()
                #     st.session_state.session_object = None
                st.rerun()

    # --- Progress and Status ---
    st.progress(st.session_state.scraping_progress)
    st.info(f"**Status:** {st.session_state.scraping_message}")
    st.caption(f"*Task:* {st.session_state.current_task}")

    # --- Scraping Logic (Runs in chunks based on session state) ---
    if st.session_state.scraping_state == 'running':
        session = st.session_state.session_object
        search_url = f"{BASE_URL}{SEARCH_ENDPOINT}?keyword={quote_plus(keyword)}"
        # Initial setup (could be expanded to get gcid etc. if needed from initial page)
        gcid, cid, lid = "", "", ""

        # Use session state to track pagination
        if 'gs_page_counter' not in st.session_state:
            st.session_state.gs_page_counter = 0
            # Initial search request context (might help)
            try:
                safe_request(session, 'GET', search_url)
                time.sleep(REQUEST_DELAY)
            except:
                pass # Ignore errors here

        try:
            # --- Phase 1: Scrape Intermediate Links ---
            if 'scraping_phase' not in st.session_state or st.session_state.scraping_phase == 'collecting':
                new_links, next_page, finished = scrape_search_results_step(
                    session, keyword, st.session_state.gs_page_counter, search_url, gcid, cid, lid
                )
                # Store newly found links in session state for later resolution
                if 'links_to_resolve' not in st.session_state:
                    st.session_state.links_to_resolve = []
                st.session_state.links_to_resolve.extend(new_links)

                st.session_state.gs_page_counter = next_page
                if finished:
                    st.session_state.scraping_message = f"✅ Scraping finished. Found {len(st.session_state.intermediate_links_found)} links. Starting resolution..."
                    st.session_state.scraping_phase = 'resolving'
                    st.session_state.intermediate_links_processed = 0
                    st.rerun()
                else:
                    time.sleep(REQUEST_DELAY)
                    st.rerun() # Continue scraping

            # --- Phase 2: Resolve Links ---
            elif st.session_state.scraping_phase == 'resolving':
                 total_links = len(st.session_state.links_to_resolve)
                 if total_links == 0:
                     st.session_state.scraping_message = "ℹ️ No links to resolve."
                     st.session_state.scraping_state = 'idle'
                     st.rerun()
                     return

                 if st.session_state.intermediate_links_processed < total_links:
                    current_index = st.session_state.intermediate_links_processed
                    link_to_resolve = st.session_state.links_to_resolve[current_index]
                    st.session_state.scraping_progress = (current_index + 1) / total_links
                    final_url = get_final_whatsapp_url(session, link_to_resolve)
                    if final_url:
                        st.session_state.scraped_data.append({'Source': link_to_resolve, 'Link': final_url})
                    else:
                        # Optionally include failed ones
                        st.session_state.scraped_data.append({'Source': link_to_resolve, 'Link': 'FAILED/NOT_FOUND'})
                    st.session_state.intermediate_links_processed = current_index + 1
                    st.session_state.scraping_message = f"🔗 Resolved {current_index + 1}/{total_links} links."
                    time.sleep(REQUEST_DELAY)
                    st.rerun() # Continue resolving
                 else:
                     # Finished resolving
                     st.session_state.scraping_message = f"🎉 Finished! Resolved {total_links} links. Found {len([d for d in st.session_state.scraped_data if d['Link'] != 'FAILED/NOT_FOUND'])} WhatsApp links."
                     st.session_state.current_task = "Complete."
                     st.session_state.scraping_state = 'idle'
                     st.session_state.scraping_progress = 1.0
                     # Clean up temp state
                     del st.session_state['gs_page_counter']
                     del st.session_state['scraping_phase']
                     del st.session_state['links_to_resolve']
                     st.rerun()

        except Exception as e:
            logger.error(f"An error occurred during scraping: {e}", exc_info=True)
            st.session_state.scraping_message = f"💥 Error: {str(e)[:100]}..."
            st.session_state.scraping_state = 'stopped'
            st.session_state.current_task = "Error."
            st.rerun()

    # --- Resume Button ---
    if st.session_state.scraping_state == 'paused':
        st.divider()
        if st.button("▶️ Resume Scraping"):
            st.session_state.scraping_state = 'running'
            st.session_state.scraping_message = "Resuming scraping..."
            st.rerun()

    # --- Display Results ---
    if st.session_state.scraped_data:
        st.divider()
        st.subheader("📊 Scraped WhatsApp Group Links")
        # Filter out failed ones for the main display if desired
        # success_data = [d for d in st.session_state.scraped_data if d['Link'] != 'FAILED/NOT_FOUND']
        # df = pd.DataFrame(success_data)
        df = pd.DataFrame(st.session_state.scraped_data)
        st.dataframe(df, use_container_width=True)

        # --- CSV Download (Only Final Links) ---
        # Prepare data for CSV: Only 'Link' column for WhatsApp links
        # Filter out failures if you only want successful links
        # csv_data_list = [d['Link'] for d in st.session_state.scraped_data if d['Link'] != 'FAILED/NOT_FOUND' and d['Link'].startswith('https://chat.whatsapp.com/')]
        # For including source, keep the dict
        csv_buffer = io.StringIO()
        # Write header
        # csv_buffer.write("WhatsApp Group Link\n") # For links only
        # for link in csv_data_list:
        #     csv_buffer.write(f"{link}\n")
        # For links with source
        df.to_csv(csv_buffer, index=False)
        csv_data = csv_buffer.getvalue()
        csv_buffer.close()

        st.download_button(
            label="💾 Download CSV (Final Links)",
            data=csv_data,
            file_name=f'groupsor_{keyword.replace(" ", "_")}_whatsapp_links.csv',
            mime='text/csv',
        )
    else:
        if st.session_state.scraping_state == 'idle' and not st.session_state.scraping_message.startswith("Ready"):
            st.info("Scraping completed or stopped. No links found or resolved.")
        elif st.session_state.scraping_state == 'idle':
            st.info("Enter a keyword and click 'Start Scraping'.")

if __name__ == "__main__":
    main()
