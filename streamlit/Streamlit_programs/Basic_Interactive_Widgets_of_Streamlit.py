import streamlit as st
#checkbox
#creating simple checkbox
st.checkbox("checkbox")#"checkbox"-label of checkbox
st.markdown("---")
#defaulty check box is false if we want to make True we can use value=True 
st.checkbox("checkbox",value=True) 
st.markdown("---")
#how to display text's if checkbox is selected or not checked
def change():
   st.write("checkbox1 event happened")
   st.write(st.session_state.kkk)#using key we can display the session state(selected means true,unselected means false)
#key is so useful for identification when we create morethan one check box 
def change1():
    st.write("checkbox2 event happened")
se=st.checkbox("checkbox",value=True,key='kkk',on_change=change)#onchange function like onclick if we select or deselct the checkbox that function will run
se2=st.checkbox("checkbox2",key="kkk2",on_change=change1)
#using variable also we can disply whether checkbox is selected or not
if se==True:
    st.write("checkbox1 is selected")
else:
    st.write("checkbox1 is not selected")
if se2==True:
    st.write("checkbox2 is selected")
else:
    st.write("checkbox2 is not selected")

#radio button
#creating radio button 
ra=st.radio("What is your gender?",options=("Male","female","others"))
st.write(f"you have selected {ra}")
#we can give key and on_change function also to radio button
def ch():
    st.write("radio button modified")
ra1=st.radio("what is your age?",options=("18 below",'18-50','50above'),on_change=ch(),key='kkkk')
#using variable also we can disply which radio button was selected by user
if ra1=="18 below":
    st.write("selected 18 below option")
elif ra1=="18-50":
    st.write("selected 18-50 option")
else:
    st.write("selected 50above option")

#create a button 
def my_click():
    st.write("button was clicked by user!!!")
st.button("clickme",on_click=my_click)
#on_click event tells whether we clicking button or not
#and one more think if we click button whole streamlit page getting refresh to avoid that we can use form but we will study that one in feature

#selcet box-it is used to select one option from the selectbox
select=st.selectbox("Select your favorite girl",options=('baby','varsha','asha','azula'))
print(select)#if we give print means,it will print in terminal
st.write("you have selected",select,"as your wife")

#multiselect box-using this we can select multiple values from the selectbox
sel_mul=st.multiselect("Selcet your favorite cars",options=("Audi","Bmw","Hyndai","ferrari","Tata"))
st.write("you have selected",sel_mul)#it's automatically display as code form
#using for loop also,we can display what we have been selected
for i in sel_mul:
    st.write(i)
