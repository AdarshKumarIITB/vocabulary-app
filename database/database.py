from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from contextlib import contextmanager
import logging
from config.settings import get_database_url

# Set up logging

_Session = None  # Global session variable to be initialized later
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_engine_and_session():
    """
    Creates SQLAlchemy engine using connection URL from config
    Sets up connection pooling with appropriate pool size and timeout
    Creates sessionmaker bound to the engine
    Returns tuple of (engine, sessionmaker)
    Configures retry logic for transient connection failures
    """

    database_url = get_database_url()
    global _Session

    try:
        # Create engine with connection pooling
        # Using NullPool for SQLite, regular pool for PostgreSQL
        
        if database_url.startswith('sqlite:'):
            engine = create_engine(
                database_url,
                poolclass=NullPool,  # SQLite doesn't support connection pooling well
                echo=False  # Set to True for SQL query logging
            )
        else:
            engine = create_engine(
                database_url,
                pool_size=5,
                max_overflow=10,
                pool_timeout=30,
                pool_recycle=3600,  # Recycle connections after 1 hour
                echo=False  # Set to True for SQL query logging
            )
        
        # Create sessionmaker
        Session = sessionmaker(bind=engine)
        
        logger.info("Database engine and session created successfully")

        _Session = Session
        return engine, Session
        
    except Exception as e:
        logger.error(f"Failed to create database engine: {str(e)}")
        raise


def init_database(engine):
    """
    Initializes database tables using SQLAlchemy models
    Takes engine as parameter
    Creates all tables defined in models.py if they don't exist
    Runs any SQL migrations from migrations folder
    Returns True if successful, raises exception if database initialization fails
    Logs initialization status
    """
    try:
        from database.models import Base
        
        # Create all tables
        Base.metadata.create_all(bind=engine)
        
        logger.info("Database tables initialized successfully")
        return True
        
    except Exception as e:
        logger.error(f"Failed to initialize database: {str(e)}")
        raise


@contextmanager
def get_session():
    """
    Context manager that provides a database session
    Creates a new session from sessionmaker
    Automatically handles commit on success
    Automatically handles rollback on exception
    Always closes session when done
    Usage: with get_session(Session) as session: perform_database_operations(session)
    """
    if _Session is None:
        raise RuntimeError("Database not initialized. Call create_engine_and_session() first.")

    session = _Session()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Database session error: {str(e)}")
        raise
    finally:
        session.close()


def test_connection(engine):
    """
    Tests if database connection is working
    Attempts a simple query to verify connectivity
    Returns True if connection successful, False otherwise
    Used during application startup to verify database is accessible
    """
    try:
        # Try to execute a simple query
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1"))
            result.fetchone()
        
        logger.info("Database connection test successful")
        return True
        
    except Exception as e:
        logger.error(f"Database connection test failed: {str(e)}")
        return False