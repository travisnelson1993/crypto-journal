from typing import Any, Dict, List


def compute_sheet_metrics(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Replicates Google Sheets logic exactly:
    - R:R can be positive or negative
    - Total R:R = SUM(rr)
    - Avg R:R = AVERAGE(rr)
    """

    closed = [t for t in trades if t.get("exit_price") is not None]

    wins = 0
    losses = 0
    breakeven = 0

    pnl_list = []
    lev_pnl_list = []
    rr_list = []

    for t in closed:
        entry = t["entry_price"]
        exit_ = t["exit_price"]
        stop = t["stop_loss"]
        lev = t.get("leverage", 1)
        direction = t["direction"].upper()

        # --- PNL %
        if direction == "LONG":
            pnl = (exit_ - entry) / entry * 100
        else:  # SHORT
            pnl = (entry - exit_) / entry * 100

        lev_pnl = pnl * lev

        pnl_list.append(pnl)
        lev_pnl_list.append(lev_pnl)

        # --- R:R (Sheets logic)
        rr = 0
        if stop and stop != entry:
            if direction == "LONG":
                rr = (exit_ - entry) / (entry - stop)
            else:
                rr = (entry - exit_) / (stop - entry)

        rr_list.append(round(rr, 2))

        # --- Win / Loss / BE
        if pnl > 0:
            wins += 1
        elif pnl < 0:
            losses += 1
        else:
            breakeven += 1

    total_trades = len(trades)
    closed_trades = len(closed)

    return {
        "trades": total_trades,
        "closed_trades": closed_trades,
        "wins": wins,
        "losses": losses,
        "breakeven": breakeven,
        "win_rate_pct": round((wins / closed_trades) * 100, 2) if closed_trades else 0,
        "gains_pct": round(sum(pnl_list), 2),
        "avg_return_pct": round(sum(pnl_list) / len(pnl_list), 2) if pnl_list else 0,
        "lev_gains_pct": round(sum(lev_pnl_list), 2),
        "avg_return_lev_pct": (
            round(sum(lev_pnl_list) / len(lev_pnl_list), 2) if lev_pnl_list else 0
        ),
        "total_rr": round(sum(rr_list), 2),
        "avg_rr": round(sum(rr_list) / len(rr_list), 2) if rr_list else 0,
        "largest_win_pct": round(max(pnl_list), 2) if pnl_list else 0,
        "largest_lev_win_pct": round(max(lev_pnl_list), 2) if lev_pnl_list else 0,
        "largest_rr_win": round(max(rr_list), 2) if rr_list else 0,
    }
