import argparse
from core.logger import setup_logging
from .client import PumpMaster


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ip", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=502)
    parser.add_argument("--poll", type=float, default=1.0)
    args = parser.parse_args()

    setup_logging()
    PumpMaster(args.ip, args.port, poll_interval=args.poll).run()


if __name__ == "__main__":
    main()