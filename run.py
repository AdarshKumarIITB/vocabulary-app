#!/usr/bin/env python3
"""
Vocabulary Tutor Application Entry Point
Production-ready with comprehensive error handling
"""

import sys
import signal
import logging
import threading
import schedule
import time
from datetime import datetime
from flask import Flask, request, jsonify
from logging.handlers import RotatingFileHandler
import io,os

# Import all components
from config.settings import load_config
from database.database import create_engine_and_session, init_database, test_connection
from database.models import cleanup_old_events
from llm_backend.main import initialize_application, webhook_handler, cleanup_old_data
from llm_backend.orchestrator import schedule_daily_word, setup_theme_thread

# Setup logging
def setup_logging():
    """Configure comprehensive logging with Unicode support"""
    # Fix for Windows console encoding issues
    if sys.platform == 'win32':
        # Set console to UTF-8
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    
    # Create logs directory if it doesn't exist
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Console handler with UTF-8 encoding
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(console_formatter)
    
    # File handler with rotation and UTF-8 encoding
    file_handler = RotatingFileHandler(
        'logs/vocabulary_tutor.log',
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
    )
    file_handler.setFormatter(file_formatter)
    
    # Error file handler with UTF-8 encoding
    error_handler = RotatingFileHandler(
        'logs/errors.log',
        maxBytes=10*1024*1024,
        backupCount=5,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(file_formatter)
    
    # Add handlers
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(error_handler)
    
    return root_logger

logger = setup_logging()

# Flask app for webhooks
app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False

# Global variables for graceful shutdown
shutdown_flag = threading.Event()
scheduler_thread = None
cleanup_thread = None
app_components = {}

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        # Check database connection
        db_healthy = test_connection(app_components.get('engine'))
        
        # Check Slack connection (you could ping Slack API here)
        slack_healthy = app_components.get('slack_client') is not None
        
        if db_healthy and slack_healthy:
            return jsonify({
                'status': 'healthy',
                'timestamp': datetime.utcnow().isoformat(),
                'components': {
                    'database': 'healthy',
                    'slack': 'healthy'
                }
            }), 200
        else:
            return jsonify({
                'status': 'degraded',
                'timestamp': datetime.utcnow().isoformat(),
                'components': {
                    'database': 'healthy' if db_healthy else 'unhealthy',
                    'slack': 'healthy' if slack_healthy else 'unhealthy'
                }
            }), 503
            
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 503

@app.route('/slack/events', methods=['POST'])
def slack_events():
    """Webhook endpoint for Slack events"""
    try:
        # Get request data
        request_data = request.get_json()
        
        # Log request for debugging (be careful with sensitive data)
        logger.debug(f"Received webhook: {request_data.get('event', {}).get('type')}")
        
        # Process with error handling
        result = webhook_handler(request_data)
        
        # Return appropriate response
        status_code = result.get('statusCode', 200)
        body = result.get('body', 'OK')
        
        if status_code == 200:
            return body, 200
        else:
            return jsonify({'error': body}), status_code
            
    except Exception as e:
        logger.error(f"Webhook processing failed: {e}", exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500

def run_scheduler():
    """Run the scheduler in a separate thread"""
    logger.info("Scheduler thread started")
    
    while not shutdown_flag.is_set():
        try:
            schedule.run_pending()
            time.sleep(1)
        except Exception as e:
            logger.error(f"Scheduler error: {e}", exc_info=True)
            time.sleep(5)  # Wait before retrying
            
    logger.info("Scheduler thread stopped")

def run_cleanup():
    """Run periodic cleanup tasks"""
    logger.info("Cleanup thread started")
    
    while not shutdown_flag.is_set():
        try:
            # Run cleanup every hour
            cleanup_old_data()
            
            # Sleep for an hour, but check shutdown flag every second
            for _ in range(3600):
                if shutdown_flag.is_set():
                    break
                time.sleep(1)
                
        except Exception as e:
            logger.error(f"Cleanup error: {e}", exc_info=True)
            time.sleep(300)  # Wait 5 minutes before retrying
            
    logger.info("Cleanup thread stopped")

def handle_shutdown(signum, frame):
    """Gracefully handle shutdown signals"""
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    
    # Set shutdown flag
    shutdown_flag.set()
    
    # Wait for threads to finish (with timeout)
    if scheduler_thread and scheduler_thread.is_alive():
        scheduler_thread.join(timeout=5)
        
    if cleanup_thread and cleanup_thread.is_alive():
        cleanup_thread.join(timeout=5)
    
    logger.info("Shutdown complete")
    sys.exit(0)

def main():
    """Main entry point"""
    global scheduler_thread, cleanup_thread, app_components
    
    try:
        logger.info("=" * 50)
        logger.info("Starting Vocabulary Tutor Application")
        logger.info("=" * 50)
        
        # Initialize all components
        logger.info("Initializing application components...")
        app_components = initialize_application()
        
        if not app_components:
            logger.error("Failed to initialize application")
            sys.exit(1)
            
        # Setup theme thread
        logger.info("Setting up theme thread...")
        theme_thread_id = setup_theme_thread(app_components['slack_client'])
        if theme_thread_id:
            logger.info(f"Theme thread ready: {theme_thread_id}")
        else:
            logger.warning("Could not setup theme thread, continuing without it")
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, handle_shutdown)
        signal.signal(signal.SIGTERM, handle_shutdown)
        
        # Start scheduler thread
        logger.info("Starting scheduler thread...")
        scheduler_thread = threading.Thread(target=run_scheduler, daemon=False)
        scheduler_thread.start()
        
        # Start cleanup thread
        logger.info("Starting cleanup thread...")
        cleanup_thread = threading.Thread(target=run_cleanup, daemon=False)
        cleanup_thread.start()
        
        # Schedule daily word posting
        config = app_components['config']
        daily_time = config.get('daily_word_time', '09:00')
        schedule.every().day.at(daily_time).do(
            lambda: schedule_daily_word(
                app_components['db_session'],
                app_components['slack_client']
            )
        )
        logger.info(f"Scheduled daily word posting at {daily_time}")
        
        # Start Flask server
        logger.info("Starting webhook server on port 3000...")
        app.run(
            host='0.0.0.0',
            port=3000,
            debug=False,  # Never use debug=True in production
            threaded=True,  # Handle concurrent requests
            use_reloader=False  # Prevent double initialization
        )
        
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
        handle_shutdown(signal.SIGINT, None)
        
    except Exception as e:
        logger.error(f"Fatal error in main: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()