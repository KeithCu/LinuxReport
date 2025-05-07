"""
config_utils.py

Utilities for loading configuration from config.yaml file.
"""

import os
import yaml
from shared import PATH
import logging

# Empty default configuration with no password fallback
DEFAULT_CONFIG = {
    'admin': {
        'password': 'CHANGE_THIS_PASSWORD'  # Emergency fallback only if file missing
    }
}

def load_config():
    """
    Load configuration from config.yaml file.
    Returns a dictionary with configuration values.
    """
    config_path = os.path.join(PATH, 'config.yaml')
    config = DEFAULT_CONFIG.copy()
    
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                yaml_config = yaml.safe_load(f)
                
                # Update config with values from YAML file
                if yaml_config and isinstance(yaml_config, dict):
                    # Handle admin section
                    if 'admin' in yaml_config and isinstance(yaml_config['admin'], dict):
                        config['admin'].update(yaml_config['admin'])
        else:
            logging.warning(f"Config file not found: {config_path}. Using fallback values.")
    except Exception as e:
        logging.error(f"Error loading config.yaml: {e}")
    
    return config

def get_admin_password():
    """Get the admin password from configuration."""
    config = load_config()
    return config['admin']['password'] 