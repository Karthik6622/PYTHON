import streamlit as st
import json

# Your dictionary data
da = {'key': 'value', 'another_key': 'another_value'}

# Convert dictionary to JSON string with indentation (indent=2)
json_data = json.dumps(da, indent=2)

# Set the color using HTML and CSS
styled_button = f'<span style="color: white; background-color: green; padding: 8px 12px; border-radius: 5px; cursor: pointer;">DOWNLOAD JSON DATA</span>'

# Render the styled download button
st.markdown(styled_button, unsafe_allow_html=True)

# Use st.download_button with the JSON data
st.download_button("Hidden Download Button", data=json_data, file_name="lovedata.json", key="download_button")
