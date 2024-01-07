import streamlit as st
import matplotlib.pyplot as plt
import pandas as pd
st.title("HI ! iam in straemlit web app")
dic={'x':[1,23,45,53,89],'y':[4,56,7,8,0]}
dd=pd.DataFrame(dic)
fig=plt.figure(figsize=(10,10))
ax=fig.add_axes([0,0,2,1])

ax.plot(dd['x'],dd['y'])
st.pyplot(fig)