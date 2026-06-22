"""
User Service
An MCP-enabled multi-tenant user management service.
"""

import logging

__version__ = "0.1.0"
__author__ = "Multi-Tenant Platform Team"

# Configure package-level logger
logger = logging.getLogger("user_service")
logger.setLevel(logging.INFO)

# Ensure logs are propagated or handled gracefully
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

__all__ = ["__version__", "__author__", "logger"]