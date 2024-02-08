import streamlit as st
st.title("Personal Chatbot")
chat_history=[]
input=st.chat_input(placeholder="Type somethings")
for i in chat_history:
    st.write(i)
if input!='exit':
    chat_history.append(input)
elif input=='exit':

    st.button("Go to Homepage!!!",key='clickevent()')
    st.markdown("""
                <script>
                function clickevent(){
                window.parent.location.href="https://babylovechatbot.streamlit.app/embed=true"
                }
                </script>
                """,unsafe_allow_html=True)