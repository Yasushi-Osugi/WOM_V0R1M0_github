pysi/utils/util.py
def make_logger(cfg: Optional[object] = None):
    import os, logging
    level_name = os.getenv("LOGLEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")
    return logging.getLogger("pysi")
