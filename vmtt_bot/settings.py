import os

from dotenv import load_dotenv

load_dotenv()

API_TOKEN = os.environ['API_TOKEN']
LOG_LEVEL = os.getenv('LOG_LEVEL', 'DEBUG')

YC_OAUTH_TOKEN = os.environ['YC_OAUTH_TOKEN']
YC_FOLDER_ID = os.environ['YC_FOLDER_ID']
