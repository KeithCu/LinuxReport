"""
config_utils.py

Utilities for loading configuration from config.yaml file.
"""

import os
import yaml
from shared import PATH
import logging

def load_config():
    """
    Load configuration from config.yaml file.
    Returns a dictionary with configuration values.
    Raises an exception if the config file is missing or if necessary keys are missing.
    """
    config_path = os.path.join(PATH, 'config.yaml')
    
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                yaml_config = yaml.safe_load(f)
                
                # Update config with values from YAML file
                if yaml_config and isinstance(yaml_config, dict):
                    # Handle admin section
                    if 'admin' in yaml_config and isinstance(yaml_config['admin'], dict):
                        return yaml_config
                    else:
                        raise ValueError("Missing 'admin' section in config file.")
        else:
            raise FileNotFoundError(f"Config file not found: {config_path}")
    except Exception as e:
        logging.error(f"Error loading config.yaml: {e}")
        raise

def get_admin_password():
    """Get the admin password from configuration."""
    config = load_config()
    return config['admin']['password'] 