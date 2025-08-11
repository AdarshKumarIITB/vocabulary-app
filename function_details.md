# Vocabulary Tutor v1 - Complete Project Structure and Function Details

## Project Directory Structure

```
vocabulary-app/
├── README.md
├── requirements.txt
├── .env
├── .gitignore
├── config/ 
│   ├── __init__.py
│   └── settings.py
├── database/
│   ├── __init__.py
│   ├── models.py
│   ├── database.py
│   └── migrations/ 
│       └── 001_initial_schema.sql
├── llm_backend/
│   ├── __init__.py
│   ├── main.py
│   ├── word_generator.py
│   ├── tutor.py
│   ├── orchestrator.py
│   └── prompts.py
├── slack_integration/
│   ├── __init__.py
│   └── slack_client.py
└── run.py
```

## File Details and Functions

### **README.md**
Project documentation explaining setup, configuration, and usage instructions for the vocabulary tutor.

### **requirements.txt**
```
sqlalchemy
psycopg2-binary 
openai
slack-sdk
python-dotenv
schedule
```

### **.env**
```
# Database
DATABASE_URL=postgresql://user:password@localhost/vocab_db

# OpenAI
OPENAI_API_KEY=your_api_key_here

# Slack
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_CHANNEL_ID=C1234567890

# App Settings
DAILY_WORD_TIME=09:00
TIMEZONE=America/New_York
```

### **.gitignore**
```
.env
*.pyc
__pycache__/
*.db
venv/
.vscode/
.idea/
```

### **config/__init__.py**
Empty file to make config a Python package.

### **config/settings.py**
```python
def load_config():
    # Loads all environment variables from .env file using python-dotenv
    # Sets defaults if environment variables are not present
    # Returns a dictionary with all configuration values including:
    # - database_url: Connection string for the database
    # - openai_api_key: API key for OpenAI
    # - slack_bot_token: Bot token for Slack authentication
    # - slack_channel_id: Channel ID where bot operates
    # - daily_word_time: Time to post daily word (e.g., "09:00")
    # - timezone: Timezone for scheduling (e.g., "India/Kolkata")
    
def get_database_url():
    # Constructs and returns the database connection string from environment variables
    # Handles different database types (PostgreSQL)
    # Validates URL format and returns properly formatted connection string
    
def get_slack_config():
    # Returns Slack-specific configuration as a dictionary
    # Includes: bot_token, channel_id
    # Validates that required Slack credentials are present
    # Raises exception if any required Slack config is missing

def get_openai_config():
    # Returns OpenAI configuration including API key and model name
    # Default model: "gpt-4" or "gpt-3.5-turbo" based on preference
    # Validates API key is present and properly formatted
    
def get_scheduler_config():
    # Returns scheduling configuration for daily word posting
    # Includes: daily_word_time (as string "HH:MM"), timezone
    # Converts time string to proper format for scheduler
```

### **database/__init__.py**
Empty file to make database a Python package.

### **database/models.py**
```python
# SQLAlchemy ORM model and CRUD operations for WordHistory table

from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class WordHistory(Base):
    # SQLAlchemy ORM model for WordHistory table
    # Table name in database will be 'word_history'
    __tablename__ = 'word_history'
    
    # Primary key, auto-incrementing integer
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # The vocabulary word, must be unique and not null
    word = Column(String, unique=True, nullable=False)
    
    # Flag indicating if user knew the word
    # True = user knew it, False = user learned it, None = not yet responded
    known_flag = Column(Boolean, nullable=True)
    
    # Timestamp when word was added to database
    timestamp = Column(DateTime, default=datetime.utcnow)

def create_word(session, word):
    # Creates a new word entry in the WordHistory table
    # Takes database session and word string as parameters
    # Initializes with known_flag as None (user hasn't responded yet)
    # Auto-generates ID and timestamp
    # Returns the newly created WordHistory object
    # Commits the transaction to persist the data
    
def read_words(session, known_flag=None):
    # Reads words from database based on known_flag filter
    # If known_flag is 1: returns all words where known_flag is True
    # If known_flag is 0: returns all words where known_flag is False  
    # If known_flag is None: returns all words in the database
    # Returns list of WordHistory objects
    
def update_known_flag(session, word_id, known_flag):
    # Updates the known_flag of a specific word entry by its ID
    # Takes session, word_id (integer), and known_flag (boolean) as parameters
    # Finds the word entry by ID
    # Updates its known_flag to the provided value
    # Commits the change to database
    # Returns the updated WordHistory object, or None if word not found
    
def check_last_word_flag(session):
    # Checks the known_flag status of the most recent word in the table
    # Orders words by timestamp descending and gets the first one
    # Returns the known_flag value (True, False, or None)
    # If no words exist in database, returns None
    # Used to determine if system should generate new word or wait for response
    
def get_word_by_name(session, word):
    # Checks if a specific word already exists in the database
    # Takes session and word string as parameters
    # Queries database for exact word match
    # Returns the WordHistory object if found, None otherwise
    # Used to prevent duplicate word generation
```

### **database/database.py**
```python
def create_engine_and_session():
    # Creates SQLAlchemy engine using connection URL from config
    # Sets up connection pooling with appropriate pool size and timeout
    # Creates sessionmaker bound to the engine
    # Returns tuple of (engine, sessionmaker)
    # Configures retry logic for transient connection failures
    
def init_database(engine):
    # Initializes database tables using SQLAlchemy models
    # Takes engine as parameter
    # Creates all tables defined in models.py if they don't exist
    # Runs any SQL migrations from migrations folder
    # Returns True if successful, raises exception if database initialization fails
    # Logs initialization status
    
def get_session():
    # Context manager that provides a database session
    # Creates a new session from sessionmaker
    # Automatically handles commit on success
    # Automatically handles rollback on exception
    # Always closes session when done
    # Usage: with get_session() as session: perform_database_operations(session)
    
def test_connection(engine):
    # Tests if database connection is working
    # Attempts a simple query to verify connectivity
    # Returns True if connection successful, False otherwise
    # Used during application startup to verify database is accessible
```

### **database/migrations/001_initial_schema.sql**
```sql
-- Initial schema for WordHistory table
-- This migration creates the word_history table for v1

CREATE TABLE IF NOT EXISTS word_history (
    id SERIAL PRIMARY KEY,
    word VARCHAR(255) UNIQUE NOT NULL,
    known_flag BOOLEAN,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create index on timestamp for efficient ordering
CREATE INDEX IF NOT EXISTS idx_word_history_timestamp ON word_history(timestamp DESC);

-- Create index on known_flag for efficient filtering
CREATE INDEX IF NOT EXISTS idx_word_history_known_flag ON word_history(known_flag);
```

### **llm_backend/__init__.py**
Empty file to make llm_backend a Python package.

### **llm_backend/main.py**
```python
def initialize_application():
    # Main initialization function that sets up all components
    # Loads configuration from config/settings.py
    # Initializes database connection and creates tables if needed
    # Creates Slack client with proper authentication
    # Sets up OpenAI client with API key
    # Returns dictionary with all initialized components:
    # {'config': config_dict, 'db_session': sessionmaker, 'slack_client': client, 'openai_client': client}
    # Handles any initialization errors and provides clear error messages
    
def start_scheduler():
    # Starts the background scheduler for daily word posting
    # Uses the schedule library to set up daily job
    # Reads scheduled time from config (e.g., "09:00")
    # Configures timezone from settings
    # Runs scheduler in a separate background thread
    # Returns the thread object for management
    # Handles timezone conversions properly
    
def webhook_handler(request_data):
    # Processes incoming webhooks from Slack
    # Validates the webhook payload structure
    # Extracts event type, thread_id, user_id, and message text from Slack event
    # Filters out bot messages to prevent loops
    # Routes valid user messages to orchestrator.handle_user_interaction
    # Returns appropriate HTTP response to acknowledge receipt to Slack
    # Handles different Slack event types (message, app_mention, etc.)
    # Implements Slack's URL verification challenge if needed
```

### **llm_backend/word_generator.py**
```python
def generate_word(session):
    # Main function to generate a new vocabulary word
    # First checks if conditions are met for new word generation
    # Calls check_last_word_flag to see if last word has been responded to
    # If known_flag is None (no response yet), returns message that no new word needed
    # If known_flag is True or False, proceeds with generation
    # Reads all existing words from database to avoid duplicates
    # Separates words into known_words list and unknown_words list
    # Calls LLM to generate new word with appropriate difficulty
    # Validates generated word is not duplicate
    # If duplicate, retries generation until unique word found
    # Returns dictionary with word data structure for Slack posting
    
def call_llm_for_word(prompt):
    # Makes API call to OpenAI with the word generation prompt
    # Takes formatted prompt string as parameter
    # Sets up OpenAI client with proper API key
    # Configures model (GPT-4 or GPT-3.5-turbo) and temperature
    # Handles rate limiting with exponential backoff
    # Retries up to 3 times if API call fails
    # Returns raw LLM response text
    # Raises exception after max retries with clear error message
    
def parse_word_response(llm_response):
    # Extracts structured data from LLM's response
    # Expects JSON format with word, meanings, and examples
    # Parses JSON and validates all required fields are present
    # Cleans up any formatting issues in the response
    # Returns dictionary with structure:
    # {
    #   'word': 'vocabulary_word',
    #   'meanings': ['meaning1', 'meaning2'],
    #   'examples': ['example sentence 1', 'example sentence 2']
    # }
    # Handles parsing errors gracefully with fallback
    
def validate_word_uniqueness(session, word):
    # Checks if generated word already exists in database
    # Calls get_word_by_name to check for exact match
    # Returns True if word is unique (not in database)
    # Returns False if word already exists
    # Case-insensitive comparison to avoid near-duplicates
    
def prepare_slack_messages(word_data):
    # Prepares the word data for posting to Slack
    # Takes parsed word data dictionary as input
    # Creates list of messages to post in thread:
    # 1. Main thread message: just the word
    # 2. First reply: definitions/meanings
    # 3. Second reply: example sentences
    # 4. Third reply: instruction for user response
    # Returns list of formatted message strings
```

### **llm_backend/tutor.py**
```python
def process_user_message(session, thread_id, user_message, slack_client):
    # Main entry point when user posts in a vocabulary thread
    # Fetches complete thread context for understanding
    # Returns response message to be posted back to Slack thread
    
def fetch_thread_context(slack_client, thread_id):
    # Retrieves all messages from a specific Slack thread
    # Calls slack_client.get_thread_messages with thread_id
    # Formats messages into readable context for LLM
    # Includes message sender (bot/user) and content
    # Preserves chronological order of messages
    # Returns formatted string with full conversation history
    # Handles pagination if thread has many messages
    
    
def generate_tutor_response(thread_context, user_message):
    # Generates contextual tutor response for any user message
    # Constructs prompt with full thread context and user's latest message
    # Instructs LLM to act as vocabulary tutor
    # Handles various interaction types:
    # - Questions about the word
    # - Requests for more examples
    # - Clarification on meanings
    # - Off-topic messages (redirects back to vocabulary)
    # Returns tutor's response as string
    # Maintains encouraging and educational tone
    
def call_llm_for_tutoring(prompt):
    # Makes API call to OpenAI for tutoring responses
    # Similar to call_llm_for_word but with different parameters
    # May use different temperature for more conversational responses
    # Handles API errors and retries
    # Returns LLM response text
```

### **llm_backend/orchestrator.py**
```python
def schedule_daily_word():
    # Sets up and runs scheduled job for daily word posting
    # Checks configuration for scheduled time (e.g., "09:00")
    # Before posting, verifies conditions are met:
    # - Checks if last word's known_flag is not None (user has responded)
    # - Ensures system is not in dormant state
    # If conditions met, triggers post_new_word_workflow
    # Logs scheduling activities and any issues
    # Handles timezone conversions for consistent timing
    
def post_new_word_workflow(session, slack_client):
    # Complete workflow for generating and posting a new word
    # Step 1: Generate new word using word_generator.generate_word
    # Step 2: Create new thread in Slack with the word
    # Step 3: Post definitions as first reply in thread
    # Step 4: Post examples as second reply in thread
    # Step 5: Post instructions as third reply in thread
    # Step 6: Only after confirming all Slack posts successful, add word to database
    # Returns True if entire workflow succeeds
    # Returns False and rolls back if any step fails
    # Ensures database stays in sync with Slack posts
    
def handle_user_interaction(session, slack_client, thread_id, user_id, message):
    # Central router for all user interactions in vocabulary threads
    # Validates that message is from a user (not bot)
    # Checks if message is in a vocabulary thread
    # If user replies "1" (knew the word):
    #   - Updates known_flag to True in database using update_word_status
    #   - Immediately triggers post_new_word_workflow for next word
    # For any other message:
    #   - Updates known_flag to False in database using update_word_status
    #   - Passes to tutor.process_user_message for handling
    #   - Posts tutor response back to thread
    # Returns success/failure status
    
def update_word_status(session, thread_id, known_flag_value):
    # Updates the known_flag for a word based on thread interaction
    # Maps thread_id to corresponding word in database
    # Updates known_flag to provided value (True or False)
    # Commits change to database
    # Returns updated word object or None if not found
```

### **llm_backend/prompts.py**
```python
def get_word_generation_prompt(existing_words, known_words, unknown_words, theme=None):
    # Constructs detailed prompt for LLM to generate new vocabulary word
    # Includes list of all existing words to avoid duplicates
    # Provides known_words list to gauge user's vocabulary level
    # Provides unknown_words list to understand learning progress
    # If theme is specified, instructs to generate word within that theme
    # Asks for response in specific JSON format with word, meanings, examples
    # Instructs on appropriate difficulty based on known/unknown ratio
    # Returns complete prompt string ready for LLM API call
    
def get_tutor_response_prompt(thread_context, user_message):
    # Creates prompt for LLM to respond as vocabulary tutor
    # Includes complete thread context for continuity
    # Provides user's latest message for response
    # Sets personality: helpful, encouraging, educational
    # Instructs to stay on topic of vocabulary learning
    # For off-topic messages, instructs to politely redirect
    # Returns formatted prompt string
    
def get_system_prompt():
    # Returns base system prompt used across all LLM interactions
    # Defines the assistant as a vocabulary tutor
    # Sets tone: professional but friendly, educational
    # Establishes boundaries: focus on vocabulary learning
    # Used as consistent base for all LLM calls
```

### **slack_integration/__init__.py**
Empty file to make slack_integration a Python package.

### **slack_integration/slack_client.py**
```python
def __init__(self, token, channel_id):
    # Initializes Slack client with authentication
    # Takes bot token and channel ID as parameters
    # Creates WebClient from slack_sdk with the token
    # Stores channel_id for all future operations
    # Validates authentication by calling auth.test
    # Raises exception if authentication fails
    
def create_thread(self, initial_message):
    # Posts a new message to channel that starts a thread
    # Takes initial message text (the vocabulary word) as parameter
    # Uses chat.postMessage API with channel_id
    # Returns thread_timestamp (ts) which serves as thread_id
    # Thread_id is used for all subsequent replies
    # Handles any Slack API errors with clear error messages
    
def post_to_thread(self, thread_id, message):
    # Posts a reply message within an existing thread
    # Takes thread_id (timestamp) and message text as parameters
    # Uses chat.postMessage with thread_ts parameter
    # Maintains thread continuity by replying to correct thread
    # Returns message timestamp of the posted reply
    # Raises exception if thread doesn't exist or post fails
    
def get_thread_messages(self, thread_id):
    # Fetches all messages within a specific thread
    # Takes thread_id (timestamp) as parameter
    # Uses conversations.replies API endpoint
    # Returns list of message dictionaries with:
    # - user: ID of message sender
    # - text: message content
    # - ts: timestamp
    # - bot_id: present if message is from bot
    # Handles pagination if thread has many messages
    # Sorts messages chronologically
    
def post_word_sequence(self, word_data):
    # Posts complete word learning sequence to new thread
    # Takes word_data dictionary with word, meanings, examples
    # Creates initial thread with just the word
    # Posts definitions as first reply
    # Posts examples as second reply
    # Posts user instructions as third reply
    # Returns thread_id for tracking
    # Ensures all posts succeed or rolls back
    
def validate_webhook(self, request_body, headers):
    # Validates incoming webhook is from Slack
    # Verifies request signature for security
    # Handles URL verification challenge during setup
    # Returns True if valid webhook, False otherwise
    # Prevents unauthorized webhook calls
    
def parse_webhook_event(self, request_body):
    # Extracts relevant data from Slack webhook payload
    # Parses JSON body to get event details
    # For any other event apart from text-based replies on a thread - don't care 
    # Returns dictionary with:
    # - type: event type (message, app_mention, etc.)
    # - thread_id: thread_ts if in thread, None otherwise
    # - user_id: ID of user who sent message
    # - text: message content
    # - channel: channel where event occurred
    # Handles different event structures safely
```

### **run.py**
```python
def main():
    # Entry point for the entire application
    # Initializes all components by calling main.initialize_application
    # Starts the scheduler thread for daily word posting
    # Sets up webhook server to receive Slack events
    # Keeps application running continuously
    # Handles graceful shutdown on SIGINT/SIGTERM
    # Logs startup status and any critical errors
    
def setup_webhook_server():
    # Creates Flask or FastAPI server to receive Slack webhooks
    # Sets up POST endpoint at /slack/events
    # Routes webhooks to main.webhook_handler
    # Configures server port from environment or defaults to 3000
    # Implements health check endpoint at /health
    # Runs server with appropriate production settings
    # Handles concurrent requests properly
    
def handle_shutdown(signum, frame):
    # Gracefully handles application shutdown
    # Stops scheduler thread cleanly
    # Closes database connections
    # Logs shutdown status
    # Exits with appropriate code

if __name__ == "__main__":
    # Standard Python entry point
    # Calls main() function to start application
    # Sets up signal handlers for clean shutdown
    # Ensures proper cleanup on exit
```

## Environment Variables Summary

```
# Required
DATABASE_URL          # PostgreSQL or SQLite connection string
OPENAI_API_KEY       # OpenAI API key for LLM calls
SLACK_BOT_TOKEN      # Bot token for Slack authentication
SLACK_CHANNEL_ID     # Channel ID where bot operates

# Optional with defaults
DAILY_WORD_TIME      # Time for daily word (default: "09:00")
TIMEZONE             # Timezone for scheduling (default: "IST")
OPENAI_MODEL         # Model to use (default: "gpt-3.5-turbo")
LOG_LEVEL            # Logging level (default: "INFO")
```

## Key Design Decisions for v1

1. **Simple Database Schema**: Only tracking word, known_flag, and timestamp
2. **Thread Isolation**: Each word gets its own Slack thread
3. **Dormancy Rule**: No new words until user responds to current word
4. **Direct Slack API**: Using slack_sdk instead of MCP for simplicity
5. **Synchronous Operations**: No complex async handling for v1
6. **No Quiz/Scoring**: Saving quiz functionality for future versions
7. **Single User**: No multi-user support needed in v1

