import streamlit as st

#form creation(1st method)
st.markdown("<h1>User Registration</h1>",unsafe_allow_html=True)
form=st.form("form1")
k=form.text_input("Enter your Name")
form.form_submit_button("Submit")#submit button is required field of form
st.write(k)#if click submit button,entered value will be displayed here
st.markdown("---")

#form creation(2nd method)
st.markdown("<h1>Login</h1>",unsafe_allow_html=True)
with st.form("form2"):
    kk=st.text_input("Enter your ID")
    st.form_submit_button("OK")
st.write(kk)#if click submit button,entered value will be displayed here
st.markdown("---")
#note:we can see if we click one form submit button,one more form values not changing

#creating proper User Registration form with form column function
#using form column function we can seperate the form widget as 2 column,3column as we want
st.markdown("<h2>USER REGISTRATION</h2>",unsafe_allow_html=True)
with st.form("form3"):
    col1,col2=st.columns(2)#it will seperate the form as 2 column
    fname=col1.text_input("Enter Your FirstName")
    lname=col2.text_input("Enter your Lastname")
    email=st.text_input("Enter you Email Id")
    pn=st.text_input("Enetr your PhoneNumber")
    st.form_submit_button("Submit")
#displaying entered details
dic={'firstName':fname,"lastname":lname,"Email":email,"Phonenumber":pn}
st.write(dic)

#creating user signup form with successfull message & warning message:
st.markdown("<h2 style='text-align:center;color:red'>SignUp</h2>",unsafe_allow_html=True)
with st.form("form4"):
    col1,col2=st.columns(2)#it will seperate the form as 2 column
    fname=col1.text_input("Enter Your FirstName")
    lname=col2.text_input("Enter your Lastname")
    email=st.text_input("Enter you Email Id")
    pn=st.text_input("Enetr your PhoneNumber")
    day,month,year=st.columns(3)#it will seperate the form as 3 columns
    day.text_input("Day")
    month.text_input("month")
    year.text_input("year")
    but=st.form_submit_button("Submit")
#validation and displaying error,warning and success message
    if but:
        if fname=='' and lname=='':
            st.error("Please make sure all field are filled")
            st.warning("please fill above field")
        else:
            st.success("Successfully submited!!!")

