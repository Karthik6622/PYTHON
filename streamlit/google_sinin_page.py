# app.py
import streamlit as st
# google_signin.py
from google.auth.transport.requests import Request
from google.oauth2 import id_token

def google_signin(client_id, token):
    try:
        id_info = id_token.verify_oauth2_token(token, Request(), client_id)
        return id_info
    except ValueError as e:
        return str(e)


def main():
    st.title("Google Sign-In with Streamlit")

    client_id = "31851596009-19c8881uceflnp4h9ar1anrpf7jjh6nf.apps.googleusercontent.com"  # Replace with your Google API client ID
    token = st.text_input("Enter Google ID Token:")
    
    if st.button("Sign in with Google"):
        result = google_signin(client_id, token)
        st.write("Google Sign-In Result:", result)

if __name__ == "__main__":
    main()