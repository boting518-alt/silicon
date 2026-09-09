"""Separate process; reuses the installed silicon package."""
import argparse
import logging
import signal
import threading
from sqlalchemy.exc import SQLAlchemyError
from silicon.settings import Settings
from silicon.shared.db import make_engine
from silicon.shared.jobs import enqueue_smoke, run_once


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Poll once, then exit")
    parser.add_argument("--enqueue", metavar="DEDUPE_KEY", help="Insert one development smoke job, then exit")
    args = parser.parse_args()
    engine = make_engine(Settings.from_env().database_url)
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    try:
        if args.enqueue:
            print(enqueue_smoke(engine, args.enqueue))
            return
        while not stop.is_set():
            try:
                processed = run_once(engine)
            except SQLAlchemyError:
                # Do not log SQL, DSNs, credentials, or parameter contents.
                logging.error("worker_database_unavailable")
                if args.once:
                    raise SystemExit(1)
                processed = False
            if args.once:
                return
            if not processed:
                stop.wait(1)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
