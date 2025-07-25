# app.py
import streamlit as st
import re
from urllib.parse import urljoin

# --- Configuration ---
JOIN_BASE_URL = "https://groupsor.link/group/join/"
WHATSAPP_INVITE_BASE_URL = "https://chat.whatsapp.com/invite/"

# --- Helper Functions ---

def extract_group_ids(text_content):
    """
    Extracts unique group IDs from Groupsor.link join URLs in the provided text.
    Looks for patterns like /group/join/ID where ID is alphanumeric/underscore/hyphen.
    """
    # Pattern to find /group/join/ followed by the ID
    # This regex looks for the literal path and captures the ID part
    pattern = re.escape(JOIN_BASE_URL) + r"([a-zA-Z0-9_-]+)"
    
    # Find all matches
    matches = re.findall(pattern, text_content)
    
    # Return unique IDs
    return list(set(matches))

def generate_whatsapp_links(group_ids):
    """
    Generates standard WhatsApp invite URLs from a list of group IDs.
    """
    links = []
    for gid in group_ids:
        full_link = urljoin(WHATSAPP_INVITE_BASE_URL, gid)
        links.append(full_link)
    return links

# --- Streamlit App ---

st.title("Groupsor.link ID Extractor & WhatsApp Link Generator")

st.write("""
This tool extracts group IDs from raw HTML content copied from `https://groupsor.link` 
(e.g., `Pasted_Text_1753408261077.txt`) and generates standard WhatsApp invite links.

**How to use:**
1.  Copy the HTML source of a Groupsor.link page (e.g., right-click -> "View Page Source").
2.  Paste the copied HTML content into the text area below.
3.  Click "Extract & Generate Links".
4.  View the extracted IDs and generated WhatsApp links.
5.  Download the results as a CSV file.
""")

# Text area for pasting HTML content
html_content = st.text_area("Paste HTML Content Here:", height=300)

# Button to trigger processing
if st.button("Extract & Generate Links"):
    if not html_content:
        st.warning("Please paste the HTML content first.")
    else:
        with st.spinner("Processing..."):
            try:
                # 1. Extract Group IDs
                group_ids = extract_group_ids(html_content)
                
                if not group_ids:
                    st.info("No group IDs found in the provided content. Please check the content.")
                else:
                    st.success(f"Found {len(group_ids)} unique group ID(s).")
                    
                    # 2. Generate WhatsApp Links
                    whatsapp_links = generate_whatsapp_links(group_ids)
                    
                    # 3. Display Results
                    st.subheader("Extracted IDs and Generated Links:")
                    
                    # Create a list of dictionaries for the dataframe
                    data = []
                    for gid, link in zip(group_ids, whatsapp_links):
                        data.append({"Group_ID": gid, "WhatsApp_Invite_Link": link})
                    
                    # Display in a table
                    st.dataframe(data)

                    # 4. Provide Download Link
                    import pandas as pd
                    df = pd.DataFrame(data)
                    csv = df.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="Download data as CSV",
                        data=csv,
                        file_name='extracted_whatsapp_groups.csv',
                        mime='text/csv',
                    )
                    
            except Exception as e:
                st.error(f"An error occurred during processing: {e}")

st.markdown("---")
st.caption("Note: This tool processes data locally in your browser. No data is sent to any server.")
