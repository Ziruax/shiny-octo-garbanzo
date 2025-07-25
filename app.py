# groupsor_scraper_final.py (Revised)
import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import time
import logging
from urllib.parse import urljoin, quote_plus, urlparse
import pandas as pd
import io
# Removed fake_useragent for now - Streamlit Cloud issues
import random

# --- Configuration ---
BASE_URL = "https://groupsor.link"
SEARCH_ENDPOINT = "/group/search"
AJAX_ENDPOINT_SEARCH = "/group/searchmore/" # e.g., /group/searchmore/girls
AJAX_ENDPOINT_FIND = "/group/findmore"       # General AJAX endpoint (not used here)
TIMEOUT = 20  # Increased timeout
MAX_RETRIES = 5 # Increased retries
RETRY_DELAY = 5  # Increased delay between retries
REQUEST_DELAY = 1.0  # seconds, base delay between requests (increased)
RANDOM_DELAY_RANGE = (0.5, 1.5) # Add a larger random delay component

# --- End Configuration ---

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s') # Set to INFO for visibility
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
# Removed ua_object from session state

# --- Helper Functions ---

def create_session():
    """Creates a requests session with comprehensive headers."""
    session = requests.Session()
    # Comprehensive headers mimicking a recent Chrome browser
    headers = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br', # Important
        'Cache-Control': 'max-age=0',
        'Sec-Ch-Ua': '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"', # Update version if needed
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"', # Or whatever platform
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none', # For initial page load
        'Sec-Fetch-User': '?1',
        'Upgrade-Insecure-Requests': '1',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36', # Update version if needed
        'Dnt': '1', # Do Not Track
        'Connection': 'keep-alive',
    }
    session.headers.update(headers)
    return session

def safe_request(session, method, url, **kwargs):
    """Makes a request with retries, delays, and updated headers."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            # Ensure Referer is set correctly for subsequent requests
            if 'headers' not in kwargs:
                 kwargs['headers'] = {}
            if 'Referer' not in kwargs['headers'] and hasattr(session, '_last_visited_url'):
                 kwargs['headers']['Referer'] = session._last_visited_url

            delay = REQUEST_DELAY + random.uniform(*RANDOM_DELAY_RANGE)
            time.sleep(delay)
            logger.info(f"Attempt {attempt + 1} - {method} request to {url}")
            logger.debug(f"Request headers: {session.headers}")
            logger.debug(f"Request kwargs headers: {kwargs.get('headers', {})}")

            response = session.request(method, url, timeout=TIMEOUT, **kwargs)
            logger.info(f"Response Status Code: {response.status_code}")

            # Store the last visited URL for Referer header
            if method.upper() == 'GET':
                session._last_visited_url = url

            if response.status_code == 403:
                logger.warning(f"403 Forbidden for {url}. Retrying...")
                st.session_state.scraping_message = f"⚠️ 403 Forbidden for {url[:50]}... Retrying ({attempt + 1}/{MAX_RETRIES + 1})"
                # Consider adding a longer delay or specific handling for 403 if retries don't help
            elif response.status_code == 429:
                logger.warning(f"429 Too Many Requests for {url}. Waiting longer...")
                st.session_state.scraping_message = f"⏳ 429 Rate Limited for {url[:50]}... Waiting longer before retry..."
                time.sleep(RETRY_DELAY * 2) # Wait longer before retrying
            elif response.status_code == 404:
                 logger.warning(f"404 Not Found for {url}.")
                 st.session_state.scraping_message = f"❓ 404 Not Found for {url[:50]}."
                 return response # Return 404, might be useful for end condition
            elif response.status_code >= 400:
                logger.error(f"HTTP Error {response.status_code} for {url}")
                st.session_state.scraping_message = f"❌ HTTP {response.status_code} Error for {url[:50]}..."
            else:
                response.raise_for_status()
                return response
        except requests.exceptions.Timeout:
            logger.error(f"Request timed out (attempt {attempt + 1}): {url}")
            st.session_state.scraping_message = f"⏰ Timeout for {url[:50]}... Retrying ({attempt + 1}/{MAX_RETRIES + 1})"
        except requests.exceptions.ConnectionError as e:
             logger.error(f"Connection error (attempt {attempt + 1}): {e}")
             st.session_state.scraping_message = f"🔌 Connection Error for {url[:50]}... Retrying ({attempt + 1}/{MAX_RETRIES + 1})"
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed (attempt {attempt + 1}): {e}")
            st.session_state.scraping_message = f"⚠️ Request Error for {url[:50]}... Retrying ({attempt + 1}/{MAX_RETRIES + 1})"
        except Exception as e:
            logger.error(f"Unexpected error during request (attempt {attempt + 1}): {e}", exc_info=True)
            st.session_state.scraping_message = f"💥 Unexpected Error for {url[:50]}... Retrying ({attempt + 1}/{MAX_RETRIES + 1})"

        if attempt < MAX_RETRIES:
            logger.info(f"Retrying in {RETRY_DELAY} seconds...")
            time.sleep(RETRY_DELAY)
        else:
            logger.error(f"Failed to fetch {url} after {MAX_RETRIES + 1} attempts.")
            st.session_state.scraping_message = f"❌ Failed to fetch {url[:50]}... after retries."
            return None # Return None on final failure
    return None


def get_final_whatsapp_url(session, join_url):
    """Fetches the join page and extracts the final WhatsApp URL."""
    logger.info(f"Fetching join page: {join_url}")
    st.session_state.current_task = f"Resolving: ...{join_url[-40:]}"
    # st.rerun() # Removed for efficiency, update status less frequently

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
        # --- 2. Look in JavaScript ---
        scripts = soup.find_all('script')
        for script in scripts:
            if script.string:
                # window.location.href = 'THE_URL';
                loc_match = re.search(r"window\.location\.href\s*=\s*['\"](https?://chat\.whatsapp\.com/[^'\"]*)['\"]", script.string, re.IGNORECASE)
                if loc_match:
                    final_url = loc_match.group(1)
                    logger.info(f"Found final URL in JS (window.location): {final_url}")
                    return final_url
                # window.open('THE_URL');
                open_match = re.search(r"window\.open\(['\"](https?://chat\.whatsapp\.com/[^'\"]*)['\"]", script.string, re.IGNORECASE)
                if open_match:
                    final_url = open_match.group(1)
                    logger.info(f"Found final URL in JS (window.open): {final_url}")
                    return final_url
        logger.warning(f"Final URL not found on join page {join_url}")
        return None
    except Exception as e:
        logger.error(f"Error parsing join page {join_url}: {e}", exc_info=True)
        return None

def scrape_search_ajax_step(session, keyword, page_counter):
    """Performs one step of scraping search results via AJAX."""
    logger.info(f"Fetching search AJAX page {page_counter} for keyword '{keyword}'")
    st.session_state.current_task = f"Scraping Search Page {page_counter}..."
    # st.rerun() # Removed for efficiency

    # Correct AJAX endpoint
    ajax_url = urljoin(BASE_URL, f"{AJAX_ENDPOINT_SEARCH}{quote_plus(keyword)}")
    ajax_data = {'group_no': page_counter}

    # Important: Set Referer header to the search results page
    search_results_url = f"{BASE_URL}{SEARCH_ENDPOINT}?keyword={quote_plus(keyword)}"
    headers = {
        'Referer': search_results_url,
        'Sec-Fetch-Dest': 'empty', # AJAX request
        'Sec-Fetch-Mode': 'cors',  # Cross-Origin request
        'Sec-Fetch-Site': 'same-origin',
        'X-Requested-With': 'XMLHttpRequest', # Common for AJAX
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8' # Standard for form data
    }

    # Make the POST request to the AJAX endpoint
    ajax_response = safe_request(session, 'POST', ajax_url, data=ajax_data, headers=headers)

    if not ajax_response:
        st.session_state.scraping_message = f"❌ Search AJAX request failed for page {page_counter}. Stopping."
        # st.rerun() # Removed
        return [], page_counter, True # Assume error means stop

    ajax_html = ajax_response.text.strip()

    # Check for end condition
    if not ajax_html or ajax_html == "" or "<div id=\"no\" style=\"display: none;color: #555\">No More groups</div>" in ajax_html or "No More groups" in ajax_html:
        st.session_state.scraping_message = f"✅ Reached end of search results at page {page_counter}."
        # st.rerun() # Removed
        return [], page_counter + 1, True # Finished

    soup = BeautifulSoup(ajax_html, 'html.parser')
    join_links_on_page = []
    # Pattern: <a href="/group/join/C9VkRBCEGJLG1Dl3OkVlKT">
    join_link_tags = soup.find_all('a', href=re.compile(r'^/group/join/[A-Za-z0-9]+$'))
    for tag in join_link_tags:
        href = tag.get('href')
        if href:
            full_url = urljoin(BASE_URL, href)
            join_links_on_page.append(full_url)

    if not join_links_on_page:
        logger.warning(f"No links found on search page {page_counter}. Assuming end or empty page.")
        st.session_state.scraping_message = f"⚠️ No links found on search page {page_counter}. Assuming end."
        # st.rerun() # Removed
        return [], page_counter + 1, True # Treat empty page as end

    st.session_state.scraping_message = f"📄 Search Page {page_counter}: Found {len(join_links_on_page)} links."
    # st.rerun() # Removed
    return join_links_on_page, page_counter + 1, False # Continue


# --- Streamlit App ---
def main():
    st.set_page_config(page_title="GroupSor Scraper", page_icon="🔍")
    st.title("🔍 GroupSor.link WhatsApp Group Scraper")
    st.markdown("Scrape final WhatsApp group links using keywords.")
    st.warning("⚠️ **Note:** Scraping might be unreliable due to anti-bot measures on the target site or limitations of Streamlit Cloud.")

    # --- Configuration ---
    st.sidebar.header("Configuration")
    keyword = st.sidebar.text_input("Search Keyword", value="girls")

    # --- Control Buttons ---
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("▶️ Start Scraping"):
            if st.session_state.scraping_state in ['idle', 'stopped']:
                if not keyword.strip():
                    st.sidebar.error("Please enter a search keyword.")
                    return
                st.session_state.scraped_data = []
                st.session_state.scraping_state = 'running'
                st.session_state.scraping_message = "Initializing scraper..."
                st.session_state.current_task = "Setting up..."
                st.session_state.scraping_progress = 0.0
                if not st.session_state.session_object:
                    st.session_state.session_object = create_session()
                    # Perform initial context request to get cookies/session
                    try:
                        initial_url = f"{BASE_URL}/" # Or maybe the search URL directly?
                        logger.info(f"Making initial context request to {initial_url}")
                        safe_request(st.session_state.session_object, 'GET', initial_url)
                    except Exception as e:
                        logger.warning(f"Initial context request failed: {e}")

                # Initialize scraping loop state
                st.session_state.gs_page_counter = 0
                st.session_state.links_to_resolve = []
                st.session_state.links_resolved = 0
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
                st.rerun()

    # --- Progress and Status ---
    st.progress(st.session_state.scraping_progress)
    st.info(f"**Status:** {st.session_state.scraping_message}")
    st.caption(f"*Task:* {st.session_state.current_task}")

    # --- Scraping Logic ---
    if st.session_state.scraping_state == 'running':
        session = st.session_state.session_object
        try:
            # --- Phase 1: Collect Links ---
            if 'links_collected' not in st.session_state or not st.session_state.links_collected:
                # Ensure the initial search page is loaded to get necessary cookies/context
                # This might have been done in the start button, but let's be sure
                # search_url = f"{BASE_URL}{SEARCH_ENDPOINT}?keyword={quote_plus(keyword)}"
                # try:
                #     safe_request(session, 'GET', search_url)
                # except:
                #     pass # Ignore errors in context request

                new_links, next_page, finished = scrape_search_ajax_step(
                    session, keyword, st.session_state.gs_page_counter
                )
                st.session_state.links_to_resolve.extend(new_links)
                st.session_state.gs_page_counter = next_page
                if finished:
                    st.session_state.scraping_message = f"✅ Link collection finished. Found {len(st.session_state.links_to_resolve)} links. Starting resolution..."
                    st.session_state.links_collected = True
                    st.session_state.links_resolved = 0
                    st.rerun() # Rerun to move to next phase
                else:
                    st.rerun() # Rerun to fetch next page

            # --- Phase 2: Resolve Links ---
            elif st.session_state.links_collected:
                 total_links = len(st.session_state.links_to_resolve)
                 if total_links == 0:
                     st.session_state.scraping_message = "ℹ️ No links to resolve."
                     st.session_state.scraping_state = 'idle'
                     # Cleanup
                     keys_to_delete = ['gs_page_counter', 'links_to_resolve', 'links_resolved', 'links_collected']
                     for key in keys_to_delete:
                         if key in st.session_state:
                             del st.session_state[key]
                     st.rerun()
                     return
                 if st.session_state.links_resolved < total_links:
                    current_index = st.session_state.links_resolved
                    link_to_resolve = st.session_state.links_to_resolve[current_index]
                    st.session_state.scraping_progress = (current_index + 1) / total_links
                    final_url = get_final_whatsapp_url(session, link_to_resolve)
                    if final_url and final_url.startswith("http"):
                        st.session_state.scraped_data.append({'Source': link_to_resolve, 'Link': final_url})
                        logger.info(f"Resolved successfully: {final_url}")
                    else:
                        logger.info(f"Failed to resolve or invalid URL: {link_to_resolve}")
                    st.session_state.links_resolved = current_index + 1
                    st.session_state.scraping_message = f"🔗 Resolved {current_index + 1}/{total_links} links."
                    st.rerun() # Rerun to process next link
                 else:
                     successful_count = len([d for d in st.session_state.scraped_data if d['Link'].startswith('http')])
                     st.session_state.scraping_message = f"🎉 Finished! Processed {total_links} links. Found {successful_count} WhatsApp links."
                     st.session_state.current_task = "Complete."
                     st.session_state.scraping_state = 'idle'
                     st.session_state.scraping_progress = 1.0
                     # Cleanup temp state
                     keys_to_delete = ['gs_page_counter', 'links_to_resolve', 'links_resolved', 'links_collected', '_last_visited_url'] # Clean up session var
                     for key in keys_to_delete:
                         if key in st.session_state and hasattr(st.session_state.session_object, key):
                              delattr(st.session_state.session_object, key)
                         if key in st.session_state:
                             del st.session_state[key]
                     st.rerun()
        except Exception as e:
            logger.error(f"An error occurred during scraping: {e}", exc_info=True)
            st.session_state.scraping_message = f"💥 Error: {str(e)[:100]}..."
            st.session_state.scraping_state = 'stopped'
            st.session_state.current_task = "Error."
            keys_to_delete = ['gs_page_counter', 'links_to_resolve', 'links_resolved', 'links_collected', '_last_visited_url']
            for key in keys_to_delete:
                if key in st.session_state and hasattr(st.session_state.session_object, key):
                     delattr(st.session_state.session_object, key)
                if key in st.session_state:
                    del st.session_state[key]
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
        success_data = [d for d in st.session_state.scraped_data if d['Link'].startswith('http')]
        if success_data:
            df = pd.DataFrame(success_data)
            st.dataframe(df, use_container_width=True)
            csv_buffer = io.StringIO()
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
            st.info("No successful links were resolved to display.")
    else:
        if st.session_state.scraping_state == 'idle' and not st.session_state.scraping_message.startswith("Ready"):
            st.info("Scraping completed or stopped.")
        elif st.session_state.scraping_state == 'idle':
            st.info("Enter a keyword and click 'Start Scraping'.")

if __name__ == "__main__":
    main()
