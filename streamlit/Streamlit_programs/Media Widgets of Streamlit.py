import streamlit as st
#how to remove handburger symbol in the web page using class
#we can get that element class using inect website
st.markdown("""
<style>
.st-emotion-cache-6q9sum.ef3psqc4  
{
    visibility: hidden;
}
</style>
""",unsafe_allow_html=True)
#displaying image 
st.image('2.jpg',caption="Image",use_column_width=True)#we can use width also like width=500
#displaying the audio file
st.audio('E:\Html_Practice_files\Hukum---Thalaivar-Alappara-MassTamilan.dev.mp3')
#displaying the video
st.video('E:\Html_Practice_files\google_issues_video.mp4')
