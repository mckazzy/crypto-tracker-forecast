from __future__ import annotations

import csv
import io
import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.config import settings
from app.connectors.binance_rest import MS_PER_UNIT
from app.forecast.registry import registry
from app.forecast.schema import ForecastContext, Signal, SignalDirection, SignalStatus, UserForecastInput
from app.storage.duckdb_store import DuckDBStore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/forecast")
leaderboard_router = APIRouter(prefix="/api")


def _store() -> DuckDBStore:
    from app.api.routes import get_store

    return get_store()


def _get_provider(name: str):
    """Lấy provider theo tên; tự tạo AI hoặc offline model nếu chưa đăng ký."""
    prov = registry.get(name)
    if prov is not None:
        return prov
    if name == "ai":
        if not settings.ai_enabled:
            return None
        from app.forecast.ai_provider import AIProvider

        prov = AIProvider()
        registry.register(prov)
        return prov
    if name == "local":
        # resolve "local" → intraday_lgbm@SYMBOL@TIMEFRAME (không có symbol/timeframe ở đây → gọi _get_provider_local)
        return None
    # offline model file-based
    from app.models.registry import model_registry

    if model_registry.has(name):
        from app.models.intraday import IntradayProvider

        prov = IntradayProvider(name)
        registry.register(prov)
        return prov
    return None


def _get_provider_local(symbol: str, timeframe: str):
    """Provider offline (intraday_lgbm) cho symbol/timeframe — resolve từ 'local'."""
    name = f"intraday_lgbm@{symbol}@{timeframe}"
    prov = registry.get(name)
    if prov is not None:
        return prov
    from app.models.registry import model_registry

    if not model_registry.has(name):
        return None
    from app.models.intraday import IntradayProvider

    prov = IntradayProvider(name)
    registry.register(prov)
    return prov


def _set_valid_until(signal: dict, timeframe: str) -> dict:
    """Gán valid_until = created_at + 1×timeframe (hết hạn sau 1 kỳ dự đoán).

    Ưu tiên thời điểm tạo (created_at) để forecast cũ không bị đẩy tương lai.
    """
    step_ms = MS_PER_UNIT.get(timeframe)
    if not step_ms or signal.get("valid_until"):
        return signal
    base = signal.get("created_at") or datetime.now(UTC).isoformat()
    try:
        base_dt = datetime.fromisoformat(base)
        if base_dt.tzinfo is None:
            base_dt = base_dt.replace(tzinfo=UTC)
    except ValueError:
        base_dt = datetime.now(UTC)
    signal["valid_until"] = (base_dt + timedelta(milliseconds=step_ms)).isoformat()
    return signal


@router.get("/health")
async def forecast_health() -> dict:
    return {"providers": registry.health()}


@router.post("/run")
async def run_forecast(
    provider: str = Query(...),
    symbol: str = Query(...),
    timeframe: str = Query(...),
) -> dict:
    """Chạy dự báo cho 1 provider riêng (ai hoặc local model), lưu + trả record kèm id."""
    symbol_u = symbol.upper()
    tf = timeframe.lower()

    if provider == "local":
        prov = _get_provider_local(symbol_u, tf)
    else:
        prov = _get_provider(provider)
    if prov is None:
        raise HTTPException(404, f"provider unavailable: {provider}")

    store = _store()
    candles = store.get_klines(symbol_u, tf, limit=100)
    if not candles:
        raise HTTPException(404, f"no klines for {symbol_u} {tf}")
    ctx = ForecastContext(symbol=symbol_u, timeframe=tf, candles=candles)

    try:
        signal = prov.forecast(ctx)
        registry.record_success(prov.name)
    except Exception as e:
        logger.warning("provider %s failed: %s", provider, e)
        registry.record_error(provider, str(e))
        raise HTTPException(502, f"provider {provider} failed: {e}")

    payload = signal.model_dump(mode="json")
    _set_valid_until(payload, tf)
    forecast_id = store.save_forecast(symbol_u, tf, prov.name, payload)
    return {
        "id": forecast_id,
        "symbol": symbol_u,
        "timeframe": tf,
        "provider": prov.name,
        "signal": payload,
        "valid_until": payload.get("valid_until"),
        "created_at": payload.get("created_at"),
    }


@router.post("/user")
async def create_user_forecast(req: UserForecastInput) -> dict:
    """Tạo dự báo thủ công từ User, tự động tính valid_until và lưu vào DuckDB."""
    symbol_u = req.symbol.upper()
    tf = req.timeframe.lower()
    store = _store()

    entry = req.entry
    if entry is None or entry <= 0:
        candles = store.get_klines(symbol_u, tf, limit=1)
        if candles:
            entry = float(candles[-1]["close"])
        else:
            raise HTTPException(400, f"Cannot resolve current price for {symbol_u} {tf} - please specify entry")

    tp_list = req.take_profit if isinstance(req.take_profit, list) else ([req.take_profit] if req.take_profit else [])
    sl = req.stop_loss

    rr = None
    if entry and tp_list and sl:
        risk = abs(entry - sl)
        reward = abs(tp_list[0] - entry)
        if risk > 0:
            rr = round(reward / risk, 2)

    signal_obj = Signal(
        symbol=symbol_u,
        timeframe=tf,
        direction=req.direction,
        probability=req.probability,
        entry=entry,
        take_profit=tp_list,
        stop_loss=sl,
        rr_ratio=rr,
        model="user",
        token_cost=0,
    )
    payload = signal_obj.model_dump(mode="json")
    _set_valid_until(payload, tf)

    forecast_id = store.save_forecast(symbol_u, tf, "user", payload)
    return {
        "id": forecast_id,
        "symbol": symbol_u,
        "timeframe": tf,
        "provider": "user",
        "signal": payload,
        "valid_until": payload.get("valid_until"),
        "created_at": payload.get("created_at"),
    }


@leaderboard_router.get("/leaderboard")
async def leaderboard(
    symbol: str | None = Query(None),
    timeframe: str | None = Query(None),
) -> dict:
    """Xếp hạng provider: merge forecasts table + model registry meta (type, brier)."""
    store = _store()
    rows = store.get_forecasts(symbol=symbol.upper() if symbol else None,
                               timeframe=timeframe.lower() if timeframe else None,
                               limit=5000)
    by_provider: dict[str, dict] = {}
    for r in rows:
        name = r["provider"]
        entry = by_provider.setdefault(
            name, {"name": name, "signals": 0, "ok_signals": 0, "total_token_cost": 0}
        )
        entry["signals"] += 1
        if r["status"] == "ok":
            entry["ok_signals"] += 1
        entry["total_token_cost"] += int(r["token_cost"] or 0)

    # merge model registry meta (type/brier) vào provider entries
    from app.models.registry import model_registry

    for entry in by_provider.values():
        meta = _registry_meta(entry["name"])
        if meta:
            entry["model_type"] = meta.get("type", "unknown")
            entry["brier"] = meta.get("brier")

    providers = sorted(
        by_provider.values(),
        key=lambda p: (-p["total_token_cost"], -p["signals"]),
    )
    return {"symbol": symbol, "timeframe": timeframe, "providers": providers}


def _build_outcome_map(store) -> dict[int, dict]:
    """Lấy outcome mới nhất cho mỗi forecast signal_id (do get_outcomes đã sort resolved_at DESC)."""
    outcomes = store.get_outcomes(limit=5000)
    out_map: dict[int, dict] = {}
    for o in outcomes:
        sid = o.get("signal_id")
        if sid and sid not in out_map:
            out_map[sid] = o
    return out_map


@router.get("/history")
async def forecast_history(
    symbol: str | None = Query(None),
    timeframe: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
) -> dict:
    """Lịch sử forecasts (mới nhất) — để UI hiển thị nút xác nhận outcome."""
    store = _store()
    rows = store.get_forecasts(
        symbol=symbol.upper() if symbol else None,
        timeframe=timeframe.lower() if timeframe else None,
        limit=limit,
    )
    outcome_by_id = _build_outcome_map(store)
    out = []
    for r in rows:
        sig = r["signal"]
        _set_valid_until(sig, r["timeframe"])
        raw_o = outcome_by_id.get(r["id"])
        outcome = (
            {
                "outcome": raw_o["outcome"],
                "user_override": raw_o.get("user_override", False),
                "resolved_at": raw_o.get("resolved_at"),
                "score": raw_o.get("score"),
                "exit_price": raw_o.get("exit_price"),
            }
            if raw_o is not None
            else None
        )
        out.append(
            {
                "id": r["id"],
                "symbol": r["symbol"],
                "timeframe": r["timeframe"],
                "provider": r["provider"],
                "status": r["status"],
                "created_at": r["created_at"],
                "signal": sig,
                "valid_until": sig.get("valid_until"),
                "outcome": outcome,
            }
        )
    return {"forecasts": out}


def _registry_meta(model_name: str) -> dict | None:
    from app.models.registry import model_registry

    try:
        _, meta = model_registry.load_model(model_name)
        return meta
    except Exception:
        return None


@router.get("/compare/{symbol}/{timeframe}")
async def compare_forecast(symbol: str, timeframe: str) -> dict:
    """Chạy AI + model offline (intraday_lgbm) song song, trả kết quả so sánh.

    Cả 2 signal được lưu vào forecasts (leaderboard + outcome tracking).
    """
    symbol_u = symbol.upper()
    tf = timeframe.lower()

    store = _store()
    candles = store.get_klines(symbol_u, tf, limit=100)
    if not candles:
        raise HTTPException(404, f"no klines for {symbol_u} {tf}")
    ctx = ForecastContext(symbol=symbol_u, timeframe=tf, candles=candles)

    providers: dict[str, str] = {"ai": "ai"}
    offline_name = f"intraday_lgbm@{symbol_u}@{tf}"
    if _get_provider(offline_name) is not None:
        providers[offline_name] = offline_name

    results: dict[str, dict] = {}
    for name, provider_name in providers.items():
        prov = _get_provider(provider_name)
        if prov is None:
            results[name] = {"error": f"provider unavailable: {provider_name}"}
            continue
        try:
            signal = prov.forecast(ctx)
            registry.record_success(prov.name)
            payload = signal.model_dump(mode="json")
            _set_valid_until(payload, tf)
            try:
                store.save_forecast(symbol_u, tf, prov.name, payload)
            except Exception:
                logger.exception("failed to cache forecast")
            results[name] = payload
        except Exception as e:
            logger.warning("provider %s failed: %s", provider_name, e)
            registry.record_error(provider_name, str(e))
            results[name] = {"error": str(e)}

    return {"symbol": symbol_u, "timeframe": tf, "results": results}


@router.get("/forecasts")
async def list_forecasts(
    symbol: str | None = Query(None),
    timeframe: str | None = Query(None),
    provider: str | None = Query(None),
    limit: int = Query(200, ge=1, le=1000),
) -> dict:
    """Danh sách tất cả dự báo (id, mốc thời gian, trạng thái đối chiếu)."""
    store = _store()
    rows = store.get_forecasts(
        symbol=symbol.upper() if symbol else None,
        timeframe=timeframe.lower() if timeframe else None,
        limit=limit,
    )
    outcome_by_id = _build_outcome_map(store)
    out = []
    for r in rows:
        if provider and r["provider"] != provider:
            continue
        sig = r["signal"]
        _set_valid_until(sig, r["timeframe"])
        valid_until = sig.get("valid_until")
        raw_o = outcome_by_id.get(r["id"])
        outcome = (
            {
                "outcome": raw_o["outcome"],
                "user_override": raw_o.get("user_override", False),
                "resolved_at": raw_o.get("resolved_at"),
                "score": raw_o.get("score"),
                "exit_price": raw_o.get("exit_price"),
            }
            if raw_o is not None
            else None
        )
        expired = _is_expired(valid_until)
        out.append(
            {
                "id": r["id"],
                "symbol": r["symbol"],
                "timeframe": r["timeframe"],
                "provider": r["provider"],
                "source": _provider_source(r["provider"]),
                "direction": sig.get("direction"),
                "probability": sig.get("probability"),
                "entry": sig.get("entry"),
                "take_profit": sig.get("take_profit", []),
                "stop_loss": sig.get("stop_loss"),
                "exit_price": raw_o.get("exit_price") if raw_o else None,
                "created_at": r["created_at"],
                "valid_until": valid_until,
                "expired": expired,
                "scored": outcome is not None,
                "outcome": outcome,
            }
        )
    return {"forecasts": out}


def _provider_source(provider: str) -> str:
    if provider == "ai":
        return "AI"
    if provider == "user" or provider.startswith("user"):
        return "User"
    if provider.startswith("intraday_lgbm") or provider in ("random_walk", "ewma_vol"):
        return "Local"
    return "Local"


def _is_expired(valid_until: str | None) -> bool:
    if not valid_until:
        return False
    try:
        return datetime.fromisoformat(valid_until) <= datetime.now(UTC)
    except ValueError:
        return False


def _parse_until(valid_until: str | None) -> datetime | None:
    if not valid_until:
        return None
    try:
        dt = datetime.fromisoformat(valid_until)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except ValueError:
        return None


@router.delete("/forecasts/{forecast_id}")
async def delete_forecast(forecast_id: int) -> dict:
    """Xóa 1 dự báo và outcome liên quan theo ID."""
    store = _store()
    fc = store.get_forecast_by_id(forecast_id)
    if fc is None:
        raise HTTPException(404, f"forecast {forecast_id} not found")
    store.delete_forecast(forecast_id)
    return {"deleted": True, "id": forecast_id}


@router.post("/forecasts/{forecast_id}/score")
async def score_forecast(forecast_id: int) -> dict:
    """Chấm điểm 1 dự báo: so giá cuối khung với TP/SL → điểm %."""
    from app.trading.scoring import exit_price_at, score_forecast as calc_score

    store = _store()
    fc = store.get_forecast_by_id(forecast_id)
    if fc is None:
        raise HTTPException(404, f"forecast {forecast_id} not found")

    sig = fc["signal"]
    _set_valid_until(sig, fc["timeframe"])
    valid_until = _parse_until(sig.get("valid_until"))
    if valid_until is None:
        raise HTTPException(400, "forecast missing valid_until")

    direction = sig.get("direction")
    entry = sig.get("entry")
    tp_list = sig.get("take_profit", [])
    tp = tp_list[0] if tp_list else None
    sl = sig.get("stop_loss")
    if direction not in ("LONG", "SHORT") or entry is None:
        return {
            "scored": False,
            "forecast_id": forecast_id,
            "message": f"Không chấm được — dự báo #{forecast_id} không có hướng LONG/SHORT hợp lệ",
            "exit_price": None,
        }

    exit_price = exit_price_at(store, fc["symbol"], fc["timeframe"], valid_until)
    if exit_price is None:
        return {"scored": False, "message": "Chưa tới thời điểm chốt — không có giá kết thúc", "exit_price": None}

    score = calc_score(direction, entry, tp, sl, exit_price)
    outcome = "win" if score > 0 else ("neutral" if score == 0 else "lose")
    store.save_outcome(
        {
            "signal_id": forecast_id,
            "symbol": fc["symbol"],
            "timeframe": fc["timeframe"],
            "model": fc["provider"],
            "direction": direction,
            "entry": entry,
            "tp": tp,
            "sl": sl,
            "exit_price": exit_price,
            "outcome": outcome,
            "user_override": False,
            "source": "auto-score",
            "score": score,
        }
    )
    return {
        "scored": True,
        "forecast_id": forecast_id,
        "exit_price": exit_price,
        "score": score,
        "outcome": outcome,
    }


@router.post("/forecasts/score-all")
async def score_all_expired() -> dict:
    """Chấm tất cả dự báo đã quá hạn nhưng chưa được chấm."""
    from app.trading.scoring import exit_price_at, score_forecast as calc_score

    store = _store()
    rows = store.get_forecasts(limit=1000)
    outcomes = store.get_outcomes(limit=5000)
    outcome_by_id = {o.get("signal_id"): o for o in outcomes if o.get("signal_id")}
    scored = 0
    skipped = 0
    details = []
    errors: list[dict] = []
    for r in rows:
        try:
            sig = r["signal"]
            _set_valid_until(sig, r["timeframe"])
            valid_until = _parse_until(sig.get("valid_until"))
            if valid_until is None:
                continue
            # bỏ qua nếu forecast này đã có outcome
            if outcome_by_id.get(r["id"]) is not None:
                continue
            if valid_until > datetime.now(UTC):
                skipped += 1
                continue
            direction = sig.get("direction")
            entry = sig.get("entry")
            if direction not in ("LONG", "SHORT") or entry is None:
                skipped += 1
                continue
            exit_price = exit_price_at(store, r["symbol"], r["timeframe"], valid_until)
            if exit_price is None:
                skipped += 1
                continue
            tp_list = sig.get("take_profit", [])
            tp = tp_list[0] if tp_list else None
            sl = sig.get("stop_loss")
            score = calc_score(direction, entry, tp, sl, exit_price)
            outcome = "win" if score > 0 else ("neutral" if score == 0 else "lose")
            store.save_outcome(
                {
                    "signal_id": r["id"],
                    "symbol": r["symbol"],
                    "timeframe": r["timeframe"],
                    "model": r["provider"],
                    "direction": direction,
                    "entry": entry,
                    "tp": tp,
                    "sl": sl,
                    "exit_price": exit_price,
                    "outcome": outcome,
                    "user_override": False,
                    "source": "auto-score",
                    "score": score,
                }
            )
            scored += 1
            details.append({"id": r["id"], "score": score, "exit_price": exit_price, "outcome": outcome})
        except Exception as e:
            logger.exception("score-all failed for forecast %s", r.get("id"))
            errors.append({"id": r.get("id"), "error": str(e)})
    return {"scored": scored, "skipped": skipped, "details": details, "errors": errors}


@router.get("/forecasts/analytics")
async def forecast_analytics() -> dict:
    """Tổng hợp: phân chia long/short, độ chính xác theo nguồn, win/lose."""
    store = _store()
    rows = store.get_forecasts(limit=1000)
    outcome_by_signal = _build_outcome_map(store)

    long_count = short_count = 0
    scored_total = 0
    score_sum = 0.0
    by_source: dict[str, dict] = {}
    by_direction: dict[str, dict] = {}

    for r in rows:
        sig = r["signal"]
        direction = sig.get("direction")
        src = _provider_source(r["provider"])
        if direction == "LONG":
            long_count += 1
        elif direction == "SHORT":
            short_count += 1

        by_source.setdefault(src, {"total": 0, "scored": 0, "score_sum": 0.0, "wins": 0, "losses": 0})
        by_source[src]["total"] += 1
        by_direction.setdefault(direction, {"total": 0, "scored": 0, "score_sum": 0.0})
        by_direction[direction]["total"] += 1

        o = outcome_by_signal.get(r["id"])
        if o is not None and o.get("score") is not None:
            score = float(o["score"])
            scored_total += 1
            score_sum += score
            by_source[src]["scored"] += 1
            by_source[src]["score_sum"] += score
            if o["outcome"] == "win":
                by_source[src]["wins"] += 1
            else:
                by_source[src]["losses"] += 1
            by_direction[direction]["scored"] += 1
            by_direction[direction]["score_sum"] += score

    def _acc(d):
        return round(d["score_sum"] / d["scored"], 1) if d["scored"] else 0.0

    return {
        "total": len(rows),
        "scored_total": scored_total,
        "avg_accuracy": round(score_sum / scored_total, 1) if scored_total else 0.0,
        "direction_split": {"LONG": long_count, "SHORT": short_count, "FLAT": len(rows) - long_count - short_count},
        "by_source": {
            src: {**d, "accuracy": _acc(d)} for src, d in by_source.items()
        },
        "by_direction": {
            d: {**v, "accuracy": round(v["score_sum"] / v["scored"], 1) if v["scored"] else 0.0}
            for d, v in by_direction.items()
        },
    }


@router.get("/forecasts/export.csv")
async def export_forecasts_csv(
    symbol: str | None = Query(None),
    timeframe: str | None = Query(None),
) -> StreamingResponse:
    """Xuất toàn bộ dự báo ra CSV."""
    store = _store()
    rows = store.get_forecasts(
        symbol=symbol.upper() if symbol else None,
        timeframe=timeframe.lower() if timeframe else None,
        limit=5000,
    )
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["id", "symbol", "timeframe", "provider", "source", "direction", "probability",
         "entry", "take_profit", "stop_loss", "exit_price", "rr_ratio", "created_at", "valid_until",
         "expired", "scored", "outcome", "score"]
    )
    outcome_by_id = _build_outcome_map(store)
    for r in rows:
        sig = r["signal"]
        _set_valid_until(sig, r["timeframe"])
        valid_until = sig.get("valid_until")
        outcome = outcome_by_id.get(r["id"])
        writer.writerow(
            [
                r["id"], r["symbol"], r["timeframe"], r["provider"], _provider_source(r["provider"]),
                sig.get("direction"), sig.get("probability"), sig.get("entry"),
                ";".join(str(x) for x in sig.get("take_profit", [])), sig.get("stop_loss"),
                outcome["exit_price"] if outcome else "",
                sig.get("rr_ratio"), r["created_at"], valid_until,
                "yes" if _is_expired(valid_until) else "no",
                "yes" if outcome else "no",
                outcome["outcome"] if outcome else "",
                outcome["score"] if outcome else "",
            ]
        )
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=forecasts.csv"},
    )


def _latest_outcome(store, forecast_id: int) -> dict | None:
    """Outcome chính xác theo ID dự báo (nếu có)."""
    for o in store.get_outcomes(limit=5000):
        if o.get("signal_id") == forecast_id:
            return {"outcome": o["outcome"], "user_override": o["user_override"],
                    "resolved_at": o["resolved_at"], "score": o.get("score")}
    return None


@router.post("/retrain")
async def retrain_model(symbol: str = Query(...), timeframe: str = Query(...)) -> dict:
    """Retrain offline model từ feedback outcomes (champion-challenger)."""
    from app.api.routes import get_store
    from app.trading.retrain import retrain_from_outcomes_detailed

    store = get_store()
    try:
        res = retrain_from_outcomes_detailed(store, symbol.upper(), timeframe.lower(), "intraday_lgbm", min_outcomes=5)
        return res
    except Exception as e:
        logger.exception("retrain failed")
        raise HTTPException(500, f"retrain failed: {e}")


# Route động — khai báo CUỐI CÙNG để không nuốt các route tĩnh /forecasts*
@router.get("/{symbol}/{timeframe}")
async def get_forecast(
    symbol: str,
    timeframe: str,
    provider: str | None = Query(None),
) -> dict:
    """Forecast qua registry. Provider mặc định: provider đầu tiên hoặc fallback baseline."""
    symbol_u = symbol.upper()
    tf = timeframe.lower()

    if provider is not None:
        prov = registry.get(provider)
        if prov is None:
            raise HTTPException(404, f"unknown provider: {provider}")
        candidates = [prov]
    else:
        names = registry.list()
        if not names:
            raise HTTPException(503, "no forecast providers registered")
        candidates = [registry.get(n) for n in names]
        candidates = [c for c in candidates if c is not None]

    store = _store()
    candles = store.get_klines(symbol_u, tf, limit=100)
    ctx = ForecastContext(symbol=symbol_u, timeframe=tf, candles=candles)

    last_error = None
    for prov in candidates:
        try:
            signal = prov.forecast(ctx)
            registry.record_success(prov.name)
            payload = signal.model_dump(mode="json")
            # cache mọi kết quả (kể cả failed) vào forecasts table
            try:
                store.save_forecast(symbol_u, tf, prov.name, payload)
            except Exception:
                logger.exception("failed to cache forecast")
            return payload
        except Exception as e:
            logger.warning("provider %s failed: %s", prov.name, e)
            registry.record_error(prov.name, str(e))
            last_error = e
    raise HTTPException(502, f"all providers failed: {last_error}")
