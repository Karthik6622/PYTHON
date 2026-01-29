import streamlit as st
#session_state-session state like a varible for every rerun it's store different value
#and if two differnt user is using our webapp,session state is different for user1 and user2
#here we can see session_state is incrementing for everytime button click
if 'count' not in st.session_state:#here we cheking whether alredy 'count' variable preset or not
    st.session_state.count=0
if st.button('Increment'):
    st.session_state.count+=1
st.write(st.session_state.count)
st.write(st.session_state)

#using session state we can change button lablel as we want
text='kkk'
if 'count2' not in st.session_state:
    st.session_state.count2=False
else:
    if st.session_state.count2==False:
        text='baby'
        st.session_state.count2=True
    else:
        text='kkk'
        st.session_state.count2=False
st.button(text)



