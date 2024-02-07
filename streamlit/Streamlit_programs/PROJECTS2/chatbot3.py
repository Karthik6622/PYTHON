import streamlit as st
def main1():
    while True:
        ii=st.chat_input("",key=f"kk")
        if ii:
           st.write(ii)
        