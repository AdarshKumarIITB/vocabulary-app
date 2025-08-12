import logging
import json
from openai import OpenAI
from config.settings import get_openai_config
from database.models import get_word_by_thread
from .prompts import get_tutor_response_prompt

logger = logging.getLogger(__name__)


def process_user_message(session, thread_id, user_message, slack_client):
    """
    Main entry point when user posts in a vocabulary thread
    Fetches complete thread context for understanding
    Returns response message to be posted back to Slack thread
    """
    
    logger.info(f"Processing user message in thread {thread_id}")
    
    try:
        # Get the word associated with this thread
        word_entry = get_word_by_thread(session, thread_id)
        if not word_entry:
            logger.warning(f"No word found for thread {thread_id}")
            return "I couldn't find the word associated with this thread. Please try again."
        
        # Fetch thread context
        thread_context = fetch_thread_context(slack_client, thread_id)

        #Fetch theme
        from database.models import get_current_theme
        theme = get_current_theme(session)
        
        # Generate tutor response
        response = generate_tutor_response(thread_context, user_message, word_entry.word, theme)
        
        logger.info(f"Generated response for word '{word_entry.word}'")
        return response
        
    except Exception as e:
        logger.error(f"Error in process_user_message: {str(e)}", exc_info=True)
        return "I encountered an error while processing your message. Please try again."


def fetch_thread_context(slack_client, thread_id):
    """
    Retrieves all messages from a specific Slack thread
    Calls slack_client.get_thread_messages with thread_id
    Formats messages into readable context for LLM
    Includes message sender (bot/user) and content
    Preserves chronological order of messages
    Returns formatted string with full conversation history
    """
    
    logger.debug(f"Fetching thread context for {thread_id}")
    
    try:
        # Get all messages in the thread
        messages = slack_client.get_thread_messages(thread_id)
        
        if not messages:
            logger.warning(f"No messages found in thread {thread_id}")
            return ""
        
        # Format messages for context
        context_lines = []
        for msg in messages:
            # Determine if message is from bot or user
            sender = "Bot" if msg.get('bot_id') else "User"
            text = msg.get('text', '')
            
            # Skip empty messages
            if text:
                context_lines.append(f"{sender}: {text}")
        
        context = "\n".join(context_lines)
        logger.debug(f"Thread context ({len(context_lines)} messages) retrieved")
        return context
        
    except Exception as e:
        logger.error(f"Error fetching thread context: {str(e)}", exc_info=True)
        return ""


def generate_tutor_response(thread_context, user_message, word, theme=None):
    """
    Generates contextual tutor response for any user message
    Constructs prompt with full thread context and user's latest message
    Instructs LLM to act as vocabulary tutor
    Returns tutor's response as string
    Maintains encouraging and educational tone
    """
    
    logger.debug(f"Generating tutor response for word '{word}'")
    prompt = get_tutor_response_prompt(thread_context, user_message, word, theme)
    
    try:
        # Call LLM for response
        response = call_llm_for_tutoring(prompt)
        return response
        
    except Exception as e:
        logger.error(f"Error generating tutor response: {str(e)}", exc_info=True)
        return "Let me help you with that word. Could you try using it in a sentence, or would you like more examples?"


def call_llm_for_tutoring(prompt):
    """
    Makes API call to OpenAI for tutoring responses
    Similar to call_llm_for_word but with different parameters
    May use different temperature for more conversational responses
    Handles API errors and retries
    Returns LLM response text
    """
    
    logger.debug("Calling OpenAI API for tutoring response")
    
    try:
        # Get OpenAI configuration
        config = get_openai_config()
        client = OpenAI(api_key=config['api_key'])
        
        # Make API call with conversational parameters
        response = client.chat.completions.create(
            model=config.get('model', 'gpt-3.5-turbo'),
            messages=[
                {"role": "system", "content": "You are a helpful vocabulary tutor. Be encouraging and educational."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,  # Slightly higher for more natural conversation
            max_tokens=150,   # Keep responses concise
            n=1
        )
        
        # Extract response text
        response_text = response.choices[0].message.content.strip()
        logger.debug(f"Received response: {response_text[:100]}...")
        
        return response_text
        
    except Exception as e:
        logger.error(f"OpenAI API error: {str(e)}", exc_info=True)
        
        # Retry with exponential backoff if rate limited
        if "rate_limit" in str(e).lower():
            import time
            logger.info("Rate limited, retrying after delay...")
            time.sleep(2)
            return call_llm_for_tutoring(prompt)
        
        raise e
