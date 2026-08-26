import argparse
import logging
import sys


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m app.ingest")
    sub = parser.add_subparsers(dest="cmd", required=True)

    bf = sub.add_parser("backfill", help="Backfill historical klines into DuckDB")
    bf.add_argument("--symbol", required=True)
    bf.add_argument("--timeframes", default="5m,15m,1h,4h,1d,1w")
    bf.add_argument("--days", type=int, default=365)
    bf.add_argument("--resume", action="store_true", help="Resume from checkpoint")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    if args.cmd == "backfill":
        from app.connectors.binance_rest import BinanceRestClient
        from app.config import settings
        from app.ingest.backfill import BackfillRunner
        from app.storage.duckdb_store import DuckDBStore

        client = BinanceRestClient(base_url=settings.binance_rest_base)
        try:
            client.ping()
        except RuntimeError as e:
            print(f"CONNECTIVITY CHECK FAILED: {e}", file=sys.stderr)
            return 1

        import duckdb
        import os

        os.makedirs(settings.data_dir, exist_ok=True)
        conn = duckdb.connect(settings.db_path)
        reject_path = os.path.join(settings.data_dir, "rejects", "klines-reject.log")
        store = DuckDBStore(conn, reject_log_path=reject_path)
        runner = BackfillRunner(store=store, client=client)
        tfs = [t.strip() for t in args.timeframes.split(",")]
        inserted = runner.backfill(args.symbol.upper(), tfs, days=args.days, resume=args.resume)
        print(f"Inserted/updated {inserted} candles for {args.symbol} across {len(tfs)} timeframes")
        if store.reject_log:
            print(f"{len(store.reject_log)} klines rejected — see {reject_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
