"""
main_dispatcher.py

WSGI dispatcher for LinuxReport project that handles multiple report types
and manages different application paths efficiently.
"""

import os
import sys
import logging
from typing import Dict, Any, Callable
from shared import Mode, PATH

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Dictionary to store WSGI applications for each mode
wsgi_apps: Dict[str, Callable] = {}

# Map each mode to its directory name
MODE_DIRECTORIES = {
    Mode.LINUX_REPORT: "linux_report",
    Mode.COVID_REPORT: "covid_report",
    Mode.TECHNO_REPORT: "techno_report",
    Mode.AI_REPORT: "ai_report",
    Mode.PYTHON_REPORT: "python_report",
    Mode.TRUMP_REPORT: "trump_report",
    Mode.SPACE_REPORT: "space_report",
    Mode.PV_REPORT: "pv_report",
}

def load_wsgi_app(mode: Mode) -> Callable:
    """
    Load the WSGI application for a specific mode.
    Handles path management and imports for each report type.
    """
    try:
        # Get the directory name for this mode
        dir_name = MODE_DIRECTORIES.get(mode)
        if not dir_name:
            logger.error(f"No directory mapping found for mode: {mode.value}")
            return None

        # Add the specific report's directory to Python path
        report_path = os.path.join(PATH, dir_name)
        if report_path not in sys.path:
            sys.path.insert(0, report_path)
        
        # Import the application from the specific report's app.py
        module = __import__(f"{dir_name}.app", fromlist=["application"])
        return module.application
    except ImportError as e:
        logger.error(f"Failed to import WSGI application for {mode.value}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error loading {mode.value} application: {e}")
        return None

def application(environ: Dict[str, Any], start_response: Callable) -> bytes:
    """
    Main WSGI application dispatcher.
    Routes requests to the appropriate report type based on the hostname.
    """
    try:
        # Get the hostname from the WSGI environment
        host = environ.get('HTTP_HOST', '').lower()
        
        # Map hostnames to report types
        host_to_mode = {
            'linuxreport.net': Mode.LINUX_REPORT,
            'www.linuxreport.net': Mode.LINUX_REPORT,
            'covidreport.net': Mode.COVID_REPORT,
            'www.covidreport.net': Mode.COVID_REPORT,
            'technoreport.net': Mode.TECHNO_REPORT,
            'www.technoreport.net': Mode.TECHNO_REPORT,
            'aireport.net': Mode.AI_REPORT,
            'www.aireport.net': Mode.AI_REPORT,
            'pythonreport.net': Mode.PYTHON_REPORT,
            'www.pythonreport.net': Mode.PYTHON_REPORT,
            'trumpreport.net': Mode.TRUMP_REPORT,
            'www.trumpreport.net': Mode.TRUMP_REPORT,
            'spacereport.net': Mode.SPACE_REPORT,
            'www.spacereport.net': Mode.SPACE_REPORT,
            'pvreport.net': Mode.PV_REPORT,
            'www.pvreport.net': Mode.PV_REPORT,
        }
        
        # Get the appropriate mode for this hostname
        mode = host_to_mode.get(host)
        
        if not mode:
            # Return 404 if no matching hostname is found
            logger.warning(f"No matching mode found for hostname: {host}")
            status = '404 Not Found'
            headers = [('Content-type', 'text/plain')]
            start_response(status, headers)
            return [b"404 Not Found - No matching report type for this hostname"]
        
        # Lazy load the WSGI application if not already loaded
        if mode.value not in wsgi_apps:
            wsgi_apps[mode.value] = load_wsgi_app(mode)
        
        app = wsgi_apps[mode.value]
        
        if app is None:
            # Handle case where application failed to load
            status = '500 Internal Server Error'
            headers = [('Content-type', 'text/plain')]
            start_response(status, headers)
            return [b"Error: Application failed to load"]
        
        # Pass the request to the appropriate application
        return app(environ, start_response)
        
    except Exception as e:
        logger.error(f"Dispatcher error: {e}")
        status = '500 Internal Server Error'
        headers = [('Content-type', 'text/plain')]
        start_response(status, headers)
        return [b"Internal Server Error"]

# To run this with Gunicorn:
# gunicorn --workers 2 --threads 8 --bind 127.0.0.1:8000 main_dispatcher:application