#!/usr/bin/env python3
"""
Vocabulary Tutor - Production Application Entry Point
Runs the complete application with Flask webhook server and scheduler
"""

import sys
import os
import logging
import signal
import argparse
import json
import hmac
import hashlib
from flask import Flask, request, jsonify

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import load_config, get_slack_config
from database.database import create_engine_and_session, init_database, get_session
from database.models import WordHistory, create_word, read_words, check_last_word_flag
from slack_integration.slack_client import SlackClient
from llm_backend.main import initialize_application, start_scheduler, stop_scheduler, webhook_handler
from llm_backend.word_generator import generate_word
from llm_backend.orchestrator import post_new_word_workflow

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Flask application
app = Flask(__name__)
app_components = None


def verify_slack_signature(request):
    """Verify that the request came from Slack"""
    slack_config = get_slack_config()
    signing_secret = slack_config.get('signing_secret')
    
    if not signing_secret:
        # If no signing secret configured, skip verification (dev mode)
        logger.warning("No Slack signing secret configured - skipping verification")
        return True
    
    timestamp = request.headers.get('X-Slack-Request-Timestamp', '')
    signature = request.headers.get('X-Slack-Signature', '')
    
    if not timestamp or not signature:
        return False
    
    # Check timestamp is recent (within 5 minutes)
    import time
    if abs(time.time() - float(timestamp)) > 60 * 5:
        return False
    
    # Verify signature
    sig_basestring = f"v0:{timestamp}:{request.get_data().decode('utf-8')}"
    my_signature = 'v0=' + hmac.new(
        signing_secret.encode(),
        sig_basestring.encode(),
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(my_signature, signature)


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'vocabulary-tutor',
        'timestamp': str(os.times())
    }), 200


@app.route('/slack/events', methods=['POST'])
def slack_events():
    """Webhook endpoint for Slack events"""
    try:
        # Verify the request came from Slack
        if not verify_slack_signature(request):
            logger.warning("Invalid Slack signature")
            return jsonify({'error': 'Invalid signature'}), 401
        
        # Get request data
        request_data = request.get_json()
        
        # Handle URL verification challenge
        if request_data.get('type') == 'url_verification':
            logger.info("Handling Slack URL verification")
            return jsonify({'challenge': request_data['challenge']}), 200
        
        # Process the webhook
        result = webhook_handler(request_data)
        
        # Return acknowledgment to Slack
        return '', 200
        
    except Exception as e:
        logger.error(f"Error processing Slack event: {e}")
        # Return 200 anyway to prevent Slack retries
        return '', 200


def test_database():
    """Test database connection and operations"""
    logger.info("\n=== TESTING DATABASE ===")
    try:
        engine, SessionMaker = create_engine_and_session()
        init_database(engine)
        
        with get_session() as session:
            # Test operations
            count = session.query(WordHistory).count()
            logger.info(f"✓ Database connected. Words in database: {count}")
            
            # Show last few words
            recent_words = session.query(WordHistory).order_by(
                WordHistory.timestamp.desc()
            ).limit(5).all()
            
            if recent_words:
                logger.info("Recent words:")
                for word in recent_words:
                    status = "Known" if word.known_flag == True else "Learning" if word.known_flag == False else "Pending"
                    logger.info(f"  - {word.word}: {status}")
            
        return True
    except Exception as e:
        logger.error(f"✗ Database test failed: {e}")
        return False


def test_slack():
    """Test Slack connection and posting"""
    logger.info("\n=== TESTING SLACK ===")
    try:
        slack_config = get_slack_config()
        
        if not slack_config['bot_token']:
            logger.warning("✗ Slack bot token not configured")
            return False
        
        client = SlackClient(slack_config['bot_token'], slack_config['channel_id'])
        
        # Test by creating and deleting a test message
        test_message = "🔧 Vocabulary Tutor test message (will be deleted)"
        thread_id = client.create_thread(test_message)
        
        if thread_id:
            logger.info(f"✓ Slack connected. Test thread created: {thread_id}")
            # Note: In production, you might want to delete the test message
            return True
        else:
            logger.error("✗ Failed to create test thread")
            return False
            
    except Exception as e:
        logger.error(f"✗ Slack test failed: {e}")
        return False


def test_word_generation():
    """Test word generation with LLM"""
    logger.info("\n=== TESTING WORD GENERATION ===")
    try:
        with get_session() as session:
            result = generate_word(session)
            
            if result['status'] == 'success':
                word_data = result['word_data']
                logger.info(f"✓ Generated word: {word_data['word']}")
                logger.info(f"  Meanings: {word_data['meanings'][0][:50]}...")
                
                # Clean up test word
                word_entry = session.query(WordHistory).filter_by(
                    word=word_data['word']
                ).first()
                if word_entry:
                    session.delete(word_entry)
                    session.commit()
                
                return True
            else:
                logger.warning(f"✗ Generation failed: {result.get('message')}")
                return False
                
    except Exception as e:
        logger.error(f"✗ Word generation test failed: {e}")
        return False


def test_workflow():
    """Test the complete workflow"""
    logger.info("\n=== TESTING FULL WORKFLOW ===")
    try:
        components = initialize_application()
        
        if not components['slack_client']:
            logger.warning("Using mock Slack client for workflow test")
            
            class MockSlackClient:
                def create_thread(self, message):
                    logger.info(f"[MOCK] Thread: {message}")
                    return "mock_thread_id"
                
                def post_to_thread(self, thread_id, message):
                    logger.info(f"[MOCK] Reply: {message[:50]}...")
                    return True
                
                def get_thread_messages(self, thread_id):
                    return []
            
            slack_client = MockSlackClient()
        else:
            slack_client = components['slack_client']
        
        with get_session() as session:
            success = post_new_word_workflow(session, slack_client)
            
            if success:
                logger.info("✓ Workflow completed successfully")
                
                # Clean up if using mock
                if isinstance(slack_client, type(lambda: None)):
                    last_word = session.query(WordHistory).order_by(
                        WordHistory.timestamp.desc()
                    ).first()
                    if last_word:
                        session.delete(last_word)
                        session.commit()
                
                return True
            else:
                logger.error("✗ Workflow failed")
                return False
                
    except Exception as e:
        logger.error(f"✗ Workflow test failed: {e}")
        return False


def run_production():
    """Run the application in production mode"""
    global app_components
    
    logger.info("\n" + "="*60)
    logger.info("VOCABULARY TUTOR - PRODUCTION MODE")
    logger.info("="*60)
    
    try:
        # Initialize all components
        app_components = initialize_application()
        
        # Start the scheduler
        if app_components['slack_client']:
            start_scheduler()
            logger.info("✓ Scheduler started")
        else:
            logger.warning("⚠ Slack not configured - scheduler not started")
        
        # Get port from environment or use default
        port = int(os.environ.get('PORT', 3000))
        
        logger.info(f"\n🚀 Starting webhook server on port {port}")
        logger.info(f"Webhook URL: http://localhost:{port}/slack/events")
        logger.info(f"Health check: http://localhost:{port}/health")
        logger.info("\nPress Ctrl+C to stop the server\n")
        
        # Run Flask server
        app.run(
            host='0.0.0.0',
            port=port,
            debug=False,  # Set to False in production
            use_reloader=False  # Prevents double initialization
        )
        
    except KeyboardInterrupt:
        logger.info("\nShutdown requested...")
    except Exception as e:
        logger.error(f"Failed to start production server: {e}")
        return 1
    finally:
        # Clean shutdown
        stop_scheduler()
        logger.info("Application stopped")
    
    return 0


def main():
    """Main entry point with argument parsing"""
    parser = argparse.ArgumentParser(description='Vocabulary Tutor Application')
    parser.add_argument(
        '--mode',
        choices=['production', 'test-db', 'test-slack', 'test-word', 'test-workflow'],
        default='production',
        help='Run mode (default: production)'
    )
    
    args = parser.parse_args()
    
    # Header
    logger.info("="*60)
    logger.info("VOCABULARY TUTOR v1.0")
    logger.info("="*60)
    
    # Execute based on mode
    if args.mode == 'test-db':
        return 0 if test_database() else 1
    
    elif args.mode == 'test-slack':
        return 0 if test_slack() else 1
    
    elif args.mode == 'test-word':
        initialize_application()
        return 0 if test_word_generation() else 1
    
    elif args.mode == 'test-workflow':
        return 0 if test_workflow() else 1
    
    else:  # production
        return run_production()


def handle_shutdown(signum, frame):
    """Handle shutdown signals gracefully"""
    logger.info("\nReceived shutdown signal")
    stop_scheduler()
    sys.exit(0)


if __name__ == "__main__":
    # Set up signal handlers
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)
    
    # Run main
    exit_code = main()
    sys.exit(exit_code)