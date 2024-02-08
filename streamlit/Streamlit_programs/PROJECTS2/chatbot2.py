import streamlit as st
st.title("Personal Chatbot")
chat_history=[]
input=st.chat_input(placeholder="Type somethings")
for i in chat_history:
    st.write(i)
if input!='exit':
    chat_history.append(input)
elif input=='exit':
    st.markdown("""
                <html>
                <head>
                <script type="text/javascript">
                function exitIframe() {
                    // Close or navigate back
                    window.parent.location.href = "https://babylovechatbot.streamlit.app/embed=true"
                }
                </script>
                </head>
                <body>
                <button onclick="exitIframe()">Exit Iframe</button>
                </body>
                </html>
                
                """,unsafe_allow_html=True)