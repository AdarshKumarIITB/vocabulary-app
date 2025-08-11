from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import json
import hashlib
import hmac
import time
import logging

logger = logging.getLogger(__name__)


class SlackClient:
    def __init__(self, token, channel_id):
        """
        Initializes Slack client with authentication
        Takes bot token and channel ID as parameters
        Creates WebClient from slack_sdk with the token
        Stores channel_id for all future operations
        Validates authentication by calling auth.test
        Raises exception if authentication fails
        """
        self.token = token
        self.channel_id = channel_id
        self.client = WebClient(token=token)
        
        # Validate authentication
        try:
            auth_response = self.client.auth_test()
            self.bot_id = auth_response["bot_id"]
            self.bot_user_id = auth_response["user_id"]
            logger.info(f"Slack authentication successful. Bot ID: {self.bot_id}")
        except SlackApiError as e:
            raise Exception(f"Slack authentication failed: {e.response['error']}")
    
    def create_thread(self, initial_message):
        """
        Posts a new message to channel that starts a thread
        Takes initial message text (the vocabulary word) as parameter
        Uses chat.postMessage API with channel_id
        Returns thread_timestamp (ts) which serves as thread_id
        Thread_id is used for all subsequent replies
        Handles any Slack API errors with clear error messages
        """
        try:
            response = self.client.chat_postMessage(
                channel=self.channel_id,
                text=initial_message
            )
            thread_id = response['ts']
            logger.info(f"Created new thread with ID: {thread_id}")
            return thread_id
        except SlackApiError as e:
            error_msg = f"Failed to create thread: {e.response['error']}"
            logger.error(error_msg)
            raise Exception(error_msg)
    
    def post_to_thread(self, thread_id, message):
        """
        Posts a reply message within an existing thread
        Takes thread_id (timestamp) and message text as parameters
        Uses chat.postMessage with thread_ts parameter
        Maintains thread continuity by replying to correct thread
        Returns message timestamp of the posted reply
        Raises exception if thread doesn't exist or post fails
        """
        try:
            response = self.client.chat_postMessage(
                channel=self.channel_id,
                text=message,
                thread_ts=thread_id
            )
            message_ts = response['ts']
            logger.info(f"Posted message to thread {thread_id}")
            return message_ts
        except SlackApiError as e:
            error_msg = f"Failed to post to thread: {e.response['error']}"
            logger.error(error_msg)
            raise Exception(error_msg)
    
    def get_thread_messages(self, thread_id):
        """
        Fetches all messages within a specific thread
        Takes thread_id (timestamp) as parameter
        Uses conversations.replies API endpoint
        Returns list of message dictionaries with:
        - user: ID of message sender
        - text: message content
        - ts: timestamp
        - bot_id: present if message is from bot
        Handles pagination if thread has many messages
        Sorts messages chronologically
        """
        try:
            messages = []
            cursor = None
            
            while True:
                # Fetch messages with pagination support
                response = self.client.conversations_replies(
                    channel=self.channel_id,
                    ts=thread_id,
                    cursor=cursor,
                    limit=100  # Fetch up to 100 messages at a time
                )
                
                messages.extend(response['messages'])
                
                # Check if there are more messages
                if not response.get('has_more', False):
                    break
                    
                cursor = response.get('response_metadata', {}).get('next_cursor')
            
            # Messages are already sorted chronologically by Slack
            logger.info(f"Retrieved {len(messages)} messages from thread {thread_id}")
            
            # Format messages for return
            formatted_messages = []
            for msg in messages:
                formatted_msg = {
                    'user': msg.get('user', ''),
                    'text': msg.get('text', ''),
                    'ts': msg.get('ts', ''),
                }
                if 'bot_id' in msg:
                    formatted_msg['bot_id'] = msg['bot_id']
                formatted_messages.append(formatted_msg)
            
            return formatted_messages
            
        except SlackApiError as e:
            error_msg = f"Failed to get thread messages: {e.response['error']}"
            logger.error(error_msg)
            raise Exception(error_msg)
    
    def post_word_sequence(self, word_data):
        """
        Posts complete word learning sequence to new thread
        Takes word_data dictionary with word, meanings, examples
        Creates initial thread with just the word
        Posts definitions as first reply
        Posts examples as second reply
        Posts user instructions as third reply
        Returns thread_id for tracking
        Ensures all posts succeed or rolls back
        """
        thread_id = None
        try:
            # Create thread with the word
            thread_id = self.create_thread(word_data['word'])
            
            # Post definitions
            meanings_text = "📖 *Meanings:*\n" + "\n".join(
                [f"• {meaning}" for meaning in word_data.get('meanings', [])]
            )
            self.post_to_thread(thread_id, meanings_text)
            
            # Post examples
            examples_text = "💡 *Examples:*\n" + "\n".join(
                [f"• {example}" for example in word_data.get('examples', [])]
            )
            self.post_to_thread(thread_id, examples_text)
            
            # Post instructions
            instructions = (
                "🎯 *Your turn!*\n"
                "• Reply '1' if you already knew this word\n"
                "• Or use the word in an original sentence to learn it"
            )
            self.post_to_thread(thread_id, instructions)
            
            logger.info(f"Successfully posted complete word sequence for '{word_data['word']}'")
            return thread_id
            
        except Exception as e:
            # Rollback is not possible in Slack, but log the error
            error_msg = f"Failed to post word sequence: {str(e)}"
            logger.error(error_msg)
            if thread_id:
                logger.warning(f"Partial thread created with ID: {thread_id}")
            raise Exception(error_msg)
    
    def validate_webhook(self, request_body, headers):
        """
        Validates incoming webhook is from Slack
        Verifies request signature for security
        Handles URL verification challenge during setup
        Returns True if valid webhook, False otherwise
        Prevents unauthorized webhook calls
        """
        # For Phase 2, we'll implement basic validation
        # Full signature verification would require SLACK_SIGNING_SECRET
        
        # Handle URL verification challenge
        if isinstance(request_body, str):
            try:
                body = json.loads(request_body)
            except json.JSONDecodeError:
                return False
        else:
            body = request_body
            
        # Handle Slack URL verification challenge
        if body.get('type') == 'url_verification':
            logger.info("Handling Slack URL verification challenge")
            return {'challenge': body.get('challenge')}
        
        # Basic validation - check if it has expected fields
        if 'event' in body and 'type' in body:
            return True
            
        return False
    
    def parse_webhook_event(self, request_body):
        """
        Extracts relevant data from Slack webhook payload
        Parses JSON body to get event details
        For any other event apart from text-based replies on a thread - don't care
        Returns dictionary with:
        - type: event type (message, app_mention, etc.)
        - thread_id: thread_ts if in thread, None otherwise
        - user_id: ID of user who sent message
        - text: message content
        - channel: channel where event occurred
        Handles different event structures safely
        """
        try:
            if isinstance(request_body, str):
                body = json.loads(request_body)
            else:
                body = request_body
            
            # Extract event data
            event = body.get('event', {})
            
            # Check if this is a message event
            if event.get('type') != 'message':
                logger.debug(f"Ignoring non-message event: {event.get('type')}")
                return None
            
            # Ignore bot messages to prevent loops
            if 'bot_id' in event or event.get('user') == self.bot_user_id:
                logger.debug("Ignoring bot message")
                return None
            
            # Check if it's a thread reply
            thread_id = event.get('thread_ts')
            if not thread_id:
                logger.debug("Ignoring non-thread message")
                return None
            
            # Extract relevant data
            parsed_event = {
                'type': event.get('type'),
                'thread_id': thread_id,
                'user_id': event.get('user'),
                'text': event.get('text', ''),
                'channel': event.get('channel')
            }
            
            logger.info(f"Parsed webhook event: {parsed_event}")
            return parsed_event
            
        except Exception as e:
            logger.error(f"Failed to parse webhook event: {str(e)}")
            return None