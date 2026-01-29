import streamlit as st
import pandas as pd
#creating multiple fileuploader to get files from user
#getting uploaded file names
file_names=[]
files=st.file_uploader("Select the Files",accept_multiple_files=True)
if files:
    for file in files:
        file_names.append(file.name)
st.write(file_names)

#displaying the uploaded files as a radio button and and display selected file as a table
with st.sidebar:
    selected=st.radio("Select the Uploaded file",options=file_names)
    if selected !=None:
        for file in files:
            for file.name in selected:
               dd=pd.read_excel(file)
               #pip install xlrd>=2.0.1-we have to install xlrd morethan 2.0.1 to display uploaded excel file
st.write(dd)

