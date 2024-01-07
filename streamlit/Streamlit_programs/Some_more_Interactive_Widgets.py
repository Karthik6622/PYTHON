import streamlit as st
st.title("Slider")
st.markdown("---")
#creating the slider
st.slider("this is a slider")
#creating the slider with minimum and maximum value and display the slider selected value
value=st.slider("MY SLIDER",min_value=100,max_value=200)
st.write(value)
#create a select slider
select=st.select_slider("Select slider",options=["A","B","C","E","F"])
st.write(select)

#text_input-to get single line input from user
inp=st.text_input("Enter your Course title:")
st.write(inp)
#we can maximum character for text_input.if we enter more than maximum character it won't allow to enter
inp1=st.text_input("Enter your Course title:",max_chars=20)
st.write(inp1)
#text_area-to get multiple line input from user
te=st.text_area("Enter your text",max_chars=100)
st.write(te)

#date_input-it's useful to get date input from user
date=st.date_input("Select your Date")
st.write(date)

#time_input-it allow as fetch time from the user
time=st.time_input("Enter your Time")
st.write(time)
