import logging, json, sys
def setup_logging(cfg):
    level = getattr(logging, cfg.get('logging', {}).get('level','INFO'))
    logging.basicConfig(level=level, stream=sys.stdout, format='%(message)s')
