import streamlit as st
st.title("HI THIS IS MY STREAMLIT PAGE TITLE")#title of the page
st.subheader("HI THIS IS mY SUBHEADER OF STREAMLIT PAGE")#subheader of the page.it's little bit smaller than header 
st.header("Hi this is my header of streamlit page")#header of the page and it's little bit sma1ler than title
st.text("Hi thi my text of streamlit page")#it used to display the text's in the page
#html hedings
st.markdown("# h1")
st.markdown("## h2")
st.markdown("### h3")
st.markdown("#### h4")
st.markdown("##### h5")
st.markdown("###### h6")
#bold text
st.markdown("**hello**")
#italic text
st.markdown("*hello*")
#ordered list
#here we have to put 2 spaces each value end for newline
#we can give number,roman letter anything
st.markdown('''i. karthik1  
               ii. karthik2  
               iii. karthik3'''
            )

#unordered list
#here we have to put 2 spaces each value end for newline
st.markdown('''- karthik1  
               - karthik2  
               - karthik3'''
            )
#display the programming code
st.markdown('''```python
import numpy as np  
n=np.array([34,45,23,2])  
```''')
#display the blockqoute(| karthik)
st.markdown(">karthik")
#display the horizontal line
st.markdown("---")
#displaying the link
st.markdown("[google](https://www.google.com)")
#create a table using markdown(for new row add 2 space every row end)
st.markdown("""
            | names     | age       |  
            | --------- | --------- |  
            | karthik   | 23        |  
            | mani      | 25        |  
            """)
#crating the code block using markdown
st.markdown('''
```
{
  "firstName": "John",
  "lastName": "Smith",
  "age": 25
}
```
''')
#crating subscript using markdown
#both are not working(H~2~O,X^2^)
#so we have to copy the subscript and superscript from website
st.markdown("H₂O")
st.write("H₂O")#copy and paste from
#creating superscript using markdown
st.markdown("X²")#alt+0178
#creating strikethrough using markdown
st.markdown("~~karthik~~")
#creating emoji with text 
st.markdown("that is so funny! :heart: :joy:")
#creating definition list using markdown(for newline use 2space after the end of row)
st.markdown('''term1
: definition1  
term2
: definition2     ''')
#displaying image with caption using streamlit
st.image('2.jpg',caption="Alt text",use_column_width=True)
#displaying json objects
json={"a":"1,2,3","b":"4,5,6"}
st.json(json)
#we can use write function instead of markdown function
st.write("## h2") 
#one more method to display the code
code="""
print("Hello world")
def funct():
    return 0
"""
st.code(code,language="python")

#metric function-Metrics are quantitative assessment measures that are routinely used to evaluate, compare, and track performance or production.
st.metric(label="windspeed",value="120ms⁻¹",delta="1.4ms⁻¹")#for superscript we can use \^-1+tab
#applying column function for metric
col1,col2,col3=st.columns(3)
col1.metric("Temperature","70 \u00b0F","1.2 \u00b0F")#\u00b0-unicode for temperature symbol
col2.metric("Wind", "9 mph", "-8%")
col3.metric("Humidity", "86%", "4%")

#display value as a table
import pandas as pd
table1=pd.DataFrame({'names':['Karthik','mani','Raju'],'Age':[23,25,27]})
st.table(table1)
st.dataframe(table1)
#what is the different between st.table and st.dataframe?
#st.dataframe we can save the data's as a csv and we can see the accending and decending order the data's but in table we can't see like that