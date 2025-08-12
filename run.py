#!/usr/bin/env python3
"""
Vocabulary Tutor Application Entry Point
Production-ready with comprehensive error handling
"""

print("🔍 DEBUG: Script started")

import sys
print("🔍 DEBUG: sys imported")

import signal
print("🔍 DEBUG: signal imported")

import logging
print("🔍 DEBUG: logging imported")

import threading
print("🔍 DEBUG: threading imported")

import schedule
print("🔍 DEBUG: schedule imported")

import time
print("🔍 DEBUG: time imported")

from datetime import datetime
print("🔍 DEBUG: datetime imported")

from flask import Flask, request, jsonify
print("🔍 DEBUG: Flask imported")

from logging.handlers import RotatingFileHandler
print("🔍 DEBUG: RotatingFileHandler imported")

import io, os
print("🔍 DEBUG: io, os imported")

# Import all components - ADD DEBUGGING HERE
print("🔍 DEBUG: About to import config.settings...")
try:
    from config.settings import load_config
    print("🔍 DEBUG: ✅ config.settings imported successfully")
except Exception as e:
    print(f"🔍 DEBUG: ❌ config.settings import failed: {e}")
    sys.exit(1)

print("🔍 DEBUG: About to import database.database...")
try:
    from database.database import create_engine_and_session, init_database, test_connection
    print("🔍 DEBUG: ✅ database.database imported successfully")
except Exception as e:
    print(f"🔍 DEBUG: ❌ database.database import failed: {e}")
    sys.exit(1)

print("🔍 DEBUG: About to import database.models...")
try:
    from database.models import cleanup_old_events
    print("🔍 DEBUG: ✅ database.models imported successfully")
except Exception as e:
    print(f"🔍 DEBUG: ❌ database.models import failed: {e}")
    sys.exit(1)

print("🔍 DEBUG: About to import llm_backend.main...")
try:
    from llm_backend.main import initialize_application, webhook_handler, cleanup_old_data
    print("🔍 DEBUG: ✅ llm_backend.main imported successfully")
except Exception as e:
    print(f"🔍 DEBUG: ❌ llm_backend.main import failed: {e}")
    sys.exit(1)

print("🔍 DEBUG: About to import llm_backend.orchestrator...")
try:
    from llm_backend.orchestrator import schedule_daily_word, setup_theme_thread
    print("🔍 DEBUG: ✅ llm_backend.orchestrator imported successfully")
except Exception as e:
    print(f"🔍 DEBUG: ❌ llm_backend.orchestrator import failed: {e}")
    sys.exit(1)

print("🔍 DEBUG: All imports completed successfully!")

# Setup logging
def setup_logging():
    print("🔍 DEBUG: setup_logging() called")
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
    
    print("🔍 DEBUG: setup_logging() completed")
    return root_logger

print("🔍 DEBUG: About to call setup_logging()...")
logger = setup_logging()
print("🔍 DEBUG: Logger setup completed")

print("Hello from vocabulary-app!")

# Flask app for webhooks
app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False

print("🔍 DEBUG: Flask app created")

# Global variables for graceful shutdown
shutdown_flag = threading.Event()
scheduler_thread = None
cleanup_thread = None
app_components = {}

print("🔍 DEBUG: Global variables initialized")

print("🔍 DEBUG: About to define route handlers...")

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        # Check database connection
        db_healthy = test_connection(app_components.get('engine'))
        
        # Check Slack connection
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
        
        # FAST PATH: Handle URL verification immediately (new)
        if request_data and request_data.get('type') == 'url_verification':
            challenge = request_data.get('challenge')
            logger.info("Received URL verification challenge from Slack")
            return challenge  # Return challenge string directly
        
        # EXISTING PATH: Everything else goes through normal flow (unchanged)
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

print("🔍 DEBUG: Route handlers defined")

# (Other functions: run_scheduler, run_cleanup, handle_shutdown, test_fresh_init, etc.)
# For brevity, assume these functions are defined here similar to your existing implementation.

def run_scheduler():
    """Run the scheduler in a separate thread"""
    logger.info("Scheduler thread started")
    
    while not shutdown_flag.is_set():
        try:
            schedule.run_pending()
            time.sleep(1)
        except Exception as e:
            logger.error(f"Scheduler error: {e}", exc_info=True)
            time.sleep(5)
            
    logger.info("Scheduler thread stopped")

def run_cleanup():
    """Run periodic cleanup tasks"""
    logger.info("Cleanup thread started")
    
    while not shutdown_flag.is_set():
        try:
            cleanup_old_data()
            for _ in range(3600):
                if shutdown_flag.is_set():
                    break
                time.sleep(1)
        except Exception as e:
            logger.error(f"Cleanup error: {e}", exc_info=True)
            time.sleep(300)
            
    logger.info("Cleanup thread stopped")

def handle_shutdown(signum, frame):
    """Gracefully handle shutdown signals"""
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    shutdown_flag.set()
    if scheduler_thread and scheduler_thread.is_alive():
        scheduler_thread.join(timeout=5)
    if cleanup_thread and cleanup_thread.is_alive():
        cleanup_thread.join(timeout=5)
    logger.info("Shutdown complete")
    sys.exit(0)

def test_fresh_init():
    """Test command for fresh initialization workflow"""
    from llm_backend.orchestrator import initialize_fresh_database
    from llm_backend.main import initialize_application
    from database.models import clear_all_data, check_if_database_empty
    
    app_components = initialize_application()
    slack_client = app_components['slack_client']
    session_maker = app_components['db_session']

    with session_maker() as session:
        print("Clearing database...")
        clear_all_data(session)
        if check_if_database_empty(session):
            print("Database cleared successfully")
            print("Running fresh initialization workflow...")
            success = initialize_fresh_database(session, slack_client)
            if success:
                print("✅ Fresh initialization complete!")
                print("- Theme thread created with default 'Literature' theme")
                print("- First word posted")
            else:
                print("❌ Fresh initialization failed")
        else:
            print("Failed to clear database")

def main():
    print("🔍 DEBUG: ✨ main() function called!")
    global scheduler_thread, cleanup_thread, app_components

    try:
        print("🚀 STEP 1: Starting main() function")
        logger.info("=" * 50)
        logger.info("Starting Vocabulary Tutor Application")
        logger.info("=" * 50)

        print("🚀 STEP 2: About to initialize application components...")
        logger.info("Initializing application components...")
        
        try:
            print("🚀 STEP 3: Calling initialize_application()...")
            app_components = initialize_application()
            print("🚀 STEP 4: initialize_application() completed successfully!")
        except Exception as init_error:
            print(f"❌ FATAL: initialize_application() failed: {init_error}")
            logger.error(f"Fatal error in initialize_application: {init_error}", exc_info=True)
            return

        if not app_components:
            print("❌ FATAL: app_components is None or empty")
            logger.error("Failed to initialize application")
            sys.exit(1)
        
        print("🚀 STEP 5: App components initialized successfully")
        
        try:
            from llm_backend.orchestrator import initialize_fresh_database
            from database.models import check_if_database_empty
            print("🚀 STEP 6: Imports successful")
        except Exception as import_error:
            print(f"❌ FATAL: Import failed: {import_error}")
            logger.error(f"Import error: {import_error}", exc_info=True)
            return

        print("🚀 STEP 7: About to check database...")
        db_session = app_components['db_session']
        slack_client = app_components['slack_client']
        
        try:
            with db_session() as session:
                print("🚀 STEP 8: Database session created")
                if check_if_database_empty(session):
                    print("🚀 STEP 9: Fresh database detected - running initialization workflow")
                    logger.info("Fresh database detected - running initialization workflow")
                    success = initialize_fresh_database(session, slack_client)
                    if not success:
                        print("❌ FATAL: Fresh initialization failed")
                        logger.error("Fresh initialization failed")
                        return
                    print("🚀 STEP 10: Fresh initialization completed")
                else:
                    print("🚀 STEP 9: Existing database - ensuring theme thread exists")
                    setup_theme_thread(session, slack_client)
                    print("🚀 STEP 10: Theme thread setup completed")
        except Exception as db_error:
            print(f"❌ FATAL: Database operation failed: {db_error}")
            logger.error(f"Database error: {db_error}", exc_info=True)
            return

        print("🚀 STEP 11: Setting up signal handlers...")
        signal.signal(signal.SIGINT, handle_shutdown)
        signal.signal(signal.SIGTERM, handle_shutdown)

        print("🚀 STEP 12: Starting scheduler thread...")
        logger.info("Starting scheduler thread...")
        scheduler_thread = threading.Thread(target=run_scheduler, daemon=False)
        scheduler_thread.start()

        print("🚀 STEP 13: Starting cleanup thread...")
        logger.info("Starting cleanup thread...")
        cleanup_thread = threading.Thread(target=run_cleanup, daemon=False)
        cleanup_thread.start()

        print("🚀 STEP 14: Scheduling daily word posting...")
        config = app_components['config']
        daily_time = config.get('daily_word_time', '09:00')
        schedule.every().day.at(daily_time).do(
            lambda: schedule_daily_word(
                app_components['db_session'],
                app_components['slack_client']
            )
        )
        logger.info(f"Scheduled daily word posting at {daily_time}")

        print("🚀 STEP 15: Starting Flask server...")
        import os
        port = int(os.getenv('PORT', 3000))
        print(f"🚀 STEP 16: About to start Flask on port {port}")
        logger.info(f"Starting webhook server on port {port}")
        
        app.run(
            host='0.0.0.0',
            port=port,
            debug=False,
            threaded=True,
            use_reloader=False
        )
        
        print("🚀 STEP 17: Flask server started successfully!")

    except KeyboardInterrupt:
        print("🚀 Received keyboard interrupt")
        logger.info("Received keyboard interrupt")
        handle_shutdown(signal.SIGINT, None)

    except Exception as e:
        print(f"❌ FATAL ERROR in main: {e}")
        logger.error(f"Fatal error in main: {e}", exc_info=True)
        sys.exit(1)

print("🔍 DEBUG: About to check if __name__ == '__main__'...")

if __name__ == "__main__":
    print("🔍 DEBUG: ✨ Script is being run directly!")
    if len(sys.argv) > 1 and sys.argv[1] == "test-fresh-init":
        print("🔍 DEBUG: Running test-fresh-init")
        test_fresh_init()
    else:
        print("🔍 DEBUG: About to call main()...")
        main()