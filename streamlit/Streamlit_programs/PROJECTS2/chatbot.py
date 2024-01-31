import streamlit as st
import json
import pandas as pd
import numpy as np
import string
from tensorflow import keras
import sqlite3
from kkk import chat_history1
from streamlit_option_menu import option_menu
import streamlit.components.v1 as com
st.set_page_config(layout="wide")
with st.sidebar:
    select=option_menu(
    menu_title="",
    options=['Chatbot',"MostAskedInputs",'ProjectOverview','settings'],
    orientation="vertical",

    )
    
if select=='Chatbot':
    @st.cache_data
    def model1():
        with open("intents.json") as file:
            data=json.load(file)
        tag=[]
        input=[]
        response={}
        for indents in data['intents']:
            response[indents['tag']]=indents['responses']
            for line in indents['patterns']:
                input.append(line)
                tag.append(indents['tag'])
        #st.write(tag)
        #st.write(input)
        #st.write(response)
        #creating the dataframe
        dd=pd.DataFrame({'inputs':input,'tags':tag})
        #st.write(dd)

        #removing the puncucation from the input columns
        dd['inputs']=dd['inputs'].apply(lambda x:[wrd.lower() for wrd in x if wrd not in string.punctuation])
        dd['inputs']=dd['inputs'].apply(lambda x:''.join(x))
        #st.write(dd['inputs'])

        #applying tokenzier and padding for input column
        token=keras.preprocessing.text.Tokenizer(num_words=1000)
        token.fit_on_texts(dd['inputs'])
        se=token.texts_to_sequences(dd['inputs'])
        #st.write(se)
        #padding
        from keras.preprocessing.sequence import pad_sequences
        x_train=pad_sequences(se)
        #st.write(x_train)

        #changing the dd dataframe tag column to number using LabelEncoder
        from sklearn.preprocessing import LabelEncoder
        le=LabelEncoder()
        y_train=le.fit_transform(dd['tags'])
        #st.write(y_train)

        #finding the length og input shape,output_shape,vocabulary
        input_shpe=x_train[0].shape
        print(input_shpe)
        output_shape=np.unique(y_train)
        len_out=len(output_shape)
        #vocabulary
        word_index=token.word_index
        voc=len(word_index)

        #setup the Neural network 
        model=keras.Sequential([
            keras.layers.Embedding(voc+1,10,input_shape=input_shpe),
            keras.layers.LSTM(10,return_sequences=True),
            keras.layers.Flatten(),
            keras.layers.Dense(len_out,activation='softmax')
        ])
        model.compile(optimizer="adam",loss="sparse_categorical_crossentropy",metrics=['accuracy'])
        model.fit(x_train,y_train,epochs=500)
        return input_shpe,token,le,response,model
    #creating the chatbot
    input_shpe,token,le,response,model=model1()
    inp=input_shpe[0]
    #print(inp)
    import random
    if 'title1' not in st.session_state:
        st.session_state.title1="Love Help Chatbot"
        st.title(st.session_state.title1)
    def kk2():
        st.title("Love Help Chatbot")
        prediction_input=st.session_state.text_key
        text_p=[]
        #removing puncucation from the prediction_input
        prediction_input=[letter.lower() for letter in prediction_input if letter not in string.punctuation]
        prediction_input="".join(prediction_input)
        text_p.append(prediction_input)
        #st.write(text_p)
        
        #applying the tokenizer and padding for prediction input
        sse=token.texts_to_sequences(text_p)
        sse=np.array(sse).reshape(-1)
        from keras.preprocessing.sequence import pad_sequences
        pad=pad_sequences([sse],inp)
        #print(pad)

        #finding the output from model
        output=model.predict(pad)
        output1=output.argmax()
        #print(output)

        #if model final output morethan 7 it will display the prediction model result lessthan 7 means we will print below message
        print(output[0][output1])
        if output[0][output1]>=0.6:
            response_tag=le.inverse_transform([output1])[0]
            pp=random.choice(response[response_tag])
            #print(response_tag)
        else:
            pp="Sorry!!! I Could not understand...Please Ask related to love Topic!!!!"

        #print(response_tag)
        
        chat_history1.append({'YOU':text_p,'BABY':pp})
        #chat_history1.append({})
        for i in range(len(chat_history1)):
            c1,c2=st.columns([6,10])
            with c1:
                st.markdown(f"<h3 style='color:blue;'><strong><u>YOU</u></strong>👩‍💻: {chat_history1[i]['YOU'][0]}</h3>",unsafe_allow_html=True)
                st.markdown("<br>",unsafe_allow_html=True)
            with c2:
                st.markdown("<br>",unsafe_allow_html=True)
                st.markdown(f"<h3 style='color:green;'><strong><u>BABY</u></strong>❤️: {chat_history1[i]['BABY']}",unsafe_allow_html=True)
            #st.markdown("<br><br><br>",unsafe_allow_html=True)
        st.session_state.text_key=""
        #storing the user giving data and model response data into sqllite database
        conn=sqlite3.connect("E:\streamlit\Streamlit_programs\PROJECTS2\lovechatbot.db")
        cursor=conn.cursor()
        cursor.execute("insert into userinputresponse values(?,?)",(prediction_input,pp))
        conn.commit()
        conn.close()
    #customizing the chatbot using inspect classes
    #
    st.markdown(
        """
        <style>
            
            
            .st-emotion-cache-0.e1f1d6gn0{
                border:2px solid white;
                padding-left:15px;
                width:100%;
                box-shadow: 5px 5px 10px #4b4e4b;
                background-color:#99FF99;
            }
            .stHeadingContainer{
            text-align:center;
            color:orange;
            margin-top:20px;
            background-color:#4b4e4b;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )
    prediction_input = st.text_input("",on_change=kk2,key='text_key',value="",placeholder="Type something to know about love...")
    st.markdown(
        f"""
        <script>
            document.getElementById("text_key").select();
        </script>
        """,
        unsafe_allow_html=True,
    )
elif select=="MostAskedInputs":
    op=option_menu(
        options=['ALL','MostAskedinputs','MostAskedresponse'],
        orientation='horizontal',
        menu_title=""
    )
    con=sqlite3.connect("E:\streamlit\Streamlit_programs\PROJECTS2\lovechatbot.db")
    cur=con.cursor()
    query="select UserInput,ModelResponse from userinputresponse"
    cur.execute(query)
    data=cur.fetchall()
    dd=pd.DataFrame(data)
    dd.rename(columns={0:'input',1:'Response'},inplace=True)
    if op=='ALL':
       st.table(dd)
    elif op=='MostAskedinputs':
        if dd.empty:
            st.write("DATABASE IS EMPTY!!!!")
        else:
            count=dd['input'].value_counts().reset_index()
            se=st.selectbox("SELECT THE CATEGORY",options=['TOP10','LEAST10','TOP20','LEAST20'])
            if se=='TOP10':
                st.dataframe(count.head(10),use_container_width=True)
            elif se=='LEAST10':
                st.dataframe(count.tail(10),use_container_width=True)
            elif se=='TOP20':
                st.dataframe(count.head(20),use_container_width=True)
            elif se=='LEAST20':
                st.dataframe(count.tail(20),use_container_width=True)
    elif op=='MostAskedresponse':
        if dd.empty:
            st.write("DATABASE IS EMPTY!!!!")
        else:
            count=dd['Response'].value_counts().reset_index()
            se=st.selectbox("SELECT THE CATEGORY",options=['TOP10','LEAST10','TOP20','LEAST20'])
            if se=='TOP10':
                st.dataframe(count.head(10),use_container_width=True)
            elif se=='LEAST10':
                st.dataframe(count.tail(10),use_container_width=True)
            elif se=='TOP20':
                st.dataframe(count.head(20),use_container_width=True)
            elif se=='LEAST20':
                st.dataframe(count.tail(20),use_container_width=True)

elif select=='ProjectOverview':
    from streamlit_lottie import st_lottie
    with open("Animation - 1706722176313.json") as c:
       con=json.load(c)
    cc1,cc2,cc3,cc4,cc5,cc6=st.columns(6)
    with cc1:
       st_lottie(con,height=100,width=100,speed=2)
    with cc2:
       st_lottie(con,height=100,width=100,speed=2)
    with cc3:
       st_lottie(con,height=100,width=100,speed=2)
    with cc4:
       st_lottie(con,height=100,width=100,speed=2)
    with cc5:
       st_lottie(con,height=100,width=100,speed=2)
    with cc6:
       st_lottie(con,height=100,width=100,speed=2)
    st.markdown("""
               <style>
                .k{
                background-color:#99FF99;
                text-align:center;
                font-size:25px;
                font-weight:bold;
                border:2px solid white;
                box-shadow:2px 5px 20px #4b4e4b;
                }
                .k p{
                font-size:25px;
                font-weight:bold;
                }
                h4{
                color:green;
                }
                .k1{
                font-size:30px;
                font-color:orange;
                text-align:center;
                background-color:#ff9900;
                }
                .k2{
                font-size:25px;
                font-color:orange;
                text-align:center;
                background-color:#ffb84d;
                font-weight:bold;
                }
                h4{
                font-size:20px;
                font-weight:bold;
                background-color:#ffcc80;
                }
                h5{
                color:blue;
                font-weight:bold;
                }
                </style>
                """,unsafe_allow_html=True)
    st.markdown("<h1 class='k1'>CREATING LOVE CAHTBOT USING DEEPLEARNING</h1>",unsafe_allow_html=True)
    st.markdown("""<div class='k'>
         <p>Creating a love chatbot using deep learning involves leveraging natural language processing (NLP) and machine learning techniques to enable the chatbot to understand and generate human-like responses in the context of love and relationships</p>       
    </div>
    """,unsafe_allow_html=True)
    st.markdown("<h2 class='k2'>Here's a comprehensive project overview:</h2>",unsafe_allow_html=True)
    st.markdown("""<div class='k'>
        <h4>1. Project Definition:</h4>
         <p><h5>Purpose:</h5>
        Design a chatbot focused on love and relationships to provide users with a supportive and engaging conversational experience.
        <br><br>
        <h5>Scope:</h5>
        The chatbot will handle conversations related to love, dating, relationship advice, and general emotional support.</p>       
    </div>
    """,unsafe_allow_html=True)
    st.markdown("""<div class='k'>
        <h4>2. Data Collection:</h4>
         <p><h5>Source:</h5>
    Gather a diverse dataset containing conversations related to love, relationships, and associated topics. This can include dialogue datasets, online forums, or custom datasets collected through surveys.
    <br><br>
    <h5>annotation:</h5>
    Annotate the dataset, marking dialogues or sentences that express emotions, inquiries, or statements related to love.</p>       
    </div>
    """,unsafe_allow_html=True)
    st.markdown("""<div class='k'>
        <h4>3. Data Preprocessing:</h4>
         <p><h5>Cleaning:</h5>
    Remove irrelevant information, correct spelling errors, and handle any inconsistencies in the dataset.
    <br><br>
    <h5>Tokenization:</h5>
    Tokenize the text into words or sub-word tokens for input to the model.
    <br><br>
    <h5>Formatting:</h5>
    Prepare the data in a format suitable for training the deep learning model.</p>       
    </div>
    """,unsafe_allow_html=True)
    st.markdown("""<div class='k'>
        <h4>4. Selecting Deep Learning Framework:</h4>
         <p><h5>Framework:</h5>
     Choose a deep learning framework such as TensorFlow,Keras for implementing the model.</p>       
    </div>
    """,unsafe_allow_html=True)
    st.markdown("""<div class='k'>
        <h4>5. Model Architecture:</h4>
         <p><h5>Architecture Choice:</h5>
    Design a suitable architecture for the love chatbot. Options include:
    Recurrent Neural Networks (RNNs): For sequential data.
    Long Short-Term Memory Networks (LSTMs): Effective for capturing long-range dependencies.
    Transformer Models: Powerful for natural language understanding and generation.
    <br><br>
    <h5>Embeddings:</h5>
    Use pre-trained word embeddings or contextual embeddings for better understanding of context.</p>       
    </div>
    """,unsafe_allow_html=True)
    st.markdown("""<div class='k'>
        <h4>6. Training the Model:</h4>
         <p><h5>Input-Output Mapping:</h5>
    Train the model to map input dialogue sequences to appropriate love-related responses.
    <br><br>
    <h5>Hyperparameter Tuning:</h5>
    Optimize hyperparameters for better model performance.</p>       
    </div>
    """,unsafe_allow_html=True)
    st.markdown("""<div class='k'>
        <h4>7. Integration with Chatbot Framework:</h4>
         <p><h5>Chatbot Framework:</h5>
    Integrate the trained model into a chatbot framework (e.g., using libraries like streamlit).
    <br><br>
    <h5>User Input Handling:</h5>
    Implement logic to process user inputs and extract relevant information.
    <br><br>
    <h5>Response Generation:</h5>
    Utilize the deep learning model to generate appropriate responses based on user inputs.</p>       
    </div>
    """,unsafe_allow_html=True)
    st.markdown("""<div class='k'>
        <h4>8. User Interface (UI) Design:</h4>
         <p><h5>Interface:</h5>
    design a user-friendly interface for the love chatbot, specifying how users will interact and receive responses.</p>       
    </div>
    """,unsafe_allow_html=True)
    st.markdown("""<div class='k'>
        <h4>9. Testing and Evaluation:</h4>
         <p><h5>Testing:</h5>
       Thoroughly test the chatbot to ensure it understands and responds appropriately to various inputs.
       <br><br> 
       <h5>Metrics:</h5>
      Evaluate the chatbot's performance using metrics such as accuracy, fluency and user satisfaction.</p>       
    </div>
    """,unsafe_allow_html=True)
    st.markdown("""<div class='k'>
        <h4>10. Deployment:</h4>
         <p><h5>Platform:</h5>
        Deploy the love chatbot to a chosen platform or integrate it with messaging applications.
        <br><br>
        <h5>User Accessibility:</h5>
        Ensure the chatbot is easily accessible to users.</p>       
    </div>
    """,unsafe_allow_html=True)
    st.markdown("""<div class='k'>
        <h4>11. Monitoring and Maintenance:</h4>
         <p><h5>Monitoring:</h5>
        Regularly monitor the chatbot's performance, addressing any issues promptly.
        <br><br>
        <h5>User Feedback:</h5>
        Collect user feedback to improve the chatbot's responses and overall experience.
        <br><br>
        <h5>Model Updates:</h5>
        Update the model periodically based on feedback and evolving conversational patterns.</p>       
    </div>
    """,unsafe_allow_html=True)
elif select=='settings':
    tab1,tab2,tab3=st.tabs(['Developer/ContactUs','Datasource/codes','Deletedatafromdatabase'])
    with tab1:
        c1,c2=st.columns(2)
        with c1:
            from streamlit_lottie import st_lottie
            with open("Animation - 1706721681647.json") as c:
                con=json.load(c)
            st_lottie(con,height=500,width=500,speed=2)
            
        with c2:
            st.write("## CreatedBY")
            st.markdown("### KARTHIK R")
            gmail_address="karthikmca6622@gmail.com"
            gmail_link=f"mailto:{gmail_address}"
            st.markdown("[karthikmca6622@gmail.com]({gmail_link})")
            phone_number="9944194787"
            phone_link=f"tel:{phone_number}"
            st.markdown("[9944194787]({phone_link})")
    with tab2:
        co1,co2=st.columns([1,2])
        with co1:
           st.markdown("## JSON DATA FILE")
           #st.markdown("---")
        with open("intents.json") as fi:
            da=json.load(fi)
        #This code converts the dictionary (da) into a JSON-formatted string using json.dumps. 
        json_data=json.dumps(da,indent=2)# the indent parameter is an optional argument that specifies the number of spaces to use for indentation when pretty-printing the JSON string
        
        with co2:
           st.markdown("<br>",unsafe_allow_html=True)
           st.download_button("DOWNLOAD JSON DATA",data=json_data,file_name="lovedata.json")
        st.markdown("---")
        co11,co22=st.columns([1,2])
        with co11:
            st.markdown("## Source code")
            #st.markdown("---")
        with co22:
            st.markdown("[https://github.com/](https://github.com/)")
        st.markdown("<hr>",unsafe_allow_html=True)
        co111,co222=st.columns([1,2])
        with co111:
            st.markdown("## Databasefile")
            #st.markdown("---")
        with co222:
            st.markdown("[https://github.com/](https://github.com/)")
            #st.markdown("---")
    with tab3:
        inp_pass=st.text_input("Enter the passcode")
        submit=st.button("RESET/CLEAR THE DATABASE")
        if submit:
            if inp_pass=='6860':
                st.write("kkkk")
                conn1 = sqlite3.connect("E:\\streamlit\\Streamlit_programs\\PROJECTS2\\lovechatbot.db")
                cursor = conn1.cursor()
                query = "DELETE FROM userinputresponse"
                cursor.execute(query)
                conn1.commit()
                st.write("Delete successful")
                conn1.close()

            else:
                st.write("Please enter correct passcode!!!!")
else:
    st.write("kkkk")