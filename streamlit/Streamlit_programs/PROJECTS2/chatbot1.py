import streamlit as st
import json
import pandas as pd
import numpy as np
import string
from tensorflow import keras
import sqlite3
#from kkk import chat_history1
from streamlit_option_menu import option_menu
import streamlit.components.v1 as com
from streamlit_lottie import st_lottie
from plotly.offline import plot
import plotly.graph_objs as go
#page_config={"page_title":"baby"}
#browser tab title and icon 
#this session state create prevent one user meassges another user can't see.it create each session for every user
if "chat_history1" not in st.session_state:
    st.session_state.chat_history1=[]
st.set_page_config(page_title="baby Love chatbot",page_icon=":cupid:",layout="wide")
st.markdown("""<style>
                .styles_terminalButton__JBj5T{
                   visibility: hidden;
               }
                </style>
                """,unsafe_allow_html=True)
with st.sidebar:
   d=st.selectbox("MODE(DARK&LIGHT)",options=['Dark','light'],key='p')
   st.markdown("""
               <style>
               .st-emotion-cache-q8sbsg.e1nzilvr5{
               margin-top:0px;
               }
               
               .st-emotion-cache-16idsys p{
                font-size:20px;
                font-weight:bold;
                color:red;
                
               }
               .styles_terminalButton__JBj5T {
                   visibility: hidden;
               }
               .st-emotion-cache-10trblm.e1nzilvr1{
               color:white
               }
                </style>
                """,unsafe_allow_html=True)
if d=='Dark':
    light = '''
    <style>
        .stApp {
        background-color: black;
        }
        .st-emotion-cache-6qob1r.eczjsme3{
        background-color:black;
        border:2px solid white;
        }
        .st-emotion-cache-18ni7ap.ezrtsby2{
        background-color:black;
        }
        button{
        color:red;
        }
        .stChatFloatingInputContainer.st-emotion-cache-90vs21.e1d2x3se2{
        background-color:black;
        }
        .st-emotion-cache-s1k4sy.e1d2x3se4{
        background-color:white;
        }
        .st-de{
        color:white;
        }
        .st-emotion-cache-10trblm.e1nzilvr1{
            color:white
        }
        st-emotion-cache-q8sbsg.e1nzilvr5{
        color:red;
        font-size:25px;
        }
        .st-emotion-cache-q8sbsg.e1nzilvr5 p{
        color:red;
        font-size:20px;
        font-weight:bold;
        }
    </style>
    '''
elif d=='light':
    light = '''
    <style>
        .stApp {
        background-color: white;
        color:red;
        }
        .st-emotion-cache-6qob1r.eczjsme3{
        background-color: white;
        border:2px solid black;
        }
        /*disaplying side default icons*/
        .st-emotion-cache-zq5wmm.ezrtsby0{
            visibility:hidden;
        }
        #MainMenu{
           visibility:hidden;
        }
        .st-emotion-cache-10trblm.e1nzilvr1 {
        color:green;
        }
        .st-ag { 
        
        border: 1px solid red;
        }
        .st-de{
        color:white;
        }
        .st-emotion-cache-q8sbsg.e1nzilvr5 p{
        color:red;
        font-size:20px;
        font-weight:bold;
        }
    </style>'''

st.markdown(light, unsafe_allow_html=True)

#givinng background color for table
st.markdown("""
            <style>
            .st-emotion-cache-165ax5l{
            background-color:black;
            border:2px solid white;
            }
            .st-emotion-cache-a51556 {
            color:orange;
            }
            tr td{
            background-color:black;
            border:2px solid white;
            color:white;
            }

            tr th{
            background-color:black;
            border:2px solid white;
            color:white;
            }
            p{
            color:red;
            font-size:15px;
            }
            .st-emotion-cache-16idsys.e1nzilvr5 p{
            color:red;
            font-size:20px;
            }
            .st-emotion-cache-zuelfj{
            background-color:black;
            border:2px solid white;
            }
            .st-emotion-cache-c34i5s {
            color:red;
            }
            </style>
            """,unsafe_allow_html=True)

with st.sidebar:
    select=option_menu(
    menu_title="",
    options=['Chatbot','ProjectOverview','settings',"EDA(Inputs-Responses&Reviews)"],
    icons=['robot','file-earmark-ppt-fill','gear-fill','people-fill'],
    orientation="vertical",

    )    
    
if select=='Chatbot':
    @st.cache_data
    def model1():
        with open("streamlit/Streamlit_programs/PROJECTS2/intents.json") as file:
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
    with st.sidebar:
        with open("streamlit/Streamlit_programs/PROJECTS2/Animation - 1706811014627.json") as s:
            ddd=json.load(s)
        st_lottie(ddd,height=250,width=250,speed=4)
    prediction_input = st.chat_input(key="text_key",placeholder="Type something to know about love...")
    #customizing pageclear button
    st.markdown("""
                    <style>
                    .st-emotion-cache-hc3laj.ef3psqc12{
                    color:red;
                    width:250px;
                    background-color:black;
                    margin-left:20px;
                    border-radius:12px 12px 12px 12px;
                    }
                    </style>
                    """,unsafe_allow_html=True)
    if prediction_input:
        
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
        accuracy=round(output[0][output1],2)
        if output[0][output1]>=0.8:
            response_tag=le.inverse_transform([output1])[0]
            pp=random.choice(response[response_tag])
            #print(response_tag)
        else:
            pp="Sorry!!! I Could not understand...Please Ask related to love Topic!!!!"

        #print(response_tag)
        
        st.session_state.chat_history1.append({'YOU':text_p,'BABY':pp})
        #chat_history1.append({})
        
        st.markdown(" <h3 style='border:5px solid white;text-align:center;font-weight:bold;background-color:black;'>Love Help Chatbot</h3>",unsafe_allow_html=True)

        with st.sidebar:
            clear=st.button("Pageclear")
        if clear:
            st.session_state.chat_history1.clear()
        else:
            for i in range(len(st.session_state.chat_history1)):
                c1,c2=st.columns([6,10])
                with c1:
                    st.markdown(f"<h3 style='color:blue;'><strong><u>YOU</u></strong>👩‍💻: {st.session_state.chat_history1[i]['YOU'][0]}</h3>",unsafe_allow_html=True)
                    #st.markdown("<br>",unsafe_allow_html=True)
                with c2:
                    st.markdown("<br>",unsafe_allow_html=True)
                    st.markdown(f"<h3 style='color:green;'><strong><u>BABY</u></strong>❤️: {st.session_state.chat_history1[i]['BABY']}",unsafe_allow_html=True)
    
        
            #st.markdown("<br><br><br>",unsafe_allow_html=True)
        #storing the user giving data and model response data into sqllite database
        conn=sqlite3.connect("streamlit/Streamlit_programs/PROJECTS2/lovechatbot.db")
        cursor=conn.cursor()
        cursor.execute("insert into userinputresponse values(?,?,?)",(prediction_input,pp,str(accuracy)))
        conn.commit()
        conn.close()
    else:
        st.markdown(" <h3 style='border:5px solid white;text-align:center;font-weight:bold;background-color:black;'>Love Help Chatbot</h3>",unsafe_allow_html=True)
        if not st.session_state.chat_history1:
           cx1,cx2,cx3=st.columns(3)
           with cx1:
               with open("streamlit/Streamlit_programs/PROJECTS2/Animation - 1706803520058.json") as s:
                  ddd=json.load(s)
               st_lottie(ddd,height=500,width=None,speed=1)
           with cx2:    
                import time as t
                ll="My name is Baby! How can I assist you with the topic of love?"
                ll1=ll.split(" ")
                for i in ll1:
                        st.markdown(f"<h6 style='text-align:center;color:red;font-weight:bold;'> {i}</h6>",unsafe_allow_html=True)
                        t.sleep(0.2)
           with cx3:
                with open("streamlit/Streamlit_programs/PROJECTS2/Animation - 1706803520058.json") as s:
                  ddd=json.load(s)
                st_lottie(ddd,height=500,width=None,speed=1)
           #st.markdown("## My name is Baby! How can I assist you with the topic of love?")
        with st.sidebar:
            clear=st.button("Pageclear")
        if clear:
            st.session_state.chat_history1.clear()
        else:     
            for i in range(len(st.session_state.chat_history1)):
                c1,c2=st.columns([6,10])
                with c1:
                    st.markdown(f"<h3 style='color:blue;'><strong><u>YOU</u></strong>👩‍💻: {st.session_state.chat_history1[i]['YOU'][0]}</h3>",unsafe_allow_html=True)
                    #st.markdown("<br>",unsafe_allow_html=True)
                with c2:
                    st.markdown("<br>",unsafe_allow_html=True)
                    st.markdown(f"<h3 style='color:green;'><strong><u>BABY</u></strong>❤️: {st.session_state.chat_history1[i]['BABY']}",unsafe_allow_html=True)
    #customizing the chatbot using inspect classes
    ##4b4e4b
    #.stChatFloatingInputContainer.st-emotion-cache-usj992.e1d2x3se2{
    st.markdown(
        """
        <style>
            .st-emotion-cache-zq5wmm.ezrtsby0{
            visibility:hidden;
            }
            
            
            .st-emotion-cache-0.e1f1d6gn0{
            
            }
            .main.st-emotion-cache-uf99v8.ea3mdgi88{
                border:2px solid orange;
                padding-left:0px;
                width:100%;
                box-shadow: 5px 5px 10px black;
                background-color:#99FF99;
            }
            
            .stHeadingContainer{
            font-size:20px;
            text-align:center;
            margin-bottom:0px;
            background-color:black;
            border:5px solid white;
            
            }
            .st-emotion-cache-s1k4sy.e1d2x3se4{
            border:5px solid white;
            background-color:None;
           
            }
            .stChatFloatingInputContainer.st-emotion-cache-usj992.e1d2x3se2{
            background-color:black;
            height:0%;
            margin-bottom:20px;
            }
            .st-emotion-cache-s1k4sy.e1d2x3se4{
            background-color:black;
            }
            .stChatInputContainer.st-emotion-cache-164vu5a.e1d2x3se5{
            background-color:black;
            height:10px;
            }
            
        </style>
        """,
        unsafe_allow_html=True,
    )
    
    st.markdown(
        f"""
        <script>
            document.getElementById("text_key").select();
        </script>
        """,
        unsafe_allow_html=True,
    )
elif select=="EDA(Inputs-Responses&Reviews)":
    #customizing all tables
    st.markdown("""
                <style>
                tr{
                background-color:black
                }
                </style>
                """,unsafe_allow_html=True
                )
    with st.sidebar:
        st.markdown("---")
        st.markdown("<h1 style='text-align:center;color:red';>Customer Review</h1>",unsafe_allow_html=True)
        customer_name1=st.empty()
        description1=st.empty()
        customer_name =customer_name1.text_input('',key="1",placeholder="Enter the Name")
        #disabling the send icon
        st.markdown("""
                    <style>
                    .st-emotion-cache-1if5ada.e1y5xkzn1{
                    visibility:hidden;
                    }
                    .st-emotion-cache-hc3lajef3psqc12{
                    color:red;
                    width:250px;
                    background-color:black;
                    margin-left:20px;
                    border-radius:12px 12px 12px 12px;
                    }
                    
                    .st-emotion-cache-zq5wmm.ezrtsby0{
                    visibility:hidden;
                    }
                    """,unsafe_allow_html=True)
        rate=st.slider("Rate from 1 to 5",0,5,3)
        st.write(f'<h6 style="color:green";>You Selected: {"⭐️"*int(rate)}</h6>',unsafe_allow_html=True)
        description=description1.text_area('',key="2",placeholder="Enter the message!!!")
        submit=st.button("submit")
        st.markdown("---")
        if submit:
           
           st.write("Thankyou for your review!!")
           c=sqlite3.connect("streamlit/Streamlit_programs/PROJECTS2/lovechatbot.db")
           cur=c.cursor()
           cur.execute("insert into review_table values(?,?,?)",(customer_name,rate,description))
           c.commit()
           c.close()
           #In Streamlit, st.empty() is a method that creates an empty container in which you can dynamically add content. The primary use of st.empty() is to create a placeholder or container that you can later fill with dynamic content based on certain conditions or user interactions.
           customer_name =customer_name1.text_input('',key="3",placeholder="Enter the Name")
           description=description1.text_area('',key="4",placeholder="Enter the message!!!")
    op=option_menu(
        options=['ALL Inputs & Responses','MostAskedinputs','Mostgivenresponses','User Reviews&Ratings','EDA for Reviews'],
        orientation='horizontal',
        menu_title=""
    )
    con=sqlite3.connect("streamlit/Streamlit_programs/PROJECTS2/lovechatbot.db")
    cur=con.cursor()
    query="select UserInput,ModelResponse,Accuracy from userinputresponse"
    cur.execute(query)
    data=cur.fetchall()
    dd=pd.DataFrame(data)
    #setting index vaue from 1
    dd.index=range(1,len(dd.index)+1)
    dd.rename(columns={0:'input',1:'Response',2:'Accuracy'},inplace=True)
    if op=='ALL Inputs & Responses':
       st.table(dd)
    elif op=='MostAskedinputs':
        if dd.empty:
            st.write("DATABASE IS EMPTY!!!!")
        else:
            count=dd['input'].value_counts().reset_index()
            #setting index vaue from 1
            count.index=range(1,len(count.index)+1)
            se=st.selectbox("SELECT THE CATEGORY",options=['TOP10','LEAST10','TOP20','LEAST20'])
            if se=='TOP10':
                st.table(count.head(10))
            elif se=='LEAST10':
                st.table(count.tail(10))
            elif se=='TOP20':
                st.table(count.head(20))
            elif se=='LEAST20':
                st.table(count.tail(20))
    elif op=='Mostgivenresponses':
        if dd.empty:
            st.write("DATABASE IS EMPTY!!!!")
        else:
            count=dd['Response'].value_counts().reset_index()
            #setting index vaue from 1
            count.index=range(1,len(count.index)+1)
            se=st.selectbox("SELECT THE CATEGORY",options=['TOP10','LEAST10','TOP20','LEAST20'])
            if se=='TOP10':
                st.table(count.head(10))
            elif se=='LEAST10':
                st.table(count.tail(10))
            elif se=='TOP20':
                st.table(count.head(20))
            elif se=='LEAST20':
                st.table(count.tail(20))
    elif op=='User Reviews&Ratings':
        conn=sqlite3.connect("streamlit/Streamlit_programs/PROJECTS2/lovechatbot.db")
        cur=conn.cursor()
        query="select * from review_table"
        cur.execute(query)
        d=cur.fetchall()
        dataframe=pd.DataFrame(d)
        cur.close()
        conn.close()
        dataframe.rename(columns={0:'Name',1:"Ratings",2:"Message"},inplace=True)
        if dataframe.empty:
            st.write("DATABASE IS EMPTY!!!!")
        else:
            st.table(dataframe)
    elif op=='EDA for Reviews':
        conn=sqlite3.connect("streamlit/Streamlit_programs/PROJECTS2/lovechatbot.db")
        cur=conn.cursor()
        query="select * from review_table"
        cur.execute(query)
        d=cur.fetchall()
        dataframe=pd.DataFrame(d)
        cur.close()
        conn.close()
        dataframe.rename(columns={0:'Name',1:"Ratings",2:"Message"},inplace=True)
        radio=st.selectbox("Select what you want to see?",options=['star Ratings','Popular messages','ALL Customer Names'])
        if radio=='star Ratings':
            if dataframe.empty:
               st.write("DATABASE IS EMPTY!!!!")
            else:
                data=go.Scatter(
                    y=dataframe['Ratings'],
                    mode="lines+markers",
                    name="lines",
                    text=dataframe['Ratings'].astype(str),
                    marker=dict(
                    color="plum",
                    ),
                )
                layout=go.Layout(
                title=dict(text="Customer Star Ratings",x=0.3,y=0.9,font=dict(size=25)),
                xaxis_title="No of Ratings",
                yaxis_title="Ratings",
                paper_bgcolor="#ff3333",
                margin=dict(l=50,r=40,b=50,t=90),
                )
                fig=go.Figure(data=data,layout=layout)
                st.plotly_chart(fig,use_container_width=True)
                #for histogram text
                da1=dataframe['Ratings'].value_counts().reset_index()
                da2=da1.sort_values(by="Ratings")
                #st.write(da2)
                data=go.Histogram(
                x=dataframe['Ratings'],
                name="Myplot",
                marker=dict(color='plum'),
                text=da2['count']
                #line=dict(width=5,color='orange')  
                )
                layout=go.Layout(
                bargap=0.1,
                title=dict(text="No of Star Ratings",x=0.4,y=0.9,font=dict(size=25)),
                xaxis_title="No of Ratings",
                yaxis_title="count",
                paper_bgcolor="#ff3333",
                margin=dict(l=50,r=40,b=50,t=90),
                )
                fig=go.Figure(data=data,layout=layout)
                st.plotly_chart(fig,use_container_width=True)
        elif radio=='Popular messages':
            if dataframe.empty:
               st.write("DATABASE IS EMPTY!!!!")
            else:
                val_count=dataframe['Message'].value_counts().reset_index()
                #st.write(val_count)
                cc1,cc2=st.columns([1,4])
                with cc1:
                    radio1=st.radio("",options=['Most Given 10','Least Given 10','Most Given 5','Least Given 5','Most Given 1','Least Given 1'])
                    if radio1=='Most Given 10':
                        dk=val_count.head(10)
                    elif radio1=='Least Given 10':
                            dk=val_count.tail(10)
                    elif radio1=='Most Given 5':
                        dk=val_count.head(5)
                    elif radio1=='Least Given 5':
                            dk=val_count.tail(5)
                    elif radio1=='Most Given 1':
                        dk=val_count.head(1)
                    elif radio1=='Least Given 1':
                            dk=val_count.tail(1)
                with cc2:
                    st.table(dk)
        elif radio=='ALL Customer Names':
            if dataframe.empty:
               st.write("DATABASE IS EMPTY!!!!")
            else:
               st.table(dataframe['Name'])
elif select=='ProjectOverview':
    with st.sidebar:
        with open("streamlit/Streamlit_programs/PROJECTS2/Animation - 1706725721151.json") as c:
           con=json.load(c)
        st_lottie(con,height=200,width=300,speed=2)
    st.markdown("""
               <style>
                .k{
                background-color:#000000;
                text-align:center;
                font-size:25px;
                font-weight:bold;
                border:2px solid white;
                box-shadow:2px 5px 20px #4b4e4b;
                color:white;
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
                background-color:#ffa31a;
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
                /*#disabling right up corner 3 dot*/
                .st-emotion-cache-zq5wmm.ezrtsby0{
                    visibility:hidden;
                }
                </style>
                """,unsafe_allow_html=True)
    st.markdown("<h1 class='k1'>CREATING LOVE CAHTBOT USING DEEPLEARNING</h1>",unsafe_allow_html=True)
    st.markdown("""<div class='k'>
         <p>Creating a love chatbot using deep learning involves leveraging natural language processing (NLP) and machine learning techniques to enable the chatbot to understand and generate human-like responses in the context of love and relationships</p>       
    </div><br>
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
    st.markdown("""
                <style>
                
                .st-emotion-cache-sh2krr.e1nzilvr5
                {
                width:300px;
                height:50px;
                
                }
                .st-emotion-cache-sh2krr.e1nzilvr5 p{
                font-size:25px;
                font-weight:bold;
                }
                /*#disabling right up corner 3 dot*/
                .st-emotion-cache-zq5wmm.ezrtsby0{
                  visibility:hidden;
                }
                </style>
                """,unsafe_allow_html=True)
    with st.sidebar:
        st.markdown("---")
        st.markdown("<h1 style='text-align:center;color:red';>Customer Review</h1>",unsafe_allow_html=True)
        customer_name1=st.empty()
        description1=st.empty()
        customer_name =customer_name1.text_input('',key="1",placeholder="Enter the Name")
        #disabling the send icon
        st.markdown("""
                    <style>
                    .st-emotion-cache-1if5ada.e1y5xkzn1{
                    visibility:hidden;
                    }
                    .st-emotion-cache-hc3laj.ef3psqc12{
                    color:red;
                    width:250px;
                    background-color:black;
                    margin-left:20px;
                    border-radius:12px 12px 12px 12px;
                    }
                    """,unsafe_allow_html=True)
        rate=st.slider("Rate from 1 to 5",0,5,3)
        st.markdown(f'<h6 style="color:green;font-size:20px;">You Selected: {"⭐️"*int(rate)}</h6>',unsafe_allow_html=True)
        description=description1.text_area('',key="2",placeholder="Enter the message!!!")
        submit=st.button("submit")
        st.markdown("---")
        if submit:
           
           st.write("Thankyou for your review!!")
           c=sqlite3.connect("streamlit/Streamlit_programs/PROJECTS2/lovechatbot.db")
           cur=c.cursor()
           cur.execute("insert into review_table values(?,?,?)",(customer_name,rate,description))
           c.commit()
           c.close()
           #In Streamlit, st.empty() is a method that creates an empty container in which you can dynamically add content. The primary use of st.empty() is to create a placeholder or container that you can later fill with dynamic content based on certain conditions or user interactions.
           customer_name =customer_name1.text_input('',key="3",placeholder="Enter the Name")
           description=description1.text_area('',key="4",placeholder="Enter the message!!!")

    tab1,tab2,tab3=st.tabs(['Developer/ContactUs','Datasource/codes','Deletedatafromdatabase'])
    with tab1:
        c1,c2=st.columns(2)
        with c1:
            from streamlit_lottie import st_lottie
            with open("streamlit/Streamlit_programs/PROJECTS2/Animation - 1706721681647.json") as c:
                con=json.load(c)

            st.markdown(f"""
                        <div class='k'>
                        {st_lottie(con,height=430,width=None,speed=2,loop=True)}
                        </div>
                           """,unsafe_allow_html=True)
            
            
        with c2:
            #st.markdown("---")
            st.write("<h2 style='color:#00ff00;text-decoration:underline;'>Contactus</h2>",unsafe_allow_html=True,use_column_width=True)
            
            st.write("<h5 style='color:orange;'> 💻 Creater:  KARTHIK R</h5>",use_column_width=True,unsafe_allow_html=True)
            
            gmail_address="karthikmca6622@gmail.com"
            gmail_link=f"mailto:{gmail_address}"
            #we can see the emojis inside the github cheat-sheet-https://github.com/ikatyang/emoji-cheat-sheet
            st.write(f"#### <h5 style='color:orange;'> :email: Email: [karthikmca6622@gmail.com]({gmail_link})</h4>",use_column_width=True,unsafe_allow_html=True)
            
            phone_number="9944194787"
            phone_link=f"tel:{phone_number}"
            st.write("#### <h5 style='color:orange;'> :iphone: Phone-Number:  [9944194787]({phone_link})</h5>",use_column_width=True,unsafe_allow_html=True)
            st.write("#### <h5 style='color:orange;'> :rocket: Github: [https://github.com/Karthik6622/PYTHON](https://github.com/Karthik6622/PYTHON)</h5>",use_container_width=True,unsafe_allow_html=True)
            st.write("#### <h5 style='color:orange;'> :o: Streamlit: [https://share.streamlit.io/](https://share.streamlit.io/)</h5>",use_container_width=True,unsafe_allow_html=True)
            st.markdown("---")
        st.markdown("---")
    with tab2:
        co1,co2=st.columns([1,2])
        with co1:
           st.markdown("<h4 style='color:#00ff00;'>JSON DATA FILE</h4>",unsafe_allow_html=True)
           #st.markdown("---")
        with open("streamlit/Streamlit_programs/PROJECTS2/intents.json") as fi:
            da=json.load(fi)
        #This code converts the dictionary (da) into a JSON-formatted string using json.dumps. 
        json_data=json.dumps(da,indent=2)# the indent parameter is an optional argument that specifies the number of spaces to use for indentation when pretty-printing the JSON string
        
        with co2:
           st.markdown("<br>",unsafe_allow_html=True)
           
           st.download_button("DOWNLOAD JSON DATA",data=json_data,file_name="lovedata.json")
        st.markdown("---")
        co11_,co22_=st.columns([1,2])
        with co11_:
            st.markdown("<h4 style='color:#00ff00;'>Source code</h4>",unsafe_allow_html=True)
            #st.markdown("---")
        with co22_:
            st.markdown("[https://github.com/Karthik6622/PYTHON/blob/main/streamlit/Streamlit_programs/PROJECTS2/chatbot1.py](https://github.com/Karthik6622/PYTHON/blob/main/streamlit/Streamlit_programs/PROJECTS2/chatbot1.py)")
        st.markdown("<hr>",unsafe_allow_html=True)
        co111,co222=st.columns([1,2])
        with co111:
            st.markdown("<h4 style='color:#00ff00;'>Databasefile</h4>",unsafe_allow_html=True)
            #st.markdown("---")
        with co222:
            st.markdown("[https://github.com/Karthik6622/PYTHON/blob/main/streamlit/Streamlit_programs/PROJECTS2/intents.json](https://github.com/Karthik6622/PYTHON/blob/main/streamlit/Streamlit_programs/PROJECTS2/intents.json)")
            #st.markdown("---")
    with tab3:
        selct=st.selectbox("Select the Database to want to Delete",options=['USERINPUTDATABASE','USERREVIEWDATABASE'])
        if selct=='USERINPUTDATABASE':
            inp_pass=st.text_input("",placeholder="Enter your Passcode to delete USERINPUTDATABASE....")
            submit=st.button("RESET/CLEAR THE DATABASE")
            if submit:
                if inp_pass=='6860':
                    #st.write("kkkk")
                    conn1 = sqlite3.connect("streamlit/Streamlit_programs/PROJECTS2/lovechatbot.db")
                    cursor = conn1.cursor()
                    query = "DELETE FROM userinputresponse"
                    cursor.execute(query)
                    conn1.commit()
                    #st.write("<h2 style='color:green';>Delete successful</h2>",unsafe_allow_html=True)
                    st.success('Delete successful')
                    conn1.close()

                else:
                    st.error("Please enter correct passcode!!!!")
        elif selct=='USERREVIEWDATABASE':
            inp_pass=st.text_input("",placeholder="Enter your Passcode to delete USERREVIEWDATABASE....")
            submit=st.button("RESET/CLEAR THE DATABASE")
            if submit:
                if inp_pass=='6860':
                    #st.write("kkkk")
                    conn1 = sqlite3.connect("streamlit/Streamlit_programs/PROJECTS2/lovechatbot.db")
                    cursor = conn1.cursor()
                    query = "DELETE FROM review_table"
                    cursor.execute(query)
                    conn1.commit()
                    #st.write("<h2 style='color:green';>Delete successful</h2>",unsafe_allow_html=True)
                    st.success('Delete successful')
                    conn1.close()
                else:
                    st.error("Please enter correct passcode!!!!")
else:        
    st.write("kkkk")
