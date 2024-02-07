import streamlit as st
st.title("Personal Chatbot")
chat_history=[]
input=st.chat_input(placeholder="Type somethings")

if input:
    chat_history.append(input)
    st.write(chat_history)