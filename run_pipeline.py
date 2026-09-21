"""
Run the weather ETL pipeline: extract, transform, load, report.

    python run_pipeline.py                     # live API if OWM_API_KEY is set, otherwise sample data
    python run_pipeline.py --source sample     # generated sample data, no key or internet needed
    python run_pipeline.py --source live       # real readings (needs OWM_API_KEY, see .env.example)
    python run_pipeline.py --cities London Rome --no-report
"""

import argparse
import sys
import time

from weather_etl import config
from weather_etl.extract import ApiKeyError, extract
from weather_etl.load import load
from weather_etl.report import build_report
from weather_etl.transform import transform_all


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Weather data ETL pipeline")
    p.add_argument("--source", choices=["live", "sample"],
                   default="live" if config.API_KEY else "sample",
                   help="where readings come from (default: live if a key is set, else sample)")
    p.add_argument("--cities", nargs="+", default=config.CITIES, help="cities to fetch")
    p.add_argument("--days", type=int, default=7, help="days of history to generate in sample mode")
    p.add_argument("--no-report", action="store_true", help="skip charts, HTML and Excel")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    print(f"Source: {args.source} | cities: {', '.join(args.cities)}")

    t = time.perf_counter()
    try:
        payloads, fetch_errors = extract(args.source, args.cities, days=args.days)
    except ApiKeyError as exc:
        print(f"Cannot continue: {exc}")
        return 2
    print(f"[1/4] EXTRACT   {len(payloads)} readings, {len(fetch_errors)} failed "
          f"({time.perf_counter() - t:.2f}s)")
    for city, reason in fetch_errors:
        print(f"        - {city}: {reason}")

    t = time.perf_counter()
    readings, rejects = transform_all(payloads)
    print(f"[2/4] TRANSFORM {len(readings)} valid, {len(rejects)} rejected "
          f"({time.perf_counter() - t:.2f}s)")
    for city, reason, _ in rejects[:5]:
        print(f"        - {city}: {reason}")

    t = time.perf_counter()
    result = load(readings, rejects, args.source, fetched=len(payloads), fetch_errors=len(fetch_errors))
    print(f"[3/4] LOAD      {result['inserted']} new, {result['duplicates']} already stored, "
          f"{result['total_rows']} rows in database ({time.perf_counter() - t:.2f}s)")

    if args.no_report:
        print("[4/4] REPORT    skipped")
    else:
        t = time.perf_counter()
        out = build_report()
        print(f"[4/4] REPORT    written to {out} ({time.perf_counter() - t:.2f}s)")
    return 0 if not fetch_errors or payloads else 1


if __name__ == "__main__":
    sys.exit(main())
