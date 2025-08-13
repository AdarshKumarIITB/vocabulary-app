import logging
import threading
from datetime import datetime
from database.models import (
    update_known_flag, 
    update_known_flag_by_thread,
    check_last_word_flag, 
    get_word_by_thread,
    get_last_word,
    create_word,
    WordHistory,
    set_theme,
    get_current_theme, 
    clear_all_data,
    SystemSettings,
    UserTheme,
    get_system_setting
)
from .word_generator import generate_word
from .tutor import process_user_message
from config.settings import set_theme_thread_id

_POST_WORD_LOCK = threading.Lock()

# Set up logging
logger = logging.getLogger(__name__)


def _make_dedupe_key(event_id: str | None, message_ts: str) -> str:
    """Generate a safe deduplication key using event_id or message_ts as fallback."""
    return event_id if event_id else f"ts:{message_ts}"


def schedule_daily_word(session_maker, slack_client):
    """Daily word scheduler, is passed session_maker and slack_client from run.py"""
    try:
        logger.info(f"Daily word scheduling check initiated at {datetime.now()}")
        
        # Create actual session from sessionmaker
        with session_maker() as session:
            last_word_flag = check_last_word_flag(session)
            
            if last_word_flag is None:
                logger.info("Last word not responded to yet. Skipping new word generation.")
                return
            
            # Generate and post new word
            post_new_word_workflow(session, slack_client)
            
    except Exception as e:
        logger.error(f"Error in schedule_daily_word: {e}", exc_info=True)


def post_new_word_workflow(session, slack_client):
    """
    Complete workflow for generating and posting a new word
    Step 1: Generate new word using word_generator.generate_word
    Step 2: Create new thread in Slack with the word
    Step 3: Post definitions as first reply in thread
    Step 4: Post examples as second reply in thread
    Step 5: Post instructions as third reply in thread
    Step 6: Only after confirming all Slack posts successful, add word to database with thread_id
    Returns True if entire workflow succeeds
    Returns False and rolls back if any step fails
    Ensures database stays in sync with Slack posts
    """
    with _POST_WORD_LOCK:
        logger.info("Starting post_new_word_workflow")
        thread_id = None
        
        try:
            # Step 1: Generate new word
            logger.debug("Generating new word")
            word_result = generate_word(session)
            
            if word_result["status"] == "waiting":
                # System is in dormant state, no new word needed
                logger.info("System in dormant state - no new word needed")
                return False
            
            if word_result["status"] != "success":
                # Failed to generate word
                logger.error(f"Failed to generate word: {word_result.get('message', 'Unknown error')}")
                return False
            
            word_data = word_result["word_data"]
            slack_messages = word_result["slack_messages"]
            
            logger.info(f"Generated word: {word_data['word']}")
            
            # Step 2: Create new thread with main message
            logger.debug("Creating Slack thread")
            thread_id = slack_client.create_thread(slack_messages[0])
            
            if not thread_id:
                logger.error("Failed to create Slack thread")
                session.rollback()
                return False
            
            logger.info(f"Created thread with ID: {thread_id}")
            
            # Step 3-5: Post replies in order
            for i, message in enumerate(slack_messages[1:], 1):
                logger.debug(f"Posting reply {i} to thread")
                success = slack_client.post_to_thread(thread_id, message)
                if not success:
                    logger.error(f"Failed to post message {i} to thread")
                    session.rollback()
                    return False
            
            # Step 6: All Slack posts successful, save to database with thread_id
            logger.debug("Saving word to database with thread_id")
            new_word = create_word(session, word_data["word"], thread_id=thread_id)
            session.commit()
            
            logger.info(f"Successfully posted word '{word_data['word']}' with thread_id '{thread_id}'")
            return True
            
        except Exception as e:
            logger.error(f"Error in post_new_word_workflow: {str(e)}", exc_info=True)
            session.rollback()
            return False


def handle_user_interaction(session, slack_client, thread_id, user_id, message, event_id=None, message_ts=None):
    """
    Central router for all user interactions in vocabulary threads
    Validates that message is from a user (not bot) and that this event hasn't been processed already.
    Checks if message is in a vocabulary thread
    If user replies "1" (knew the word):
        - Updates known_flag to True in database using update_word_status
        - Immediately triggers post_new_word_workflow for next word
    For any other message:
        - Updates known_flag to False in database using update_word_status
        - Passes to tutor.process_user_message for handling
        - Posts tutor response back to thread
    Returns success/failure status
    """        
    
    logger.info(f"Handling user interaction in thread {thread_id}")
    logger.debug(f"User {user_id} message: {message[:50]}...")
    
    try:
        logger.info(f"Handling interaction from user {user_id} in thread {thread_id}")
        # Get the word associated with this thread
        word = get_word_by_thread(session, thread_id)
        
        if not word:
            logger.warning(f"No word found for thread_id: {thread_id}")
            # This might not be a vocabulary thread, ignore
            return False
        
        # Check if this word already has a response
        if word.known_flag is not None:
            if message.strip() == "1":
                # User wants a new word even though they've already responded to this one
                logger.info(f"User requested new word from already-responded thread for '{word.word}'")
                # Post confirmation and trigger new word

                # Check if there's an unanswered word already posted
                last_word = get_last_word(session)
                if last_word and last_word.known_flag is None:
                # There's already an unanswered word - direct user to respond to it
                    slack_client.post_to_thread(
                        thread_id, 
                        f"There's already a new word waiting for you! Please respond to '{last_word.word}' in its thread before requesting another word."
                    )
                    logger.info(f"User has unanswered word '{last_word.word}' - not posting new word")
                    return True
                slack_client.post_to_thread(
                    thread_id, 
                    "I'll post a new word for you shortly!"
                )
                
                # Generate and post new word
                workflow_success = post_new_word_workflow(session, slack_client)
                
                if workflow_success:
                    logger.info("Successfully posted new word after user request")
                else:
                    logger.warning("Failed to post new word immediately, will retry on schedule")
                
                return True
            
            logger.info(f"Word '{word.word}' already has known_flag set to {word.known_flag}")
            # User is continuing conversation in a thread that's already been responded to
            # Pass to tutor for contextual response
            tutor_response = process_user_message(
                session, 
                thread_id, 
                message, 
                slack_client
            )
            try:
                slack_client.post_to_thread(thread_id, tutor_response)
            except Exception as e:
                logger.error(f"Slack post failed: {e}", exc_info=True)
                return False
            return True
        
        # This is the first response to a new word
        # Check if user replied with "1" (already knew the word)
        if message.strip() == "1":
            logger.info(f"User indicated they knew the word '{word.word}'")
            
            # Update word status to known
            updated_word = update_known_flag(session, word, True)
            session.commit()
            
            if updated_word:
                # Post confirmation message
                slack_client.post_to_thread(
                    thread_id, 
                    "Great! You already knew that word. I'll post a new word for you shortly."
                )
                
                # Immediately generate and post new word
                logger.debug("Triggering new word generation after user knew word")
                workflow_success = post_new_word_workflow(session, slack_client)
                
                if workflow_success:
                    logger.info("Successfully posted new word after user knew previous word")
                else:
                    logger.warning("Failed to post new word immediately, will retry on schedule")
                
                return True
        else:
            logger.info(f"User is learning the word '{word.word}'")
            
            # User is learning the word
            # Update word status to not known (learning)
            updated_word = update_known_flag(session, word, False)
            session.commit()
            
            if updated_word:
                # Generate tutor response
                tutor_response = process_user_message(
                    session, 
                    thread_id, 
                    message, 
                    slack_client
                )
                
                # Post tutor response back to thread
                slack_client.post_to_thread(thread_id, tutor_response)
                
                logger.info(f"Successfully handled learning interaction for word '{word.word}'")
                return True
        
        return False
        
    except Exception as e:
        logger.error(f"Error in handle_user_interaction: {str(e)}", exc_info=True)
        session.rollback()
        return False


def update_word_status(session, thread_id, known_flag_value):
    """
    Updates the known_flag for a word based on thread interaction
    Maps thread_id to corresponding word in database
    Updates known_flag to provided value (True or False)
    Returns updated word object or None if not found
    """
    return update_known_flag_by_thread(session, thread_id, known_flag_value)


def setup_theme_thread(session, slack_client):
    """Sets up the pinned theme thread if it doesn't exist"""
    try:
        # Ensure session is valid
        if session is None:
            logger.error("Session is None in setup_theme_thread")
            return None
            
        # Check for existing theme thread
        existing_theme = session.query(UserTheme).first()
        
        if existing_theme:
            logger.info(f"Found existing theme thread: {existing_theme.thread_id}")
            return existing_theme.thread_id
            
        # Create new theme thread
        theme_message = ("🎯 **Vocabulary Themes**\n\n"
                         "Reply to this thread to set your vocabulary theme (e.g., 'Science', 'Literature', 'Business'). "
                         "Current theme: Literature")
        
        thread_id = slack_client.create_thread(theme_message)
        
        # Save to database
        theme_thread = UserTheme(
            user_id="default",
            thread_id=thread_id,
            theme="Literature"
        )
        session.add(theme_thread)
        session.commit()

        set_theme_thread_id(session, thread_id) 

        
        # Try to pin (optional)
        try:
            if hasattr(slack_client, 'pin_message'):
                slack_client.pin_message(thread_id)
            else:
                logger.warning("Pin message not supported - continuing without pinning")
        except Exception as e:
            logger.warning(f"Could not pin theme thread: {e}")
            
        logger.info(f"Created theme thread: {thread_id}")
        return thread_id
        
    except Exception as e:
        logger.error(f"Error setting up theme thread: {e}")
        session.rollback()
        return None

def handle_theme_update(session, user_id, theme_text, slack_client, thread_id):
    """
    Handles theme updates from the theme thread.
    
    Args:
        session: Database session
        user_id: Slack user ID
        theme_text: The theme text from user
        slack_client: Slack client for responses
        thread_id: Thread ID to respond in
    """
    try:
        # Clean and validate theme text
        theme_text = theme_text.strip()
        
        # Check for clear theme command
        if theme_text.lower() in ['clear theme', 'reset theme', 'no theme', 'remove theme']:
            success = set_theme(session, None, user_id)
            if success:
                response = "✅ Theme cleared. Future words will be from general vocabulary."
            else:
                response = "❌ Failed to clear theme. Please try again after few minutes."
        
        # Validate theme length
        elif len(theme_text) > 100:
            response = "❌ Theme too long. Please keep it under 100 characters."
        
        # Set the new theme
        else:
            success = set_theme(session, theme_text, user_id)
            if success:
                response = f"✅ Theme set to: **{theme_text}**\nFuture vocabulary words will relate to this theme."
            else:
                response = "❌ Failed to set theme. Please try again."
        
        # Post response in thread
        slack_client.post_to_thread(thread_id, response)
        
        # Log theme change
        logger.info(f"Theme updated for user {user_id}: {theme_text}")
        
    except Exception as e:
        logger.error(f"Error handling theme update: {e}")
        slack_client.post_to_thread(
            thread_id, 
            "❌ An error occurred while updating the theme. Please try again."
        )

def is_theme_thread(session, thread_id):
    """Check if a thread is the theme settings thread"""
    theme_thread_id = get_system_setting(session,'theme_thread_id')
    return theme_thread_id and thread_id == theme_thread_id

def initialize_fresh_database(session, slack_client):
    """
    Handle fresh database initialization workflow:
    1. Clear all data
    2. Setup theme thread with default theme
    3. Generate first word based on default theme
    """
    try:
        logger.info("Starting fresh database initialization")
        
        # Clear all existing data
        if clear_all_data(session):
            logger.info("Cleared all existing data")
        
        set_theme_thread_id(session, None)

        # Setup theme thread with default theme
        theme_thread_id = setup_theme_thread(session, slack_client)
        
        if theme_thread_id:

            # Generate first word with default theme
            logger.info("Generating first word with Literature theme")
            success = post_new_word_workflow(session, slack_client)
            
            if success:
                logger.info("Fresh initialization complete - first word posted")
                return True
            else:
                logger.error("Failed to post first word during initialization")
                return False
        else:
            logger.error("Failed to setup theme thread")
            return False
            
    except Exception as e:
        logger.error(f"Error in fresh initialization: {e}")
        return False

