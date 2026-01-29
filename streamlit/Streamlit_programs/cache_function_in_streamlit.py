import streamlit as st
import time 
@st.cache_data
def print():
    time.sleep(3)
    return("HI Karthik!!!")
st.write(print())
#we can see the result.if run first time it's taking 3 second to display message but if we run second time same thing it's not taking time to display because cache function cached the previous run

