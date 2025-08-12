"""
Cache utilities for deduplication and rate limiting
"""
from collections import OrderedDict
from datetime import datetime, timedelta
import threading
import logging

logger = logging.getLogger(__name__)

class TTLCache:
    """Thread-safe TTL cache for event deduplication"""
    
    def __init__(self, max_size=10000, ttl_seconds=3600):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.cache = OrderedDict()
        self.lock = threading.Lock()
        
    def add(self, key):
        """Add a key with current timestamp"""
        with self.lock:
            # Clean expired entries first
            self._clean_expired()
            
            # Check if we need to evict oldest entries
            if len(self.cache) >= self.max_size:
                # Remove 10% of oldest entries
                num_to_remove = max(1, self.max_size // 10)
                for _ in range(num_to_remove):
                    self.cache.popitem(last=False)
                logger.info(f"Cache size limit reached. Evicted {num_to_remove} oldest entries")
            
            # Add new entry
            self.cache[key] = datetime.now()
            logger.debug(f"Added key to cache: {key}")
            
    def contains(self, key):
        """Check if key exists and is not expired"""
        with self.lock:
            if key not in self.cache:
                return False
                
            timestamp = self.cache[key]
            if datetime.now() - timestamp > timedelta(seconds=self.ttl_seconds):
                del self.cache[key]
                logger.debug(f"Key expired and removed: {key}")
                return False
                
            # Move to end (LRU behavior)
            self.cache.move_to_end(key)
            return True
            
    def _clean_expired(self):
        """Remove expired entries"""
        now = datetime.now()
        expired_keys = []
        
        for key, timestamp in self.cache.items():
            if now - timestamp > timedelta(seconds=self.ttl_seconds):
                expired_keys.append(key)
            else:
                # Since OrderedDict maintains insertion order, 
                # once we hit a non-expired entry, rest are newer
                break
                
        for key in expired_keys:
            del self.cache[key]
            
        if expired_keys:
            logger.debug(f"Cleaned {len(expired_keys)} expired entries")
            
    def get_stats(self):
        """Get cache statistics"""
        with self.lock:
            return {
                'size': len(self.cache),
                'max_size': self.max_size,
                'ttl_seconds': self.ttl_seconds
            }

class RateLimiter:
    """Simple rate limiter for API calls"""
    
    def __init__(self, max_calls=10, time_window=60):
        self.max_calls = max_calls
        self.time_window = time_window  # seconds
        self.calls = []
        self.lock = threading.Lock()
        
    def is_allowed(self):
        """Check if a call is allowed under rate limit"""
        with self.lock:
            now = datetime.now()
            # Remove old calls outside time window
            self.calls = [call_time for call_time in self.calls 
                         if now - call_time < timedelta(seconds=self.time_window)]
            
            if len(self.calls) < self.max_calls:
                self.calls.append(now)
                return True
            return False
            
    def wait_time(self):
        """Get seconds to wait before next allowed call"""
        with self.lock:
            if len(self.calls) < self.max_calls:
                return 0
            oldest_call = min(self.calls)
            wait = (oldest_call + timedelta(seconds=self.time_window) - datetime.now()).total_seconds()
            return max(0, wait)