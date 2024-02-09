import streamlit as st
import json
import pandas as pd
import string
from tensorflow import keras
import numpy
from kkk import chat_history
#setting the streamlit page layout as wide
st.set_page_config(layout="wide")
st.title("Personal Chatbot") 
@st.cache_data
def algorithm():
    with open("E:/PYTHON/streamlit/Streamlit_programs/PROJECTS2/personalintents.json") as f:
         data=json.load(f)
    tag=[]
    input=[]
    response={}
    for indents in data['intents2']:
        response[indents['tag']]=indents['responses']
        for line in indents['patterns']:
            input.append(line)
            tag.append(indents['tag'])
    data2=pd.DataFrame({'input':input,'tag':tag})
    #changing input column into the lower and removing the puncutation
    data2['input']=data2['input'].apply(lambda x:[wrd.lower() for wrd in x if wrd not in string.punctuation])
    data2['input']=data2['input'].apply(lambda x:''.join(x))

    #applyting tokenizer for input column
    token=keras.preprocessing.text.Tokenizer(num_words=1000)
    token.fit_on_texts(data2['input'])
    s=token.texts_to_sequences(data2['input'])
    #applying the padding to tghe tokenizer
    from keras.preprocessing.sequence import pad_sequences
    x_train=pad_sequences(s)

    #chaniging tag column into number using labelencoder
    from sklearn.preprocessing import LabelEncoder
    lab=LabelEncoder()
    y_train=lab.fit_transform(data2['tag'])

    #finding the total words
    voc=token.word_index
    len_voc=len(voc)
    input_shape=x_train[0].shape
    out_shape=numpy.unique(y_train)
    len_out=len(out_shape)
    #st.write(len_voc,input_shape,out_shape)

    #creating deep learning neural network model
    model=keras.Sequential([
        keras.layers.Embedding(len_voc+1,10,input_shape=input_shape),
        keras.layers.LSTM(10,return_sequences=True),
        keras.layers.Flatten(),
        keras.layers.Dense(len_out,activation='softmax'),
    ])
    model.compile(optimizer="adam",loss="sparse_categorical_crossentropy",metrics=['accuracy'])
    model.fit(x_train,y_train,epochs=300)
    return token,input_shape,model,lab,response
token,input_shape,model,lab,response=algorithm()

input=st.chat_input(placeholder="Type somethings")
input_shape2=input_shape[0]
if input!='exit' and input is not None:
    test_input=[]
    pred_input=[wrd1.lower() for wrd1 in input if wrd1 not in string.punctuation]
    pred_input=''.join(pred_input)
    test_input.append(pred_input)
    se=token.texts_to_sequences(test_input)
    #changing to 1d array
    se1=numpy.array(se).reshape(-1)
    from keras.preprocessing.sequence import pad_sequences
    user_inp=pad_sequences([se1],input_shape2)
    #st.write(user_inp)
    #predict the user input value
    predic=model.predict(user_inp)
    max=predic.argmax()
    import random
    #finding accurracy
    accuracy=predic[0][max]
    print(accuracy)
    if accuracy>=0.7:
        response_tag=lab.inverse_transform([max])[0]
        pp=random.choice(response[response_tag])
    else:
        pp="What are you asking karthik i could not understand"
    chat_history.append({'YOU':test_input,'BABY':pp})
    for i in range(len(chat_history)):
        c1,c2=st.columns([6,10])
        with c1:
            st.markdown(f"<h3 style='color:green;'><strong><u>YOU</u></strong>👩‍💻: {chat_history[i]['YOU'][0]}</h3>",unsafe_allow_html=True)
            #st.markdown("<br>",unsafe_allow_html=True)
        with c2:
            st.markdown("<br>",unsafe_allow_html=True)
            st.markdown(f"<h3 style='color:green;'><strong><u>BABY</u></strong>❤️: {chat_history[i]['BABY']}",unsafe_allow_html=True)
elif input=='exit':
    st.markdown('<a href="https://babylovechatbot.streamlit.app/?embed=true" target="_self">exit</a>', unsafe_allow_html=True)
else:
    st.write("Please enetr somthing")
    
    