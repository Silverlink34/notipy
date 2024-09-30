import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import schedule
import time
from win10toast import ToastNotifier
from pyrate_limiter import Duration, Rate, Limiter, InMemoryBucket, BucketFullException,SQLiteBucket,RedisBucket
import sqlite3
from dotenv import load_dotenv
from os import getenv, path
from redis import ConnectionPool
from redis import Redis
import json
import pdb
from datetime import datetime
import hashlib

#function to setup a new sqlite3 bucket to persist used up rates in between executions of program.
def create_or_get_sqlite_bucket(bucketName, rates, filePath):
    connection = sqlite3.connect(filePath, isolation_level="EXCLUSIVE", check_same_thread=False)
    bucket = SQLiteBucket(rates, connection, bucketName)
    return bucket

#function to use redis bucket - im using this until dev fixes sqlite bucket.
def create_or_get_redis_bucket(bucketName, rates):
    load_dotenv()
    redis_server_host = getenv("REDIS_HOST")
    redis_server_port = getenv("REDIS_PORT")
    pool = ConnectionPool.from_url("redis://"+redis_server_host+":"+redis_server_port)
    #redis_db = Redis(connection_pool=pool)
    redis_db = Redis(host=redis_server_host, port=redis_server_port, decode_responses=True)
    bucket = RedisBucket.init(rates, redis_db, bucketName)
    return bucket

#functions write data to redis
def post_dict_data_to_regis(dataName, data):
    load_dotenv()
    redis_server_host = getenv("REDIS_HOST")
    redis_server_port = getenv("REDIS_PORT")
    redis_db = Redis(host=redis_server_host, port=redis_server_port, decode_responses=True)
    data_string = json.dumps(data)
    redis_db.set(dataName, data_string)

def post_weatherdata_dates_individually_to_redis_as_ts(input_dicts_list, city):
    load_dotenv()
    redis_ts_server_host = getenv("REDIS_TS_HOST")
    redis_ts_server_port = getenv("REDIS_TS_PORT")
    redis_server_host = getenv("REDIS_HOST")
    redis_server_port = getenv("REDIS_PORT")
    redis_dbts = Redis(host=redis_ts_server_host, port=redis_ts_server_port, decode_responses=True)
    redis_db = Redis(host=redis_server_host, port=redis_server_port, decode_responses=True)
    for input_dict in input_dicts_list:
        city = city.replace(" ","_")
        dt_epoch_int = int(input_dict[city+"_date_forcasted"])
        message_dict = {dt_epoch_int : {}}
        for dict_key in input_dict.keys():
            if dict_key in [city+"_current_temp_f", city+"_high_temp_f", city+"_low_temp_f", city+"_feels_like_temp_f",city+"_humidity_percent",city+"_wind_speed_mph",city+"_cloudiness_percentage",city+"_precipitation_probability_percentage"]:
                redis_dbts.ts().add(dict_key, dt_epoch_int, input_dict[dict_key], duplicate_policy="LAST")
            # elif dict_key in ["weather_main_message", "weather_descriptive_message"]:
            #     message_dict[dt_epoch_int][dict_key] = input_dict[dict_key]
        
        # message_date_timestamp = 0
        # for ts in message_dict.keys():
        #     message_date_timestamp = ts
        
        # message_date_timestamp = str(message_date_timestamp)
        # hm_key = "wm_"+message_date_timestamp
        # #pdb.set_trace()
        # redis_db.hmset(hm_key, message_dict[int(message_date_timestamp)])

        #redis_db.set(dataName+"_"+dt_string, data_string)

#"weather_day_data"
#define rates/buckets/limiters for each api here

def get_lat_lon_by_location_name(api_key, city, stateCode, countryCode="US"):
    lat_lon = False
    url = f"http://api.openweathermap.org/geo/1.0/direct?q={city},{stateCode},{countryCode}&limit=1&appid={api_key}"
    if openweathermap_limiter.try_acquire("geo_api_request"):
        response = requests.get(url)
    data = response.json()
    return data[0]
    


def get_weather(api_key, lat, lon):
    #url = f"http://api.openweathermap.org/data/2.5/weather?q={location}&appid={api_key}"
    #url = f"https://api.openweathermap.org/data/3.0/onecall?lat={lat}&lon={lon}&appid={api_key}"
    url = f"http://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={api_key}"
    if openweathermap_limiter.try_acquire("weather_request"):
        response = requests.get(url)
    data = response.json()
    return format_weather_data(data)

def format_weather_data(weather_data):
    formatted_weather_data_dict = { "dates_data" : [] }
    for date_data in weather_data["list"]:
        date_dt = datetime.fromtimestamp(date_data['dt'])
        formatted_city = city.replace(" ","_")
        date_data_dict = {
            formatted_city+"_date_forcasted" : convert_datetime_to_epoch_string_ms(date_dt),
            formatted_city+"_current_temp_f" : convert_kelvin_to_farenheit( date_data["main"]["temp"]),
            formatted_city+"_high_temp_f" : convert_kelvin_to_farenheit( date_data["main"]["temp_max"] ),
            formatted_city+"_low_temp_f" : convert_kelvin_to_farenheit( date_data["main"]["temp_min"] ),
            formatted_city+"_feels_like_temp_f" : convert_kelvin_to_farenheit( date_data["main"]["feels_like"] ),
            formatted_city+"_humidity_percent" : date_data["main"]["humidity"],
            formatted_city+"_weather_main_message": date_data["weather"][0]["main"],
            formatted_city+"_weather_descriptive_message": date_data["weather"][0]["description"],
            formatted_city+"_wind_speed_mph": convert_meters_to_miles(date_data["wind"]["speed"]),
            formatted_city+"_cloudiness_percentage" : date_data["clouds"]["all"],
            formatted_city+"_precipitation_probability_percentage" : date_data["pop"] * 100,
            formatted_city+"_date_api_queried": convert_datetime_to_epoch_string_ms(datetime.now())
        }
        formatted_weather_data_dict["dates_data"].append(date_data_dict)
    return formatted_weather_data_dict


def get_stock(api_key, symbol):
    url = f"https://www.alphavantage.co/query?function=TIME_SERIES_INTRADAY&symbol={symbol}&interval=1min&apikey={api_key}"
    response = requests.get(url)
    data = response.json()
    return data

def get_news(api_key, keyword):
    url = f"https://newsapi.org/v2/everything?q={keyword}&apiKey={api_key}"
    if newsapi_limiter.try_acquire("news_request"):
        response = requests.get(url)
    data = response.json()
    return data['articles']


# This checks whether temperature is between 0 C and 30 C, just to demonstrate how you can add a criteria before notifying the user
def should_notify_weather(data):
    temp_k = data['main']['temp']
    temp_c = temp_k - 273.15
    if temp_c > 0 or temp_c < 30:
        return True
    return False

def should_notify_stock(data):
    last_close = float(data['Time Series (1min)'][list(data['Time Series (1min)'].keys())[0]]['4. close'])
    if last_close > 150:
        return True
    return False

def should_notify_game_price(price, threshold):
    if price <= threshold:
        return True
    return False

def display_weather(data):
    temp_k = data['main']['temp']
    temp_c = temp_k - 273.15
    print(f"Weather: {data['weather'][0]['description']}, Temperature: {temp_c:.2f}°C")

def display_stock(data):
    last_close = float(data['Time Series (1min)'][list(data['Time Series (1min)'].keys())[0]]['4. close'])
    print(f"Stock: {last_close:.2f} USD")

def send_email(subject, body, to_email, from_email, from_password):
    if to_email and from_email and from_password:
        msg = MIMEMultipart()
        msg['From'] = from_email
        msg['To'] = to_email
        msg['Subject'] = subject

        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(from_email, from_password)
        text = msg.as_string()
        server.sendmail(from_email, to_email, text)
        server.quit()

def get_steam_game_price(appid):
    url = f"https://store.steampowered.com/api/appdetails?appids={appid}"
    response = requests.get(url)
    data = response.json()
    if data[str(appid)]['success']:
        price_info = data[str(appid)]['data']['price_overview']
        return price_info['final'] / 100.0  # Price in USD
    else:
        return None
    
def display_game_price(price, name):
    print(f"{name} price: {price:.2f} USD")

def display_news(articles, keyword):
    print(f"News for {keyword}:")
    for article in articles[:5]:  # Display top 5 news articles
        print(f"- {article['title']}")

def show_windows_notification(title, message):
    toaster = ToastNotifier()
    toaster.show_toast(title, message, duration=10)

def convert_kelvin_to_farenheit(units_kelvin):
    units_farenheit = int(((float(units_kelvin) - 273.15) * 1.8 ) + 32)
    return units_farenheit

def convert_meters_to_miles(meters):
    units_miles = "%.5f" % (float(meters) / 1609.344)
    return units_miles

def convert_datetime_to_epoch_string_ms(input_dt):
    epoch = datetime.utcfromtimestamp(0)
    return (input_dt - epoch).total_seconds() * 1000

def weather_job():
    load_dotenv()
    weather_api_key = getenv('WEATHER_API_KEY')
    weather_run_interval_in_minutes=str(float(getenv('WEATHER_RUN_INTERVAL_MINUTES')))
    city = getenv('CITY')
    stateCode = getenv('STATECODE')
    redis_ts_server_host = getenv("REDIS_TS_HOST")
    redis_ts_server_port = getenv("REDIS_TS_PORT")
    print("weather job started. .env configuration set to run every "+weather_run_interval_in_minutes+" minutes. " + datetime.now().strftime('%m-%d-%Y %I:%M:%S:%f %p'))
    print("attempting to get lat and lon from geo api using city and statecode..." + datetime.now().strftime('%m-%d-%Y %I:%M:%S:%f %p'))
    geo_data = get_lat_lon_by_location_name(weather_api_key, city, stateCode, countryCode="US")
    print("geodata aquired." + datetime.now().strftime('%m-%d-%Y %I:%M:%S:%f %p'))
    print("attempting to get weather..." + datetime.now().strftime('%m-%d-%Y %I:%M:%S:%f %p'))
    weather_data = get_weather(weather_api_key, geo_data["lat"], geo_data["lon"])
    print("weather data acquired." + datetime.now().strftime('%m-%d-%Y %I:%M:%S:%f %p'))
    if redis_ts_server_host and redis_ts_server_port:
        print("posting to redis timeseriers server on all weather related timeseries keys..." + datetime.now().strftime('%m-%d-%Y %I:%M:%S:%f %p'))
        post_weatherdata_dates_individually_to_redis_as_ts(weather_data["dates_data"], city)
        print("Redis data posted!" + datetime.now().strftime('%m-%d-%Y %I:%M:%S:%f %p'))


# {'author': 'CBS News Videos',
#   'content': 'Moscow is scrambling to block a purported major Ukrainian attack '
#              'on Russian territory. CBS News foreign correspondent Ian Lee has '
#              'more on the Ukrainian raids, as well as the ongoing unrest in '
#              'the UK.',
#   'description': 'Moscow is scrambling to block a purported major Ukrainian '
#                  'attack on Russian territory. CBS News foreign correspondent '
#                  'Ian Lee has more on the Ukrainian raids...',
#   'publishedAt': '2024-08-08T15:33:59Z',
#   'source': {'id': None, 'name': 'Yahoo Entertainment'},
#   'title': 'Moscow says Ukraine has launched a massive attack into Russian '
#            'territory',
#   'url': 'https://www.yahoo.com/news/moscow-says-ukraine-launched-massive-153359775.html',
#   'urlToImage': 'https://s.yimg.com/ny/api/res/1.2/lTokAl9iCUa2p232hs4hmg--/YXBwaWQ9aGlnaGxhbmRlcjt3PTEyMDA7aD02NzU-/https://media.zenfs.com/en/video.cbsnewsvideos.com/97b0425be0ec6eda520046bde89ebeeb'}

def news_job():
    load_dotenv()
    news_api_key = getenv('NEWS_API_KEY')
    news_keywords = getenv('NEWS_KEYWORD')
    news_keywords_list = []
    if news_keywords:
        if "," in news_keywords:
            news_keywords_list = news_keywords.split(",")
        else:
            news_keywords_list.append(news_keywords)
    redis_server_host = getenv("REDIS_HOST")
    redis_server_port = getenv("REDIS_PORT")
    news_articles_dict = {}
    for news_keyword in news_keywords_list:
        news_articles = get_news(news_api_key, news_keyword)
        display_news(news_articles, news_keyword)
        if news_articles: 
            if redis_server_host and redis_server_port:
                print("posting news articles to redis if they don't exist already!" + datetime.now().strftime('%m-%d-%Y %I:%M:%S:%f %p'))
                redis_db = Redis(host=redis_server_host, port=redis_server_port, decode_responses=True)
                for news_article in news_articles:
                    news_title = news_article['title']
                    # hashObj = hashlib.sha256(news_title.encode())
                    # news_title_last5_hash = hashObj.hexdigest()[-5] + hashObj.hexdigest()[-4] + hashObj.hexdigest()[-3] + hashObj.hexdigest()[-2] + hashObj.hexdigest()[-1]
                    article_json_string = json.dumps(news_article)
                    redis_db.sadd("news_article:"+news_keyword, article_json_string)
                print("Done posting news articles to redis server. " + datetime.now().strftime('%m-%d-%Y %I:%M:%S:%f %p'))

        #show_windows_notification('News Alert', f"Top news for {news_keyword}:\n{news_body}")


# def job():
#     load_dotenv()
#     print("job started, env vars loaded.")
#     weather_api_key = getenv('WEATHER_API_KEY')
#     stock_api_key = getenv('STOCK_API_KEY')
#     news_api_key = getenv('NEWS_API_KEY')
#     city = getenv('CITY')
#     stateCode = getenv('STATECODE')
#     stock_symbol = getenv('STOCK_SYMBOL')
#     steam_appid = getenv('STEAM_APPID')
#     steam_game_name = getenv('STEAM_GAME_NAME')
#     price_threshold = getenv('STEAM_GAME_PRICE_THRESHOLD')
#     news_keywords = getenv('NEWS_KEYWORD')
#     to_email = getenv('EMAIL_TO_NOTIFY')
#     from_email = getenv('EMAIL_FROM_ADDRESS')
#     from_password = getenv('EMAIL_FROM_PASSWORD')

#     if weather_api_key and city and stateCode:
        
#         # display_weather(weather_data)
#         # # Calculate temp_c for weather notification
#         # temp_k = weather_data['main']['temp']
#         # temp_c = temp_k - 273.15

#         # if should_notify_weather(weather_data):
#         #     send_email('Weather Alert', f"Current weather: {weather_data['weather'][0]['description']}, Temperature: {temp_c:.2f}°C", to_email, from_email, from_password)
#         #     show_windows_notification('Weather Alert', f"Current weather: {weather_data['weather'][0]['description']}, Temperature: {temp_c:.2f}°C")

#     if stock_api_key and stock_symbol:
#         stock_data = get_stock(stock_api_key, stock_symbol)
#         display_stock(stock_data)
#         if should_notify_stock(stock_data):
#             last_close = float(stock_data['Time Series (1min)'][list(stock_data['Time Series (1min)'].keys())[0]]['4. close'])
#             send_email('Stock Alert', f"Current stock price of {stock_symbol}: {last_close:.2f} USD", to_email, from_email, from_password)
    
#     if steam_appid and steam_game_name and price_threshold:
#         game_price = get_steam_game_price(steam_appid)
#         if game_price is not None:
#             display_game_price(game_price, steam_game_name)
#         if game_price is not None and should_notify_game_price(game_price, price_threshold):
#             send_email('Game Price Alert', f"The price of {steam_game_name} is now {game_price:.2f} USD, which is below your threshold of {price_threshold:.2f} USD.", to_email, from_email, from_password)
#             show_windows_notification('Game Price Alert', f"The price of {steam_game_name} is now {game_price:.2f} USD, which is below your threshold of {price_threshold:.2f} USD.")
    
#     if news_api_key and news_keywords:
#         news_articles = get_news(news_api_key, news_keywords)
#         display_news(news_articles, news_keywords)
#         if news_articles:
#             news_body = '\n'.join([f"- {article['title']}" for article in news_articles[:5]])
#             send_email('News Alert', f"Top news for {news_keyword}:\n{news_body}", to_email, from_email, from_password)
#             show_windows_notification('News Alert', f"Top news for {news_keyword}:\n{news_body}")


###start of actual script here!

degreeSymbol = chr(176)
load_dotenv()
weather_run_interval_in_minutes=float(getenv('WEATHER_RUN_INTERVAL_MINUTES'))
news_run_interval_in_minutes=float(getenv('NEWS_RUN_INTERVAL_MINUTES'))
weather_api_key = getenv('WEATHER_API_KEY')
stock_api_key = getenv('STOCK_API_KEY')
news_api_key = getenv('NEWS_API_KEY')
news_keywords = getenv('NEWS_KEYWORD')
city = getenv('CITY')
stateCode = getenv('STATECODE')
stock_symbol = getenv('STOCK_SYMBOL')
steam_appid = getenv('STEAM_APPID')
steam_game_name = getenv('STEAM_GAME_NAME')
price_threshold = getenv('STEAM_GAME_PRICE_THRESHOLD')
to_email = getenv('EMAIL_TO_NOTIFY')
from_email = getenv('EMAIL_FROM_ADDRESS')
from_password = getenv('EMAIL_FROM_PASSWORD')
redis_server_host = getenv("REDIS_HOST")
redis_server_port = getenv("REDIS_PORT")
redis_ts_server_host = getenv("REDIS_TS_HOST")
redis_ts_server_port = getenv("REDIS_TS_PORT")
sqlite_file_path = getenv("SQLITE_FILE_PATH")

# openweathermap.org - free key is 60 calls a min, 1,000,000 calls a month. 
# One Call 3.0 API updated every 10 mins. 1000 calls for free a day.
openweathermap_minute_rate = Rate(60, Duration.MINUTE)
openweathermap_daily_rate = Rate(1000, Duration.DAY)
openweathermap_monthly_rate = Rate(1000000, Duration.WEEK * 4)
openweathermap_rates = [openweathermap_minute_rate, openweathermap_daily_rate, openweathermap_monthly_rate]

# newsapi.org - free key is 100 requests per day, just cuts off.
newsapi_daily_rate = Rate(100, Duration.DAY)
newsapi_rates = [newsapi_daily_rate]

#set bucket types based on .env vars set
if redis_server_host and redis_server_port:
    if weather_api_key and city and stateCode: 
        print("Redis Configuration & Weather API Configuration Found! Setting up openweathermap_bucket rate limiter as a redis type bucket.")
        openweathermap_bucket = create_or_get_redis_bucket("openweathermap_bucket", openweathermap_rates)
        openweathermap_limiter = Limiter(openweathermap_bucket)
        weather_job()
        schedule.every(weather_run_interval_in_minutes).minutes.do(weather_job)
    if news_api_key and news_keywords:
        print("Redis Configuration & News API Configuration Found! Setting up newsapi_bucket rate limiter as a redis type bucket.")
        newsapi_bucket = create_or_get_redis_bucket("newsapi_bucket", newsapi_rates)
        newsapi_limiter = Limiter(newsapi_bucket)
        news_job()
        schedule.every(news_run_interval_in_minutes).minutes.do(news_job)
elif sqlite_file_path:
    if weather_api_key and city and stateCode:
        print("SQLITE Configuration Found & Weather API Configuration Found! Setting up openweathermap_bucket rate limiter as a SQLITE type bucket.")
        openweathermap_bucket = create_or_get_sqlite_bucket("openweathermap_bucket", openweathermap_rates)
        openweathermap_limiter = Limiter(openweathermap_bucket)
        weather_job()
        schedule.every(weather_run_interval_in_minutes).minutes.do(weather_job)
    if news_api_key and news_keywords:
        print("SQLITE Configuration Found & News API Configuration Found! Setting up newsapi_bucket rate limiter as a SQLITE type bucket.")
        newsapi_bucket = create_or_get_sqlite_bucket("newsapi_bucket", newsapi_rates)
        newsapi_limiter = Limiter(newsapi_bucket)
        news_job()
        schedule.every(news_run_interval_in_minutes).minutes.do(news_job)
else:
    if weather_api_key and city and stateCode:
        print("Could not find a redis server configuration or sqlite filepath in .env variables. Setting up openweathermap_bucket rate limiter as an InMemoryBucket type bucket.")
        openweathermap_bucket = InMemoryBucket(openweathermap_rates)
        openweathermap_limiter = Limiter(openweathermap_bucket)
        weather_job()
        schedule.every(weather_run_interval_in_minutes).minutes.do(weather_job)
    if news_api_key and news_keywords:
        print("Could not find a redis server configuration or sqlite filepath in .env variables. Setting up newsapi_bucket rate limiter as an InMemoryBucket type bucket.")
        newsapi_bucket = InMemoryBucket(newsapi_rates)
        newsapi_limiter = Limiter(newsapi_bucket)
        news_job()
        schedule.every(news_run_interval_in_minutes).minutes.do(news_job)

#schedule.every(run_interval_in_minutes).minutes.do(job)

while True:
    schedule.run_pending()
    time.sleep(1)