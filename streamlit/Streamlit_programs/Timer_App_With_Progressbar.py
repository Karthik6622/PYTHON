import streamlit as st
import time as t
from datetime import time
st.title("Progressbar")
st.markdown("---")
#creating a simple progressbar
st.progress(0)
#progress bar created but we give value 0 that's why line not moving
st.markdown("---")
#create progrssbar with sleep time
#here we creating progress bar for 10 second
bar=st.progress(0)
for i in range(10):
    bar.progress((i+1)*10)#it will increase 10 by 10
    t.sleep(1)#sleep is used to handle the progress waiting time,1-second
st.markdown("---")
#create a progressbar by getting time input from user
#calculating minute:second:millisecond to second using function
def sec_cal(value):
    m,s,mm=str(value).split(':')
    cal=int(m)*60+int(s)+int(mm)/1000#1000 millisecond equal to 1 second
    return cal
ti=st.time_input("Enter you progress time",value=time(0,0,0))#if we set value attribute,it will take ddefaultly mentioned value 
                                   #(0,0,0)-(minute,second,millisecond)
#if time is empty,we telling to select time
if str(ti)=="00:00:00":
    st.write("Plese select the progress time!!!")
else:
    #getting total second using function
    total_sec=sec_cal(ti)
    #st.write(total_sec)
    #splitng total second for 100 times(for 100 percentange)
    sp=total_sec/100
    bar1=st.progress(0)
    #empty()-used to display progress status of progressbar
    progress_status=st.empty()
    for j in range(1,100+1):
        bar1.progress(j)
        progress_status.write(str(j)+"%")
        t.sleep(sp)
    