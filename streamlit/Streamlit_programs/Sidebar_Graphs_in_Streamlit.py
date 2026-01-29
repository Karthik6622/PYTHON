import streamlit as st
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
#creating the sidebar with normal write widget
#st.sidebar.write("This is my sidebar")

#creating inbutbox and radio button inside the sidebar
#side=st.sidebar
#age=side.text_input("Enter the age")
#ra=side.radio("Seelect the Gender",options=['male','female','others'])
#st.write(age,ra)

#draw the graph using matplotlib
#x=np.arange(0,4*np.pi,0.1)
#y=np.sin(x)
#fig=plt.figure(figsize=(10,10))
#ax=fig.add_axes([0,0,2,1])
#ax.plot(x,y)
#st.write(fig)

#draw more than one graph and display the graph as we selected from sidebar
#creating side bar using with notation
#reading file from local directory
dd=pd.read_csv("file:///C:/Users/Admin/PYTHON/Matplotlib_Practise_files/car-sales.csv")
st.write(dd)
with st.sidebar:
    st.markdown("<h3>Charts</h3>",unsafe_allow_html=True)
    ra=st.radio("pleae select one Chart",options=['Histogram','Barchart','Scatter'])
if ra=='Histogram':
    fig=plt.figure()
    plt.hist(dd['Doors'])
    st.write(fig)
elif ra=='Barchart':
    fig=plt.figure()
    plt.bar(dd['Make'],dd['Price'])
    st.write(fig)
else:
    fig=plt.figure()
    plt.scatter(dd['Doors'],dd['Price'])
    st.write(fig)


    