#!/usr/bin/env python
# coding: utf-8

# In[24]:


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
# from selenium.webdriver.common.by import By
# from selenium.webdriver.chrome.service import Service
# from selenium.webdriver.support.select import Select


# In[2]:


baseURL='https://dol.ny.gov/'


# ## CIVILIAN LABOR DATA: 
# ###### LABOR FORCE, EMPLOYED, EMP by POP percent

# In[3]:


originUrl='https://dol.ny.gov/labor-statistics-new-york-city-region'
laborURL='statistics-new-york-city-labor-force-data'
# download excel file from the link in url
r= requests.get(baseURL+laborURL, allow_redirects=True)
open('raw_data/jobs_data.xlsx', 'wb').write(r.content)

# read the file
rate_df=pd.read_excel('raw_data/jobs_data.xlsx', skiprows=2)

# remove columns with no dates
rate_df=rate_df.dropna(subset=['YEAR']).reset_index(drop=True)
rate_df=rate_df[['YEAR', 'Labor Force', 'Employment', 'Emp/Pop', 'Unemp Rate']].replace(",", regex=True)
rate_df[['Labor Force', 'Employment', 'Emp/Pop', 'Unemp Rate']]=rate_df[[
    'Labor Force', 'Employment', 'Emp/Pop', 'Unemp Rate']].apply(pd.to_numeric)

# pandemic_period=df[df.YEAR > '2000-01-01'].reset_index(drop=True)
rate_df['month']=pd.to_datetime(rate_df['YEAR']).dt.strftime("%Y-%m")
rate_df[['month', "Labor Force"]].to_json('data/labor.json', orient='records')
rate_df[['month', "Employment"]].to_json('data/employment.json', orient='records')
rate_df[['month', 'Emp/Pop']].to_json('data/empPop.json', orient='records')


# ## Unemployment rate

# In[4]:


#script to scrape new unemployment rate for us and merge it with old data and nyc data
national_unemp_url = "https://data.bls.gov/timeseries/LNS14000000"

response=requests.get(national_unemp_url)
doc=BeautifulSoup(response.text, 'html.parser')
table=doc.find_all('table', {"id":"table0"})

ele_list=[]

for ele in table:
    for ele1 in ele.find_all('tr'):  
        for ele2 in ele1.find_all('td'):
            ele_dict={}
            ele_dict['year']=ele1.find('th').text.strip()
            ele_dict['us_rate']=ele2.text.strip()
            ele_list.append(ele_dict)            
us_df=pd.DataFrame(ele_list)

us_df=us_df[~(us_df.us_rate =="")]
us_df['us_rate']=us_df['us_rate'].astype(float)
years=['2023','2022', '2021']
us_df=us_df[us_df.year.isin(years)].reset_index(drop=True)
us_df['month']=pd.Series(pd.period_range("1/1/2021", freq="M", periods=len(us_df))).astype(str)

us_df=us_df[['month', 'us_rate']]

# read nyc_rate and old data files
nyc_rate =rate_df[['month', 'Unemp Rate']]
final_us=pd.read_csv('raw_data/old_us_rate.csv')

us_rate=pd.concat([us_df,final_us]).reset_index(drop=True).drop_duplicates()
merged_rate=pd.merge(us_rate, nyc_rate)

merged_rate['datetime']= pd.to_datetime(merged_rate.month)

merged_rate=merged_rate.sort_values('datetime', ascending=False)[['month','us_rate','Unemp Rate'
                                                                 ]].reset_index(drop=True)
merged_rate.to_json('data/rate.json', orient='records')


# ## Job Recovery

# In[5]:


# direct download for NYC, no filtering needed
jobsURL='statistics-total-nyc-nonfarm-jobs-seasonally-adjusted'

r= requests.get(baseURL+jobsURL, allow_redirects=True)
open('raw_data/raw_employment_data.xlsx', 'wb').write(r.content)
# read the file
jobs_df=pd.read_excel('raw_data/raw_employment_data.xlsx', skiprows=9)
# # file out nan columns

jobs_df=jobs_df[['YEAR', 'JAN', 'FEB', 'MAR', 'APR','MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']]

# create column names here
column_names=['year', "01","02","03","04","05","06","07","08","09","10","11","12"]
# insert new columns names into the original dataset
jobs_df.columns=column_names
#filter data
pandemic_years=[2020, 2021, 2022, 2023]
jobs_df=jobs_df[jobs_df.year.isin(pandemic_years)].reset_index(drop=True)
# flatten the data to. make it graphics ready
jobs_df=jobs_df.melt(id_vars=['year'])
# create a datetime column for viz purposes
jobs_df['date']=pd.to_datetime(jobs_df.year.astype(str)+"-"+jobs_df.variable)
jobs_df['month']=jobs_df.year.astype(str)+"-"+jobs_df.variable
# replace  commas from the value column so that we can convert it into a string later
jobs_df=jobs_df.replace(",", "", regex=True)
# rename value column
jobs_df=jobs_df[['date','month','value' ]].rename(columns={'value':'jobs'})
# flter to get all entries after Jan 2020
jobs_df=jobs_df[jobs_df.date > "2020-01-31"].reset_index(drop=True)
# remove empty columns
jobs_df['jobs']=jobs_df.jobs.replace(" ", np.nan).astype(float)
# drop na values
jobs_df=jobs_df[jobs_df.jobs.notna()].reset_index(drop=True)
# multiple by 1000 to create original value
jobs_df['jobs']=(jobs_df.jobs*1000).astype(int)
# sort columbs by datetime
jobs_df=jobs_df.sort_values('date').reset_index(drop=True)
#create a job loss column from baseline: Feb 2020

feb2020record=jobs_df.jobs[0]
jobs_df['jobloss_from_feb2020']=(jobs_df['jobs']-feb2020record).astype(int)
jobs_df['jobs_added']=jobs_df.jobs.diff().fillna(0)
#create two separate datasets
jobs_added=jobs_df[['month','jobs_added']]
job_recovery=jobs_df[['month','jobs','jobloss_from_feb2020']]
#save files
jobs_added.to_json('data/jobs_added.json', orient='records')
job_recovery.to_json('data/job_recovery.json', orient='records')


# ## Earnings

# In[6]:


# direct download for NYC, no filtering needed
earningsURL='statistics-state-and-area-employment-hours-and-earnings'

r= requests.get(baseURL+earningsURL, allow_redirects=True)
open('raw_data/earnings.xlsx', 'wb').write(r.content)
# read the file

earnings=pd.read_excel('raw_data/earnings.xlsx', sheet_name='average weekly earnings', skiprows=12)
tp_earnings=earnings.set_index('Year').T[[
    2007,2008,2009,2010,2011,2012,2013,2014,2015,2016,2017,2018,2019,2020, 2021,2022, 2023]]

earnings=tp_earnings.T.reset_index().drop(columns='Annual')

column_names=['year', "01","02","03","04","05","06","07","08","09","10","11","12"]
earnings.columns=column_names

earning=earnings.replace(",", "", regex=True)
earning=earnings.replace("$", "", regex=True)

earnings=earnings.melt(id_vars=['year']).dropna(subset=['value'])
earnings=earnings.rename(columns={'value':'weekly_earnings'})
earnings=earnings.sort_values(['year','variable']).reset_index(drop=True)

earnings=earnings[earnings.year > 2010].reset_index(drop=True)
earnings['month']=earnings.year.astype(str)+"-"+earnings.variable.astype(str)
earnings['pct_chng_earnings']=(earnings.groupby('variable').weekly_earnings.pct_change()*100).round(1)

earnings=earnings[earnings.pct_chng_earnings.notna()].reset_index(drop=True)

earnings=earnings[['month', 'weekly_earnings', 'pct_chng_earnings']]


# #### inflation

# In[7]:


inflationURL="https://data.bls.gov/timeseries/CUURS12ASA0?output_view=pct_12mths&include_graphs=False"

response=requests.get(inflationURL)
doc=BeautifulSoup(response.text, 'html.parser')
table=doc.find_all('table', {"id":"table0"})

tableList=[]
columnList=[]
for tr in table[0].find_all('tr'):
    for col in tr.find_all('th', {'scope':'col'}):
        columnDict={}
        columnDict['category']= col.text.strip()    
        columnList.append(columnDict)       
    for row in tr.find_all('th', {'scope':'row'}): 
        for td in tr.find_all('td'):
            tableDict={}
            tableDict['year']=row.text.strip()
            tableDict['value']=td.text.strip()
            tableList.append(tableDict)
table_df=pd.DataFrame(tableList)
column_df=pd.DataFrame(columnList)

pivoted=table_df.pivot(columns='year',values='value',index=None)

dfList=[pivoted[[f'{column}']].dropna().reset_index(drop=True).T for column in pivoted.columns]
inflation=pd.concat(dfList).reset_index()

inflation=inflation.iloc[:, :13]
column_names=['year', "01","02","03","04","05","06","07","08","09","10","11","12"]
inflation.columns=column_names
inflation=inflation.melt(id_vars='year').rename(columns={'value':'yoy_chng_inf'})

inflation=inflation[
    inflation.yoy_chng_inf !=""].reset_index(drop=True).sort_values(['year','variable']).reset_index(drop=True)
inflation['month']=inflation.year.astype(str)+"-"+inflation.variable.astype(str)
inflation=inflation[['month', 'yoy_chng_inf']]

real_earnings=pd.merge(earnings, inflation)
real_earnings.to_json('data/earnings.json', orient='records')


# ## INDUSTRY

# In[30]:


# 'Management, Scientific, and Technical Consulting Services'
# https://www1.nyc.gov/assets/omb/downloads/csv/nycemploy-sa03-22.csv

# significant_ind = [
#    'Construction of Buildings','Couriers and messengers','Transportation and Warehousing',
#     'Information', 'Financial Activities','Professional, Scientific, and Technical Services',
#     'Administrative and Support Services','Educational Services','Ambulatory Health Care Services',
#     'Social Assistance','Food Services and Drinking Places']
    
ombURL = 'https://www1.nyc.gov/assets/omb/js/pages/reports.js'
response=requests.get(ombURL)
doc=BeautifulSoup(response.text, 'html.parser')

df=pd.DataFrame(doc)
trans=df[0].str.split("]", expand=True).T
trans=trans[trans[0].str.contains("Employment Data")].reset_index(drop=True)
trans[['indicator', 'release_date','no.', "name", "URL" ]]=trans[0].str.split(",", expand=True)
trans=trans[["name",'release_date',  "URL" ]]
trans=trans.replace('"', "", regex=True)
trans['release_date']=trans.release_date.replace({"4/21/203":'4/21/2023'})
trans['release_date']=pd.to_datetime(trans.release_date)
trans=trans[~trans.name.str.contains("NSA")]
sorted_trans=trans.sort_values('release_date', ascending=False)

# download excel file from the link in url
url=sorted_trans.URL[0]
baseURL='https://www1.nyc.gov'
r= requests.get(baseURL+url, allow_redirects=True)

open('raw_data/industry_data.csv', 'wb').write(r.content)
# read the file
ind_df=pd.read_csv('raw_data/industry_data.csv', skiprows=3)
ind_df=ind_df[1:].reset_index(drop=True)


new_df=(ind_df.set_index('Industry:').apply(pd.to_numeric)*1000).reset_index()
new_df[['year', 'month']]=new_df['Industry:'].str.split('M', expand=True)
filtered_df=new_df[new_df.year.astype(int) >= 2019].reset_index(drop=True)
filtered_df['month']=filtered_df.year.astype(str)+"-"+filtered_df.month.astype(str)

filtered_df=filtered_df[['month', 'Total Nonfarm', 'Total Private', 'Financial Activities','Finance and Insurance',
     'Securities', 'Banking', 'Real Estate','Information', 'Professional and Business Services',
     'Professional, Scientific, and Technical Services','Management of Companies and Enterprises', 
     'Administrative Services','Employment Services', 'Education and Health Services','Educational Services',
    'Health Care and Social Assistance','Leisure and Hospitality', 'Arts, Entertainment, and Recreation',
    ' Accommodation and Food Services', 'Other Services','Trade, Transportation, and Utilities', 'Retail Trade',
    'Wholesale Trade', 'Transportation and Warehousing', 'Utilities','Construction', ' Manufacturing', ' Government']]

filtered_df['datetime']=pd.to_datetime(filtered_df.month)
filtered_df=filtered_df.sort_values('datetime', ascending=False).reset_index(drop=True)

latest_month=pd.to_datetime(filtered_df.month).dt.strftime("%m")[0]

filtered_df=filtered_df.drop(columns='datetime')

transposed=filtered_df.set_index('month').T.reset_index().rename(columns={"index":'sector'})

transposed['sector']=transposed.sector.str.strip()

column_names=transposed.columns[
    transposed.columns.str.contains(f'sector|2019-{latest_month}|2023-{latest_month}')].to_list()

transposed=transposed[column_names]

transposed['chngFromPrepandemic']=(
    (transposed.iloc[:, 1]-transposed.iloc[:, -1]).div(transposed.iloc[:, -1])*100).round(1)

sectors=['Finance and Insurance', 'Real Estate','Information', 'Professional, Scientific, and Technical Services',
         'Management of Companies and Enterprises', 'Administrative Services', 'Employment Services',
         'Educational Services','Health Care and Social Assistance', 'Arts, Entertainment, and Recreation',
         'Accommodation and Food Services', 'Retail Trade','Wholesale Trade', 'Transportation and Warehousing',
         'Utilities','Construction', 'Manufacturing', 'Government']

cleaned_df=transposed[transposed.sector.isin(sectors)].reset_index(drop=True)

cleaned_df['month']=cleaned_df.columns[1]

cleaned_df=cleaned_df.sort_values("chngFromPrepandemic", ascending=False).reset_index(drop=True)

cleaned_df.to_json('data/industry.json', orient='records')


# In[ ]:




