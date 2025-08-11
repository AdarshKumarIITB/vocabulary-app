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

from config.settings import load_config, get_database_url, get_slack_config, get_openai_config, get_scheduler_config
from database.database import create_engine_and_session, init_database, get_session
from database.models import WordHistory, check_last_word_flag
from slack_integration.slack_client import SlackClient
from llm_backend.orchestrator import post_new_word_workflow, handle_user_interaction
from openai import OpenAI

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


def initialize_application():
    """
    Main initialization function that sets up all components
    """
    try:
        logger.info("Initializing application components...")
        
        # Load configuration
        config = load_config()
        app_components['config'] = config
        logger.info("✓ Configuration loaded")
        
        # Initialize database
        database_url = get_database_url()
        if not database_url:
            raise ValueError("DATABASE_URL not configured")
        
        engine, SessionMaker = create_engine_and_session()
        init_database(engine)
        app_components['db_session'] = SessionMaker
        logger.info("✓ Database initialized")
        
        # Initialize Slack client
        slack_config = get_slack_config()
        if not slack_config['bot_token'] or not slack_config['channel_id']:
            logger.warning("⚠ Slack credentials not fully configured - using mock mode")
            app_components['slack_client'] = None
        else:
            slack_client = SlackClient(
                slack_config['bot_token'],
                slack_config['channel_id']
            )
            app_components['slack_client'] = slack_client
            logger.info("✓ Slack client initialized")
        
        # Initialize OpenAI client
        openai_config = get_openai_config()
        if not openai_config['api_key']:
            logger.warning("⚠ OpenAI API key not configured")
            app_components['openai_client'] = None
        else:
            openai_client = OpenAI(api_key=openai_config['api_key'])
            app_components['openai_client'] = openai_client
            logger.info("✓ OpenAI client initialized")
        
        logger.info("Application initialization complete")
        return app_components
        
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


def webhook_handler(request_data):
    """
    Processes incoming webhooks from Slack
    """
    try:
        # Handle Slack URL verification challenge
        if 'challenge' in request_data:
            logger.info("Handling Slack URL verification challenge")
            return {
                'statusCode': 200,
                'body': request_data['challenge']
            }
        
        # Parse the event
        if 'event' not in request_data:
            logger.warning("No event in webhook payload")
            return {'statusCode': 200, 'body': 'OK'}
        
        event = request_data['event']
        event_id = request_data.get("event_id")
        message_ts = event.get("ts")
        
        # Ignore bot messages to prevent loops
        if event.get('bot_id') or event.get('subtype') == 'bot_message':
            return {'statusCode': 200, 'body': 'Ignoring bot message'}
        
        # Check if it's a message event
        if event.get('type') != 'message':
            return {'statusCode': 200, 'body': 'Not a message event'}
        
        # Extract relevant information
        thread_ts = event.get("thread_ts") or event.get("ts")
        user_id = event.get("user")
        message_text = event.get("text", "")
        
        if not user_id or not message_text:
            return {'statusCode': 200, 'body': 'Missing user or text'}
        
        logger.info(f"Processing message from user {user_id} in thread {thread_ts}: {message_text}")
        
        # Route to orchestrator with deduplication parameters
        if app_components['slack_client']:
            with get_session() as session:
                success = handle_user_interaction(
                    session,
                    app_components['slack_client'],
                    thread_id=thread_ts,
                    user_id=user_id,
                    message=message_text,
                    event_id=event_id,
                    message_ts=message_ts,
                )
                
                if success:
                    logger.info("User interaction handled successfully")
                else:
                    logger.warning("Failed to handle user interaction")
        else:
            logger.warning("Slack client not configured, cannot handle interaction")
        
        return {'statusCode': 200, 'body': 'OK'}
        
    except Exception as e:
        logger.error(f"Error handling webhook: {e}")
        # Still return 200 to prevent Slack retries
        return {'statusCode': 200, 'body': 'Error processed'}