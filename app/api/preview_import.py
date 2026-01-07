# preview_import.py
import csv
import re
import sys
from datetime import datetime

from app.utils.side_parser import infer_action_and_direction

_qty_re = re.compile(r"([+-]?[0-9,]*\.?[0-9]+)")


def parse_money(value):
    if value is None:
        return None
    v = value.strip()
    if v in ("", "--", "-"):
        return None
    v = v.replace("%", "").strip()
    v = re.sub(r"[A-Za-z]+$", "", v).strip()
    v = v.replace(",", "")
    if v.startswith("(") and v.endswith(")"):
        v = "-" + v[1:-1]
    try:
        return float(v)
    except Exception:
        m = _qty_re.search(v)
        return float(m.group(1)) if m else None


def parse_qty_unit(filled):
    if not filled:
        return None, None
    parts = filled.strip().split()
    if len(parts) >= 2:
        try:
            return float(parts[0].replace(",", "")), parts[1]
        except Exception:
            m = _qty_re.search(filled)
            if m:
                return float(m.group(1)), parts[-1] if len(parts) > 1 else None
    else:
        m = _qty_re.search(filled)
        if m:
            return float(m.group(1)), None
    return None, None


def parse_datetime(s):
    if not s:
        return None
    fmts = ["%m/%d/%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%m/%d/%Y"]
    for f in fmts:
        try:
            return datetime.strptime(s, f)
        except Exception:
            pass
    try:
        from dateutil.parser import parse as dateutil_parse

        return dateutil_parse(s)
    except Exception:
        return s


def preview(path, max_rows=50):
    with open(path, newline="", encoding="utf-8") as fin:
        reader = csv.DictReader(fin)
        total = 0
        parsed = 0
        examples = []
        for row in reader:
            total += 1
            side = row.get("Side") or row.get("side") or ""
            action, direction, reason = infer_action_and_direction(side)
            symbol = (
                row.get("Underlying Asset")
                or row.get("Ticker")
                or row.get("symbol")
                or ""
            ).strip()
            order_time = parse_datetime(row.get("Order Time"))
            avg_fill = parse_money(row.get("Avg Fill"))
            price = parse_money(row.get("Price"))
            filled_qty, filled_unit = parse_qty_unit(row.get("Filled"))
            ok = action is not None and direction is not None
            if ok:
                parsed += 1
            if len(examples) < 10 and not ok:
                examples.append(
                    {
                        "row_index": total,
                        "side": side,
                        "action": action,
                        "direction": direction,
                    }
                )
            if total <= max_rows:
                print(
                    f"#{total:03d} ticker={symbol} side='{side}' => action={action} direction={direction} reason={reason} filled={filled_qty} unit={filled_unit} avg_fill={avg_fill} price={price} time={order_time}"
                )
        print("\nSummary:")
        print(" total rows:", total)
        print(" parsed rows (action+direction found):", parsed)
        print(" skipped rows:", total - parsed)
        print(" first skipped examples:", examples)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python preview_import.py path/to/file.csv")
    else:
        preview(sys.argv[1])
