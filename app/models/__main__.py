from __future__ import annotations

import argparse
import logging
import sys

logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m app.models")
    sub = parser.add_subparsers(dest="cmd", required=True)

    tr = sub.add_parser("train", help="Train + save model to registry")
    tr.add_argument("--symbol", required=True)
    tr.add_argument("--timeframes", default="1h,4h")
    tr.add_argument("--model", default="intraday_lgbm", choices=["intraday_lgbm", "meta_lgbm", "elasticnet"])

    ev = sub.add_parser("eval", help="Walk-forward eval model vs baseline")
    ev.add_argument("--symbol", required=True)
    ev.add_argument("--timeframes", default="1h,4h")

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    if args.cmd == "train":
        from app.models.train import train_model

        for tf in [t.strip() for t in args.timeframes.split(",")]:
            name = train_model(args.symbol.upper(), tf, args.model)
            print(f"trained: {name}")
    elif args.cmd == "eval":
        from app.models.eval import eval_symbol

        for tf in [t.strip() for t in args.timeframes.split(",")]:
            report = eval_symbol(args.symbol.upper(), tf)
            print(f"{args.symbol.upper()} {tf}: acc={report['accuracy']:.3f} brier={report['brier']:.3f} n={report['n']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
