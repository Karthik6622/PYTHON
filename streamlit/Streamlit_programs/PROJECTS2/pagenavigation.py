import streamlit as st

def home_page():
    st.title("Home Page")
    st.write("This is the home page.")
    
def next_page():
    st.title("Next Page")
    st.write("You've navigated to the next page.")

# Streamlit app
st.title("Page Navigation Example")

# User input for command
command = st.text_input("Type 'open next page' to navigate:", "")

# Conditionally generate link for the next page based on user input
if command.lower() == "open next page":
    next_page_url = st.url_builder(page="next")
    st.write(f"[Open Next Page]({next_page_url})")

# Page selection based on URL query parameters
page = st.experimental_get_query_params().get("page", "home")

# Display pages based on the URL query parameter
if page == "home":
    home_page()
elif page == "next":
    next_page()
