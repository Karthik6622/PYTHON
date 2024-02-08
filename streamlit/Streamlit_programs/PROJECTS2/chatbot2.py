import streamlit as st
import json
import pandas as pd
#setting the streamlit page layout as wide
st.set_page_config(layout="wide")
@st.cache_data
def algorithm():
    with open("E:/PYTHON/streamlit/Streamlit_programs/PROJECTS2/personalintents.json") as f:
         data=json.load(f)
    tag=[]
    input[]
    response={}
    for indents in data['intents2']:
        response[indents['tag']]=indents['resonses']
        for line in indents:
            tag.append(line['tag'])
            input.append(line['patterens'])
    data2=pd.DataFrame({'input':input,'tag':tag})
    st.dataframe(data2)
st.title("Personal Chatbot")
chat_history=[]
input=st.chat_input(placeholder="Type somethings")
for i in chat_history:
    st.write(i)
if input!='exit':
    chat_history.append(input)
elif input=='exit':
    st.markdown('<a href="https://babylovechatbot.streamlit.app/?embed=true" target="_self">exit</a>', unsafe_allow_html=True)
    
    