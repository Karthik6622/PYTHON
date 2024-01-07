import streamlit as st
#inp=st.text_input("Enter your Name:")
#button=st.button("Submit")
#if button:
    #ch=st.checkbox("Want to show your name?")
    #if ch:
        #st.write(inp)
#st.markdown("---")
#if we wnat to display like first enter our name then then after click button.display one checkbox for conformation.once clicked checkbox ,name should display
#but using above code we can't get that one cause if we click check whole page will refresh to avoid that we can use one of the call back function on_change
def printer(value):
    st.write(value)
inp1=st.text_input("Enter your Name:",key='k')
button1=st.button("Submit",key='kk')
if button1:
    ch1=st.checkbox("Want to show your name?",on_change=printer,args=(inp1,))

st.markdown("---")
