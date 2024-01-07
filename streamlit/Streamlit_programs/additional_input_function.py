import streamlit as st
import pandas as pd
#number_input-is used to get only number value from user
ss=st.number_input("Enter the Number:")
st.write(ss)
#if we want to change the acceptable value float to int we can use below code
#The step parameter is set to 1, which means that only integer values are allowed.
#The value parameter is set to 0, providing a default value.
#The format parameter is set to "%d" to ensure that the displayed value is formatted as an integer.
s=st.number_input("Enter the Number:",step=1, value=0,format="%d")
st.write(s)

st.markdown("---")

#toggle-it is like a on or off swith or enable or disable
to=st.toggle("Enable",value=True)#defaultly it disable,if we want to enable we can give value=True
st.write(to)

st.markdown("---")

#color_picker-it is used to help user pick the color
color=st.color_picker("Select the color")
st.write(color)#it's display hexa colorcode of selected color
st.markdown("---")

#data_editor-is a streamlit command that allows the user to edit dataframes in a table
dd=pd.read_csv("E:\R-Programming\car-sales.csv")
st.data_editor(dd)

#download_button-The st.download_button function in Streamlit is used to create a download button that allows users to download a file.
data="Karthik"
st.download_button("download csv",data=data,file_name="karthik.csv")
#label: The label that appears on the button.
#data: The content you want to download. This could be a string, bytes, or a file-like object.
#file_name: The name you want to give to the downloaded file.