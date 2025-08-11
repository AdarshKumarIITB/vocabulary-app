import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def load_config():
    """
    Loads all environment variables from .env file using python-dotenv
    Sets defaults if environment variables are not present
    Returns a dictionary with all configuration values including:
    - database_url: Connection string for the database
    - openai_api_key: API key for OpenAI
    - slack_bot_token: Bot token for Slack authentication
    - slack_channel_id: Channel ID where bot operates
    - daily_word_time: Time to post daily word (e.g., "09:00")
    - timezone: Timezone for scheduling (e.g., "America/New_York")
    """
    
    config = {
        'database_url': get_database_url(),
        'openai_api_key': os.getenv('OPENAI_API_KEY', ''),
        'slack_bot_token': os.getenv('SLACK_BOT_TOKEN', ''),
        'slack_channel_id': os.getenv('SLACK_CHANNEL_ID', ''),
        'slack_signing_secret': os.getenv('SLACK_SIGNING_SECRET', ''),
        'daily_word_time': os.getenv('DAILY_WORD_TIME', '09:00'),
        'timezone': os.getenv('TIMEZONE', 'America/New_York')
    }
    
    # Validate critical configurations
    if not config['database_url']:
        raise ValueError("DATABASE_URL is not configured in .env file")
    
    return config


def get_database_url():
    """
    Constructs and returns the database connection string from environment variables
    Handles different database types (PostgreSQL, SQLite)
    Validates URL format and returns properly formatted connection string
    """
    
    database_url = os.getenv('DATABASE_URL', '')
    
    if not database_url:
        # Default to SQLite if not specified
        database_url = 'sqlite:///vocabulary.db'
    
    # Validate URL format
    if not (database_url.startswith('sqlite://') or 
            database_url.startswith('postgresql://') or 
            database_url.startswith('postgres://')):
        raise ValueError(f"Invalid DATABASE_URL format: {database_url}")
    
    # Handle Heroku-style postgres:// URLs (convert to postgresql://)
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    return database_url


def get_slack_config():
    """
    Returns Slack-specific configuration as a dictionary
    Includes: bot_token, channel_id, signing_secret
    Validates that required Slack credentials are present
    Raises exception if any required Slack config is missing
    """
    
    slack_config = {
        'bot_token': os.getenv('SLACK_BOT_TOKEN', ''),
        'channel_id': os.getenv('SLACK_CHANNEL_ID', ''),
        'signing_secret': os.getenv('SLACK_SIGNING_SECRET', '')
    }
    
    # Validate required fields
    missing_fields = []
    for key, value in slack_config.items():
        if not value or value == 'your_token_here':
            missing_fields.append(f"SLACK_{key.upper()}")
    
    if missing_fields:
        print(f"Warning: Missing Slack configuration: {', '.join(missing_fields)}")
        print("Slack integration will not work without these values.")
    
    return slack_config


def get_openai_config():
    """
    Returns OpenAI configuration including API key and model name
    Default model: "gpt-4" or "gpt-3.5-turbo" based on preference
    Validates API key is present and properly formatted
    """
    openai_config = {
        'api_key': os.getenv('OPENAI_API_KEY', ''),
        'model': os.getenv('OPENAI_MODEL', 'gpt-4o'),
        'max_tokens': int(os.getenv('OPENAI_MAX_TOKENS', '300')),
        'temperature': float(os.getenv('OPENAI_TEMPERATURE', '0.7'))
    }
    
    # Validate API key
    if not openai_config['api_key'] or openai_config['api_key'] == 'your_api_key_here':
        print("Warning: OpenAI API key not configured.")
        print("Please set OPENAI_API_KEY in .env file to use LLM features.")
        openai_config['api_key'] = None
    
    return openai_config


def get_scheduler_config():
    """
    Returns scheduling configuration for daily word posting
    Includes: daily_word_time (as string "HH:MM"), timezone
    Converts time string to proper format for scheduler
    """
    
    import re
    
    daily_time = os.getenv('DAILY_WORD_TIME', '09:00')
    timezone = os.getenv('TIMEZONE', 'America/New_York')
    
    # Validate time format (HH:MM)
    if not re.match(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$', daily_time):
        print(f"Warning: Invalid DAILY_WORD_TIME format: {daily_time}")
        print("Using default: 09:00")
        daily_time = '09:00'
    
    scheduler_config = {
        'daily_word_time': daily_time,
        'timezone': timezone,
        'hour': int(daily_time.split(':')[0]),
        'minute': int(daily_time.split(':')[1])
    }
    
    return scheduler_config