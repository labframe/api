"""Custom logging formatters for colored logs with timestamps."""

import logging
import re
from datetime import datetime

import colorlog


class ColoredTimestampFormatter(logging.Formatter):
    """Formatter that colors timestamps along with the log level."""

    def __init__(self, *args, **kwargs):
        """Initialize the formatter with a format that includes timestamp."""
        # Store datefmt for timestamp formatting
        self.datefmt = kwargs.pop('datefmt', '%Y-%m-%d %H:%M:%S')
        # Store log colors
        self.log_colors = kwargs.pop('log_colors', {
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'bold_red',
        })
        # Extract format string
        fmt = kwargs.pop('fmt', None) or (args[0] if args else '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        # Remove log_color and reset codes from format - we'll handle colors manually
        fmt = fmt.replace('%(log_color)s', '').replace('%(reset)s', '')
        # Call parent with remaining args and kwargs
        super().__init__(fmt, self.datefmt, *args[1:], **kwargs)

    def format(self, record):
        """Format the log record with colored timestamp and level."""
        # Get the log color for the level
        level_color_code = self._get_color_code(record.levelname, self.log_colors)
        reset_code = '\033[0m'
        
        # Format timestamp with color
        timestamp = datetime.fromtimestamp(record.created).strftime(self.datefmt)
        timestamp_colored = f"{level_color_code}{timestamp}{reset_code}"
        
        # Format level name with color
        levelname_colored = f"{level_color_code}{record.levelname}{reset_code}"
        
        # Format the message using parent class but replace asctime and levelname
        formatted = super().format(record)
        
        # Replace timestamp and levelname with colored versions
        # First, replace the formatted timestamp (from parent)
        formatted = formatted.replace(
            datetime.fromtimestamp(record.created).strftime(self.datefmt),
            timestamp_colored,
            1
        )
        # Replace levelname with colored version
        formatted = formatted.replace(record.levelname, levelname_colored, 1)
        
        return formatted

    def _get_color_code(self, levelname, log_colors):
        """Get ANSI color code for the log level."""
        color_name = log_colors.get(levelname, '')
        color_map = {
            'black': '\033[30m',
            'red': '\033[31m',
            'green': '\033[32m',
            'yellow': '\033[33m',
            'blue': '\033[34m',
            'purple': '\033[35m',
            'cyan': '\033[36m',
            'white': '\033[37m',
            'bold_red': '\033[1;31m',
            'bold_green': '\033[1;32m',
            'bold_yellow': '\033[1;33m',
            'bold_blue': '\033[1;34m',
            'bold_purple': '\033[1;35m',
            'bold_cyan': '\033[1;36m',
        }
        return color_map.get(color_name, '')


class ColoredAccessFormatter(logging.Formatter):
    """Formatter for access logs that colors status codes and includes timestamps."""

    def __init__(self, *args, **kwargs):
        """Initialize the formatter with a format that includes timestamp."""
        # Store datefmt for timestamp formatting
        self.datefmt = kwargs.pop('datefmt', '%Y-%m-%d %H:%M:%S')
        # Store log colors
        self.log_colors = kwargs.pop('log_colors', {
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'bold_red',
        })
        # Use a simple format - we'll format everything manually
        fmt = kwargs.pop('fmt', None) or (args[0] if args else '%(asctime)s - %(message)s')
        # Remove log_color and reset codes from format
        fmt = fmt.replace('%(log_color)s', '').replace('%(reset)s', '')
        # Call parent with remaining args and kwargs
        super().__init__(fmt, self.datefmt, *args[1:], **kwargs)

    def format(self, record):
        """Format the log record with colored timestamp and status codes."""
        # Get the log color for the level
        level_color_code = self._get_color_code(record.levelname, self.log_colors)
        reset_code = '\033[0m'
        
        # Format timestamp with color (green for INFO)
        timestamp = datetime.fromtimestamp(record.created).strftime(self.datefmt)
        timestamp_colored = f"{level_color_code}{timestamp}{reset_code}"
        
        # Get the original message
        message = record.getMessage()
        
        # Color status codes in the message
        def color_status_code(match):
            status = match.group(0)
            try:
                status_int = int(status)
                
                if 200 <= status_int < 300:
                    # Green for 2xx
                    return f"\033[32m{status}{reset_code}"  # Green
                elif 300 <= status_int < 400:
                    # Cyan for 3xx
                    return f"\033[36m{status}{reset_code}"  # Cyan
                elif 400 <= status_int < 500:
                    # Yellow for 4xx
                    return f"\033[33m{status}{reset_code}"  # Yellow
                elif 500 <= status_int < 600:
                    # Red for 5xx
                    return f"\033[31m{status}{reset_code}"  # Red
                else:
                    return status
            except ValueError:
                return status
        
        # Replace status codes with colored versions
        # Match 3-digit numbers that are likely HTTP status codes
        colored_message = re.sub(r'\b(\d{3})\b', color_status_code, message)
        
        # Return formatted message with colored timestamp
        return f"{timestamp_colored} - {colored_message}"
    
    def _get_color_code(self, levelname, log_colors):
        """Get ANSI color code for the log level."""
        color_name = log_colors.get(levelname, '')
        color_map = {
            'black': '\033[30m',
            'red': '\033[31m',
            'green': '\033[32m',
            'yellow': '\033[33m',
            'blue': '\033[34m',
            'purple': '\033[35m',
            'cyan': '\033[36m',
            'white': '\033[37m',
            'bold_red': '\033[1;31m',
            'bold_green': '\033[1;32m',
            'bold_yellow': '\033[1;33m',
            'bold_blue': '\033[1;34m',
            'bold_purple': '\033[1;35m',
            'bold_cyan': '\033[1;36m',
        }
        return color_map.get(color_name, '')

