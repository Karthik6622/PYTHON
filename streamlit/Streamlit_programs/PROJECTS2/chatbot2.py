import streamlit as st
st.title("Personal Chatbot")
chat_history=[]
input=st.chat_input(placeholder="Type somethings")
for i in chat_history:
    st.write(i)
if input!='exit':
    chat_history.append(input)
elif input=='exit':
    st.markdown('<a href="https://babylovechatbot.streamlit.app/?embed=true" target="_self">Google</a>', unsafe_allow_html=True)
    
    