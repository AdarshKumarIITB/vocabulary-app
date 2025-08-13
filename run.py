import os
import signal
import sys
import threading
import logging
from flask import Flask, request, jsonify

from config.settings import load_config
from database.database import create_engine_and_session, init_database
from llm_backend.orchestrator import schedule_daily_word, handle_user_interaction
from slack_integration.slack_client import SlackClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Flask app
app = Flask(__name__)

# Global variables (will be initialized)
session_maker = None
slack_client = None
scheduler_thread = None
config = None

def initialize_components():
    """Initialize all application components"""
    global session_maker, slack_client, config
    
    try:
        # Load configuration
        config = load_config()
        logger.info("Configuration loaded successfully")
        
        # Initialize database
        engine, session_maker = create_engine_and_session()
        init_database(engine)
        logger.info("Database initialized successfully")
        
        # Initialize Slack client
        slack_client = SlackClient(
            token=config['slack_bot_token'],
            channel_id=config['slack_channel_id']
        )
        logger.info("Slack client initialized successfully")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize application: {e}")
        return False

def start_background_scheduler():
    """Start the daily word scheduler in background thread"""
    global scheduler_thread
    
    try:
        scheduler_thread = threading.Thread(
            target=schedule_daily_word,
            args=(session_maker, slack_client),
            daemon=True
        )
        scheduler_thread.start()
        logger.info("Daily word scheduler started")
        
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy"}), 200

@app.route('/slack/events', methods=['POST'])
def slack_events():
    """Handle Slack webhook events"""
    try:
        data = request.get_json()
        
        # Handle URL verification challenge
        if data.get("type") == "url_verification":
            return jsonify({"challenge": data.get("challenge")})
        
        # Handle events
        if data.get("type") == "event_callback":
            event = data.get("event", {})
            
            # Only process message events in threads
            if (event.get("type") == "message" and 
                event.get("thread_ts") and 
                not event.get("bot_id")):
                
                thread_id = event.get("thread_ts")
                user_id = event.get("user")
                message = event.get("text", "")
                
                # Handle the interaction
                with session_maker() as session:
                    handle_user_interaction(
                        session=session,
                        slack_client=slack_client,
                        thread_id=thread_id,
                        user_id=user_id,
                        message=message
                    )
        
        return jsonify({"status": "ok"}), 200
        
    except Exception as e:
        logger.error(f"Error handling Slack event: {e}")
        return jsonify({"error": "Internal server error"}), 500

def handle_shutdown(signum, frame):
    """Gracefully handle application shutdown"""
    logger.info("Received shutdown signal, cleaning up...")
    
    if scheduler_thread and scheduler_thread.is_alive():
        logger.info("Stopping scheduler...")
    
    logger.info("Application shutdown complete")
    sys.exit(0)

# Initialize application components when imported by Gunicorn
def create_app():
    """Application factory for Gunicorn"""
    logger.info("Creating Vocabulary Tutor application...")
    
    # Initialize components
    if not initialize_components():
        logger.error("Application initialization failed")
        raise RuntimeError("Failed to initialize application")
    
    # Start scheduler
    start_background_scheduler()
    
    logger.info("Application created successfully")
    return app

# For Gunicorn: create app instance
app = create_app()

def main():
    """Main entry point for development server"""
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)
    
    # Get port from environment
    port = int(os.environ.get('PORT', 3000))
    
    logger.info(f"Starting development server on port {port}")
    logger.warning("Using Flask development server - not suitable for production!")
    
    # Start Flask app (development only)
    app.run(
        host='0.0.0.0',
        port=port,
        debug=False
    )

if __name__ == "__main__":
    main()