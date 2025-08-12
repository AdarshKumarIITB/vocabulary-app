"""
LLM Backend Main Module - Complete Implementation
Handles initialization, scheduling, and webhook processing
"""

import logging
import schedule
import time
import threading
import json
from datetime import datetime
from functools import wraps

from config.settings import load_config, get_database_url, get_slack_config, get_openai_config, get_scheduler_config, get_theme_thread_id, set_theme_thread_id
from database.database import create_engine_and_session, init_database, get_session
from database.models import WordHistory, check_last_word_flag, add_processed_event, check_event_processed, cleanup_old_events
from slack_integration.slack_client import SlackClient
from llm_backend.orchestrator import post_new_word_workflow, handle_user_interaction
from openai import OpenAI
from utils.cache import TTLCache, RateLimiter  # Ensure these exist
from .orchestrator import handle_theme_update, setup_theme_thread

logger = logging.getLogger(__name__)

# Global variables for components
app_components = {
    'config': None,
    'db_session': None,
    'slack_client': None,
    'openai_client': None,
    'scheduler_thread': None,
    'scheduler_stop_event': None
}

# Initialize caches and rate limiters
event_cache = TTLCache(max_size=10000, ttl_seconds=3600)
slack_rate_limiter = RateLimiter(max_calls=60, time_window=60)  # 60 calls per minute
openai_rate_limiter = RateLimiter(max_calls=50, time_window=60)  # 50 calls per minute


def initialize_application():
    """Initialize all application components"""
    logger.info("Initializing application components...")
    
    try:
        # Load configuration
        config = load_config()
        logger.info("✓ Configuration loaded")
        
        # Initialize database
        engine, SessionMaker = create_engine_and_session()
        init_database(engine)
        logger.info("✓ Database initialized")
        
        # Initialize Slack client
        slack_client = SlackClient(
            token=config['slack_bot_token'],
            channel_id=config['slack_channel_id']
        )
        logger.info("✓ Slack client initialized")
        
        # Initialize OpenAI client
        openai_client = OpenAI(api_key=config['openai_api_key'])
        logger.info("✓ OpenAI client initialized")
        
        # Set up theme thread with proper session management
        with get_session() as session:
            try:
                setup_theme_thread(session, slack_client)
            except Exception as e:
                logger.error(f"Error setting up theme thread: {e}")
                # Continue initialization even if theme setup fails
        
        logger.info("Application initialization complete")
        
        components = {
            'config': config,
            'db_session': SessionMaker,
            'slack_client': slack_client,
            'openai_client': openai_client
        }

        global app_components
        app_components.update(components)

        return components
        
    except Exception as e:
        logger.error(f"Failed to initialize application: {e}")
        raise


def scheduled_word_job():
    """Job function that runs on schedule to post new words"""
    try:
        logger.info("Running scheduled word posting job...")
        
        with get_session() as session:
            # Check if we should post a new word
            last_word_flag = check_last_word_flag(session)
            
            if last_word_flag is None:
                # No words yet, or last word hasn't been responded to
                if session.query(WordHistory).count() == 0:
                    # No words at all, post the first one
                    logger.info("Posting first word of the day")
                    if app_components['slack_client']:
                        post_new_word_workflow(session, app_components['slack_client'])
                    else:
                        logger.warning("Slack client not configured, skipping word post")
                else:
                    logger.info("Waiting for user response to previous word")
            else:
                # User has responded, post new word
                logger.info("User has responded to previous word, posting new word")
                if app_components['slack_client']:
                    post_new_word_workflow(session, app_components['slack_client'])
                else:
                    logger.warning("Slack client not configured, skipping word post")
                    
    except Exception as e:
        logger.error(f"Error in scheduled job: {e}")


def scheduler_worker():
    """Worker function that runs the scheduler in a separate thread"""
    logger.info("Scheduler thread started")
    
    while not app_components['scheduler_stop_event'].is_set():
        schedule.run_pending()
        time.sleep(60)  # Check every minute
    
    logger.info("Scheduler thread stopped")


def start_scheduler():
    """
    Starts the background scheduler for daily word posting
    """
    try:
        scheduler_config = get_scheduler_config()
        
        # Schedule the daily job
        daily_time = scheduler_config['daily_word_time']
        logger.info(f"Scheduling daily word posting at {daily_time}")
        
        schedule.every().day.at(daily_time).do(scheduled_word_job)
        
        # Also run immediately if this is the first run
        if app_components['db_session']:
            with get_session() as session:
                if session.query(WordHistory).count() == 0:
                    logger.info("No words in database, running initial word post")
                    scheduled_word_job()
        
        # Start scheduler thread
        app_components['scheduler_stop_event'] = threading.Event()
        scheduler_thread = threading.Thread(target=scheduler_worker, daemon=True)
        scheduler_thread.start()
        app_components['scheduler_thread'] = scheduler_thread
        
        logger.info(f"Scheduler started - will post daily at {daily_time}")
        return scheduler_thread
        
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")
        raise


def stop_scheduler():
    """Stops the scheduler thread gracefully"""
    if app_components['scheduler_stop_event']:
        logger.info("Stopping scheduler...")
        app_components['scheduler_stop_event'].set()
        
        if app_components['scheduler_thread']:
            app_components['scheduler_thread'].join(timeout=5)
            logger.info("Scheduler stopped")


def with_retry(max_retries=3, backoff_factor=2):
    """Decorator for retry logic with exponential backoff"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        wait_time = backoff_factor ** attempt
                        logger.warning(f"{func.__name__} failed (attempt {attempt + 1}/{max_retries}), "
                                     f"retrying in {wait_time}s: {e}")
                        time.sleep(wait_time)
                    else:
                        logger.error(f"{func.__name__} failed after {max_retries} attempts: {e}")
            raise last_exception
        return wrapper
    return decorator


def webhook_handler(request_data):
    """Enhanced webhook handler with comprehensive error handling"""
    try:
        # Parse request body
        try:
            data = json.loads(request_data) if isinstance(request_data, str) else request_data
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in webhook: {e}")
            return {'statusCode': 400, 'body': 'Invalid JSON'}
        
        # Handle Slack URL verification
        if data.get('type') == 'url_verification':
            return {'statusCode': 200, 'body': data.get('challenge')}
        
        # Extract event
        event = data.get('event', {})
        if not event:
            logger.warning("No event in webhook payload")
            return {'statusCode': 200, 'body': 'No event'}
        
        # Generate deduplication key
        dedupe_key = _generate_dedupe_key(event, data)
        if not dedupe_key:
            logger.error("Could not generate deduplication key")
            # Still process but log for monitoring
            dedupe_key = f"fallback_{datetime.now().timestamp()}"
        
        # Check if already processed (memory cache first, then DB)
        if event_cache.contains(dedupe_key):
            logger.debug(f"Event already processed (cache hit): {dedupe_key}")
            return {'statusCode': 200, 'body': 'Already processed'}
        
        # Check database for deduplication (with error handling)
        try:
            with get_session() as session:
                if check_event_processed(session, dedupe_key):
                    logger.debug(f"Event already processed (DB hit): {dedupe_key}")
                    event_cache.add(dedupe_key)  # Add to cache to avoid DB lookups
                    return {'statusCode': 200, 'body': 'Already processed'}
        except Exception as e:
            logger.error(f"Database deduplication check failed: {e}")
            # Continue processing even if DB check fails
        
        # Rate limiting check
        if not slack_rate_limiter.is_allowed():
            wait_time = slack_rate_limiter.wait_time()
            logger.warning(f"Rate limit exceeded, need to wait {wait_time}s")
            return {'statusCode': 429, 'body': f'Rate limited. Retry after {wait_time}s'}
        
        # Process the event
        try:
            result = _process_event_with_error_handling(event, data)
            
            # Mark as processed after successful handling
            event_cache.add(dedupe_key)
            try:
                with get_session() as session:
                    add_processed_event(session, dedupe_key, event.get('type'))
            except Exception as e:
                logger.error(f"Failed to persist processed event to DB: {e}")
                # Continue - cache will prevent reprocessing for TTL duration
            
            return result
            
        except Exception as e:
            logger.error(f"Error processing event: {e}", exc_info=True)
            # Don't mark as processed if there was an error
            return {'statusCode': 500, 'body': 'Internal error'}
            
    except Exception as e:
        logger.error(f"Unexpected error in webhook handler: {e}", exc_info=True)
        return {'statusCode': 500, 'body': 'Internal server error'}

def _generate_dedupe_key(event, data):
    """Generate a deduplication key with multiple fallbacks"""
    try:
        # Priority 1: event_id (most reliable)
        if event_id := data.get('event_id'):
            return f"event_{event_id}"
        
        # Priority 2: client_msg_id for user messages
        if client_msg_id := event.get('client_msg_id'):
            return f"client_{client_msg_id}"
        
        # Priority 3: combination of ts + user/bot
        if ts := event.get('ts'):
            user_or_bot = event.get('user', event.get('bot_id', 'unknown'))
            return f"ts_{ts}_{user_or_bot}"
        
        # Priority 4: event_time + type
        if event_time := data.get('event_time'):
            event_type = event.get('type', 'unknown')
            return f"time_{event_time}_{event_type}"
            
        logger.warning("Could not generate reliable dedupe key")
        return None
        
    except Exception as e:
        logger.error(f"Error generating dedupe key: {e}")
        return None

def _process_event_with_error_handling(event, data):
    """Process event with comprehensive error handling"""
    try:
        event_type = event.get('type')
        
        # Skip bot messages
        if event.get('bot_id'):
            logger.debug("Skipping bot message")
            return {'statusCode': 200, 'body': 'Bot message ignored'}
        
        # Handle only message events in threads
        if event_type != 'message':
            logger.debug(f"Ignoring non-message event: {event_type}")
            return {'statusCode': 200, 'body': 'Not a message event'}
        
        # Check if it's a thread message
        thread_ts = event.get('thread_ts')
        if not thread_ts:
            logger.debug("Not a thread message")
            return {'statusCode': 200, 'body': 'Not in thread'}
        
        # Extract necessary information
        user_id = event.get('user')
        text = event.get('text', '').strip()
        channel = event.get('channel')
        
        if not user_id or not text:
            logger.warning(f"Missing user_id or text: user={user_id}, text={text}")
            return {'statusCode': 200, 'body': 'Missing data'}
        
        # Check if this is the theme thread
        with get_session() as session:
            if _is_theme_thread(thread_ts, channel,session):
                return _handle_theme_update(user_id, text,session)
        
        # Process as vocabulary interaction
        # Extract event_id and message_ts for deduplication
        event_id = data.get('event_id', '')
        message_ts = event.get('ts', '')

        logger.debug(f"Processing vocabulary interaction: thread={thread_ts}, user={user_id}, text={text[:50]}")

        
        with get_session() as session:
            # Call with ALL required parameters
            handle_user_interaction(
                session=session,
                slack_client=app_components['slack_client'],
                thread_id=thread_ts,
                user_id=user_id,
                message=text,
                event_id=event_id,
                message_ts=message_ts
            )
        
        return {'statusCode': 200, 'body': 'Processed'}
        
    except Exception as e:
        logger.error(f"Error in event processing: {e}", exc_info=True)
        raise



def _is_theme_thread(thread_ts, channel,session):
    """Check if this is the theme settings thread"""
    theme_thread_id = get_theme_thread_id(session)  # Ensure get_theme_thread_id() is defined/imported
    return theme_thread_id and thread_ts == theme_thread_id

def _handle_theme_update(user_id, text,session):
    """Process theme updates from the theme thread"""
    try:
        slack_client = app_components['slack_client']  # retrieve global instance
        thread_id=get_theme_thread_id(session)
        with get_session() as session:
            handle_theme_update(
                session=session,
                user_id=user_id,
                theme_text=text,
                slack_client=slack_client,
                thread_id=thread_id
            )
        return {'statusCode': 200, 'body': 'Theme updated'}
    except Exception as e:
        logger.error(f"Error updating theme: {e}")
        return {'statusCode': 500, 'body': 'Failed to update theme'}

# Cleanup job to run periodically
def cleanup_old_data():
    """Clean up old processed events from database"""
    try:
        with get_session() as session:
            cleanup_old_events(session, hours=24)
        logger.info("Cleanup job completed successfully")
    except Exception as e:
        logger.error(f"Cleanup job failed: {e}")