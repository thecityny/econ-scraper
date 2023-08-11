#!/usr/bin/env python
# coding: utf-8

# In[1]:


import requests
import warnings
import pandas as pd
# Ignore all warnings
warnings.filterwarnings("ignore")

import numpy as np
from urllib.request import urlopen, Request
from urllib.parse import urlencode
# from selenium import webdriver
from bs4 import BeautifulSoup


# In[3]:


## Subway ridership

# try: 
#     !wget -O raw_data/subway.csv "https://data.ny.gov/api/views/vxuj-8kew/rows.csv?accessType=DOWNLOAD&sorting=true"
# except:
#     pass
#     print("No subway file")

riders_df=pd.read_json("https://data.ny.gov/api/id/vxuj-8kew.json?$query=select%20*%2C%20%3Aid%20limit%2010000")

riders_df=riders_df[['date', 'subways_total_estimated_ridership', 'subways_of_comparable_pre_pandemic_day']]


riders_df.columns=['date', 'riders', 'riders_recovered']

riders_df['date']=pd.to_datetime(riders_df.date)

riders_df=riders_df.sort_values("date")
riders_df=riders_df.drop_duplicates(subset=['date']).reset_index(drop=True)

riders_df['avg_recovery']=(riders_df.riders_recovered.rolling(window=7).mean()*100).round()
riders_df['date']=pd.to_datetime(riders_df.date).dt.strftime("%Y-%m-%d")
riders_df=riders_df[6:].reset_index(drop=True)

riders_df=riders_df.dropna(subset=['riders'])
riders_df.to_json('data/subway_riders.json', orient='records')


# OFFICE OCCUPANCY
sheet_id = "1JLlcLJ_dKBct7zK804L-p7P_7SYlIRegBHSfIKs8ek0"
sheet_name = "office_occupancy"
officeURL = f'https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={sheet_name}'

oc=pd.read_csv(officeURL) 
oc=oc.replace("%", "", regex=True)
oc=oc.melt(id_vars='week_ending').rename(columns={'variable':'metro', 'value':'occupancy'})
oc.to_json('data/occupancy.json', orient='records')


## HOTEL OCCUPANCY
sheet_name = "hotel_occupancy"
hotelURL = f'https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={sheet_name}'

hotel=pd.read_csv(hotelURL) 
demand=hotel[['period', 'demand2020', 'demand2021', 'demand2022', 'demand2023]]
change=hotel[['period', 'change2020', 'change2021', 'change2022', 'change2023']]

demand.columns=demand.columns.str.replace('demand',"")
change.columns=demand.columns.str.replace('change',"")

melted_demand=demand.melt(id_vars='period').dropna().rename(
    columns={'value':'demand', 'variable':'year'}).reset_index(drop=True)
melted_change=change.melt(id_vars='period').dropna().rename(
    columns={'value':'pct_chng', 'variable':'year'}).reset_index(drop=True)
merged_hotel=pd.merge(melted_demand, melted_change, on=['period', 'year'])

merged_hotel['month']=pd.to_datetime(merged_hotel.period+"-"+merged_hotel.year).dt.strftime("%Y-%m")
final_hotel=merged_hotel[['month', 'demand', 'pct_chng']].reset_index(drop=True)

final_hotel.to_json('data/hotel_demand.json', orient='records')


# In[ ]:




