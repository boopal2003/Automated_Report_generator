# utils/logger.py
import logging
import os
from logging.handlers import RotatingFileHandler

BASE_DIR = os.path.dirname(os.path.dirname(__file__))  # project root when this file is in utils/
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

def _make_logger(name: str, filename: str, level=logging.INFO):
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # already configured
    logger.setLevel(level)
    fh = RotatingFileHandler(os.path.join(LOG_DIR, filename), maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    fh.setLevel(level)
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    # also add console handler for dev
    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    return logger

app_logger = _make_logger("report_gen.app", "app.log")
sql_error_logger = _make_logger("report_gen.sql_errors", "sql_errors.log", level=logging.WARNING)
exec_logger = _make_logger("report_gen.executions", "executions.log", level=logging.INFO)
