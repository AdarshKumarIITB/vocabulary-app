from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime, timezone

Base = declarative_base()

class WordHistory(Base):
    """SQLAlchemy ORM model for WordHistory table"""
    __tablename__ = 'word_history'
    
    # Primary key, auto-incrementing integer
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # The vocabulary word, must be unique and not null
    word = Column(String, unique=True, nullable=False)
    
    # Flag indicating if user knew the word
    # True = user knew it, False = user learned it, None = not yet responded
    known_flag = Column(Boolean, nullable=True)
    
    # Slack thread ID for tracking conversations
    thread_id = Column(String, nullable=True)
    
    # Timestamp when word was added to database
    timestamp = Column(DateTime, default=datetime.utcnow)


def create_word(session, word, thread_id=None):
    """
    Creates a new word entry in the WordHistory table
    Takes database session, word string, and optional thread_id as parameters
    Initializes with known_flag as None (user hasn't responded yet)
    Auto-generates ID and timestamp
    Returns the newly created WordHistory object
    """
    new_word = WordHistory(word=word, known_flag=None, thread_id=thread_id)
    session.add(new_word)
    session.flush()  # Flush to get the ID, but don't commit
    return new_word


def read_words(session, known_flag=None):
    """
    Reads words from database based on known_flag filter
    If known_flag is 1: returns all words where known_flag is True
    If known_flag is 0: returns all words where known_flag is False  
    If known_flag is None: returns all words in the database
    Returns list of WordHistory objects
    """
    query = session.query(WordHistory)
    
    if known_flag == 1:
        query = query.filter(WordHistory.known_flag == True)
    elif known_flag == 0:
        query = query.filter(WordHistory.known_flag == False)
    # If known_flag is None, return all words (no filter)
    
    return query.all()


def update_known_flag(session, word, known_flag):
    """
    Updates the known_flag of a specific word entry
    Takes session, word (WordHistory object), and known_flag (boolean) as parameters
    Updates its known_flag to the provided value
    Returns the updated WordHistory object
    """
    if word:
        word.known_flag = known_flag
        session.flush()  # Flush to ensure update is pending
        return word
    
    return None


def update_known_flag_by_thread(session, thread_id, known_flag):
    """
    Updates the known_flag of a word entry by its thread_id
    Takes session, thread_id (string), and known_flag (boolean) as parameters
    Finds the word entry by thread_id
    Updates its known_flag to the provided value
    Returns the updated WordHistory object, or None if word not found
    """
    word_entry = session.query(WordHistory).filter(WordHistory.thread_id == thread_id).first()
    
    if word_entry:
        word_entry.known_flag = known_flag
        session.flush()  # Flush to ensure update is pending
        return word_entry
    
    return None


def get_word_by_thread(session, thread_id):
    """
    Gets a word entry by its thread_id
    Takes session and thread_id as parameters
    Returns the WordHistory object if found, None otherwise
    """
    return session.query(WordHistory).filter(WordHistory.thread_id == thread_id).first()


def check_last_word_flag(session):
    """
    Checks the known_flag status of the most recent word in the table
    Orders words by timestamp descending and gets the first one
    Returns the known_flag value (True, False, or None)
    If no words exist in database, returns None
    Used to determine if system should generate new word or wait for response
    """
    last_word = session.query(WordHistory).order_by(WordHistory.timestamp.desc()).first()
    
    if last_word:
        return last_word.known_flag
    
    return None


def get_last_word(session):
    """
    Gets the most recent word entry from the database
    Returns the WordHistory object or None if no words exist
    """
    return session.query(WordHistory).order_by(WordHistory.timestamp.desc()).first()


def get_word_by_name(session, word):
    """
    Checks if a specific word already exists in the database
    Takes session and word string as parameters
    Queries database for exact word match
    Returns the WordHistory object if found, None otherwise
    Used to prevent duplicate word generation
    """
    return session.query(WordHistory).filter(WordHistory.word == word).first()