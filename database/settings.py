# New file: database/settings.py
# For managing system-wide settings in database

from sqlalchemy import Column, String, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import json
import logging
import os

logger = logging.getLogger(__name__)
Base = declarative_base()

class SystemSetting(Base):
    """Store system-wide settings"""
    __tablename__ = 'system_settings'
    
    key = Column(String(100), primary_key=True)
    value = Column(Text)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

def get_setting(session, key, default=None):
    """Get a system setting value"""
    try:
        setting = session.query(SystemSetting).filter_by(key=key).first()
        if setting:
            # Try to parse as JSON if possible
            try:
                return json.loads(setting.value)
            except:
                return setting.value
        return default
    except Exception as e:
        logger.error(f"Error getting setting {key}: {e}")
        return default

def set_setting(session, key, value):
    """Set or update a system setting"""
    try:
        # Convert to JSON if not string
        if not isinstance(value, str):
            value = json.dumps(value)
            
        setting = session.query(SystemSetting).filter_by(key=key).first()
        if setting:
            setting.value = value
            setting.updated_at = datetime.utcnow()
        else:
            setting = SystemSetting(key=key, value=value)
            session.add(setting)
        session.commit()
        return True
    except Exception as e:
        session.rollback()
        logger.error(f"Error setting {key}: {e}")
        return False

# Use these instead of environment variables for theme thread
def get_theme_thread_id(session):
    """Get the theme thread ID from database"""
    return get_setting(session, 'theme_thread_id')

def set_theme_thread_id(session, thread_id):
    """Store the theme thread ID in database"""
    os.environ['THEME_THREAD_ID'] = thread_id
    return thread_id