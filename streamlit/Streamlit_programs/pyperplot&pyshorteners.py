import streamlit as st
import pyshorteners as p
import pyperclip
#  The pyperclip library is a Python module that provides a cross-platform clipboard interface. It allows you to interact with the clipboard in a simple and consistent way, regardless of the operating system (Windows, macOS, Linux).
proxy_config = {
    'http': 'http://proxy:8080',
    'https': 'https://proxy:8080',
}
shortner=p.Shortener(proxies=proxy_config)
#creating the url shortner
#A URL shortener is a service or tool that takes a long URL and generates a shorter version, typically consisting of a few characters or a short alphanumeric string. The primary purpose of a URL shortener is to create a more compact and user-friendly link
def copy_to_clipboard():
    pyperclip.copy(shorted_url)
fo=st.form("form1")
url=fo.text_input("Enter the URL")
bu=fo.form_submit_button("Submit")
if bu:
    shorted_url=shortner.tinyurl.short(url)
    st.write(shorted_url)
    st.button("Copy",on_click=copy_to_clipboard)
#above program we shortening the url and copy to clipboard
    
#create program for copying string to cliboard and paste to st.write
def copy():
    pyperclip.copy(text)#we can check whther text copied to clipboard or not using notpad ctrl+v
    st.success("text copied to clipboard successfully")
with st.form("form2",clear_on_submit=True):#clear_on_submit=True-after click submit button existing value be clear
    text=st.text_input("Enter the Text:")
    s=st.form_submit_button("Submit")
if s:
    ss=st.button("Copy to Clipboard",on_click=copy)

#now we displaying whatever present in clipboard
st.write(pyperclip.paste())

    