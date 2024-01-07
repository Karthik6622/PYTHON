import streamlit as st
import folium
import pandas as pd
from streamlit_folium import folium_static

st.set_page_config(layout='wide')#st.set_page_config(layout='wide') is used to configure the layout of the Streamlit app to be wide
#retreiving json file from the below path 
#json file has all state coortinates and statename,state_code
json=f"E:\streamlit\Streamlit_programs\states_india.geojson"
indias_covid_data=pd.read_csv('covid_cases_india.csv')
#st.write(indias_covid_data)
#creating base map
#tiles="CartoDB position": This sets the base map style to "CartoDB position." CartoDB is a platform for creating and sharing maps, and it provides various map styles. The "position" style typically refers to a light-colored and minimalist map.
m=folium.Map(location=(23.47,77.94),tiles="CartoDB position",name="Light",zoom_start=5,attr="My Data Attribution")#location=(23.47,77.94)-center of the map(madya pradeshr)
#zoom_start=while map opening how much zoom it should display
li=indias_covid_data.columns
st.write(li)
select=st.selectbox("SELECT",options=[li[2],li[3],li[4],li[5]])
#here we creating Choropleth map adding that to base map
folium.Choropleth(
    geo_data=json,  # GeoJSON data containing the geometries of the regions (e.g., states)
    name="choropleth",  # Name of the choropleth layer
    data=indias_covid_data,  # DataFrame containing the data to be visualized on the map
    columns=["state_code", select],  # Columns specifying the key and value for mapping data to regions
    key_on="feature.properties.state_code",  # JSON path to the key in the GeoJSON data
    fill_opacity=0.9,  # Opacity of the filled polygons representing regions (ranges from 0 to 1)
    line_opacity=0.1,  # Opacity of the borders of the polygons (ranges from 0 to 1)
    # Additional parameters can be added here as needed
).add_to(m)
#legend_name=select,
#Folium to create a GeoJson layer on a map. 
folium.GeoJson(json,name='States',popup=folium.GeoJsonPopup(fields=["st_nm"])).add_to(m)
#The folium_static function is part of the streamlit_folium library, which is an extension for Streamlit to embed Folium maps. It is used to display a Folium map created within a Streamlit app
folium_static(m,width=1200,height=800)

