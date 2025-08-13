import os
import signal
import sys
import threading
import time
import logging
from flask import Flask, request, jsonify
from waitress import serve

from llm_backend.main import initialize_application, start_scheduler as start_main_scheduler, webhook_handler, stop_scheduler
from slack_integration.slack_client import SlackClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global variables
app = Flask(__name__)
session_maker = None
slack_client = None
scheduler_thread = None
openai_client = None

def initialize_app():
    """Initialize all application components"""
    global session_maker, slack_client, openai_client
    
    try:
        components = initialize_application()
        slack_client = components['slack_client']
        session_maker = components['db_session']
        openai_client = components['openai_client']
        return True
    except Exception as e:
        logger.error(f"Failed to initialize application: {e}")
        return False

def start_scheduler():
    """Start the daily word scheduler from main.py"""
    try:
        start_main_scheduler()    
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy"}), 200

@app.route('/slack/events', methods=['POST'])
def slack_events():
    """Handle Slack webhook events using main.py webhook_handler"""
    try:
        result = webhook_handler(request.get_json())
        return jsonify(result.get('body', {})), result.get('statusCode', 200)
    except Exception as e:
        logger.error(f"Error handling Slack event: {e}")
        return jsonify({"error": "Internal server error"}), 500

def handle_shutdown(signum, frame):
    """Gracefully handle application shutdown"""
    logger.info("Received shutdown signal, cleaning up...")
    stop_scheduler()
    logger.info("Application shutdown complete")
    sys.exit(0)

def main():
    """Main application entry point"""
    logger.info("Starting Vocabulary Tutor application...")
    
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)
    
    # Initialize application
    if not initialize_app():
        logger.error("Application initialization failed")
        sys.exit(1)
    
    # Start scheduler
    start_scheduler()
    
    # Get port from environment (Railway sets this)
    port = int(os.environ.get('PORT', 3000))
    
    logger.info(f"Starting webhook server on port {port}")
    
    # Start Flask app
    serve(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()