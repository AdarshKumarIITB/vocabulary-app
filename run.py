#!/usr/bin/env python3
"""
Production-ready entry point for Vocabulary Tutor application.
Handles all common failure scenarios and provides comprehensive logging.
"""

import os
import sys
import time
import signal
import logging
import traceback
from datetime import datetime
from threading import Thread, Event
from flask import Flask, request, jsonify
import schedule

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import load_config, get_database_url, get_slack_config, get_openai_config, get_scheduler_config
from database.database import create_engine_and_session, init_database, get_session, test_connection
from llm_backend.orchestrator import handle_user_interaction, post_new_word_workflow
from slack_integration.slack_client import SlackClient

# Configure logging with more detail
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('vocabulary_tutor.log')
    ]
)
logger = logging.getLogger(__name__)

# Global variables for graceful shutdown
app = Flask(__name__)
shutdown_event = Event()
scheduler_thread = None
engine = None
SessionLocal = None
slack_client = None
config = None

def initialize_application():
    """Initialize all application components with comprehensive error handling."""
    global engine, SessionLocal, slack_client, config
    
    try:
        logger.info("=" * 50)
        logger.info("Starting Vocabulary Tutor Application")
        logger.info(f"Start time: {datetime.now()}")
        logger.info("=" * 50)
        
        # Load configuration
        logger.info("Loading configuration...")
        config = load_config()
        logger.info("Configuration loaded successfully")
        
        # Initialize database
        logger.info("Initializing database connection...")
        database_url = get_database_url()
        engine, SessionLocal = create_engine_and_session()
        
        # Test database connection
        if not test_connection(engine):
            raise Exception("Database connection test failed")
        logger.info("Database connection successful")
        
        # Initialize database schema
        logger.info("Initializing database schema...")
        init_database(engine)
        logger.info("Database schema initialized")
        
        # Initialize Slack client
        logger.info("Initializing Slack client...")
        slack_config = get_slack_config()
        slack_client = SlackClient(
            token=slack_config['bot_token'],
            channel_id=slack_config['channel_id']
        )
        logger.info("Slack client initialized successfully")
        
        # Verify OpenAI configuration
        logger.info("Verifying OpenAI configuration...")
        openai_config = get_openai_config()
        if not openai_config.get('api_key'):
            raise Exception("OpenAI API key not configured")
        logger.info("OpenAI configuration verified")
        
        logger.info("Application initialization complete!")
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize application: {str(e)}")
        logger.error(traceback.format_exc())
        return False

def run_scheduled_word():
    """Execute scheduled word posting with error handling."""
    if shutdown_event.is_set():
        return
    
    try:
        logger.info("Running scheduled word posting...")
        with get_session() as session:
            success = post_new_word_workflow(session, slack_client)
            if success:
                logger.info("Scheduled word posted successfully")
            else:
                logger.info("Conditions not met for posting new word (waiting for user response)")
    except Exception as e:
        logger.error(f"Error in scheduled word posting: {str(e)}")
        logger.error(traceback.format_exc())
        # Don't crash the scheduler thread - continue running

def scheduler_worker():
    """Background thread for running scheduled tasks."""
    logger.info("Scheduler thread started")
    
    while not shutdown_event.is_set():
        try:
            schedule.run_pending()
            time.sleep(30)  # Check every 30 seconds
        except Exception as e:
            logger.error(f"Error in scheduler: {str(e)}")
            logger.error(traceback.format_exc())
            time.sleep(60)  # Wait a bit longer if there's an error
    
    logger.info("Scheduler thread stopped")

def start_scheduler():
    """Start the background scheduler for daily word posting."""
    global scheduler_thread
    
    try:
        scheduler_config = get_scheduler_config()
        daily_time = scheduler_config.get('daily_word_time', '09:00')
        
        logger.info(f"Setting up daily word posting at {daily_time}")
        schedule.every().day.at(daily_time).do(run_scheduled_word)
        
        # Also run immediately on startup if needed
        logger.info("Checking if immediate word posting is needed...")
        run_scheduled_word()
        
        # Start scheduler thread
        scheduler_thread = Thread(target=scheduler_worker, daemon=True)
        scheduler_thread.start()
        logger.info("Scheduler started successfully")
        
    except Exception as e:
        logger.error(f"Failed to start scheduler: {str(e)}")
        logger.error(traceback.format_exc())

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for monitoring."""
    try:
        # Check database connection
        db_healthy = test_connection(engine) if engine else False
        
        # Check Slack client
        slack_healthy = slack_client is not None
        
        # Overall health
        healthy = db_healthy and slack_healthy
        
        return jsonify({
            'status': 'healthy' if healthy else 'unhealthy',
            'timestamp': datetime.now().isoformat(),
            'components': {
                'database': 'connected' if db_healthy else 'disconnected',
                'slack': 'initialized' if slack_healthy else 'not initialized'
            }
        }), 200 if healthy else 503
        
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 503

@app.route('/slack/events', methods=['POST'])
def slack_events():
    """Handle incoming Slack events."""
    try:
        data = request.get_json()
        
        # Handle Slack URL verification challenge
        if data and data.get('type') == 'url_verification':
            logger.info("Handling Slack URL verification challenge")
            return jsonify({'challenge': data.get('challenge')}), 200
        
        # Handle event callbacks
        if data and data.get('type') == 'event_callback':
            event = data.get('event', {})
            
            # Log event for debugging
            logger.debug(f"Received Slack event: {event.get('type')}")
            
            # Filter out bot messages and subtypes we don't care about
            if event.get('bot_id') or event.get('subtype'):
                logger.debug("Ignoring bot message or subtype")
                return '', 200
            
            # Only process messages in threads
            thread_ts = event.get('thread_ts')
            if not thread_ts:
                logger.debug("Ignoring message not in thread")
                return '', 200
            
            # Extract event details
            user_id = event.get('user')
            text = event.get('text', '')
            channel = event.get('channel')
            
            # Verify it's from our vocabulary channel
            if channel != slack_client.channel_id:
                logger.debug(f"Ignoring message from different channel: {channel}")
                return '', 200
            
            logger.info(f"Processing user message in thread {thread_ts}: {text[:50]}...")
            
            # Process in a separate thread to respond quickly to Slack
            Thread(
                target=process_slack_event_async,
                args=(thread_ts, user_id, text),
                daemon=True
            ).start()
            
            return '', 200
        
        # Return success for any other event types
        return '', 200
        
    except Exception as e:
        logger.error(f"Error handling Slack event: {str(e)}")
        logger.error(traceback.format_exc())
        # Return 200 to prevent Slack from retrying
        return '', 200

def process_slack_event_async(thread_id, user_id, message):
    """Process Slack events asynchronously to avoid timeout."""
    try:
        with get_session() as session:
            handle_user_interaction(
                session=session,
                slack_client=slack_client,
                thread_id=thread_id,
                user_id=user_id,
                message=message
            )
    except Exception as e:
        logger.error(f"Error processing Slack event: {str(e)}")
        logger.error(traceback.format_exc())
        # Try to notify user of error
        try:
            slack_client.post_to_thread(
                thread_id,
                "I encountered an error processing your message. Please try again later."
            )
        except:
            pass  # If we can't even post error message, just log and continue

def handle_shutdown(signum, frame):
    """Gracefully handle application shutdown."""
    logger.info(f"Received shutdown signal {signum}")
    shutdown_event.set()
    
    # Wait for scheduler thread to stop
    if scheduler_thread and scheduler_thread.is_alive():
        logger.info("Waiting for scheduler thread to stop...")
        scheduler_thread.join(timeout=5)
    
    # Close database connections
    if engine:
        logger.info("Closing database connections...")
        engine.dispose()
    
    logger.info("Shutdown complete")
    sys.exit(0)

# Initialize app on module load (for Gunicorn)
# This runs when Gunicorn imports the module
if not initialize_application():
    logger.error("Failed to initialize application. Exiting.")
    sys.exit(1)

# Start scheduler on module load
start_scheduler()

def main():
    """Main entry point for direct execution (development/testing)."""
    # This function only runs when executing directly, not via Gunicorn
    try:
        port = int(os.environ.get('PORT', 3000))
        logger.info(f"Starting development server on port {port}")
        logger.warning("Using Flask development server. Use Gunicorn for production!")
        
        # Development server settings
        app.run(
            host='0.0.0.0',
            port=port,
            debug=False,
            use_reloader=False,
            threaded=True,
        )
    except Exception as e:
        logger.error(f"Failed to start web server: {str(e)}")
        logger.error(traceback.format_exc())
        sys.exit(1)

# Set up signal handlers at module level
signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)

if __name__ == "__main__":
    # Only runs when executing directly: python run.py
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
        handle_shutdown(signal.SIGINT, None)
    except Exception as e:
        logger.error(f"Unhandled exception in main: {str(e)}")
        logger.error(traceback.format_exc())
        sys.exit(1)