import streamlit as st
st.title("Uploading the Files")
st.markdown("---")
#fileuploder-using this we can upload the file,image,etc..
#create image uploader 
st.file_uploader("Please upload the Image:",type=['png'])
#type=['png']-if we give type like that,it will only accept png extention images .if we any other image extention it will throw the error
#if we want to upload Jpg image,mention inside the type jpg
st.file_uploader("Please upload the Image:",type=['png','jpg'])
#we can upload using Browsefile button or drag and drop
#how to display uploaded image
#if we declare fileuploader as same as above fileuploader error will come to avoid that we can use key attribute for below fileuploder
image=st.file_uploader("Please upload the Image:",type=['png','jpg'],key="bab")
if image is not None:
    st.image(image,width=200)
#how to create uploader for  pdf and doc file
st.file_uploader("Uploading the Pdf or Doc",type=['pdf','doc'])

#how to create multiple image uploader 
st.file_uploader("Multiple Image Uploader",type=['png','jpg'],accept_multiple_files=True)
#using "accept_multiple_files=True" attribute we can upload morethan one files

#how to display multile images
im=st.file_uploader("Multiple Image Uploader",type=['png','jpg'],accept_multiple_files=True,key='ba')
for j in im:
    if j is not None:
        st.image(j,width=200) 

#how to create video uploader and display the uploaded video
vi=st.file_uploader("Upload the video",type=['mp4'])
st.video(vi)#using this video function we can't set video height and width
#so we can use heml for display the customized video
video_width = 200
video_height = 200
st.markdown(
f'<video src="google_issues_video.mp4" height="200" width="200" controls autoplay muted></video>'
,unsafe_allow_html=True
)
