import json
import streamlit as st
import streamlit.components.v1 as com
from streamlit_lottie import st_lottie
#com.iframe("https://lottiefiles.com/animations/add-to-cart-success-DU3FQVUhuk")
#reading json file using file handling method
with open("Animation - 1703333228161.json") as file:
    content=json.load(file)
st_lottie(content,height=300,width=200,speed=2,reverse=True)
#speed-it used to set animation playing time
#reverse-it is used to play animation in reverse
#using height and width attribute we can set anmation height and width