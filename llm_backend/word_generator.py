import json
import time
from openai import OpenAI
from database.models import (
    check_last_word_flag, 
    read_words, 
    get_word_by_name,
    create_word,
    WordHistory
)
from .prompts import get_word_generation_prompt, get_system_prompt
from database.models import get_current_theme
import logging

logger = logging.getLogger(__name__)



def generate_word(session):
    """
    Main function to generate a new vocabulary word
    First checks if conditions are met for new word generation
    Calls check_last_word_flag to see if last word has been responded to
    If known_flag is None (no response yet), returns message that no new word needed
    If known_flag is True or False, proceeds with generation
    Reads all existing words from database to avoid duplicates
    Separates words into known_words list and unknown_words list
    Calls LLM to generate new word with appropriate difficulty
    Validates generated word is not duplicate
    If duplicate, retries generation until unique word found
    Returns dictionary with word data structure for Slack posting
    """
    try:
        # Check if we should generate a new word
        last_word_flag = check_last_word_flag(session)
        
        # If last word hasn't been responded to, don't generate new word
        if last_word_flag is None and session.query(WordHistory).count() > 0:
            return {
                "status": "waiting",
                "message": "Waiting for user response to last word before generating new one"
            }
        
        # Get all existing words from database
        all_words = read_words(session, known_flag=None)
        existing_words = [word.word for word in all_words]
        
        # Separate into known and unknown words
        known_words = [word.word for word in all_words if word.known_flag == True]
        unknown_words = [word.word for word in all_words if word.known_flag == False]

        # Get current theme if set
        current_theme = get_current_theme(session)
        if current_theme:
            logger.info(f"Generating word with theme: {current_theme}")
        
        # Generate new word with retry logic for duplicates
        max_retries = 5
        for attempt in range(max_retries):
            # Create prompt for word generation
            prompt = get_word_generation_prompt(
                existing_words=existing_words,
                known_words=known_words,
                unknown_words=unknown_words,
                theme=current_theme 
            )
            
            # Call LLM to generate word
            llm_response = call_llm_for_word(prompt)
            
            # Parse the response
            word_data = parse_word_response(llm_response)
            

            if validate_word_uniqueness(session, word_data["word"]):
                
                logger.info(f"Generated unique word: {word_data['word']}")
                if current_theme:
                    word_data['theme'] = current_theme

                # Prepare and return the word data for Slack
                slack_messages = prepare_slack_messages(word_data)

                return {
                    "status": "success",
                    "word_data": word_data,
                    "slack_messages": slack_messages
                }
            else:
                # Word is duplicate, retry
                logger.warning(f"Generated duplicate word: {word_data['word']}. Retrying...")

                if attempt < max_retries - 1:
                    continue
        
        return {
            "status": "error",
            "message": "Failed to generate unique word after multiple attempts"
        }
    except Exception as e:
        logger.error(f"Error generating word: {e}")
        raise



def call_llm_for_word(prompt):
    """
    Makes API call to OpenAI with the word generation prompt
    Takes formatted prompt string as parameter
    Sets up OpenAI client with proper API key
    Configures model (GPT-4 or GPT-3.5-turbo) and temperature
    Handles rate limiting with exponential backoff
    Retries up to 3 times if API call fails
    Returns raw LLM response text
    Raises exception after max retries with clear error message
    """
    
    from config.settings import get_openai_config
    openai_config = get_openai_config()
    api_key = openai_config['api_key']
    
    if not api_key or api_key == "your_api_key_here":
        raise ValueError("OpenAI API key not configured. Please set OPENAI_API_KEY in .env file")
    
    # Initialize OpenAI client
    client = OpenAI(api_key=api_key)
    
    # Retry logic with exponential backoff
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=openai_config['model'],
                messages=[
                    {"role": "system", "content": get_system_prompt()},
                    {"role": "user", "content": prompt}
                ],
                temperature=openai_config['temperature'],  # Some creativity for word selection
                max_tokens=openai_config['max_tokens']  
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            if attempt < max_retries - 1:
                # Exponential backoff: 2^attempt seconds
                wait_time = 2 ** attempt
                time.sleep(wait_time)
                continue
            else:
                raise Exception(f"Failed to call OpenAI API after {max_retries} attempts: {str(e)}")


def parse_word_response(llm_response):
    """
    Extracts structured data from LLM's response
    Expects JSON format with word, meanings, and examples
    Parses JSON and validates all required fields are present
    Cleans up any formatting issues in the response
    Returns dictionary with structure:
    {
        'word': 'vocabulary_word',
        'meanings': ['meaning1', 'meaning2'],
        'examples': ['example sentence 1', 'example sentence 2']
    }
    Handles parsing errors gracefully with fallback
    """
    
    try:
        # Try to parse as JSON
        cleaned_response = llm_response.strip()
        if cleaned_response.startswith('```json'):
            cleaned_response = cleaned_response[7:]  # Remove ```json
        elif cleaned_response.startswith('```'):
            cleaned_response = cleaned_response[3:]   # Remove ```
            
        if cleaned_response.endswith('```'):
            cleaned_response = cleaned_response[:-3]  # Remove trailing ```
            
        cleaned_response = cleaned_response.strip()


        word_data = json.loads(cleaned_response)
        
        # Validate required fields
        required_fields = ["word", "meanings", "examples"]
        for field in required_fields:
            if field not in word_data:
                raise ValueError(f"Missing required field: {field}")
        
        # Ensure meanings and examples are lists
        if not isinstance(word_data["meanings"], list):
            word_data["meanings"] = [word_data["meanings"]]
        
        if not isinstance(word_data["examples"], list):
            word_data["examples"] = [word_data["examples"]]
        
        # Clean up any whitespace
        word_data["word"] = word_data["word"].strip()
        word_data["meanings"] = [m.strip() for m in word_data["meanings"]]
        word_data["examples"] = [e.strip() for e in word_data["examples"]]
        
        return word_data
        
    except (json.JSONDecodeError, ValueError) as e:
        # Fallback: try to extract word from response even if not proper JSON
        # This is a safety net but shouldn't normally be needed
        print(f"Failed to parse LLM response as JSON: {e}")
        print(f"Raw response: {llm_response}")
        
        # Return None to trigger retry
        return None


def validate_word_uniqueness(session, word):
    """
    Checks if generated word already exists in database
    Calls get_word_by_name to check for exact match
    Returns True if word is unique (not in database)
    Returns False if word already exists
    Case-insensitive comparison to avoid near-duplicates
    """
    
    # Check for exact match (case-insensitive)
    existing_word = get_word_by_name(session, word.lower())
    
    # Also check with original case
    if not existing_word:
        existing_word = get_word_by_name(session, word)
    
    # Return True if unique (not found), False if exists
    return existing_word is None


def prepare_slack_messages(word_data):
    """
    Prepares the word data for posting to Slack
    Takes parsed word data dictionary as input
    Creates list of messages to post in thread:
    1. Main thread message: just the word
    2. First reply: definitions/meanings
    3. Second reply: example sentences
    4. Third reply: instruction for user response
    Returns list of formatted message strings
    """
    
    messages = []
    
    # 1. Main thread message - just the word
    messages.append(f"📚 Today's vocabulary word: *{word_data['word']}*")
    
    # 2. Definitions/meanings
    meanings_text = "*Meanings:*\n"
    for i, meaning in enumerate(word_data['meanings'], 1):
        meanings_text += f"{i}. {meaning}\n"
    messages.append(meanings_text.strip())
    
    # 3. Example sentences
    examples_text = "*Examples:*\n"
    for i, example in enumerate(word_data['examples'], 1):
        examples_text += f"• {example}\n"
    messages.append(examples_text.strip())
    
    # 4. User instruction
    instruction = (
        "Did you already know this word?\n"
        "• Reply '1' if you already knew it\n"
        "• Reply with any other message to learn it (you can ask questions about the word or use it in a sentence for me to give feedback or ask for phonetic or syllable breakdown of the pronunciation)\n"
    )
    messages.append(instruction)
    
    return messages