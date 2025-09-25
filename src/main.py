from .config_loader import load_config
from .logging_setup import setup_logging

def main():
    cfg = load_config()
    setup_logging(cfg)
    print('Google_Drive_Manager placeholder CLI')

if __name__ == '__main__':
    main()
