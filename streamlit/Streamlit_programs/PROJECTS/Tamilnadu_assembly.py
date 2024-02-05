import streamlit as st
import pandas as pd
import plotly.express as px
from plotly.offline import plot
import plotly.graph_objs as go
import numpy as np
import streamlit.components.v1 as com
from streamlit_option_menu import option_menu
from plotly.subplots import make_subplots
import math
#setting the page cofig for wide web page (we can avoid unnessery space between sidebar and main page)
st.set_page_config(layout='wide')
st.markdown("""
<style>
#MainMenu{
    visibility: hidden;
}
.stApp{
    background-color:black;
}
</style>
""",unsafe_allow_html=True)
#pip install stremlit-option-menu
#optionmenu is used to create attractive side bar with options
#creating the side bar and inside the side we giving plot option to user select
with st.sidebar:
   see=option_menu(
       menu_title="Main menu",
       menu_icon="code-square",
       options=['Home','Barplot','Lineplot','GeoMap','Histogram','Predictions'],
       icons=['house-heart-fill','bar-chart','graph-up','globe','file-bar-graph','box-fill'],
       orientation="horizontal",
       default_index=0,
   )
#reding the Tamilnadu assembly election data through the csv file
dd=pd.read_csv("streamlit/Streamlit_programs/PROJECTS/Tamil_Nadu_AE.csv")
#st.write(dd)
#extract the Pa
d=dd['Party'].value_counts().reset_index()
ye=dd['Year'].unique()
#st.write(ye)
#st.write(d)
#print(multi_selet)
if see=='Barplot':
    sa=option_menu(
     menu_title="",
     options=['Party','Total'],
     icons=["p-square-fill","union"],
     orientation='horizontal',
    )
    if sa=='Party':
        with st.sidebar:
            multi_selet=st.multiselect("Select the party:",options=d['Party'].unique(),default=['ADMK','BJP'])
            region=st.selectbox("Select the region",options=['ALL','Constituency_Name','District_Name','Sub_Region'],index=1)
            options=ye.tolist()
        if region=='Constituency_Name':
            with st.sidebar:
                con_multi=st.multiselect("Sleect your constituency",options=dd['Constituency_Name'].unique(),default=dd['Constituency_Name'].unique()[1])
        elif region=='District_Name':
            with st.sidebar:
                con_multi=st.multiselect("Sleect your District",options=dd['District_Name'].unique(),default=dd['District_Name'].unique()[1])
        elif region=='Sub_Region':
            with st.sidebar:
                con_multi=st.multiselect("Sleect your Subregion",options=dd['Sub_Region'].unique(),default=dd['Sub_Region'].unique()[1])
        with st.sidebar:
           checkbox_all=st.checkbox("Select All")
           selected_checkbox=[]
           for ii in options:
               default_value=True if ii in [2021,2011] else False
               if checkbox_all or st.checkbox(str(ii),value=default_value):
                   selected_checkbox.append(ii)
        c1,c2=st.columns(2)
        if region=='ALL':
            data=[]
            for se in selected_checkbox:
                dd2=dd[dd['Year']==se]
                for select in multi_selet:
                    group=dd2[dd2['Party']==select].groupby('Year')['Votes'].sum().reset_index()
                    #width=[]
                    #for j in range(len(group['Year'])):
                        #width.append(1)
                    select=go.Bar(
                    x=group['Year'],
                    y=group['Votes'],
                    text=group['Votes'],  
                    #width=width,  
                    name=select+str(se),
                    marker=dict(
                        
                    line=dict(
                        color='plum',
                    width=2
                    )
                        )
                        )
                    data.append(select)
            layout1=go.Layout(
            title=dict(text="Total votes Yearwise",x=0.4,y=1),
            xaxis=dict(title="YEAR",tickangle=-60),
            yaxis=dict(title="TOTAL VOTES",tickangle=40),
            #height=400,
            #width=600,
            barmode='group',
            bargap=0.3
                )
            
            fig=go.Figure(data=data,layout=layout1)
            with c1:
                st.plotly_chart(fig,use_container_width=True)
            #creating the bar chart for each year vo
            data=[]
            for se in selected_checkbox:
                dd5=dd[dd['Year']==se]
                for select in multi_selet:
                    group1=dd5[dd5['Party']==select].groupby('Year')['Vote_Share_Percentage'].mean().reset_index()
                    #st.write(group1)
                    select=go.Bar(
                    x=group1['Year'],
                    y=group1['Vote_Share_Percentage'],
                    text=round(group1['Vote_Share_Percentage'],1),  
                    #width=width,  
                    name=select+str(se),
                    marker=dict(
                        
                    line=dict(
                        color='plum',
                    width=2
                    )
                        )
                        )
                    data.append(select)
            layout1=go.Layout(
            title=dict(text="ToTal votes Share Percenteage",x=0.4,y=1),
            xaxis=dict(title="YEAR",tickangle=-60),
            yaxis=dict(title="TOTAL Vote Share percentage",tickangle=40),
           #height=400,
           # width=600,
            barmode='group',
            bargap=0.3
                )

            fig1=go.Figure(data=data,layout=layout1)
            with c2:
                st.plotly_chart(fig1,use_container_width=True)

            data=[]
            for se in selected_checkbox:
                dd5=dd[dd['Year']==se]
                for select in multi_selet:
                    group1=dd5[dd5['Party']==select].groupby('Year')['Margin'].sum().reset_index()
                    #st.write(group1)
                    select=go.Bar(
                    x=group1['Year'],
                    y=group1['Margin'],
                    text=round(group1['Margin'],1),  
                    #width=width,  
                    name=select+str(se),
                    marker=dict(
                        
                    line=dict(
                        color='plum',
                    width=2
                    )
                        )
                        )
                    data.append(select)
            layout1=go.Layout(
            title=dict(text="ToTal Margin votes",x=0.4,y=1),
            xaxis=dict(title="YEAR",tickangle=-60),
            yaxis=dict(title="TOTAL Margin votes",tickangle=40),
            #height=400,
            #width=600,
            barmode='group',
            bargap=0.3
                )

            fig1=go.Figure(data=data,layout=layout1)
            with c1:
                st.plotly_chart(fig1,use_container_width=True)

            data=[]
            for se in selected_checkbox:
                dd5=dd[dd['Year']==se]
                for select in multi_selet:
                    group1=dd5[dd5['Party']==select].groupby('Year')['Margin_Percentage'].mean().reset_index()
                    #st.write(group1)
                    select=go.Bar(
                    x=group1['Year'],
                    y=group1['Margin_Percentage'],
                    text=round(group1['Margin_Percentage'],1),  
                    #width=width,  
                    name=select+str(se),
                    marker=dict(
                        
                    line=dict(
                        color='plum',
                    width=2
                    )
                        )
                        )
                    data.append(select)
            layout1=go.Layout(
            title=dict(text="ToTal Margin Percentage",x=0.4,y=1),
            xaxis=dict(title="YEAR",tickangle=-60),
            yaxis=dict(title="TOTAL Margin_Percentage",tickangle=40),
            #height=400,
            #width=600,
            barmode='group',
            bargap=0.3
                )

            fig1=go.Figure(data=data,layout=layout1)
            with c2:
                st.plotly_chart(fig1,use_container_width=True)
        
        else:
            #Constituency_Name'
            data=[]
            for se in selected_checkbox:
                dd2=dd[dd['Year']==se]
                for select in multi_selet:
                    #st.write(select)
                    ass=select
                    group=dd2[dd2['Party']==select].groupby([region,'Year'])['Votes'].sum().reset_index()
                    #width=[]
                    #for j in range(len(group['Year'])):
                        #width.append(1)
                    #st.write(group)
                    for c in con_multi:
                        group1=group[group[region]==c]
                        #st.write(group1)
                        select=go.Bar(
                        x=group1['Year'],
                        y=group1['Votes'],
                        text=group1['Votes'],  
                        #width=width,  
                        name=c+' '+ass+' '+str(se),
                        marker=dict(
                        line=dict(
                            color='plum',
                        width=2
                        )
                            )
                            )
                        data.append(select)
            layout1=go.Layout(
            title=dict(text="ToTal votes Yearwise",x=0.4,y=1),
            xaxis=dict(title="YEAR",tickangle=-60),
            yaxis=dict(title="TOTAL VOTES",tickangle=40),
            #height=400,
            #width=600,
            barmode='group',
            bargap=0.3
                )
            
            fig=go.Figure(data=data,layout=layout1)
            with c1:
               st.plotly_chart(fig,use_container_width=True)

            data=[]
            for se in selected_checkbox:
                dd5=dd[dd['Year']==se]
                for select in multi_selet:
                    ass=select
                    group1=dd5[dd5['Party']==select].groupby([region,'Year'])['Vote_Share_Percentage'].mean().reset_index()
                    #st.write(group1)
                    for c in con_multi:
                        group2=group1[group1[region]==c]
                        #st.write(group2)
                        select=go.Bar(
                        x=group2['Year'],
                        y=group2['Vote_Share_Percentage'],
                        text=round(group2['Vote_Share_Percentage'],1),  
                        #width=width,  
                        name=c+' '+ass+' '+str(se),
                        marker=dict(
                            
                        line=dict(
                            color='plum',
                        width=2
                        )
                            )
                            )
                        data.append(select)
            layout1=go.Layout(
            title=dict(text="ToTal votes Share Percenteage",x=0.4,y=1),
            xaxis=dict(title="YEAR",tickangle=-60),
            yaxis=dict(title="TOTAL Vote Share percentage",tickangle=40),
            #height=400,
            #width=600,
            barmode='group',
            bargap=0.3
                )

            fig1=go.Figure(data=data,layout=layout1)
            with c2:
               st.plotly_chart(fig1,use_container_width=True)    
            

            data=[]
            for se in selected_checkbox:
                dd5=dd[dd['Year']==se]
                for select in multi_selet:
                    ass=select
                    group3=dd5[dd5['Party']==select].groupby([region,'Year'])['Margin'].sum().reset_index()
                    #st.write(group1)
                    for c in con_multi:
                        group4=group3[group3[region]==c]
                        select=go.Bar(
                        x=group4['Year'],
                        y=group4['Margin'],
                        text=round(group4['Margin'],1),  
                        #width=width,  
                        name=c+' '+ass+' '+str(se),
                        marker=dict(
                            
                        line=dict(
                            color='plum',
                        width=2
                        )
                            )
                            )
                        data.append(select)
            layout1=go.Layout(
            title=dict(text="ToTal Margin votes",x=0.4,y=1),
            xaxis=dict(title="YEAR",tickangle=-60),
            yaxis=dict(title="TOTAL Margin votes",tickangle=40),
            #height=400,
            #width=600,
            barmode='group',
            bargap=0.3
                )

            fig1=go.Figure(data=data,layout=layout1)
            with c1:
               st.plotly_chart(fig1,use_container_width=True)

            data=[]
            for se in selected_checkbox:
                dd5=dd[dd['Year']==se]
                for select in multi_selet:
                    ass=select
                    group4=dd5[dd5['Party']==select].groupby([region,'Year'])['Margin_Percentage'].mean().reset_index()
                    #st.write(group1)
                    for c in con_multi:
                        group5=group4[group4[region]==c]
                        select=go.Bar(
                        x=group5['Year'],
                        y=group5['Margin_Percentage'],
                        text=round(group5['Margin_Percentage'],1),  
                        #width=width,  
                        name=c+' '+ass+' '+str(se),
                        marker=dict(
                            
                        line=dict(
                            color='plum',
                        width=2
                        )
                            )
                            )
                        data.append(select)
            layout1=go.Layout(
            title=dict(text="ToTal Margin Percentage",x=0.4,y=1),
            xaxis=dict(title="YEAR",tickangle=-60),
            yaxis=dict(title="TOTAL Margin_Percentage",tickangle=40),
            #height=400,
            #width=600,
            barmode='group',
            bargap=0.3
                )

            fig1=go.Figure(data=data,layout=layout1)
            with c2:
               st.plotly_chart(fig1,use_container_width=True)
    elif sa=='Total':
        with st.sidebar:
            region=st.selectbox("Select the region",options=['ALL','Constituency_Name','District_Name','Sub_Region'],index=1)
            options=ye.tolist()
            
        col1,col2=st.columns(2)
        if region=='Constituency_Name':
            with st.sidebar:
                con_multi=st.multiselect("Sleect your constituency",options=dd['Constituency_Name'].unique(),default=dd['Constituency_Name'].unique()[0])
        elif region=='District_Name':
            with st.sidebar:
                con_multi=st.multiselect("Sleect your District",options=dd['District_Name'].unique(),default=dd['District_Name'].unique()[0])
        elif region=='Sub_Region':
            with st.sidebar:
                con_multi=st.multiselect("Sleect your Subregion",options=dd['Sub_Region'].unique(),default=dd['Sub_Region'].unique()[0])
        with st.sidebar:
           checkbox_all=st.checkbox("Select All")
           selected_checkbox=[]
           for ii in options:
               default_value=True if ii in [2021,2011] else False
               if checkbox_all or st.checkbox(str(ii),value=default_value):
                   selected_checkbox.append(ii)
        col1,col2=st.columns(2)
        if region=='ALL':
            data=[]
            for se in selected_checkbox:
                dd2=dd[dd['Year']==se]
                g=dd2.groupby(['Constituency_Name'])['Valid_Votes'].unique().reset_index()
                g2=g['Valid_Votes'].sum()
                #st.write(g2)
                select=go.Bar(
                x=[se],
                y=g2,
                text=g2,  
                #width=width,  
                name=str(se),
                marker=dict(
                    
                line=dict(
                    color='plum',
                width=2
                )
                    )
                    )
                data.append(select)
            layout1=go.Layout(
            title=dict(text="Total Validvotes Yearwise",x=0.5,y=1),
            xaxis=dict(title="Year",tickangle=-60,color="green"),
            yaxis=dict(title="Total Validvotes",tickangle=40,color="green"),
            #height=400,
            #width=600,
            barmode='group',
            bargap=0.3
                )
            
            fig=go.Figure(data=data,layout=layout1)
            with col1:
                st.plotly_chart(fig,use_container_width=True)
            #creating the bar chart for each year vo
            data=[]
            for se in selected_checkbox:
                dd5=dd[dd['Year']==se]
               
                g3=dd5.groupby(['Constituency_Name'])['Electors'].unique().reset_index()
                g4=g3['Electors'].sum()
                select=go.Bar(
                x=[se],
                y=g4,
                text=g4,  
                #width=width,  
                name=str(se),
                marker=dict(
                    
                line=dict(
                    color='plum',
                width=2
                )
                    )
                    )
                data.append(select)
            layout1=go.Layout(
            title=dict(text="Total Electors(voters) Yearwise",x=0.3,y=1),
            xaxis=dict(title="Year",tickangle=-60),
            yaxis=dict(title="Total Electors",tickangle=40),
            #height=400,
            #width=600,
            barmode='group',
            bargap=0.3
                )

            fig1=go.Figure(data=data,layout=layout1)
            with col2:
                st.plotly_chart(fig1,use_container_width=True)

            data=[]
            for se in selected_checkbox:
                dd7=dd[dd['Year']==se]
                g7=dd7.groupby(['Constituency_Name'])['Turnout_Percentage'].unique().reset_index()
                g8=g7['Turnout_Percentage'].sum()/len(g7['Turnout_Percentage'])
                select=go.Bar(
                x=[se],
                y=g8,
                text=np.round(g8,2),  
                #width=width,  
                name=str(se),
                marker=dict(
                    
                line=dict(
                    color='plum',
                width=2
                )
                    )
                    )
                data.append(select)
            layout1=go.Layout(
            title=dict(text="Total Turnout Vote Percentage",x=0.4,y=1),
            xaxis=dict(title="Year",tickangle=-60),
            yaxis=dict(title="Total Turnout Percentage",tickangle=40),
            #height=400,
            #width=600,
            barmode='group',
            bargap=0.3
                )

            fig1=go.Figure(data=data,layout=layout1)
            with col1:
               st.plotly_chart(fig1,use_container_width=True)

        else:
            #Constituency_Name'
            data=[]
            for se in selected_checkbox:
                dd2=dd[dd['Year']==se]
        
                g10=dd2.groupby([region,'Year'])['Valid_Votes'].sum().reset_index()
                for c in con_multi:
                    g11=g10[g10[region]==c]
                    #st.write(g11)
                    select=go.Bar(
                    x=[se],
                    y=g11['Valid_Votes'],
                    text=g11['Valid_Votes'],  
                    #width=width,  
                    name=c+' '+str(se),
                    marker=dict(
                    line=dict(
                        color='plum',
                    width=2
                    )
                        )
                        )
                    data.append(select)
            layout1=go.Layout(
            title=dict(text="Total Validvotes Yearwise",x=0.4,y=1),
            xaxis=dict(title="Year",tickangle=-60),
            yaxis=dict(title="Total Validvotes",tickangle=40),
            #height=400,
            #width=600,
            barmode='group',
            bargap=0.3
                )
            
            fig=go.Figure(data=data,layout=layout1)
            with col1:
                st.plotly_chart(fig,use_container_width=True)

            

            data=[]
            for se in selected_checkbox:
                dd2=dd[dd['Year']==se]
        
                g11=dd2.groupby([region,'Year'])['Electors'].sum().reset_index()
                for c in con_multi:
                    g12=g11[g11[region]==c]
                    #st.write(g11)
                    select=go.Bar(
                    x=[se],
                    y=g12['Electors'],
                    text=g12['Electors'],  
                    #width=width,  
                    name=c+' '+str(se),
                    marker=dict(
                    line=dict(
                        color='plum',
                    width=2
                    )
                        )
                        )
                    data.append(select)
            layout1=go.Layout(
            title=dict(text="Total Electors(voters) Yearwise",x=0.4,y=1),
            xaxis=dict(title="Year",tickangle=-60),
            yaxis=dict(title="Total Electors",tickangle=40),
            #height=400,
           # width=600,
            barmode='group',
            bargap=0.3
                )
            
            fig=go.Figure(data=data,layout=layout1)
            with col2:
                st.plotly_chart(fig,use_container_width=True)   
            

            data=[]
            for se in selected_checkbox:
                dd2=dd[dd['Year']==se]
                if region=='Constituency_Name':
                    g13=dd2.groupby([region,'Year'])['Turnout_Percentage'].unique().reset_index()
                    g13['Turnout_Percentage']=g13['Turnout_Percentage'].str[0]
                    #st.write(g13)
                else:
                    g50=dd2.groupby([region,'Constituency_Name','Year'])['Turnout_Percentage'].unique().reset_index()
                    g51=g50.groupby([region])['Constituency_Name'].nunique()
                    g52=g50.groupby([region,'Year'])['Turnout_Percentage'].sum().reset_index()
                    g13=pd.merge(g51,g52,on=region)
                    g13['Turnout_Percentage']=g13['Turnout_Percentage'].str[0]
                    g13["Turnout_Percentage"]=round(g13['Turnout_Percentage']/g13['Constituency_Name'],2)
                    #st.write(g13)
                for c in con_multi:
                    g14=g13[g13[region]==c]
                    #st.write(g11)
                    select=go.Bar(
                    x=[se],
                    y=g14['Turnout_Percentage'],
                    text=g14['Turnout_Percentage'],  
                    #width=width,  
                    name=c+' '+str(se),
                    marker=dict(
                    line=dict(
                        color='plum',
                    width=2
                    )
                        )
                        )
                    data.append(select)
            layout1=go.Layout(
            title=dict(text="Total Turnout vote Percentage Yearwise",x=0.4,y=1),
            xaxis=dict(title="Year",tickangle=-60,color="green"),
            yaxis=dict(title="Total Turnout Percentage",tickangle=40,color="green"),
            #height=400,
            #width=600,
            barmode='group',
            bargap=0.3
                )
            
            fig=go.Figure(data=data,layout=layout1)
            with col1:
                st.plotly_chart(fig,use_container_width=True)   
elif see=='Lineplot':
    with st.sidebar:
       multi_select=st.multiselect("Select the party",options=d['Party'],default=['ADMK','DMK'])
       min_year=dd['Year'].min()
       max_year=dd['Year'].max()
       slide=st.slider("Select The Yers",min_value=min_year,max_value=max_year,value=2021)
       dd__=dd[dd['Year'].between(min_year,slide)].reset_index()
       ssl=st.selectbox("Select the region",options=['ALL','Constituency_Name','District_Name','Sub_Region'],index=0)
       if ssl=='Constituency_Name':
           ssl1=st.multiselect("Select your Constituency",options=dd__['Constituency_Name'].unique(),default=dd__['Constituency_Name'].unique()[0])
       elif ssl=='District_Name':
           ssl1=st.multiselect("Select your District",options=dd__['District_Name'].unique(),default=dd__['District_Name'].unique()[0])
       elif ssl=='Sub_Region':
           ssl1=st.multiselect("Select your Subregion",options=dd__['Sub_Region'].unique(),default=dd__['Sub_Region'].unique()[0])
    if ssl=='ALL':       
        data1=[]
        for sse in multi_select:
            dd3=dd__[dd__['Party']==sse]
            #st.write(dd3)
            group1=dd3.groupby(['Year'])['Votes'].sum().reset_index()
            dataa=go.Scatter(
            x=group1['Year'],
            y=group1['Votes'],
            mode="lines+markers",
            name=sse,
            text=group1['Votes'],
            )
            data1.append(dataa)
            #print(data1)
            lay=go.Layout(
            title=dict(text="Election Party's Total Votes Comparison",x=0.4,y=1),
            #height=400,
            #width=1000,
            )
        figg=go.Figure(data=data1,layout=lay)
        st.plotly_chart(figg,use_container_width=True)
        length=len(multi_select)
        for sse in multi_select:
            c1,c2=st.columns(2)
            dd3=dd[dd['Party']==sse].reset_index()
            #st.write(dd3)
            dd4=dd3[dd3['Year'].between(min_year,slide)]
            group1=dd4.groupby(['Year'])['Votes'].sum().reset_index()
            da=go.Pie(
                labels=group1['Year'],
                values=group1['Votes'],
                name=sse,
            )
            lay1=go.Layout(
            title=dict(text=f"{sse} Votes Yearwise",x=0.4,y=1),
            #height=400,
            #width=500,
            )
            dataa=go.Scatter(
            x=group1['Year'],
            y=group1['Votes'],
            mode="lines+markers",
            name=sse,
            text=group1['Votes'],
            )
            data1.append(dataa)
            print(data1)
            lay=go.Layout(
            title=dict(text=f"{sse} total vote",x=0.4,y=1),
            #height=400,
            #width=600,
            )
            figg1=go.Figure(data=da,layout=lay1)
            with c1:
               st.plotly_chart(figg1,use_container_width=True)
            figg2=go.Figure(data=dataa,layout=lay)
            with c2:
               st.plotly_chart(figg2,use_container_width=True)
    else:       
        data11=[]
        for sse in multi_select:
            dd3_=dd__[dd__['Party']==sse]
            #st.write(dd3_)
            for s__ in ssl1:
                #st.write(s__)
                dd4_=dd3_[dd3_[ssl]==s__]
                #st.write(dd4_)
                group1=dd4_.groupby(['Year'])['Votes'].sum().reset_index()
                #st.write(group1)
                dataa=go.Scatter(
                x=group1['Year'],
                y=group1['Votes'],
                mode="lines+markers",
                name=sse+" "+s__,
                text=group1['Votes'],
                )
                data11.append(dataa)
        layy=go.Layout(
        title=dict(text="Election Party's Total Votes Comparison",x=0.4,y=1),
        #height=400,
        #width=1000,
        )
                
                #print(data1)
        figgg=go.Figure(data=data11,layout=layy)
        st.plotly_chart(figgg,use_container_width=True)
        for sse in multi_select:
            dd3=dd__[dd__['Party']==sse]
            for s__ in ssl1:
            #st.write(dd3)
                dd4_=dd3[dd3[ssl]==s__]
                group1=dd4_.groupby(['Year'])['Votes'].sum().reset_index()
                c1,c2=st.columns(2)
                da=go.Pie(
                    labels=group1['Year'],
                    values=group1['Votes'],
                    name=sse,
                )
                lay1=go.Layout(
                title=dict(text=f"{sse} {s__} Votes Yearwise",x=0.4,y=1),
                #height=400,
                #width=500,
                )
                dataa=go.Scatter(
                x=group1['Year'],
                y=group1['Votes'],
                mode="lines+markers",
                name=sse,
                text=group1['Votes'],
                )
                lay=go.Layout(
                title=dict(text=f"{sse} {s__} total vote",x=0.4,y=1),
                )
                figg1=go.Figure(data=da,layout=lay1)
                with c1:
                    st.plotly_chart(figg1,use_container_width=True)
                figg2=go.Figure(data=dataa,layout=lay)
                with c2:
                    st.plotly_chart(figg2,use_container_width=True)
        
elif see=='GeoMap':
    
    import folium
    from streamlit_folium import folium_static
    import json
    
    with st.sidebar:
        k=st.selectbox("select",options=['TotalVote','Party'])
    with st.sidebar:
        sele=option_menu(
            menu_title="",
            options=['Consituency','District'],
            icons=['circle-half','circle-fill'],
        )  

    if k=='TotalVote' and sele=='Consituency':
        m = folium.Map(location=(11.12712250, 78.65689420), zoom_start=7, name="tamilnadu", attri="MY Tamilnadu")
        j = json.load(open("streamlit/Streamlit_programs/PROJECTS/TAMIL NADU_ASSEMBLY.geojson",'r'))

        with st.sidebar:
           select_option=st.selectbox("Select the options",options=['Valid_Votes','Electors','Turnout_Percentage'])
           selects = st.selectbox("Select the year", options=dd['Year'].unique())  
        dd4_4 = dd[['Constituency_No', 'Constituency_Name', 'Year', 'Party','Votes', select_option]]
        d5 = dd4_4.groupby(['Constituency_No', 'Constituency_Name', 'Year'])[select_option].unique().reset_index()
        d5[select_option]=d5[select_option].str[0]
        d6 = d5[d5['Year'] == selects]
        cno=d6['Constituency_No'].tolist()
        cvote=d6[select_option].tolist()
        dic={}
        for i,j1 in zip(cno,cvote):
            dic.update({i:j1})
        for jj in cno:
            for ii in range(0,234):
                if j['features'][ii]['properties']['AC_NO']==jj:
                    j['features'][ii]['properties'].update({select_option:dic[jj]})
        st.markdown(f"{select_option} of {selects} Year {sele}wise")
        folium.Choropleth(
        geo_data=j,
        name="kkkk",
        data=d6,
        columns=['Constituency_No',select_option],
        key_on="feature.properties.AC_NO",
        highlight=True,
        fill_color='Reds',
        fill_opacity=0.7,
        line_opacity=0.2,
        legend_name=select_option,
        ).add_to(m)
        folium.GeoJson(j, name="Tamilnadu",tooltip=folium.GeoJsonTooltip(fields=['AC_NAME',select_option])).add_to(m)
        folium_static(m, height=800, width=1200)
        #st.write(d6)
    elif k=='Party' and sele=='Consituency':
        m1 = folium.Map(location=(11.12712250, 78.65689420), zoom_start=7, name="tamilnadu", attri="MY Tamilnadu")
        j = json.load(open("streamlit/Streamlit_programs/PROJECTS/TAMIL NADU_ASSEMBLY.geojson",'r'))
        with st.sidebar:
           select_option1=st.selectbox("Select the options",options=['Votes','Vote_Share_Percentage','Margin','Margin_Percentage'])
           party_select=st.selectbox("Select the party",options=dd['Party'].unique())
           selects1 = st.selectbox("Select the year", options=dd['Year'].unique())   
        party_table=dd[dd['Party']==party_select]
        dd4_41 = party_table[['Constituency_No', 'Constituency_Name', 'Year', 'Party', select_option1]]
        d51=dd4_41.groupby(['Constituency_No', 'Constituency_Name', 'Year'])[select_option1].sum().reset_index()
        d51[select_option1] = d51[select_option1]
        d61 = d51[d51['Year'] == selects1]
        #st.write(d61)
        cno=d61['Constituency_No'].tolist()
        cvote=d61[select_option1].tolist()
        dic={}
        for i,j1 in zip(cno,cvote):
            dic.update({i:j1})
        for j1 in cno:
            for i1 in range(0,234):
                if j['features'][i1]['properties']['AC_NO']==j1:
                    j['features'][i1]['properties'].update({select_option1:dic[j1]})
        for i11 in range(0,234):
                if select_option1 not in j['features'][i11]['properties']:
                    j['features'][i11]['properties'].update({select_option1:0})
        #st.write(dic)
        #st.write(j['features'][180]['properties'])
        st.markdown(f"{party_select} {select_option1} of {selects1} Year {sele}wise")          
        folium.Choropleth(
        geo_data=j,
        name="choropleth",
        data=d61,
        columns=['Constituency_No',select_option1],
        key_on="feature.properties.AC_NO",
        highlight=True,
        fill_color='Reds',
        fill_opacity=0.7,
        line_opacity=0.2,
        legend_name=select_option1,
        ).add_to(m1)
        folium.GeoJson(j, name="Tamilnadu",tooltip=folium.GeoJsonTooltip(fields=['AC_NAME',select_option1])).add_to(m1)
        folium_static(m1, height=800, width=1200)
        #st.write(d6)
    
    elif k=='TotalVote' and sele=='District':
        m = folium.Map(location=((11.12712250, 78.65689420)), zoom_start=7, name="map", attri="My tamilnadu")
        json_data = json.load(open("streamlit/Streamlit_programs/PROJECTS/TAMIL NADU_DISTRICTS.geojson", 'r'))

        with st.sidebar:
            ss = st.selectbox("Select the options", options=['Valid_Votes', 'Electors', 'Turnout_Percentage'])
            ss1 = st.selectbox("Select the year", dd['Year'].unique())

        
        if ss=='Turnout_Percentage':
             #st.write('kkkkkk')
             b = dd[['Constituency_Name', 'District_Name', 'Year', ss]]
             b1 = b.groupby(['Constituency_Name', 'District_Name', 'Year'])[ss].unique().reset_index()
             b2 = b1.groupby(['District_Name', 'Year'])[ss].sum().reset_index()
             b2_year2 = b2[b2['Year'] == ss1]
             b2_year2[ss]=b2_year2[ss].str[0]
             bs=dd[['Constituency_Name', 'District_Name', 'Year']]
             bs1=bs[bs['Year']==ss1]
             bs2=bs1.groupby(['District_Name'])['Constituency_Name'].nunique().reset_index()
             #bs2=bs2.drop(columns=['District_Name'])
             #st.write(bs2)
             #st.write(b2_year2)
             b2_year=pd.merge(bs2,b2_year2,on='District_Name')
             b2_year['percentagefor100']=round(b2_year['Turnout_Percentage']/b2_year['Constituency_Name'],1)
             b2_year['District_Name'] = b2_year['District_Name'].apply(lambda x: str(x).title())
             b2_year=b2_year.drop(columns=['Turnout_Percentage'])
             b2_year.rename(columns={'percentagefor100':'Turnout_Percentage'},inplace=True)
             #st.write(b1)
             #st.write(b2)
             #st.write(b2_year)
        else:
            #st.write("aaaaa")
            b = dd[['Constituency_Name', 'District_Name', 'Year', ss]]
            b1 = b.groupby(['Constituency_Name', 'District_Name', 'Year'])[ss].unique().reset_index()
            b2 = b1.groupby(['District_Name', 'Year'])[ss].sum().reset_index()
            b2_year = b2[b2['Year'] == ss1]
            b2_year[ss]=b2_year[ss].str[0]
            b2_year['District_Name'] = b2_year['District_Name'].apply(lambda x: str(x).title())
        
        #st.write(b2_year)
        #st.write(b2_year)
        cno=b2_year['District_Name'].tolist()
        cvote=b2_year[ss].tolist()
        dic={}
        for i,j1 in zip(cno,cvote):
            dic.update({i:j1})
        for j1 in cno:
            for i1 in range(0,37):
                if json_data['features'][i1]['properties']['dtname']==j1:
                    json_data['features'][i1]['properties'].update({ss:dic[j1]})
        for i11 in range(0,37):
                if ss not in json_data['features'][i11]['properties']:
                    json_data['features'][i11]['properties'].update({ss:0})
        st.markdown(f"{ss} of {ss1} Year {sele}wise") 
        folium.Choropleth(
            geo_data=json_data,
            data=b2_year,
            columns=['District_Name', ss],
            key_on="feature.properties.dtname",
            highlight=True,
            fill_color='Reds',  # Specify the fill color directly
            fill_opacity=0.7,
            line_opacity=0.2,
            legend_name=ss,
            smooth_factor=0,
            line_color='black',
            line_weight=1,
        ).add_to(m)

        folium.GeoJson(json_data, name="Tamil nadu", tooltip=folium.GeoJsonTooltip(fields=['dtname',ss])).add_to(m)
        folium_static(m, height=800, width=1200)


    elif k=='Party' and sele=='District':
        m = folium.Map(location=(11.12712250, 78.65689420), zoom_start=7, name="tamilnadu", attri="MY Tamilnadu")
        j = json.load(open("streamlit/Streamlit_programs/PROJECTS/TAMIL NADU_DISTRICTS.geojson",'r'))
        with st.sidebar:
           select_option1=st.selectbox("Select the options",options=['Votes','Vote_Share_Percentage','Margin','Margin_Percentage'])
           party_select=st.selectbox("Select the party",options=dd['Party'].unique())
           selects1 = st.selectbox("Select the year", options=dd['Year'].unique())
        if select_option1== 'Vote_Share_Percentage':
            party_table=dd[dd['Party']==party_select]
            dd4_41 = party_table[['District_Name', 'Year', 'Party', select_option1]]
            d51=dd4_41.groupby(['District_Name', 'Year'])[select_option1].sum().reset_index()
            d55 = d51[d51['Year'] == selects1]
            bs=party_table[['Constituency_Name', 'District_Name', 'Year']]
            bs1=bs[bs['Year']==selects1]
            bs2=bs1.groupby(['District_Name'])['Constituency_Name'].nunique().reset_index()
            #bs2=bs2.drop(columns=['District_Name'])
            #st.write(bs2)
            #st.write(b2_year2)
            d61=pd.merge(bs2,d55,on='District_Name')
            d61['percentagefor100']=round(d61['Vote_Share_Percentage']/d61['Constituency_Name'],1)
            d61['District_Name'] = d61['District_Name'].apply(lambda x: str(x).title())
            d61=d61.drop(columns=['Vote_Share_Percentage'])
            d61.rename(columns={'percentagefor100':'Vote_Share_Percentage'},inplace=True)
            
            d61['District_Name'] = d61['District_Name'].apply(lambda x: str(x).title())
            
            #st.write(d61)
        elif select_option1=='Margin_Percentage':
            party_table=dd[dd['Party']==party_select]
            dd4_41 = party_table[['District_Name', 'Year', 'Party', select_option1]]
            d51=dd4_41.groupby(['District_Name', 'Year'])[select_option1].sum().reset_index()
            d55 = d51[d51['Year'] == selects1]
            bs=party_table[['Constituency_Name', 'District_Name', 'Year']]
            bs1=bs[bs['Year']==selects1]
            bs2=bs1.groupby(['District_Name'])['Constituency_Name'].nunique().reset_index()
            #bs2=bs2.drop(columns=['District_Name'])
            #st.write(bs2)
            #st.write(b2_year2)
            d61=pd.merge(bs2,d55,on='District_Name')
            d61['percentagefor100']=round(d61['Margin_Percentage']/d61['Constituency_Name'],1)
            d61['District_Name'] = d61['District_Name'].apply(lambda x: str(x).title())
            d61=d61.drop(columns=['Margin_Percentage'])
            d61.rename(columns={'percentagefor100':'Margin_Percentage'},inplace=True)
            
            d61['District_Name'] = d61['District_Name'].apply(lambda x: str(x).title())
            
            st.write(d61)
        else:
            party_table=dd[dd['Party']==party_select]
            dd4_41 = party_table[['District_Name', 'Year', 'Party', select_option1]]
            d51=dd4_41.groupby(['District_Name', 'Year'])[select_option1].sum().reset_index()
            d61 = d51[d51['Year'] == selects1]
            d61['District_Name'] = d61['District_Name'].apply(lambda x: str(x).title())
            #st.write(d61)

        cno=d61['District_Name'].tolist()
        cvote=d61[select_option1].tolist()
        dic={}
        for i,j1 in zip(cno,cvote):
            dic.update({i:j1})
        for j1 in cno:
            for i1 in range(0,37):
                if j['features'][i1]['properties']['dtname']==j1:
                    j['features'][i1]['properties'].update({select_option1:dic[j1]})
        for i11 in range(0,37):
                if select_option1 not in j['features'][i11]['properties']:
                    j['features'][i11]['properties'].update({select_option1:0})
        #st.write(dic)
        #st.write(j['features'][180]['properties'])
        st.markdown(f"{party_select} {select_option1} of {selects1} Year {sele}wise") 
        folium.Choropleth(
        geo_data=j,
        name="choropleth",
        data=d61,
        columns=['District_Name',select_option1],
        key_on="feature.properties.dtname",
        highlight=True,
        fill_color='Reds',
        fill_opacity=0.7,
        line_opacity=0.2,
        legend_name=select_option1,
        ).add_to(m)
        folium.GeoJson(j, name="Tamilnadu",tooltip=folium.GeoJsonTooltip(fields=['dtname',select_option1])).add_to(m)
        folium_static(m, height=800, width=1200)
    elif k=='TotalVote' and sele=='Region':
        st.write("toatl vote and region")

    elif k=='Party' and sele=='Region':
        st.write("party and Region")
    
    #st.write(d5)
   
    #d6['Constituency_Name']=d6['Constituency_Name'].str.title()
    #st.write(d6)
    #st.write(len(d6))
    #st.write(j['features'][0]['properties'])
    

elif see=='Histogram':
    
    with st.sidebar:
        s11=st.selectbox("Select the options",options=['Total','Party'])
        s_1=option_menu(
            menu_title='',
            options=['ALL','Constituency_Name','District_Name','Sub_Region'],
            icons=['snow2','stack','star-half','suit-club-fill'],
            default_index=1
        )
    col1,col2=st.columns([1,3])
    with col1:
        op=dd['Year'].unique().astype(str)
        op=list(op)
        op.insert(0,'ALL Year')
        s_=st.radio("Selct the Year",options=op)
        if s_=='ALL Year':
            dd1=dd
        else:
            dd1=dd[dd['Year']==int(s_)]
    #st.write(dd1)
    with col2:
        if s11=='Total':
            with st.sidebar:
                    s12=st.selectbox("Select the options",options=['Sex','Age','Constituency_Type','Deposit_Lost'])
            if s_1=='ALL':
                
                if s12=='Sex':
                    da1=len(dd1[dd1['Sex']=='MALE'])+len(dd1[dd1['Sex']=='M'])
                    da2=len(dd1[dd1['Sex']=='FEMALE'])+len(dd1[dd1['Sex']=='F'])
                    da3=len(dd1[dd1['Sex']=='O'])
                    da5=pd.DataFrame({'MALE':[da1],'FEMALE':[da2],'Others':[da3]})
                    #st.write(da5)
                    dataa=go.Bar(
                    x=da5.columns,
                    y=da5.loc[0],
                    name="Sex histogram",
                    text=da5.loc[0]

                    )
                    lay=go.Layout(
                        title=dict(text="Histogram for male and female",x=0.4,y=1)
                    )
                    dadad=go.Pie(
                    values=da5.loc[0],
                    labels=da5.columns,
                    )
                    layy=go.Layout(
                        title=dict(text="Pie chart for male and female",x=0.4,y=1)
                    )
                    fi=go.Figure(data=dataa,layout=lay)
                    st.plotly_chart(fi,use_container_width=True)
                    fii=go.Figure(data=dadad,layout=layy)
                    st.plotly_chart(fii,use_container_width=True)
                elif  s12=='Age':
                    da6=len(dd1[dd1['Age']<30])
                    da7=len(dd1[dd1['Age'].between(30,50)])
                    da8=len(dd1[dd1['Age'].between(50,70)])
                    da9=len(dd1[dd1['Age']>70])
                    da10=pd.DataFrame({'below30':[da6],'30-50':[da7],'50-70':[da8],'70above':[da9]})
                    dataa=go.Bar(
                    x=da10.columns,
                    y=da10.loc[0],
                    name="Age histogram",
                    text=da10.loc[0],
                    marker=dict(
                        color='plum',
                        line=dict(
                        color='orange',  
                        ),
                    ),
                    
                    )
                    lay=go.Layout(
                        title=dict(text="Histogram for Different AgeGroups",x=0.4,y=1)
                    )
                    dadad=go.Pie(
                    values=da10.loc[0],
                    labels=da10.columns,
                    )
                    layy=go.Layout(
                        title=dict(text="Pie chart for Different AgeGroups",x=0.4,y=1)
                    )
                    fi=go.Figure(data=dataa,layout=lay)
                    st.plotly_chart(fi,use_container_width=True)
                    fii=go.Figure(data=dadad,layout=layy)
                    st.plotly_chart(fii,use_container_width=True)
                elif s12=='Constituency_Type':
                    dataa=go.Histogram(
                    x=dd1[s12],
                    name=f"{s12} histogram",
                    text=[len(dd1[dd1[s12]=='GEN']),len(dd1[dd1[s12]=='SC']),len(dd1[dd1[s12]=='ST'])],
                    marker=dict(
                        color='plum',
                        line=dict(
                        color='orange',  
                        ),
                    ),
                    
                    )
                    lay=go.Layout(
                        title=dict(text=f"Histogram for {s12}",x=0.4,y=1)
                    )
                    dadad=go.Pie(
                    values=[len(dd1[dd1[s12]=='GEN']),len(dd1[dd1[s12]=='SC']),len(dd1[dd1[s12]=='ST'])],
                    labels=['GEN','SC','ST'],
                    )
                    layy=go.Layout(
                        title=dict(text=f"Pie chart for {s12}",x=0.4,y=1)
                    )
                    fi=go.Figure(data=dataa,layout=lay)
                    st.plotly_chart(fi,use_container_width=True)
                    fii=go.Figure(data=dadad,layout=layy)
                    st.plotly_chart(fii,use_container_width=True)
                else:
                    dataa=go.Histogram(
                    x=dd1[s12],
                    name=f"{s12} histogram",
                    text=[len(dd1[dd1[s12]=='no']),len(dd1[dd1[s12]=='yes'])],
                    marker=dict(
                        color='plum',
                        line=dict(
                        color='orange',  
                        ),
                    ),
                    
                    )
                    lay=go.Layout(
                        title=dict(text=f"Histogram for {s12}",x=0.4,y=1)
                    )
                    dadad=go.Pie(
                    values=[len(dd1[dd1[s12]=='no']),len(dd1[dd1[s12]=='yes'])],
                    labels=['no','yes'],
                    )
                    layy=go.Layout(
                        title=dict(text=f"Pie chart for {s12}",x=0.4,y=1)
                    )
                    fi=go.Figure(data=dataa,layout=lay)
                    st.plotly_chart(fi,use_container_width=True)
                    fii=go.Figure(data=dadad,layout=layy)
                    st.plotly_chart(fii,use_container_width=True)
            else:
                s_2=st.multiselect(f"Select the {s_1}",options=dd1[s_1].unique(),default=dd1[s_1].unique()[0:1])
                #st.write(s_2)
                if s12=='Sex':
                    da=[]
                    daa=[]
                    for i in s_2:
                        d_3=dd1[dd1[s_1]==i]
                        #st.write(d_3)
                        da1=len(d_3[d_3['Sex']=='MALE'])+len(d_3[d_3['Sex']=='M'])
                        da2=len(d_3[d_3['Sex']=='FEMALE'])+len(d_3[d_3['Sex']=='F'])
                        da3=len(d_3[d_3['Sex']=='O'])
                        da5=pd.DataFrame({'MALE':[da1],'FEMALE':[da2],'Others':[da3]})
                        #st.write(da5)
                        dataa=go.Bar(
                        x=da5.columns,
                        y=da5.loc[0],
                        name=i,
                        text=da5.loc[0]

                        )
                        lay=go.Layout(
                            title=dict(text="Histogram for male and female",x=0.4,y=1),
                            barmode='group',
                            height=600,
                        )
                        dadad=go.Pie(
                        values=da5.loc[0],
                        labels=da5.columns,
                        )      
                                    
                        da.append(dataa)
                        daa.append(dadad)
                    fi=go.Figure(data=da,layout=lay)
                    st.plotly_chart(fi,use_container_width=True)
                    #st.write(daaa)
                    for ll,ll1 in zip(daa,s_2):
                        #st.write(ll1)
                        layy=go.Layout(
                            title=dict(text=f"Pie chart for male and female({ll1})",x=0.4,y=1)
                        )    
                        fii=go.Figure(data=ll,layout=layy)
                        st.plotly_chart(fii,use_container_width=True)
                elif  s12=='Age':
                    da=[]
                    daa=[]
                    for i in s_2:
                        d_3=dd1[dd1[s_1]==i]
                        da6=len(d_3[d_3['Age']<30])
                        da7=len(d_3[d_3['Age'].between(30,50)])
                        da8=len(d_3[d_3['Age'].between(50,70)])
                        da9=len(d_3[d_3['Age']>70])
                        da10=pd.DataFrame({'below30':[da6],'30-50':[da7],'50-70':[da8],'70above':[da9]})
                        dataa=go.Bar(
                        x=da10.columns,
                        y=da10.loc[0],
                        name=i,
                        text=da10.loc[0],
                        marker=dict(
                            line=dict(
                            color='orange',  
                            ),
                        ),
                        
                        )
                        lay=go.Layout(
                            title="Histogram for Canditate ages"
                        )
                        dadad=go.Pie(
                        values=da10.loc[0],
                        labels=da10.columns,
                        )      
                                    
                        da.append(dataa)
                        daa.append(dadad)
                    fi=go.Figure(data=da,layout=lay)
                    st.plotly_chart(fi,use_container_width=True)
                    for ll,ll1 in zip(daa,s_2):
                        layy=go.Layout(
                            title=dict(text=f"Pie chart for Canditate ages({ll1})",x=0.4,y=1)
                        )    
                        fii=go.Figure(data=ll,layout=layy)
                        st.plotly_chart(fii,use_container_width=True)
                elif s12=='Constituency_Type':
                    da=[]
                    daa=[]
                    for i in s_2:
                        d_3=dd1[dd1[s_1]==i]
                        dataa=go.Histogram(
                        x=d_3[s12],
                        name=i,
                        text=[len(d_3[d_3[s12]=='GEN']),len(d_3[d_3[s12]=='SC']),len(d_3[d_3[s12]=='ST'])],
                        marker=dict(
                            line=dict(
                            color='orange',  
                            ),
                        ),
                        
                        )
                        lay=go.Layout(
                            title=dict(text=f"Histogram for {s12}",x=0.3,y=1)
                        )
                        dadad=go.Pie(
                        values=[len(d_3[d_3[s12]=='GEN']),len(d_3[d_3[s12]=='SC']),len(d_3[d_3[s12]=='ST'])],
                        labels=['GEN','SC','ST'],
                        )      
                        da.append(dataa)
                        daa.append(dadad)
                    fi=go.Figure(data=da,layout=lay)
                    st.plotly_chart(fi)
                    for ll,ll1 in zip(daa,s_2):
                        layy=go.Layout(
                            title=dict(text=f"Pie chart for {s12}({ll1})",x=0.4,y=1)
                        )    
                        fii=go.Figure(data=ll,layout=layy)
                        st.plotly_chart(fii,use_container_width=True)
                else:
                    da=[]
                    daa=[]
                    for i in s_2:
                        #st.write(i)
                        d_3=dd1[dd1[s_1]==i]
                        #st.write(d_3)
                        dataa=go.Histogram(
                        x=d_3[s12],
                        name=i,
                        text=[len(d_3[d_3[s12]=='no']),len(d_3[d_3[s12]=='yes'])],
                        marker=dict(
                            line=dict(
                            color='orange',  
                            ),
                        ),
                        
                        )
                        lay=go.Layout(
                            title=dict(text=f"Histogram for {s12}",x=0.4,y=1)
                        )
                        dadad=go.Pie(
                        values=[len(d_3[d_3[s12]=='no']),len(d_3[d_3[s12]=='yes'])],
                        labels=['no','yes'],
                        )     
                        da.append(dataa)
                        daa.append(dadad)
                    fi=go.Figure(data=da,layout=lay)
                    st.plotly_chart(fi,use_container_width=True)
                    for ll,ll1 in zip(daa,s_2):
                        layy=go.Layout(
                            title=dict(text=f"Pie chart for {s12}({ll1})",x=0.4,y=1)
                        )    
                        fii=go.Figure(data=ll,layout=layy)
                        st.plotly_chart(fii,use_container_width=True)    
        else:
            with st.sidebar:
                    s20=st.selectbox("Select the options",options=dd1[s11].unique())
                    s20_1=dd1[dd1[s11]==s20]
                    s21=st.selectbox("Select the options",options=['Sex','Age','Constituency_Type','Deposit_Lost'])
            if s_1=='ALL':
                
                if s21=='Sex':
                    da1=len(s20_1[s20_1['Sex']=='MALE'])+len(s20_1[s20_1['Sex']=='M'])
                    da2=len(s20_1[s20_1['Sex']=='FEMALE'])+len(s20_1[s20_1['Sex']=='F'])
                    da3=len(s20_1[s20_1['Sex']=='O'])
                    da5=pd.DataFrame({'MALE':[da1],'FEMALE':[da2],'Others':[da3]})
                    #st.write(da5)
                    dataa=go.Bar(
                    x=da5.columns,
                    y=da5.loc[0],
                    name="Sex histogram",
                    text=da5.loc[0]

                    )
                    lay=go.Layout(
                        title=dict(text="Histogram for male and female",x=0.4,y=1)
                    )
                    dadad=go.Pie(
                    values=da5.loc[0],
                    labels=da5.columns,
                    )
                    layy=go.Layout(
                        title=dict(text="Pie chart for male and female",x=0.4,y=1)
                    )
                    fi=go.Figure(data=dataa,layout=lay)
                    st.plotly_chart(fi,use_container_width=True)
                    fii=go.Figure(data=dadad,layout=layy)
                    st.plotly_chart(fii,use_container_width=True)
                elif  s21=='Age':
                    da6=len(s20_1[s20_1['Age']<30])
                    da7=len(s20_1[s20_1['Age'].between(30,50)])
                    da8=len(s20_1[s20_1['Age'].between(50,70)])
                    da9=len(s20_1[s20_1['Age']>70])
                    da10=pd.DataFrame({'below30':[da6],'30-50':[da7],'50-70':[da8],'70above':[da9]})
                    dataa=go.Bar(
                    x=da10.columns,
                    y=da10.loc[0],
                    name="Age histogram",
                    text=da10.loc[0],
                    marker=dict(
                        color='plum',
                        line=dict(
                        color='orange',  
                        ),
                    ),
                    
                    )
                    lay=go.Layout(
                        title=dict(text="Histogram for Candidate's AgeGroup",x=0.4,y=1)
                    )
                    dadad=go.Pie(
                    values=da10.loc[0],
                    labels=da10.columns,
                    )
                    layy=go.Layout(
                        title=dict(text="Pie chart for Candidate's AgeGroup",x=0.4,y=1)
                    )
                    fi=go.Figure(data=dataa,layout=lay)
                    st.plotly_chart(fi,use_container_width=True)
                    
                    fi=go.Figure(data=dataa,layout=lay)
                    st.plotly_chart(fi,use_container_width=True)
                    fii=go.Figure(data=dadad,layout=layy)
                    st.plotly_chart(fii,use_container_width=True)
                elif s21=='Constituency_Type':
                    dataa=go.Histogram(
                    x=s20_1[s21],
                    name=f"{s21} histogram",
                    text=[len(s20_1[s20_1[s21]=='GEN']),len(s20_1[s20_1[s21]=='SC']),len(s20_1[s20_1[s21]=='ST'])],
                    marker=dict(
                        color='plum',
                        line=dict(
                        color='orange',  
                        ),
                    ),
                    
                    )
                    lay=go.Layout(
                        title=dict(text=f"Histogram for {s21}",x=0.4,y=1)
                    )
                    dadad=go.Pie(
                    values=[len(s20_1[s20_1[s21]=='GEN']),len(s20_1[s20_1[s21]=='SC']),len(s20_1[s20_1[s21]=='ST'])],
                    labels=['GEN','SC','ST'],
                    )
                    layy=go.Layout(
                        title=dict(text=f"Pie chart for {s21}",x=0.4,y=1)
                    )
                    fi=go.Figure(data=dataa,layout=lay)
                    st.plotly_chart(fi,use_container_width=True)
                    fii=go.Figure(data=dadad,layout=layy)
                    st.plotly_chart(fii,use_container_width=True)
                else:
                    dataa=go.Histogram(
                    x=s20_1[s21],
                    name=f"{s21} histogram",
                    text=[len(s20_1[s20_1[s21]=='no']),len(s20_1[s20_1[s21]=='yes'])],
                    marker=dict(
                        color='plum',
                        line=dict(
                        color='orange',  
                        ),
                    ),
                    
                    )
                    lay=go.Layout(
                        title=dict(text=f"Histogram for {s21}",x=0.4,y=1)
                    )
                    dadad=go.Pie(
                    values=[len(s20_1[s20_1[s21]=='no']),len(s20_1[s20_1[s21]=='yes'])],
                    labels=['no','yes'],
                    )
                    layy=go.Layout(
                        title=dict(text=f"Pie chart for {s21}",x=0.4,y=1)
                    )
                    fi=go.Figure(data=dataa,layout=lay)
                    st.plotly_chart(fi,use_container_width=True) 
                    fii=go.Figure(data=dadad,layout=layy)
                    st.plotly_chart(fii,use_container_width=True)
            else:
                s_2=st.multiselect(f"Select the {s_1}",options=dd1[s_1].unique(),default=dd1[s_1].unique()[0:1])
                if s21=='Sex':
                    da=[]
                    daa=[]
                    for i in s_2:
                        d_3=s20_1[s20_1[s_1]==i]
                        da1=len(d_3[d_3['Sex']=='MALE'])+len(d_3[d_3['Sex']=='M'])
                        da2=len(d_3[d_3['Sex']=='FEMALE'])+len(d_3[d_3['Sex']=='F'])
                        da3=len(d_3[d_3['Sex']=='O'])
                        da5=pd.DataFrame({'MALE':[da1],'FEMALE':[da2],'Others':[da3]})
                        #st.write(da5)
                        dataa=go.Bar(
                        x=da5.columns,
                        y=da5.loc[0],
                        name=i,
                        text=da5.loc[0]

                        )
                        lay=go.Layout(
                            title=dict(text="Histogram for male and female",x=0.4,y=1),
                            barmode='group',
                            height=600,
                        )
                        dadad=go.Pie(
                        values=da5.loc[0],
                        labels=da5.columns,
                        )     
                        da.append(dataa)
                        daa.append(dadad)
                    fi=go.Figure(data=da,layout=lay)
                    st.plotly_chart(fi,use_container_width=True)
                    for ll,ll1 in zip(daa,s_2):
                        #st.write(ll1)
                        layy=go.Layout(
                            title=dict(text=f"Pie chart for male and female({ll1})",x=0.4,y=1)
                        )    
                        fii=go.Figure(data=ll,layout=layy)
                        st.plotly_chart(fii,use_container_width=True)
                elif  s21=='Age':
                    da=[]
                    daa=[]
                    for i in s_2:
                        d_3=s20_1[s20_1[s_1]==i]
                        da6=len(d_3[d_3['Age']<30])
                        da7=len(d_3[d_3['Age'].between(30,50)])
                        da8=len(d_3[d_3['Age'].between(50,70)])
                        da9=len(d_3[d_3['Age']>70])
                        da10=pd.DataFrame({'below30':[da6],'30-50':[da7],'50-70':[da8],'70above':[da9]})
                        dataa=go.Bar(
                        x=da10.columns,
                        y=da10.loc[0],
                        name=i,
                        text=da10.loc[0],
                        marker=dict(
                            line=dict(
                            color='orange',  
                            ),
                        ),
                        
                        )
                        lay=go.Layout(
                            title=dict(text="Histogram for Canditate ages",x=0.4,y=1)
                        )
                        dadad=go.Pie(
                        values=da10.loc[0],
                        labels=da10.columns,
                        )     
                        da.append(dataa)
                        daa.append(dadad)
                    fi=go.Figure(data=da,layout=lay)
                    st.plotly_chart(fi,use_container_width=True)
                    for ll,ll1 in zip(daa,s_2):
                        #st.write(ll1)
                        layy=go.Layout(
                            title=dict(text=f"Pie chart for male and female({ll1})",x=0.4,y=1)
                        )    
                        fii=go.Figure(data=ll,layout=layy)
                        st.plotly_chart(fii,use_container_width=True)
                elif s21=='Constituency_Type':
                    da=[]
                    daa=[]
                    for i in s_2:
                        d_3=s20_1[s20_1[s_1]==i]
                        dataa=go.Histogram(
                        x=d_3[s21],
                        name=i,
                        text=[len(d_3[d_3[s21]=='GEN']),len(d_3[d_3[s21]=='SC']),len(d_3[d_3[s21]=='ST'])],
                        marker=dict(
                            line=dict(
                            color='orange',  
                            ),
                        ),
                        
                        )
                        lay=go.Layout(
                            title=dict(text=f"Histogram for {s21}",x=0.4,y=1)
                        )
                        dadad=go.Pie(
                        values=[len(d_3[d_3[s21]=='GEN']),len(d_3[d_3[s21]=='SC']),len(d_3[d_3[s21]=='ST'])],
                        labels=['GEN','SC','ST'],
                        )      
                        da.append(dataa)
                        daa.append(dadad)
                    fi=go.Figure(data=da,layout=lay)
                    st.plotly_chart(fi,use_container_width=True)
                    for ll,ll1 in zip(daa,s_2):
                        layy=go.Layout(
                            title=dict(text=f"Pie chart for {s21}({ll1})",x=0.4,y=1)
                        )    
                        fii=go.Figure(data=ll,layout=layy)
                        st.plotly_chart(fii,use_container_width=True)
                else:
                    da=[]
                    daa=[]
                    for i in s_2:
                        d_3=s20_1[s20_1[s_1]==i]
                        dataa=go.Histogram(
                        x=d_3[s21],
                        name=i,
                        text=[len(d_3[d_3[s21]=='no']),len(d_3[d_3[s21]=='yes'])],
                        marker=dict(
                            line=dict(
                            color='orange',  
                            ),
                        ),
                        
                        )
                        lay=go.Layout(
                            title=dict(text=f"Histogram for {s21}",x=0.4,y=1)
                        )
                        dadad=go.Pie(
                        values=[len(d_3[d_3[s21]=='no']),len(d_3[d_3[s21]=='yes'])],
                        labels=['no','yes'],
                        )      
                        da.append(dataa)
                        daa.append(dadad)
                    fi=go.Figure(data=da,layout=lay)
                    st.plotly_chart(fi,use_container_width=True) 
                    for ll,ll1 in zip(daa,s_2):
                        layy=go.Layout(
                            title=dict(text=f"Pie chart for {s21}({ll1})",x=0.4,y=1)
                        )    
                        fii=go.Figure(data=ll,layout=layy)
                        st.plotly_chart(fii,use_container_width=True)           
elif see=='Predictions':
    ff=option_menu(
        menu_title="",
        options=["TotalWise","PartyWise","PartywiseGender","Partywiseposition"],
        orientation="horizontal",
    )
    
    with st.sidebar:
        fu=option_menu(
            menu_title="",
            options=['Future','Dataset']
        )
    
    if ff=='TotalWise' and fu=='Dataset':
        with st.sidebar:
            pred_date=st.selectbox("Select the Year",options=dd['Year'].unique(),index=0)
            dataset=dd[dd['Year']==pred_date]
            pred_cons=st.multiselect("Select the constiunency",options=np.sort(dataset['Constituency_Name'].unique())[::-1])
            #st.write(dataset['Constituency_Name'].unique().tolist().index(pred_cons))
        #here for vote prediction i prefer to use multiple linear regression algorithm and random forest regressor
        #dataset-random forest regressor
        #future-mulitiple Linear regression(why we are not using random forest regression means,it only give given year values not giving future year values)
        from sklearn.ensemble import RandomForestRegressor#for sklearn.ensemble installation-->pip install scikit-learn
        #converting dataset to each year constitueny_name and that valid votes
        daata = dataset.groupby(['Year', 'Constituency_Name']).agg({'Valid_Votes': set, 'Turnout_Percentage': set,'Electors':set}).reset_index()
        # Convert sets to lists
        #st.write(daata)
        daata['Valid_Votes'] = daata['Valid_Votes'].apply(list)
        daata['Turnout_Percentage'] = daata['Turnout_Percentage'].apply(list)
        daata['Electors'] = daata['Electors'].apply(list)
        daata['Valid_Votes'] = daata['Valid_Votes'].str[0]
        daata['Turnout_Percentage'] = daata['Turnout_Percentage'].str[0]
        daata['Electors'] = daata['Electors'].str[0]
        #daata=dataset[['Year','Constituency_Name','Valid_Votes']]
        #encoding the dataset
        #because Constituency_Name is string or categorical column
        df_encoded=pd.get_dummies(daata,'Constituency_Name')

        #after encoding seperating the independent and dependent variable as X,y
        X = df_encoded.drop(columns=['Valid_Votes','Turnout_Percentage','Electors'])
        y =df_encoded[['Valid_Votes','Turnout_Percentage','Electors']]
        #applying X and y values for random forest algorithm
        #rfr=RandomForestRegressor(n_estimators=10,random_state=4)#he algorithm going to create 393 decision trees as we given values 393
        rfr=RandomForestRegressor(n_estimators=5,random_state=5)
        rfr.fit(X,y)#fitting the value into the model
        #now our model ready to predict year and constituency wise valid votes
        #now we are going to get input(year,Constituency) from users to predict the valid votes
        #we unable to give directly our input values into model so we are encoding the entire constituency_names column.then we taking user selected constituency encoded data from encoded dataset
        encode_cons=pd.get_dummies(daata['Constituency_Name'].unique())
        dad=[]
        kkk=[]
        kkk1=[]
        if not pred_cons:
            st.warning("⚠️ Please select at least one constituency.")
        else:
            st.markdown(
            """
            <style>
            table{
            background-color: #333030;
            font-color:white;
            }
            </style>
            """,unsafe_allow_html=True)
            with st.container():
                for pp in pred_cons:
                    #getting only user given constituency encoded values
                    p_=encode_cons[pp].tolist()
                    #inserting user given date to encoded costituency value
                    p_.insert(0,pred_date)
                    #reshaping to 2dimention array
                    p_=np.array([p_]).reshape(1,-1)
                    #predecit the vaild_votes for user given values
                    pred_validvote=list(rfr.predict(p_))
                    dad.append(pred_validvote[0])
                    dataset1=dataset[dataset['Constituency_Name']==pp]
                    dataset2=dataset1.groupby('Constituency_Name').agg({'Valid_Votes': set, 'Turnout_Percentage': set,'Electors':set}).reset_index()
                    dataset2['Valid_Votes'] = dataset2['Valid_Votes'].apply(list)
                    dataset2['Turnout_Percentage'] = dataset2['Turnout_Percentage'].apply(list)
                    dataset2['Electors'] = dataset2['Electors'].apply(list)
                    dataset2['Valid_Votes'] = dataset2['Valid_Votes'].str[0]
                    dataset2['Turnout_Percentage'] = dataset2['Turnout_Percentage'].str[0]
                    dataset2['Electors'] = dataset2['Electors'].str[0]
                    #st.write(dataset2)
                    kkk1.extend([round(dataset2['Valid_Votes'][0].astype(float)),dataset2['Turnout_Percentage'][0].astype(float).round(1),round(dataset2['Electors'][0].astype(float))])
                    kkk.append(kkk1)
                    kkk1=[]
                #st.write(dad)
                #st.write(pred_cons)
                #st.write(kkk)
                dddd=pd.DataFrame(data=dad,columns=['Valid_Votes','Turnout_Percentage','Electors'],index=[pred_cons])
                st.markdown("<h2 style='text-align:center;background-color:#59E137;color:white;'>Predicted Valid Votes,Turnout_Percentage,Electors</h2><br>",unsafe_allow_html=True)
                al=rfr.score(X,y)*100
                st.markdown(f"""<p style='color:#46FF03;text-align:right'>Algorithm Accuracy:{al}</p>""",unsafe_allow_html=True)
                st.table(dddd)
                dddd1=pd.DataFrame(data=[kj for kj in kkk ],columns=['Valid_Votes','Turnout_Percentage','Electors'],index=[pred_cons])
                st.markdown("<h2 style='text-align:center;background-color:#59E137;color:white;'>Actual Valid Votes,Turnout_Percentage,Electors</h2><br>",unsafe_allow_html=True)
                st.table(dddd1)
    
    elif ff=="TotalWise" and fu=='Future':
        from sklearn.linear_model import LinearRegression
        from sklearn.model_selection import train_test_split
        daata = dd.groupby(['Year', 'Constituency_Name']).agg({'Valid_Votes': set, 'Turnout_Percentage': set,'Electors':set}).reset_index()
        # Convert sets to lists
        #st.write(daata)
        daata['Valid_Votes'] = daata['Valid_Votes'].apply(list)
        daata['Turnout_Percentage'] = daata['Turnout_Percentage'].apply(list)
        daata['Electors'] = daata['Electors'].apply(list)
        daata['Valid_Votes'] = daata['Valid_Votes'].str[0]
        daata['Turnout_Percentage'] = daata['Turnout_Percentage'].str[0]
        daata['Electors'] = daata['Electors'].str[0]
        #st.write(daata)
        df_encoded=pd.get_dummies(daata,'Constituency_Name')
        X = df_encoded.drop(columns=['Valid_Votes','Turnout_Percentage','Electors'])
        y =df_encoded[['Valid_Votes','Turnout_Percentage','Electors']]
        x_train,x_test,y_train,y_test=train_test_split(X,y,test_size=0.001,random_state=0)
        log1=LinearRegression()
        log1.fit(x_train,y_train)
        encode_cons=pd.get_dummies(daata['Constituency_Name'].unique())
        #st.write(encode_cons)
        with st.sidebar:
            pred_date=st.text_input("Enter the future predict year",value=2040)
            pred_date=int(pred_date)
            pred_cons=st.multiselect("Select the constiunency",options=dd['Constituency_Name'].unique(),default=['TIRUCHENDUR','THOOTHUKKUDI','TIRUNELVELI'])
        dadd=[]
        for ps in pred_cons:
                p_=encode_cons[ps].tolist()
                p_.insert(0,pred_date)
                p_=np.array([p_]).reshape(1,-1)
                #predecit the vaild_votes for user given values
                li=list(log1.predict(p_))
                dadd.append(li[0])
        dddd=pd.DataFrame(data=[f for f in dadd],columns=['Valid_Votes','Turnout_Percentage','Electors'],index=[pred_cons])
        st.markdown("<h2 style='text-align:center;background-color:#59E137;color:white;'>Prediction of future(ValidVotes,Turnout_Percentage,Electors)</h2><br>",unsafe_allow_html=True)
        al=log1.score(X,y)*100
        st.markdown(f"""<p style='color:#46FF03;text-align:right'>Algorithm Accuracy:{al}</p>""",unsafe_allow_html=True)
        st.markdown(
            """
            <style>
            table{
            background-color: #333030;
            font-color:white;
            }
            td{
            border: 2px solid white;
            font-color:white;
            }
            th{
            border: 2px solid white;
            background-color: #03C5FF;
            font-color:white;
            }
            </style>
            """,unsafe_allow_html=True
        )
        st.table(dddd)
        columns = st.columns(len(pred_cons))
        with st.container():
            for w,ps in enumerate(pred_cons):
                p_=encode_cons[ps].tolist()
                p_.insert(0,pred_date)
                p_=np.array([p_]).reshape(1,-1)
                #predecit the vaild_votes for user given values
                li=list(log1.predict(p_))
                dadd.append(li[0])
                ddss=daata[daata['Constituency_Name']==ps]
                #st.write(ddss)
                ddss1=ddss.groupby(['Year']).agg({'Valid_Votes':set,'Turnout_Percentage':set,'Electors':set}).reset_index()
                ddss1['Valid_Votes']=ddss1['Valid_Votes'].apply(list)
                ddss1['Turnout_Percentage']=ddss1['Turnout_Percentage'].apply(list)
                ddss1['Electors']=ddss1['Electors'].apply(list)
                ddss1['Valid_Votes']=ddss1['Valid_Votes'].str[0]
                ddss1['Turnout_Percentage']=ddss1['Turnout_Percentage'].str[0]
                ddss1['Electors']=ddss1['Electors'].str[0]
                with columns[w]:
                    st.markdown(f"<h6 style='text-align:center;background-color:#FA1313;padding-top:10px;border:2px solid white;'>Actual Vaildvote,Turnout_percentage,Electors of {ps} every year</h6>",unsafe_allow_html=True)        
                    st.table(ddss1)
            
    elif ff=="PartyWise" and fu=='Dataset':
        with st.sidebar:
            year_select=st.selectbox("Select the Year",options=dd['Year'].unique(),index=0)
            ds=dd[dd['Year']==year_select]
            ds1=ds.sort_values(by="Party",key=lambda x:x.map(ds['Party'].value_counts()),ascending=False)
            party_select=st.multiselect("Select the Party",options=ds1['Party'].unique())
            con_select=st.multiselect("Select the Constiuency",options=ds1['Constituency_Name'].unique())
        if not party_select and not con_select:
            st.warning("🚨 Please select atleast one Party and constituency name")
        else:
            from sklearn.ensemble import RandomForestClassifier
            co1,co2=st.columns(2)
            st.markdown("<h2 style='text-align:center;background-color:#59E137;color:white;'>Predicted valid Votes(Partywise)</h2><br>",unsafe_allow_html=True)
            for ps in party_select:
                for ps1 in con_select:     
                    x=dd.groupby(['Constituency_Name','Party','Year'])['Votes'].unique().reset_index()
                    x['Votes']=x['Votes'].str[0]
                    px=x[x['Party']==ps]
                    px.drop('Party',axis=1,inplace=True)
                    X=pd.get_dummies(px,columns=['Constituency_Name'])
                    xx=X.drop('Votes',axis=1)
                    yy=X['Votes']
                    rfr2=RandomForestClassifier(n_estimators=10,random_state=0)
                    rfr2.fit(xx,yy)
                    en_code=pd.get_dummies(px['Constituency_Name'].unique())
                    k2_ = en_code[ps1].tolist()
                    k2_.insert(0,year_select)
                    k3_=np.array(k2_).reshape(1,-1)
                    li=list(rfr2.predict(k3_)) 
                    st.markdown(f"<h6 style='text-align:center;background-color:#FA1313;padding-top:10px;border:2px solid white;'>{ps1} {ps}</h6>",unsafe_allow_html=True)        
                    #das=pd.DataFrame(data=[int(li[0])],columns=['Votes'],index=[year_select])
                    #das=das.rename_axis("Year")
                    #st.dataframe(das,use_container_width=True)
                    al=rfr2.score(xx,yy)*100
                    st.markdown(
                        f"""
                      <style>
                      table{{
                          width:100%;
                          text-align:center;
                          background-color: #333030; /* Set background color */
                          border: 2px solid white;
                          
                      }}
                      tr{{
                      border:2px solid white;
                      }}
                      
                      </style>
                      <table> 
                      <tr>
                      <th>Year</th>
                      <th>Votes</th>
                      </tr>
                      <tr>
                      <td>{year_select}</td>
                      <td>{li[0]}</td>
                      </tr>
                

                        """,unsafe_allow_html=True
                    )
                    st.markdown(f"""<p style='color:#46FF03;text-align:right'>Algorithm Accuracy:{al}</p>""",unsafe_allow_html=True)
                

    elif ff=="PartyWise" and fu=='Future':
        
        with st.sidebar:
            year_select=st.text_input("Enter the Year",value=2025)
            party_select=st.multiselect("Select the Party",options=dd['Party'].unique(),default=['ADMK',"NTK"])
            con_select=st.multiselect("Select the Constiuency",options=dd['Constituency_Name'].unique(),default=['TIRUCHENDUR','AVADI'])
        
            #st.write(year_select,party_select,con_select)
        st.markdown("<h2 style='text-align:center;background-color:#59E137;color:white;'>Predicted valid Votes for Future(Partywise)</h2><br>",unsafe_allow_html=True)
        from sklearn.model_selection import train_test_split
        from sklearn.linear_model import LinearRegression
        x=dd.groupby(['Constituency_Name','Party','Year'])['Votes'].unique().reset_index()
        x['Votes']=x['Votes'].str[0]
        #st.write(x)
        g=pd.get_dummies(x,columns=['Constituency_Name','Party'])
        x1=g.drop('Votes',axis=1)
        y1=g['Votes']
        #xx_train,xx_test,yy_train,yy_test=train_test_split(x1,y1,test_size=0.1,random_state=5)
        lii=LinearRegression()
        lii.fit(x1,y1)
        a1=lii.score(x1,y1)*100
        st.markdown(f"""<p style='color:#46FF03;text-align:right'>Algorithm Accuracy:{a1}</p>""",unsafe_allow_html=True)
        g1=pd.get_dummies(x['Constituency_Name'].unique())
        g2=pd.get_dummies(x['Party'].unique())
        for mm in party_select:
            for nn in con_select:
                dx1=g1[nn].tolist()
                dx2=g2[mm].tolist()
                dx3=dx1+dx2
                dx3.insert(0,int(year_select))
                #st.write(dx3)
                k3_=np.array(dx3).reshape(1,-1)
                li=list(lii.predict(k3_))
                st.markdown(f"<h6 style='text-align:center;background-color:#FA1313;padding-top:10px;border:2px solid white;'>{mm} {nn}</h6>",unsafe_allow_html=True)
                #st.write(type(k))
                st.markdown(
                        f"""
                      <style>
                      table{{
                          width:100%;
                          text-align:center;
                          background-color: #333030; /* Set background color */
                          border: 2px solid white;
                          
                      }}
                      tr{{
                      border:2px solid white;
                      }}
                      
                      </style>
                      <table> 
                      <tr>
                      <th>Year</th>
                      <th>Votes</th>
                      </tr>
                      <tr>
                      <td>{year_select}</td>
                      <td>{int(li[0])}</td>
                      </tr>

                        """,unsafe_allow_html=True
                    )
                st.markdown("<br>",unsafe_allow_html=True)
    elif ff=='PartywiseGender' and fu=='Dataset':
        with st.sidebar:
            en_year=st.selectbox("Enter the Year to Predict",options=dd['Year'].unique())
            fg=dd[dd['Year']==en_year]
            paa=st.selectbox("Select the Constituency",options=fg['Party'].unique())
            ddd=fg[fg['Party']==paa]
            coon=st.multiselect("Select the Constituency",options=ddd['Constituency_Name'].unique())
        if not coon:
            st.warning("⚠️ Please select atleast one Constituency Name!!!")
        else:
            #st.write(ddd)
            st.markdown("<h2 style='text-align:center;background-color:#59E137;color:white;'>Gender Prediction(Partywise)</h2><br>",unsafe_allow_html=True)
            from sklearn.ensemble import RandomForestClassifier
            from sklearn.model_selection import train_test_split
            ddd.fillna("M",inplace=True)
            dec={'M':0,'MALE':1,'F':2,'FEMALE':3,'O':4}
            ddd['Sex']=ddd['Sex'].replace(dec)
            #hg2=pd.get_dummies(hg['Sex'])
            #st.write(hg)
            ddd=ddd[['Year','Constituency_Name','Party','Sex']]
            hg1=pd.get_dummies(ddd,columns=['Constituency_Name','Party'])
            hhx=hg1.drop('Sex',axis=1)
            #xs_train,xs_test,ys_train,ys_test=train_test_split(hhx,hg['Sex'],test_size=0.001,random_state=45)
            lolo=RandomForestClassifier(n_estimators=20,random_state=45)
            lolo.fit(hhx,ddd['Sex'])
            a1=lolo.score(hhx,ddd['Sex'])
            st.markdown(f"""<p style='color:#46FF03;text-align:right'>Algorithm Accuracy:{a1}</p>""",unsafe_allow_html=True)
            encode_cons=pd.get_dummies(ddd['Constituency_Name'].unique())
            #st.write(encode_cons.shape)
            en_pa=pd.get_dummies(ddd['Party'].unique())
            #st.write(en_pa.shape)
            for c in coon:
                dx1=encode_cons[c].tolist()
                #st.write(dx1)
                dx2=en_pa[paa].tolist()
                dx3=dx1+dx2
                dx3.insert(0,int(en_year))
                #st.write(dx3)
                k3_=np.array(dx3).reshape(1,-1)
                li=lolo.predict(k3_)
                #st.markdown("""<br>""",unsafe_allow_html=True)
                st.markdown(f"<h6 style='text-align:center;background-color:#FA1313;padding-top:10px;border:2px solid white;'>{paa} {c} {str(en_year)}</h6>",unsafe_allow_html=True)
                #st.wrpaa,c,)
                k=li[0]
                if k==0 or k==1:
                    k1="Male"
                elif k==2 or k==3:
                    k1="Female"
                else:
                    k1="Others"
                st.markdown(f"""
                            <style>
                      table{{
                          width:100%;
                          text-align:center;
                          background-color: #333030; /* Set background color */
                          border: 2px solid white;
                          
                      }}
                      tr{{
                      border:2px solid white;
                      }}
                      
                      </style>
                <table>
                     <tr>
                     <th>Gender Prediction</th>       
                     <td>{k1}</td>       
                     </tr>        
                </table><br>
                """,unsafe_allow_html=True)        
                

        
    elif ff=='Partywiseposition' and fu=='Dataset':
        hg=dd[['Year','Constituency_Name','Party','Position']]
        with st.sidebar:
            see_year=st.selectbox("Select the Year",options=hg['Year'].unique())
            hgg=hg[hg['Year']==see_year]
            party_multi=st.selectbox("Select the Party",options=hgg['Party'].unique())
        from sklearn.tree import DecisionTreeClassifier
        from sklearn.model_selection import train_test_split
        hgg2=hgg[hgg['Party']==party_multi]
        hg1=pd.get_dummies(hgg2,columns=['Constituency_Name','Party'])
        hgx=hg1.drop('Position',axis=1)
        hgy=hg1['Position']
        xxx_train,xxx_test,yyy_train,yyy_test=train_test_split(hgx,hgy,test_size=0.01,random_state=98)
        rfr3=DecisionTreeClassifier(criterion='gini')
        rfr3.fit(hgx,hgy)
        #st.write(rfr3.score(hgx,hgy)*100)
        enn=pd.get_dummies(hgg2['Constituency_Name'].unique())
        enn1=pd.get_dummies(hgg2['Party'].unique())
        enn1_filter=enn1.loc[(enn1 !=0).any(axis=1)]
        with st.sidebar:
            cons_multi=st.multiselect("Select the constituency",options=hgg2['Constituency_Name'].unique())
        if not cons_multi:
            st.warning("⚠️ Please select atleast one Constituency Name!!!")
        else:
            st.markdown("<h2 style='text-align:center;background-color:#59E137;color:white;'>Position Prediction For Future(Partywise)</h2><br>",unsafe_allow_html=True)
            for co in cons_multi:
                st.markdown(f"<h6 style='text-align:center;background-color:#FA1313;padding-top:10px;border:2px solid white;'>{party_multi} {co} {see_year}</h6>",unsafe_allow_html=True)
                ll=enn[co].tolist()
                ll1=enn1_filter[party_multi].tolist()
                ll2=ll+ll1
                ll2.insert(0,see_year)
                ll3=np.array(ll2).reshape(1,-1)
                prdict=list(rfr3.predict(ll3))
                st.markdown(f"""
                            <style>
                      table{{
                          width:100%;
                          text-align:center;
                          background-color: #333030; /* Set background color */
                          border: 2px solid white;
                          
                      }}
                      tr{{
                      border:2px solid white;
                      }}
                      
                      </style>
                <table>
                     <tr>
                     <th>Position Prediction</th>       
                     <td>{prdict[0]}</td>       
                     </tr>        
                </table><br>
                """,unsafe_allow_html=True) 
    elif ff=='PartywiseGender' and fu=='Future':
        ddd=dd[['Year','Constituency_Name','Party','Sex']]
        with st.sidebar:
            us_year=st.text_input("Enter the Year",value=2050)
            us_party=st.selectbox("Select the party",options=ddd['Party'].unique())
            ddd1=ddd[ddd['Party']==us_party]
            us_con=st.multiselect("Select the Constituency",options=ddd1['Constituency_Name'].unique())
        if not us_con:
           st.warning("⚠️ Please select atleast one Constituency Name!!!")
        else:
            st.markdown("<h2 style='text-align:center;background-color:#59E137;color:white;'>Gender Prediction For Future(Partywise)</h2><br>",unsafe_allow_html=True)
            from sklearn.ensemble import RandomForestClassifier
            from sklearn.model_selection import train_test_split
            dec={'M':0,'MALE':1,'F':2,'FEMALE':3,'O':4}
            ddd1['Sex']=ddd1['Sex'].replace(dec)
            ddd1['Sex']=ddd1['Sex'].fillna(round(ddd1['Sex'].mean()))
            #st.write(ddd1)
            hg1=pd.get_dummies(ddd1,columns=['Constituency_Name','Party'])
            hhx=hg1.drop('Sex',axis=1)
            #xc_train,xc_text,yc_train,yc_test=train_test_split(hhx,ddd['Sex'],test_size=0.01,random_state=89)
            lolo1=RandomForestClassifier(n_estimators=10,random_state=76)
            lolo1.fit(hhx,ddd1['Sex'])
            a1=lolo1.score(hhx,ddd1['Sex'])*100
            st.markdown(f"""<p style='color:#46FF03;text-align:right'>Algorithm Accuracy:{a1}</p>""",unsafe_allow_html=True)
            enn=pd.get_dummies(ddd1['Constituency_Name'].unique())
            enn1=pd.get_dummies(ddd1['Party'].unique())
            enn1_filter=enn1.loc[(enn1 !=0).any(axis=1)]
            for us in us_con:
                dx1=enn[us].tolist()
                #st.write(dx1)
                dx2=enn1_filter[us_party].tolist()
                dx3=dx1+dx2
                dx3.insert(0,int(us_year))
                #st.write(dx3)
                k3_=np.array(dx3).reshape(1,-1)
                li=lolo1.predict(k3_)
                #st.write(us,us_party,str(us_year))
                st.markdown(f"<h6 style='text-align:center;background-color:#FA1313;padding-top:10px;border:2px solid white;'>{us} {us_party} {str(us_year)}</h6>",unsafe_allow_html=True)
                k=li[0]
                if k==0 or k==1:
                    k1="Male"
                elif k==2 or k==3:
                    k1="Female"
                else:
                    k1="Others" 
                st.markdown(f"""
                            <style>
                      table{{
                          width:100%;
                          text-align:center;
                          background-color: #333030; /* Set background color */
                          border: 2px solid white;
                          
                      }}
                      tr{{
                      border:2px solid white;
                      }}
                      
                      </style>
                <table>
                     <tr>
                     <th>Gender Prediction</th>       
                     <td>{k1}</td>       
                     </tr>        
                </table><br>
                """,unsafe_allow_html=True)  

    elif ff=='Partywiseposition' and fu=='Future':
        ddd=dd[['Year','Constituency_Name','Party','Position']]
        with st.sidebar:
            us_year=st.text_input("Enter the Year",value=2050)
            us_party=st.selectbox("Select the party",options=ddd['Party'].unique())
            ddd1=ddd[ddd['Party']==us_party]
            us_con=st.multiselect("Select the Constituency",options=ddd1['Constituency_Name'].unique())
        if not us_con:
           st.warning("⚠️ Please select atleast one Constituency Name!!!")
        else:
            st.markdown("<h2 style='text-align:center;background-color:#59E137;color:white;'>Gender Prediction For Future(Partywise)</h2><br>",unsafe_allow_html=True)
            from sklearn.ensemble import RandomForestClassifier
            from sklearn.model_selection import train_test_split
            #st.write(ddd1)
            hg1=pd.get_dummies(ddd1,columns=['Constituency_Name','Party'])
            hhx=hg1.drop('Position',axis=1)
            #xc_train,xc_text,yc_train,yc_test=train_test_split(hhx,ddd['Sex'],test_size=0.01,random_state=89)
            lolo1=RandomForestClassifier(n_estimators=10,random_state=76)
            lolo1.fit(hhx,ddd1['Position'])
            a1=lolo1.score(hhx,ddd1['Position'])*100
            st.markdown(f"""<p style='color:#46FF03;text-align:right'>Algorithm Accuracy:{a1}</p>""",unsafe_allow_html=True)
            enn=pd.get_dummies(ddd1['Constituency_Name'].unique())
            enn1=pd.get_dummies(ddd1['Party'].unique())
            enn1_filter=enn1.loc[(enn1 !=0).any(axis=1)]
            for us in us_con:
                dx1=enn[us].tolist()
                #st.write(dx1)
                dx2=enn1_filter[us_party].tolist()
                dx3=dx1+dx2
                dx3.insert(0,int(us_year))
                #st.write(dx3)
                k3_=np.array(dx3).reshape(1,-1)
                li=list(lolo1.predict(k3_))
                #st.write(us,us_party,str(us_year))
                st.markdown(f"<h6 style='text-align:center;background-color:#FA1313;padding-top:10px;border:2px solid white;'>{us} {us_party} {str(us_year)}</h6>",unsafe_allow_html=True)
                st.markdown(f"""
                                <style>
                        table{{
                            width:100%;
                            text-align:center;
                            background-color: #333030; /* Set background color */
                            border: 2px solid white;
                            
                        }}
                        tr{{
                        border:2px solid white;
                        }}
                        
                        </style>
                    <table>
                        <tr>
                        <th>Position Prediction</th>       
                        <td>{li[0]}</td>       
                        </tr>        
                    </table><br>
                    """,unsafe_allow_html=True) 
else:
    with st.sidebar:
        sa=option_menu(
            menu_title="",
            options=['Project Overview','Winners','History','ContactUs/Sourcecode'],
            icons=['ticket-detailed-fill','trophy-fill','clock-history','person-lines-fill']
            
        )
    if sa=="History":
        st.markdown("<h1 style='text-align:center;background-color:#59E137;'> Tamil Nadu Legislative Assembly election</h1>",unsafe_allow_html=True)
        st.markdown("<br>",unsafe_allow_html=True)
        #st.image("streamlit//Streamlit_programs//PROJECTS//tamilnadu_logo.jpg",use_column_width=True)
        st.markdown(
            """
            <style>
            .custom-height {
                background-color:#333030;
                font-size:15px;
                width:100%;
            }
            .kkk{
            background-color:#333030;
            }
            .kkk p{
            font-size:19px;

            }
            h2{
            text-align:center;
            background-color:#59E137;
            }
            .custom-height img{
              width:100%;
            }
            </style>
            <div class="custom-height">
            <img src='https://raw.githubusercontent.com/Karthik6622/PYTHON/main/streamlit/Streamlit_programs/PROJECTS/tamilnadu_logo.jpg' height=500></img>
            <h2>Overview</h2>
            <p>
                The state of Tamil Nadu is divided into 234 assembly constituencies, each of which elects a member (called an MLA) to represent it at the state's unicameral legislative assembly, as per Article 168 of the Constitution of India. The Tamil Nadu Legislative Assembly convenes at Fort St. George, Chennai. The member that manages to receive the support of the majority of the members of the assembly (that is the Chief Ministerial candidate of the party that secures more than 50% of the seats), which is a minimum of 118 members, is appointed as the Chief Minister of Tamil Nadu, who is the executive head of the Government of Tamil Nadu. The Governor of Tamil Nadu, the state's ceremonial head, will invite the Chief-Minister-elect and his Council of Ministers to be sworn in, to lead the state government for a term of the next five years.
                The Chief Election Commissioner of India, Sunil Arora, holding a press conference in New Delhi on February 26, 2021, to announce the schedule for Legislative Assembly election of Tamil Nadu along with those of Assam, Kerala, West Bengal, and Puducherry.[4]
                Tamil Nadu's partisan politics have been dominated by its two regional Dravidian parties, Dravida Munnetra Kazhagam (DMK) and All India Anna Dravida Munnetra Kazhagam (AIADMK), for the last 50 years (since 1967). Each recognized party in India is given a polling symbol by the Election Commission of India, an independent and neutral body of officers that conducts and regulates all the elections in the country. The DMK contests with the Rising Sun symbol, while the AIADMK contests with the Two Leaves.
                The legislative assembly of Tamil Nadu goes to polls alongside the legislative assemblies of three other Indian states, namely Assam, Kerala, and West Bengal, and that of the union territory of Puducherry.
            </p>
            </div>
            """,unsafe_allow_html=True
        )
            
        st.markdown("""""",unsafe_allow_html=True)
        st.markdown(
            """
            
            """,
            unsafe_allow_html=True)
        st.markdown("""<h2>Elections in Tamil Nadu</h2>""",unsafe_allow_html=True)
        st.markdown(
            """
            <div class="kkk">
            <p>Tamil Nadu has a parliamentary system as defined by its constitution, with power distributed between the state government and the districts.

            The Governor of Tamil Nadu is the ceremonial head of the state. However, it is the Chief Minister of Tamil Nadu who is the leader of the party or political alliance having a majority in the state elections to the Tamil Nadu Legislative Assembly. The chief minister is the leader of the executive branch of the government of Tamil Nadu. The chief minister is the chief adviser to the governor of Tamil Nadu and the head of the state council of ministers.

            Elections in Tamil Nadu are conducted every five years to elect members to the Tamil Nadu Legislative Assembly and members of parliament to the Lok Sabha. There are 234 assembly constituencies and 39 Lok Sabha constituencies. The state has conducted 16 assembly elections and 17 Lok Sabha elections since independence.</p>
            </div>
            """,unsafe_allow_html=True)
        st.markdown("""<h2>Elections</h2>""",unsafe_allow_html=True)
        st.markdown(
            """
            <div class="kkk">
            <p>
            The Tamil Nadu State Election Commission is the federal body of Tamil Nadu that is enacted under the provisions of the Constitution and is responsible for monitoring and administering all the electoral processes in Tamil Nadu. This body is responsible for ensuring elections are free and fair, without any bias.

            Elections ensure the conduct of members pre-elections, during elections, and post-elections is as per statutory legislation.

            All election-related disputes are handled by the Election Commission. The Madras High Court has held that where the enacted laws are silent or make insufficient provisions to deal with a given situation in the conduct of elections, the Election Commission has the residuary powers under the Constitution to act as appropriate.
            </p></div>
            """,unsafe_allow_html=True)
        st.markdown("""<h2>Types of elections</h2>""",unsafe_allow_html=True)
        st.markdown(
            """
            <div class="kkk">
            <p>
            Elections in Tamil Nadu include elections for:<br>

            Members of Parliament in the Rajya Sabha (Upper House)<br>
            Members of Parliament in the Lok Sabha (Lower House)<br>
            Members of the Tamil Nadu Legislative Assembly<br>
            Members of local governance bodies (municipal bodies and panchayats)<br>
            A by-election is held when the seat-holder of a particular constituency dies, resigns, or is disqualified.
            </p></div>
            """,unsafe_allow_html=True)
        st.markdown("""<h2>Rajya Sabha elections</h2>""",unsafe_allow_html=True)
        st.markdown(
            """
            <div class="kkk">
            <p>
            Members of parliament in the Rajya Sabha (Council of States) from Tamil Nadu are not directly elected by being voted upon by all adult citizens of the state but by the members of the Tamil Nadu Legislative Assembly. Candidates who win the Rajya Sabha elections are called "Members of Parliament" and hold their seats for six years. The house meets in the Rajya Sabha Chamber of the Sansad Bhavan in New Delhi on matters relating to the creation of new laws or removing or improving the existing laws that affect all citizens of India. Elections take place to elect 18 members from Tamil Nadu.
            </p></div>
            """,unsafe_allow_html=True)
        st.markdown("""<h2>Lok Sabha elections</h2>""",unsafe_allow_html=True)
        st.markdown(
            """
            <div class="kkk">
            <p>
            Members of parliament in the Lok Sabha (House of the People) from Tamil Nadu are directly elected by being voted upon by all adult citizens of the state from a set of candidates who stand in their respective constituencies. Every adult citizen of Tamil Nadu can vote only in their constituency. Candidates who win the Lok Sabha elections are called "Members of Parliament" and hold their seats for five years or until the body is dissolved by the president of India on the advice of the council of ministers. The house meets in the Lok Sabha Chamber of the Sansad Bhavan in New Delhi on matters relating to the creation of new laws or removing or improving the existing laws that affect all citizens of India. Elections take place once every five years to elect 39 members from Tamil Nadu.
            </p></div>
            """,unsafe_allow_html=True)
        st.markdown("""<h2>Legislative Assembly elections</h2>""",unsafe_allow_html=True)
        st.markdown(
            """
            <div class="kkk">
            <p>
            Members of the Tamil Nadu Legislative Assembly are directly elected by being voted upon by all adult citizens of the state from a set of candidates who stand in their respective constituencies. Every adult citizen of Tamil Nadu can vote only in their constituency. Candidates who win the legislative assembly elections are called "Members of the Legislative Assembly" and hold their seats for five years or until the body is dissolved by the governor of Tamil Nadu on the advice of the council of ministers. The house meets in the Assembly Chamber of the Chief Secretariat in Chennai on matters relating to the creation of new laws or removing or improving the existing laws that affect all citizens of Tamil Nadu. Elections take place once every five years to elect 234 members to the legislative assembly. The leader of the majority party or alliance takes oath as chief minister of Tamil Nadu.
            </p></div>
            """,unsafe_allow_html=True)
        st.markdown("""<h2>By-election</h2>""",unsafe_allow_html=True)
        st.markdown(
            """
            <div class="kkk">
            <p>
            When an elected candidate to either the Rajya Sabha, Lok Sabha, or Tamil Nadu Legislative Assembly leaves the office vacant before their term ends, a by-election is conducted to find a suitable replacement to fill the vacant position. It is often referred to as by-polls.

            Common reasons for by-elections:

            Resignation of the sitting M.P. or an M.L.A.
            Death of the sitting M.P. or an M.L.A.
            But other reasons occur when the incumbent is disqualified for being ineligible to continue in office (criminal conviction, failure to maintain a minimum level of attendance in the office due to election irregularities found later, or when a candidate wins more than one seat and has to vacate one).
            </p></div>
            """,unsafe_allow_html=True)
    elif sa=='Winners':
        multi=st.multiselect("Select the Year",options=dd['Year'].unique(),default=[2021,2011])
        for m in multi:
            #getting the total votes,total electors,and total turnout percentage
            wd5=dd[dd['Year']==m]
            wd6=wd5.groupby(['Constituency_Name']).agg({'Valid_Votes':'unique','Electors':'unique','Turnout_Percentage':'unique'}).reset_index()
            wd6['Valid_Votes']=wd6['Valid_Votes'].str[0]
            wd6['Electors']=wd6['Electors'].str[0]
            wd6['Turnout_Percentage']=wd6['Turnout_Percentage'].str[0]
            total_valid_votes=wd6['Valid_Votes'].sum()
            total_electors=wd6['Electors'].sum()
            Avg_turnout_percentage=wd6['Turnout_Percentage'].sum()/len(wd6['Turnout_Percentage'])
            #st.write(total_valid_votes,total_electors,Avg_turnout_percentage)
            c1,c2,c3=st.columns(3)
            with c1:
                data=go.Indicator(
                    mode="number",
                    value=total_valid_votes,
                    title=f"Total Valid Votes Of {m}"
                )
                la=go.Layout(
                    height=150,
                    margin=dict(l=10,r=10,b=10,t=40),
                    paper_bgcolor="#0D0404",
                )
                fi=go.Figure(data=[data],layout=la)
                st.plotly_chart(fi,use_container_width=True)
            with c2:
                data=go.Indicator(
                    mode="number",
                    value=total_electors,
                    title=f"Total Electors Of {m}"
                )
                la=go.Layout(
                    height=150,
                    margin=dict(l=10,r=10,b=10,t=40),
                    paper_bgcolor="#0D0404",
                )
                fi=go.Figure(data=[data],layout=la)
                st.plotly_chart(fi,use_container_width=True)
            with c3:
                data=go.Indicator(
                    mode="number",
                    value=Avg_turnout_percentage,
                    title=f"Total Turnoutvote Percentage Of {m}"
                )
                la=go.Layout(
                    height=150,
                    margin=dict(l=10,r=10,b=10,t=40),
                    paper_bgcolor="#0D0404",
                )
                fi=go.Figure(data=[data],layout=la)
                st.plotly_chart(fi,use_container_width=True)
            #getting the 1 st postion paries
            wd=dd.groupby(['Year','Constituency_Name','Position'])['Party'].unique().reset_index()
            wd1=wd[wd['Year']==m]
            wd1['Party']=wd1['Party'].str[0]
            wd2=wd1.groupby(['Party'])['Position'].value_counts().reset_index()
            wd3=wd2[wd2['Position']==1]
            wd4=wd3.sort_values('count',ascending=False)
            coo1,coo2=st.columns(2)
            with coo1:
               trace=go.Table(
                header=dict(values=wd4['Party']),
                cells=dict(values=wd4['count']),
               )
               layout=go.Layout(
                title=F"ASSEMBLY ELECTION {m} Winning Seats",
               )
               fig=go.Figure(data=[trace],layout=layout)
               st.plotly_chart(fig,use_container_width=True)
               #st.markdown("---")
            with coo2:
               count=wd4['count'].sum()
               trace=go.Pie(
                labels=wd4['Party'],
                values=wd4['count'],
                hole=0.5,
                textinfo="value+percent"
               )
               layout=go.Layout(
                title=f"ASSEMBLY ELECTION {m} Winning Seats",
                annotations=[
                {
                "font": {"size": 25},
                "text": f"{count}",
                "showarrow":False,
                "x": 0.5,
                "y": 0.5,
               }
               ]
               )
               fig=go.Figure(data=[trace],layout=layout)
               st.plotly_chart(fig,use_container_width=True)
            st.markdown("---")
    elif sa=='ContactUs/Sourcecode':
        c1,c2=st.columns([4,4])
        with c1:
            st.markdown("<h2>Created BY</h2>",unsafe_allow_html=True)
            st.markdown("<br>",unsafe_allow_html=True)      
        with c2:
            st.markdown("<h3>Karthik R</h3>",unsafe_allow_html=True)
            st.markdown("<h4>(DataScientist & ML Engineer)</h4>",unsafe_allow_html=True)
            # Create a Gmail contact link
            gmail_address="karthikmca6622@gmail.com"
            gmail_link = f"mailto:{gmail_address}"
            st.markdown(f"[karthikmca6622@gmail.com]({gmail_link})")
            phone_number="9944194787"
            phone_link = f"tel:{phone_number}"
            st.markdown(f"[9944194787]({phone_link})")
        st.markdown("---")
        c11,c22=st.columns([4,4])
        with c11:
            st.markdown("<h2>Download The Dataset</h2>",unsafe_allow_html=True)
            st.markdown("<br>",unsafe_allow_html=True)
            st.markdown("<br>",unsafe_allow_html=True)
        with c22:
            file_select=st.selectbox("Please select the format to download the Dataset",options=['CSV','EXCEL','HTML','TEXT','PDF'])
            if file_select=='CSV':
                da=dd.to_csv(index=False)
                # Encode CSV string as bytes
                csv_byte=da.encode("utf-8")
                st.download_button("Download CSV",data=csv_byte,file_name="TN_ASSEMBLY_Election_data.csv")
            elif file_select=='EXCEL':
                da=dd.to_excel('details2.xlsx')
                file_path='details2.xlsx'
                st.download_button("Download Excel Format",data=file_path,file_name="TN_ASSEMBLY_Election_data.xlsx")
            elif file_select=='HTML':
                da=dd.to_html(index=False)
                st.download_button("Download HTML Format",data=da,file_name="TN_ASSEMBLY_Election_data.html")
            elif file_select=='TEXT':
                da=dd.to_csv(index=False)
                st.download_button("Download text Format",data=da,file_name="TN_ASSEMBLY_Election_data.txt")
        st.markdown("---")
        c1,c2=st.columns([4,4])
        with c1:
            st.markdown("<h2>Source Code Of Projects</h2>",unsafe_allow_html=True)
        with c2:
            st.markdown("[https://github.com/Karthik6622/PYTHON/blob/main/streamlit/Streamlit_programs/PROJECTS/Tamilnadu_assembly.py](https://github.com/Karthik6622/PYTHON/blob/main/streamlit/Streamlit_programs/PROJECTS/Tamilnadu_assembly.py)",unsafe_allow_html=True)
        st.markdown("---")
        c,c0=st.columns([4,4])
        with c:
            st.markdown("<h2>Source files Of Projects(Dataset,Json)</h2>",unsafe_allow_html=True)
        with c0:
            st.markdown("[https://github.com/Karthik6622/PYTHON/tree/main/streamlit/Streamlit_programs/PROJECTS](https://github.com/Karthik6622/PYTHON/tree/main/streamlit/Streamlit_programs/PROJECTS)",unsafe_allow_html=True)
        st.markdown("---")
    elif sa=="Project Overview":
    
        st.markdown("<h1 style='text-align:center;background-color:#59E137;'>Project Overview: Tamil Nadu Assembly Election EDA & Prediction</h1>",unsafe_allow_html=True)
        st.markdown("<br>",unsafe_allow_html=True)
        st.markdown(
            """
            <style>
            .intro{
            border:5px solid white;
            font-size:30px;
            background-color: #333030;
            color:white;
            text-align:center;
            }
            </style>
            <div class="intro">
            <h3><u>Introduction</u></h3>
            <p>
            The "Tamil Nadu Assembly Election EDA & Prediction" project aims to analyze historical data related to Tamil Nadu assembly elections and build predictive models for upcoming elections. Through this project, we seek to gain insights into voting patterns, understand the impact of various factors on election outcomes, and ultimately predict the results of future elections.
            </p>
            </div>
            """,unsafe_allow_html=True
        )
        st.markdown(
            """
            <style>
            .intro{
            border:5px solid white;
            font-size:30px;
            background-color: #333030;
            color:white;
            text-align:center;
            margin-top:5px;
             }
            </style>
            <div class="intro">
            <h2><u>Objectives</u></h2>
            <h3>Exploratory Data Analysis (EDA):</h3>
            <p>
            Conduct a thorough analysis of historical data, exploring trends, patterns, and relationships among different variables related to Tamil Nadu assembly elections.
            </p>
            <h3>Feature Engineering:</h3>
            <p>Identify key features that significantly influence election outcomes and create relevant variables for predictive modeling.</p>
            <h3>Predictive Modeling:</h3>
            <p> Develop machine learning models to predict election results based on historical data. Evaluate and fine-tune models for accuracy and reliability.</p>
            <h3>Visualization: </h3>
            <p>Create interactive visualizations to present key findings, trends, and predictions to stakeholders and the general public.</p>
            <h3>Stakeholder Engagement:</h3>
            <p>Engage with stakeholders, political analysts, and the public to discuss and validate the insights derived from the analysis and predictions.</p>
            </div>
            """,unsafe_allow_html=True
        )
        st.markdown(
            """
            <style>
            .intro{
            border:5px solid white;
            font-size:30px;
            background-color: #333030;
            color:white;
            text-align:center;
            margin-top:5px;
             }
            </style>
            <div class="intro">
            <h2><u>Methodology</u></h2>
            <h3>Data Collection:</h3>
            <p>
            Gather comprehensive data sets on Tamil Nadu assembly elections, including information on constituencies, candidates, voter demographics, and election results.
            </p>
            <h3>Data Cleaning and Preprocessing: </h3>
            <p>
            Cleanse the data, handle missing values, and preprocess it for analysis. Ensure data quality and consistency.
            </p>
            <h3>Exploratory Data Analysis:</h3>
            <p>
              Perform in-depth exploratory data analysis to uncover patterns, correlations, and trends within the data. Use statistical and visual analysis techniques.
            </p>
            <h3>Feature Engineering:</h3>
            <p>
            Identify and create relevant features that contribute to the predictive power of the models.
            </p>
            <h3>Machine Learning Models:</h3>
            <p>
            Employ machine learning algorithms, such as Random Forest, Logistic Regression, or others, to predict election outcomes based on historical data.
            </p>
            <h3>Evaluation and Fine-Tuning: </h3>
            <p>
             Evaluate model performance, fine-tune parameters, and validate predictions using historical election results.
            </p>
            </div>
            """,unsafe_allow_html=True
        )
        st.markdown(
            """
            <style>
            .intro{
            border:5px solid white;
            font-size:30px;
            background-color: #333030;
            color:white;
            text-align:center;
            margin-top:5px;
             }
            </style>
            <div class="intro">
            <h2><u>Deliverables</u></h2>
            <h3>Interactive Data Visualizations:</h3>
            <p>
            Share interactive visualizations showcasing key insights and trends derived from the EDA.
            </p>
            <h3>Predictive Models:</h3>
            <p>
            Provide well-documented machine learning models for predicting election outcomes.
            </p>
            <h3>Stakeholder Reports: </h3>
            <p>
             Generate reports summarizing the findings, insights, and predictions, suitable for stakeholders and the general public. 
            </p>
            <h3>Public Engagement:</h3>
            <p>
            Conduct presentations and engage with the public through online platforms to share insights and predictions, fostering a data-driven understanding of elections.
            </p>
            </div>
            """,unsafe_allow_html=True
        )
        st.markdown(
            """
            <style>
            .intro{
            border:5px solid white;
            font-size:30px;
            background-color: #333030;
            color:white;
            text-align:center;
            margin-top:5px;
             }
            </style>
            <div class="intro">
            <h2><u>Timeline</u></h2>
            <h3>The project will be conducted over [insert duration], with key milestones and deliverables scheduled as follows:</h3>
            <p>
            Data Collection and Cleaning: [Start Date - End Date]<br>
            Exploratory Data Analysis: [Start Date - End Date]<br>
            Feature Engineering: [Start Date - End Date]<br>
            Predictive Modeling: [Start Date - End Date]<br>
            Visualization and Reporting: [Start Date - End Date]
            </p>
            </div>
            """,unsafe_allow_html=True
        )
        st.markdown(
            """
            <style>
            .intro{
            border:5px solid white;
            font-size:30px;
            background-color: #333030;
            color:white;
            text-align:center;
            margin-top:5px;
             }
            </style>
            <div class="intro">
            <h2><u>Conclusion</u></h2>
            <h3></h3>
            <p>
            The "Tamil Nadu Assembly Election EDA & Prediction" project aims to provide valuable insights into the dynamics of Tamil Nadu assembly elections. Through a combination of exploratory data analysis, predictive modeling, and stakeholder engagement, we aim to contribute to a better understanding of electoral processes and outcomes.
            </p>
            </div>
            """,unsafe_allow_html=True
        )
st.markdown(
    """
    <script>
        window.onload = function() {
            window.scrollTo(0, 0);
        }
    </script>
    """,
    unsafe_allow_html=True
)
