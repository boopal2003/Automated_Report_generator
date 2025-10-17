# run_server.py
import os
import sys
import signal
import logging
from waitress import serve

# Ensure script directory is the working dir and on sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Now import the flask app
from app import app

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger("report_gen")

def handle_signals(signum, frame):
    logger.info("Received signal %s, shutting down.", signum)
    sys.exit(0)

signal.signal(signal.SIGINT, handle_signals)
signal.signal(signal.SIGTERM, handle_signals)

def main():
    port = int(os.environ.get("PORT", "7878"))
    host = os.environ.get("HOST", "0.0.0.0")

    if not os.environ.get("OPENAI_API_KEY"):
        logger.warning("OPENAI_API_KEY is not set. LLM calls will fail unless you set this environment variable.")

    logger.info("Starting Waitress on %s:%s", host, port)
    serve(app, host=host, port=port)

if __name__ == "__main__":
    main()
