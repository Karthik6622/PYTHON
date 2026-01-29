import streamlit as st
#this is unofficial way to use html in streamlit
st.markdown("<h1 style='color:orange';>Custom HTML In Streamlit</h1>",unsafe_allow_html=True)

#now we going to see officail way to create html tags in streamlit
import streamlit.components.v1 as com
#once created com.html,one box will be created in streamlit web app
#we can set height and width and scrolling
com.html("""
    <style>
         h2{
         color:red;
         text-align:center;
         }
         p{
         color:blue;
         background-color:green;
         }
    </style>
    <div>
   <h2>Random text</h2>
         <p>Video provides a powerful way to help you prove your point. When you click Online Video, you can paste in the embed code for the video you want to add. You can also type a keyword to search online for the video that best fits your document.
To make your document look professionally produced, Word provides header, footer, cover page, and text box designs that complement each other. For example, you can add a matching cover page, header, and sidebar. Click Insert and then choose the elements you want from the different galleries.
Themes and styles also help keep your document coordinated. When you click Design and choose a new Theme, the pictures, charts, and SmartArt graphics change to match your new theme. When you apply styles, your headings change to match the new theme.
Save time in Word with new buttons that show up where you need them. To change the way a picture fits in your document, click it and a button for layout options appears next to it. When you work on a table, click where you want to add a row or a column, and then click the plus sign.
Reading is easier, too, in the new Reading view. You can collapse parts of the document and focus on the text you want. If you need to stop reading before you reach the end, Word remembers where you left off - even on another device.
</p>
    </div>      
         """,height=300,width=500,scrolling=True)

#how to apply css color attributes from external css file
#opening custom.css file using python file handling method
with open('custom.css','r') as file:
    content=file.read()
com.html(f"""
    <style>
       {content} 
    </style>
    <div>
   <h2>Random text</h2>
         <p>Video provides a powerful way to help you prove your point. When you click Online Video, you can paste in the embed code for the video you want to add. You can also type a keyword to search online for the video that best fits your document.
To make your document look professionally produced, Word provides header, footer, cover page, and text box designs that complement each other. For example, you can add a matching cover page, header, and sidebar. Click Insert and then choose the elements you want from the different galleries.
Themes and styles also help keep your document coordinated. When you click Design and choose a new Theme, the pictures, charts, and SmartArt graphics change to match your new theme. When you apply styles, your headings change to match the new theme.
Save time in Word with new buttons that show up where you need them. To change the way a picture fits in your document, click it and a button for layout options appears next to it. When you work on a table, click where you want to add a row or a column, and then click the plus sign.
Reading is easier, too, in the new Reading view. You can collapse parts of the document and focus on the text you want. If you need to stop reading before you reach the end, Word remembers where you left off - even on another device.
</p>
    </div>      
         """,height=400)




