from fastapi import APIRouter, Depends
from sqlalchemy import select, func, case, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.trade import Trade

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


# =================================================
# PERFORMANCE ANALYTICS (RESULTS)
# =================================================
@router.get("/performance")
async def performance_summary(db: AsyncSession = Depends(get_db)):
    """
    Outcome-focused performance analytics (Edgewonk / TradeZella style)
    """

    risk_usd = (
        func.abs(Trade.entry_price - Trade.stop_loss)
        * Trade.original_quantity
    )

    r_multiple = Trade.realized_pnl / func.nullif(risk_usd, 0)

    pnl_pct = Trade.realized_pnl_pct
    lev_pnl_pct = pnl_pct * func.coalesce(Trade.leverage, 1)

    wins = func.sum(case((Trade.realized_pnl > 0, 1), else_=0))
    losses = func.sum(case((Trade.realized_pnl < 0, 1), else_=0))
    breakeven = func.sum(case((Trade.realized_pnl == 0, 1), else_=0))
    trades = func.count()

    stmt = (
        select(
            trades.label("trades"),
            wins.label("wins"),
            losses.label("losses"),
            breakeven.label("breakeven"),
            (wins / func.nullif(wins + losses, 0) * 100).label("win_rate_ex_be"),
            func.sum(pnl_pct).label("gains_pct"),
            func.avg(pnl_pct).label("avg_return_pct"),
            func.sum(lev_pnl_pct).label("lev_gains_pct"),
            func.avg(lev_pnl_pct).label("avg_return_lev_pct"),
            func.sum(r_multiple).label("total_rr"),
            func.avg(r_multiple).label("avg_rr"),
            func.max(r_multiple).label("largest_rr_win"),
        )
        .where(Trade.end_date.isnot(None))
    )

    row = (await db.execute(stmt)).one()

    def f(x):
        return float(x) if x is not None else 0.0

    return {
        "trades": row.trades or 0,
        "wins": row.wins or 0,
        "losses": row.losses or 0,
        "breakeven": row.breakeven or 0,
        "win_rate_excluding_breakeven_pct": f(row.win_rate_ex_be),
        "gains_pct": f(row.gains_pct) * 100,
        "avg_return_pct": f(row.avg_return_pct) * 100,
        "lev_gains_pct": f(row.lev_gains_pct) * 100,
        "avg_return_lev_pct": f(row.avg_return_lev_pct) * 100,
        "total_rr": f(row.total_rr),
        "avg_rr": f(row.avg_rr),
        "largest_rr_win": f(row.largest_rr_win),
    }


# =================================================
# RISK / DISCIPLINE METRICS (BASIC)
# =================================================
@router.get("/risk-discipline")
async def risk_discipline_summary(db: AsyncSession = Depends(get_db)):
    stmt = (
        select(
            func.count().label("total_closed"),
            func.sum(case((Trade.stop_loss.is_(None), 1), else_=0)).label("missing_stop"),
            func.sum(case((Trade.stop_loss.isnot(None), 1), else_=0)).label("has_stop"),
        )
        .where(Trade.end_date.isnot(None))
    )

    row = (await db.execute(stmt)).one()

    total = row.total_closed or 0
    has = row.has_stop or 0
    missing = row.missing_stop or 0

    return {
        "total_closed_trades": total,
        "trades_with_stop_loss": has,
        "trades_missing_stop_loss": missing,
        "percent_with_stop_loss": round((has / total * 100) if total else 0.0, 2),
        "percent_missing_stop_loss": round((missing / total * 100) if total else 0.0, 2),
    }


# =================================================
# DISCIPLINE SCORE v1 (R-BASED)
# =================================================
@router.get("/discipline-score")
async def discipline_score_v1(
    db: AsyncSession = Depends(get_db),
    max_r_allowed: float = 1.0,
    max_leverage: float = 10.0,
):
    risk_usd = (
        func.abs(Trade.entry_price - Trade.stop_loss)
        * Trade.original_quantity
    )

    r_multiple = Trade.realized_pnl / func.nullif(risk_usd, 0)

    stop_defined = case((Trade.stop_loss.isnot(None), 1), else_=0)

    risk_within_limit = case(
        (and_(r_multiple.isnot(None), func.abs(r_multiple) <= max_r_allowed), 1),
        else_=0,
    )

    leverage_within_limit = case(
        (func.coalesce(Trade.leverage, 1) <= max_leverage, 1),
        else_=0,
    )

    stmt = (
        select(
            func.count().label("trades_evaluated"),
            func.avg(stop_defined).label("stop_rate"),
            func.avg(risk_within_limit).label("risk_rate"),
            func.avg(leverage_within_limit).label("leverage_rate"),
        )
        .where(Trade.end_date.isnot(None))
    )

    row = (await db.execute(stmt)).one()

    stop_rate = float(row.stop_rate or 0)
    risk_rate = float(row.risk_rate or 0)
    leverage_rate = float(row.leverage_rate or 0)

    score = (
        stop_rate * 0.40
        + risk_rate * 0.30
        + leverage_rate * 0.30
    ) * 100

    return {
        "trades_evaluated": row.trades_evaluated or 0,
        "discipline_score": round(score, 2),
        "rules": {
            "stop_loss_defined_pct": round(stop_rate * 100, 2),
            "risk_within_limit_pct": round(risk_rate * 100, 2),
            "leverage_within_limit_pct": round(leverage_rate * 100, 2),
        },
    }


# =================================================
# DISCIPLINE SCORE v2 (EQUITY-AWARE, ALL TRADES)
# =================================================
@router.get("/discipline-score/v2")
async def discipline_score_v2(
    db: AsyncSession = Depends(get_db),
    max_risk_pct: float = 0.01,
    max_leverage: float = 10.0,
):
    stop_defined = case((Trade.stop_loss.isnot(None), 1), else_=0)
    equity_snapshot_present = case((Trade.account_equity_at_entry.isnot(None), 1), else_=0)

    risk_within_limit = case(
        (
            and_(
                Trade.risk_pct_at_entry.isnot(None),
                Trade.risk_pct_at_entry <= max_risk_pct,
            ),
            1,
        ),
        else_=0,
    )

    leverage_within_limit = case(
        (
            func.coalesce(Trade.leverage, 1) <= max_leverage,
            1,
        ),
        else_=0,
    )

    stmt = (
        select(
            func.count().label("trades_evaluated"),
            func.avg(stop_defined).label("stop_rate"),
            func.avg(equity_snapshot_present).label("equity_rate"),
            func.avg(risk_within_limit).label("risk_rate"),
            func.avg(leverage_within_limit).label("leverage_rate"),
        )
        .where(Trade.end_date.isnot(None))
    )

    row = (await db.execute(stmt)).one()

    stop_rate = float(row.stop_rate or 0)
    equity_rate = float(row.equity_rate or 0)
    risk_rate = float(row.risk_rate or 0)
    leverage_rate = float(row.leverage_rate or 0)

    score = (
        stop_rate * 0.30
        + equity_rate * 0.20
        + risk_rate * 0.30
        + leverage_rate * 0.20
    ) * 100

    return {
        "trades_evaluated": row.trades_evaluated or 0,
        "discipline_score": round(score, 2),
        "note": "Includes legacy trades",
    }


# =================================================
# DISCIPLINE SCORE v2 — ELIGIBLE TRADES ONLY
# =================================================
@router.get("/discipline-score/v2/eligible")
async def discipline_score_v2_eligible(
    db: AsyncSession = Depends(get_db),
    max_risk_pct: float = 0.01,
    max_leverage: float = 10.0,
):
    stop_defined = case((Trade.stop_loss.isnot(None), 1), else_=0)
    equity_snapshot_present = case((Trade.account_equity_at_entry.isnot(None), 1), else_=0)

    risk_within_limit = case(
        (
            and_(
                Trade.risk_pct_at_entry.isnot(None),
                Trade.risk_pct_at_entry <= max_risk_pct,
            ),
            1,
        ),
        else_=0,
    )

    leverage_within_limit = case(
        (func.coalesce(Trade.leverage, 1) <= max_leverage, 1),
        else_=0,
    )

    stmt = (
        select(
            func.count().label("trades_evaluated"),
            func.avg(stop_defined).label("stop_rate"),
            func.avg(equity_snapshot_present).label("equity_rate"),
            func.avg(risk_within_limit).label("risk_rate"),
            func.avg(leverage_within_limit).label("leverage_rate"),
        )
        .where(
            Trade.end_date.isnot(None),
            Trade.stop_loss.isnot(None),
            Trade.account_equity_at_entry.isnot(None),
            Trade.risk_pct_at_entry.isnot(None),
        )
    )

    row = (await db.execute(stmt)).one()
    trades = int(row.trades_evaluated or 0)

    if trades == 0:
        return {
            "trades_evaluated": 0,
            "discipline_score": None,
            "note": "No eligible trades yet",
        }

    stop_rate = float(row.stop_rate or 0)
    equity_rate = float(row.equity_rate or 0)
    risk_rate = float(row.risk_rate or 0)
    leverage_rate = float(row.leverage_rate or 0)

    score = (
        stop_rate * 0.30
        + equity_rate * 0.20
        + risk_rate * 0.30
        + leverage_rate * 0.20
    ) * 100

    return {
        "trades_evaluated": trades,
        "discipline_score": round(score, 2),
        "rules": {
            "stop_loss_defined_pct": round(stop_rate * 100, 2),
            "equity_snapshot_present_pct": round(equity_rate * 100, 2),
            "risk_within_limit_pct": round(risk_rate * 100, 2),
            "leverage_within_limit_pct": round(leverage_rate * 100, 2),
        },
    }


# =================================================
# DISCIPLINE SCORE v2 — ROLLING (ELIGIBLE TRADES ONLY)
# =================================================
@router.get("/discipline-score/v2/eligible/rolling")
async def discipline_score_v2_eligible_rolling(
    db: AsyncSession = Depends(get_db),
    n: int = 20,
    max_risk_pct: float = 0.01,
    max_leverage: float = 10.0,
):
    stop_defined = case((Trade.stop_loss.isnot(None), 1), else_=0)
    equity_snapshot_present = case((Trade.account_equity_at_entry.isnot(None), 1), else_=0)

    risk_within_limit = case(
        (
            and_(
                Trade.risk_pct_at_entry.isnot(None),
                Trade.risk_pct_at_entry <= max_risk_pct,
            ),
            1,
        ),
        else_=0,
    )

    leverage_within_limit = case(
        (func.coalesce(Trade.leverage, 1) <= max_leverage, 1),
        else_=0,
    )

    eligible_trades_subq = (
        select(Trade.id)
        .where(
            Trade.end_date.isnot(None),
            Trade.stop_loss.isnot(None),
            Trade.account_equity_at_entry.isnot(None),
            Trade.risk_pct_at_entry.isnot(None),
        )
        .order_by(Trade.end_date.desc(), Trade.id.desc())
        .limit(n)
        .subquery()
    )

    stmt = (
        select(
            func.count().label("trades"),
            func.avg(stop_defined).label("stop_rate"),
            func.avg(equity_snapshot_present).label("equity_rate"),
            func.avg(risk_within_limit).label("risk_rate"),
            func.avg(leverage_within_limit).label("leverage_rate"),
        )
        .where(Trade.id.in_(select(eligible_trades_subq.c.id)))
    )

    row = (await db.execute(stmt)).one()
    trades = int(row.trades or 0)

    if trades == 0:
        return {
            "window_size": n,
            "trades_evaluated": 0,
            "discipline_score": None,
        }

    stop_rate = float(row.stop_rate or 0)
    equity_rate = float(row.equity_rate or 0)
    risk_rate = float(row.risk_rate or 0)
    leverage_rate = float(row.leverage_rate or 0)

    score = (
        stop_rate * 0.30
        + equity_rate * 0.20
        + risk_rate * 0.30
        + leverage_rate * 0.20
    ) * 100

    return {
        "window_size": n,
        "trades_evaluated": trades,
        "discipline_score": round(score, 2),
    }


# =================================================
# DISCIPLINE SCORE v2 — TREND (ELIGIBLE TRADES ONLY)
# =================================================
@router.get("/discipline-score/v2/eligible/trend")
async def discipline_score_v2_trend(
    db: AsyncSession = Depends(get_db),
    window: int = 20,
    limit: int = 100,
    max_risk_pct: float = 0.01,
    max_leverage: float = 10.0,
):
    # Base eligibility filter
    base_filter = [
        Trade.end_date.isnot(None),
        Trade.stop_loss.isnot(None),
        Trade.account_equity_at_entry.isnot(None),
        Trade.risk_pct_at_entry.isnot(None),
    ]

    eligible_stmt = (
        select(Trade.id, Trade.end_date)
        .where(*base_filter)
        .order_by(Trade.end_date.asc(), Trade.id.asc())
        .limit(limit)
    )

    eligible = (await db.execute(eligible_stmt)).all()

    points = []

    for idx, (trade_id, end_date) in enumerate(eligible):
        if idx + 1 < window:
            continue

        window_ids = [
            t[0] for t in eligible[idx + 1 - window : idx + 1]
        ]

        stop_defined = case((Trade.stop_loss.isnot(None), 1), else_=0)
        equity_snapshot_present = case((Trade.account_equity_at_entry.isnot(None), 1), else_=0)

        risk_within_limit = case(
            (
                and_(
                    Trade.risk_pct_at_entry.isnot(None),
                    Trade.risk_pct_at_entry <= max_risk_pct,
                ),
                1,
            ),
            else_=0,
        )

        leverage_within_limit = case(
            (func.coalesce(Trade.leverage, 1) <= max_leverage, 1),
            else_=0,
        )

        stmt = (
            select(
                func.avg(stop_defined).label("stop_rate"),
                func.avg(equity_snapshot_present).label("equity_rate"),
                func.avg(risk_within_limit).label("risk_rate"),
                func.avg(leverage_within_limit).label("leverage_rate"),
            )
            .where(Trade.id.in_(window_ids))
        )

        row = (await db.execute(stmt)).one()

        score = (
            float(row.stop_rate or 0) * 0.30
            + float(row.equity_rate or 0) * 0.20
            + float(row.risk_rate or 0) * 0.30
            + float(row.leverage_rate or 0) * 0.20
        ) * 100

        points.append({
            "trade_id": trade_id,
            "end_date": end_date.isoformat(),
            "discipline_score": round(score, 2),
            "trades_in_window": window,
        })

    return {
        "window": window,
        "points": points,
    }


# =================================================
# DISCIPLINE SCORE v2 — RULE VIOLATIONS (PER TRADE)
# =================================================
@router.get("/discipline-score/v2/violations")
async def discipline_rule_violations(
    db: AsyncSession = Depends(get_db),
    limit: int = 100,
    max_risk_pct: float = 0.01,
    max_leverage: float = 10.0,
):
    stmt = (
        select(Trade)
        .where(Trade.end_date.isnot(None))
        .order_by(Trade.end_date.desc(), Trade.id.desc())
        .limit(limit)
    )

    trades = (await db.execute(stmt)).scalars().all()

    results = []

    for t in trades:
        violations = []

        if t.stop_loss is None:
            violations.append("missing_stop_loss")

        if t.account_equity_at_entry is None:
            violations.append("missing_equity_snapshot")

        if (
            t.risk_pct_at_entry is not None
            and t.risk_pct_at_entry > max_risk_pct
        ):
            violations.append("risk_exceeded")

        if (
            t.leverage is not None
            and t.leverage > max_leverage
        ):
            violations.append("leverage_exceeded")

        eligible = (
            t.stop_loss is not None
            and t.account_equity_at_entry is not None
            and t.risk_pct_at_entry is not None
        )

        results.append({
            "trade_id": t.id,
            "end_date": t.end_date.isoformat() if t.end_date else None,
            "eligible": eligible,
            "violations": violations,
        })

    return {
        "rules": {
            "stop_loss_defined": True,
            "equity_snapshot_present": True,
            "risk_within_limit": True,
            "leverage_within_limit": True,
        },
        "trades": results,
    }


# =================================================
# EQUITY CURVE & DRAWDOWN (SNAPSHOT-BASED)
# =================================================
@router.get("/equity-curve")
async def equity_curve(
    db: AsyncSession = Depends(get_db),
    eligible_only: bool = True,
    sma_window: int = 10,
    ema_window: int = 5,
):
    filters = [
        Trade.end_date.isnot(None),
        Trade.account_equity_at_entry.isnot(None),
    ]

    if eligible_only:
        filters.extend([
            Trade.stop_loss.isnot(None),
            Trade.risk_pct_at_entry.isnot(None),
        ])

    stmt = (
        select(
            Trade.id,
            Trade.end_date,
            Trade.account_equity_at_entry,
        )
        .where(*filters)
        .order_by(Trade.end_date.asc(), Trade.id.asc())
    )

    rows = (await db.execute(stmt)).all()

    points = []
    peak_equity = None

    max_dd_pct = 0.0
    max_dd_usd = 0.0

    # ---------- Build equity curve + drawdown ----------
    for trade_id, end_date, equity in rows:
        equity = float(equity)

        if peak_equity is None or equity > peak_equity:
            peak_equity = equity

        drawdown_pct = (equity - peak_equity) / peak_equity * 100

        if drawdown_pct < max_dd_pct:
            max_dd_pct = drawdown_pct
            max_dd_usd = equity - peak_equity

        points.append({
            "trade_id": trade_id,
            "end_date": end_date.isoformat(),
            "equity": round(equity, 2),
            "peak_equity": round(peak_equity, 2),
            "drawdown_pct": round(drawdown_pct, 2),
        })

    # ---------- Equity curve smoothing (SMA + EMA) ----------
    def compute_sma(values, window):
        sma = []
        for i in range(len(values)):
            if i + 1 < window:
                sma.append(None)
            else:
                sma.append(sum(values[i + 1 - window : i + 1]) / window)
        return sma

    def compute_ema(values, window):
        ema = []
        k = 2 / (window + 1)
        prev = None

        for v in values:
            if prev is None:
                prev = v
            else:
                prev = v * k + prev * (1 - k)
            ema.append(prev)

        return ema

    equity_values = [p["equity"] for p in points]

    sma_vals = compute_sma(equity_values, sma_window)
    ema_vals = compute_ema(equity_values, ema_window)

    for i, p in enumerate(points):
        p["sma"] = round(sma_vals[i], 2) if sma_vals[i] is not None else None
        p["ema"] = round(ema_vals[i], 2)

    # ---------- FINAL RETURN (outside loops) ----------
    return {
        "max_drawdown_pct": round(max_dd_pct, 2),
        "max_drawdown_usd": round(max_dd_usd, 2),
        "points": points,
    }


# =================================================
# LOSS STREAK DETECTION (PSYCHOLOGICAL RISK)
# =================================================
@router.get("/loss-streaks")
async def loss_streaks(
    db: AsyncSession = Depends(get_db),
    eligible_only: bool = False,
    max_losses: int = 3,
):
    stmt = (
        select(
            Trade.id,
            Trade.end_date,
            Trade.realized_pnl,
        )
        .where(Trade.end_date.isnot(None))
        .order_by(Trade.end_date.asc(), Trade.id.asc())
    )

    if eligible_only:
        stmt = stmt.where(
            Trade.stop_loss.isnot(None),
            Trade.account_equity_at_entry.isnot(None),
        )

    rows = (await db.execute(stmt)).all()

    current_streak = 0
    max_streak_seen = 0
    recent_losses = []

    for trade_id, end_date, pnl in rows:
        if pnl is None or pnl >= 0:
            current_streak = 0
            recent_losses.clear()
            continue

        # loss
        current_streak += 1
        max_streak_seen = max(max_streak_seen, current_streak)

        recent_losses.append({
            "trade_id": trade_id,
            "end_date": end_date.isoformat(),
            "realized_pnl": float(pnl),
        })

    trading_halted = current_streak >= max_losses

    return {
        "current_loss_streak": current_streak,
        "max_loss_streak": max_streak_seen,
        "trading_halted": trading_halted,
        "halt_rule": f"max {max_losses} consecutive losses",
        "recent_losses": recent_losses[-max_losses:],
    }


# =================================================
# DAILY MAX LOSS RULE (ACCOUNT PROTECTION)
# =================================================
@router.get("/daily-max-loss")
async def daily_max_loss(
    db: AsyncSession = Depends(get_db),
    max_daily_loss_usd: float = 100.0,
    eligible_only: bool = False,
):
    from datetime import datetime

    today = datetime.utcnow().date()

    stmt = (
        select(
            Trade.id,
            Trade.end_date,
            Trade.realized_pnl,
        )
        .where(
            Trade.end_date.isnot(None),
            func.date(Trade.end_date) == today,
        )
        .order_by(Trade.end_date.asc(), Trade.id.asc())
    )

    if eligible_only:
        stmt = stmt.where(
            Trade.stop_loss.isnot(None),
            Trade.account_equity_at_entry.isnot(None),
        )

    rows = (await db.execute(stmt)).all()

    trades = []
    daily_pnl = 0.0

    for trade_id, end_date, pnl in rows:
        if pnl is None:
            continue

        pnl_f = float(pnl)
        daily_pnl += pnl_f

        trades.append({
            "trade_id": trade_id,
            "end_date": end_date.isoformat(),
            "realized_pnl": pnl_f,
        })

    trading_halted = daily_pnl <= -abs(max_daily_loss_usd)

    return {
        "date": today.isoformat(),
        "daily_pnl": round(daily_pnl, 2),
        "max_daily_loss_usd": round(max_daily_loss_usd, 2),
        "trading_halted": trading_halted,
        "halt_reason": (
            "Daily loss limit exceeded" if trading_halted else None
        ),
        "trades": trades,
    }


# =================================================
# EQUITY REGIME & TRADING HALT (DECISION ENGINE)
# =================================================
@router.get("/equity-regime")
async def equity_regime(
    db: AsyncSession = Depends(get_db),
    max_drawdown_pct: float = -5.0,
    max_losses: int = 3,
    max_daily_loss_usd: float = 100.0,
    ema_window: int = 5,
):
    """
    Determines trading regime and halt status based on equity, drawdown,
    loss streaks, and daily loss limits.
    """

    # ---------- Equity curve ----------
    eq = await equity_curve(
        db=db,
        eligible_only=True,
        sma_window=ema_window,
        ema_window=ema_window,
    )

    points = eq["points"]
    if not points:
        return {
            "regime": "unknown",
            "trading_halted": True,
            "reason": "No equity data available",
        }

    latest = points[-1]
    equity = latest["equity"]
    ema = latest["ema"]
    drawdown = latest["drawdown_pct"]

    # ---------- Loss streak ----------
    streak = await loss_streaks(
        db=db,
        eligible_only=True,
        max_losses=max_losses,
    )

    # ---------- Daily max loss ----------
    daily = await daily_max_loss(
        db=db,
        eligible_only=True,
        max_daily_loss_usd=max_daily_loss_usd,
    )

    # ---------- Decision logic ----------
    halted = False
    reasons = []

    if streak["trading_halted"]:
        halted = True
        reasons.append("Max loss streak reached")

    if daily["trading_halted"]:
        halted = True
        reasons.append("Daily max loss exceeded")

    if drawdown <= max_drawdown_pct:
        halted = True
        reasons.append("Max drawdown exceeded")

    if halted:
        return {
            "regime": "halted",
            "trading_halted": True,
            "reasons": reasons,
            "equity": equity,
            "ema": ema,
            "drawdown_pct": drawdown,
        }

    # ---------- Risk mode ----------
    if equity >= ema:
        regime = "risk_on"
    else:
        regime = "risk_reduced"

    return {
        "regime": regime,
        "trading_halted": False,
        "equity": equity,
        "ema": ema,
        "drawdown_pct": drawdown,
        "notes": (
            "Trade normally" if regime == "risk_on"
            else "Reduce position size"
        ),
    }


# =================================================
# POSITION SIZING AUTHORIZATION (REGIME-BASED)
# =================================================
@router.get("/position-sizing")
async def position_sizing(
    db: AsyncSession = Depends(get_db),
    base_risk_pct: float = 0.01,
):
    # --- Reuse equity regime ---
    regime_data = await equity_regime(db=db)

    regime = regime_data["regime"]
    trading_halted = regime_data["trading_halted"]

    if regime == "risk_on":
        multiplier = 1.0
        notes = "Full risk allowed"
    elif regime == "risk_reduced":
        multiplier = 0.25
        notes = "Reduced risk mode"
    else:
        multiplier = 0.0
        notes = "Trading halted by risk engine"

    allowed_risk_pct = base_risk_pct * multiplier

    return {
        "regime": regime,
        "base_risk_pct": round(base_risk_pct, 4),
        "allowed_risk_pct": round(allowed_risk_pct, 4),
        "risk_multiplier": multiplier,
        "trading_allowed": not trading_halted,
        "notes": notes,
    }
