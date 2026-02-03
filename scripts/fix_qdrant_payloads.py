#!/usr/bin/env python3
import os
import json
import math
import argparse
import logging
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()
QDRANT_BASE = os.getenv("QDRANT_BASE_URL") or f"http://{os.getenv('QDRANT_HOST','localhost')}:{os.getenv('QDRANT_PORT','6333')}"
DEFAULT_COLLECTION = os.getenv("QDRANT_COLLECTION", "sales_vol_staging")
DEFAULT_BATCH = int(os.getenv("FIX_BATCH", "200"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def is_json_serializable(obj):
    try:
        json.dumps(obj)
        return True
    except Exception:
        return False

def sanitize_value(v):
    try:
        import numpy as np
        if isinstance(v, (np.integer,)):
            return int(v)
        if isinstance(v, (np.floating,)):
            fv = float(v)
            return None if not math.isfinite(fv) else fv
    except Exception:
        pass
    try:
        if hasattr(v, "isoformat"):
            return v.isoformat()
    except Exception:
        pass
    try:
        if isinstance(v, float):
            return None if not math.isfinite(v) else v
    except Exception:
        pass
    if isinstance(v, (str, int, bool, type(None))):
        return v
    if isinstance(v, (list, tuple)):
        return [sanitize_value(x) for x in v]
    if isinstance(v, dict):
        return {str(k): sanitize_value(val) for k, val in v.items()}
    try:
        return str(v)
    except Exception:
        return None

def sanitize_payload(payload):
    out = {}
    for k, v in (payload or {}).items():
        out[str(k)] = sanitize_value(v)
    return out

def upsert_points(collection, points, try_individual_on_error=True):
    if not points:
        return None
    sanitized_points = []
    for i, p in enumerate(points):
        pid = p.get("id")
        payload = p.get("payload", {}) or {}
        vector = p.get("vector")
        if pid is None:
            raise ValueError(f"Point at index {i} missing 'id': {p}")
        if not isinstance(pid, (int, str)):
            raise ValueError(f"Point id must be int or str (index {i}): {pid} ({type(pid)})")
        if not isinstance(payload, dict):
            raise ValueError(f"Point payload must be a dict (index {i}): {payload} ({type(payload)})")
        sanitized = sanitize_payload(payload)
        if not is_json_serializable(sanitized):
            raise ValueError(f"Sanitized payload not JSON-serializable (index {i}): {sanitized}")
        # vector must be present for upsert in this Qdrant collection
        if vector is None:
            raise ValueError(f"Point at index {i} id={pid} missing vector; cannot upsert without vector")
        sanitized_points.append({"id": pid, "vector": vector, "payload": sanitized})

    url = f"{QDRANT_BASE}/collections/{collection}/points"
    headers = {"Content-Type": "application/json"}
    body = {"points": sanitized_points}
    r = requests.put(url, headers=headers, data=json.dumps(body), timeout=30)
    if r.status_code < 400:
        logger.info("Batch upsert successful: %d points", len(sanitized_points))
        return r.json()
    logger.error("Batch upsert failed: status=%s body=%s", r.status_code, r.text)
    if r.status_code == 400 and try_individual_on_error:
        logger.info("Attempting individual upserts to isolate failing point...")
        for idx, p in enumerate(sanitized_points):
            try:
                r2 = requests.put(url, headers=headers, data=json.dumps({"points": [p]}), timeout=30)
                if r2.status_code < 400:
                    logger.info("Point %s upserted successfully (id=%s)", idx, p.get("id"))
                    continue
                else:
                    logger.error("Point %s failed: status=%s body=%s", idx, r2.status_code, r2.text)
                    raise RuntimeError(f"Upsert failed for point index {idx}, id={p.get('id')}: {r2.status_code} {r2.text}")
            except Exception:
                logger.exception("Exception while upserting point index %s id=%s", idx, p.get("id"))
                raise
    r.raise_for_status()

def safe_parse_point(item):
    if item is None:
        return None, None, None
    if isinstance(item, str):
        try:
            item = json.loads(item)
        except Exception:
            logger.debug("Could not json-decode point string: %s", item)
            return None, None, None
    if isinstance(item, dict):
        if "id" in item and "payload" in item:
            vec = item.get("vector") or item.get("vectors") or item.get("payload_vector")
            if isinstance(vec, dict) and "default" in vec:
                vec = vec["default"]
            return item.get("id"), item.get("payload") or {}, vec
        if "point" in item and isinstance(item["point"], dict):
            p = item["point"]
            vec = p.get("vector") or p.get("vectors")
            if isinstance(vec, dict) and "default" in vec:
                vec = vec["default"]
            return p.get("id"), p.get("payload") or {}, vec
        if "payload" in item:
            vec = item.get("vector")
            if isinstance(vec, dict) and "default" in vec:
                vec = vec["default"]
            return item.get("id"), item.get("payload") or {}, vec
        return item.get("id"), item, item.get("vector")
    return None, None, None

def scroll_points(collection, batch_size=500):
    url = f"{QDRANT_BASE}/collections/{collection}/points/scroll"
    headers = {"Content-Type": "application/json"}
    offset = None
    while True:
        body = {"limit": batch_size, "with_payload": True, "with_vector": True}
        if offset:
            body["offset"] = offset
        r = requests.post(url, headers=headers, data=json.dumps(body), timeout=30)
        r.raise_for_status()
        resp = r.json()
        result = resp.get("result")
        if isinstance(result, dict) and "points" in result:
            points = result["points"]
        elif isinstance(result, list):
            points = result
        elif isinstance(resp.get("points"), list):
            points = resp["points"]
        elif isinstance(resp, list):
            points = resp
        else:
            points = []
        if not points:
            break
        for p in points:
            yield p
        next_offset = None
        if isinstance(result, dict):
            next_offset = result.get("next_page") or result.get("next_page_offset") or result.get("offset")
        next_offset = next_offset or resp.get("next_page") or resp.get("next_page_offset") or resp.get("offset")
        if not next_offset:
            break
        offset = next_offset

def parse_and_normalize(payload):
    out = dict(payload)
    month_year = payload.get("month_year") or payload.get("date")
    if month_year:
        try:
            if isinstance(month_year, str) and len(month_year) == 7 and month_year[4] == "-":
                dt = datetime.strptime(month_year, "%Y-%m")
            else:
                dt = datetime.fromisoformat(str(month_year).replace("Z", "+00:00"))
            out["month_year"] = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat().replace("+00:00", "Z")
            out.pop("month_year_missing", None)
            out.pop("month_year_normalization_error", None)
        except Exception:
            out["month_year_normalization_error"] = True
    else:
        out["month_year_missing"] = True

    sales = payload.get("sales") or payload.get("sales_amount") or payload.get("sales_vol")
    if sales is None:
        out["sales_missing"] = True
    else:
        try:
            if isinstance(sales, str):
                sales_clean = sales.replace(",", "").strip()
            else:
                sales_clean = sales
            val = float(sales_clean)
            if math.isfinite(val):
                out["sales"] = val
                out.pop("sales_normalization_error", None)
            else:
                out["sales_normalization_error"] = True
        except Exception:
            out["sales_normalization_error"] = True
    return out

def fix_payloads_main(collection=DEFAULT_COLLECTION, dry_run=True, batch_size=200, preview_file=None, limit=None):
    to_upsert = []
    scanned = 0
    changed = 0
    skipped_unparseable = 0
    sample_problems = []
    preview_fh = None
    if preview_file:
        preview_fh = open(preview_file, "w", encoding="utf-8")
        logger.info("Writing preview batches to %s", preview_file)

    try:
        for raw_point in scroll_points(collection, batch_size):
            scanned += 1
            pid, payload, vector = safe_parse_point(raw_point)
            if payload is None:
                skipped_unparseable += 1
                if len(sample_problems) < 20:
                    sample_problems.append({"raw": raw_point})
                continue
            if pid is None and isinstance(raw_point, dict):
                pid = raw_point.get("id")
            normalized = parse_and_normalize(payload)
            if normalized != payload:
                changed += 1
                if pid is None:
                    skipped_unparseable += 1
                    if len(sample_problems) < 20:
                        sample_problems.append({"id": pid, "before": payload, "after": normalized})
                    continue
                # include vector (required by your collection)
                if vector is None:
                    # fallback: try to fetch vector for this id
                    try:
                        fetch_r = requests.post(f"{QDRANT_BASE}/collections/{collection}/points/scroll",
                                                headers={"Content-Type": "application/json"},
                                                data=json.dumps({"ids": [pid], "with_vector": True}), timeout=10)
                        fetch_r.raise_for_status()
                        fetch_resp = fetch_r.json()
                        fetched_points = fetch_resp.get("result") or fetch_resp.get("points") or []
                        if isinstance(fetched_points, dict) and "points" in fetched_points:
                            fetched_points = fetched_points["points"]
                        if fetched_points:
                            fp = fetched_points[0]
                            vector = fp.get("vector") or (fp.get("vectors") or {}).get("default")
                    except Exception:
                        logger.exception("Failed to fetch vector for id=%s; skipping", pid)
                        vector = None
                if vector is None:
                    skipped_unparseable += 1
                    if len(sample_problems) < 20:
                        sample_problems.append({"id": pid, "reason": "missing_vector", "before": payload, "after": normalized})
                    continue
                to_upsert.append({"id": pid, "vector": vector, "payload": normalized})
            if len(to_upsert) >= batch_size:
                logger.info("Prepared %d changes (total changed so far: %d)", len(to_upsert), changed)
                if preview_fh:
                    preview_fh.write(json.dumps({"points": to_upsert}, ensure_ascii=False) + "\n")
                    preview_fh.flush()
                if not dry_run:
                    try:
                        upsert_points(collection, to_upsert)
                    except Exception:
                        logger.exception("Upsert batch failed; aborting apply")
                        raise
                to_upsert = []
                if limit and changed >= limit:
                    logger.info("Reached limit %d; stopping", limit)
                    break
        if to_upsert and (not limit or changed < limit):
            if limit and changed + len(to_upsert) > limit:
                to_upsert = to_upsert[: max(0, limit - changed)]
            logger.info("Prepared final %d changes.", len(to_upsert))
            if preview_fh:
                preview_fh.write(json.dumps({"points": to_upsert}, ensure_ascii=False) + "\n")
                preview_fh.flush()
            if not dry_run:
                try:
                    upsert_points(collection, to_upsert)
                except Exception:
                    logger.exception("Final upsert failed; aborting apply")
                    raise
    finally:
        if preview_fh:
            preview_fh.close()

    logger.info("Done. Scanned: %d, Changed: %d, Skipped unparseable: %d", scanned, changed, skipped_unparseable)
    if sample_problems:
        logger.info("Sample problematic items (up to 20):")
        for s in sample_problems[:20]:
            logger.info(json.dumps(s))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fix Qdrant payloads (normalize month_year and sales).")
    parser.add_argument("--apply", action="store_true", help="Apply changes (default is dry-run).")
    parser.add_argument("--batch", type=int, default=DEFAULT_BATCH, help="Upsert batch size.")
    parser.add_argument("--preview-file", type=str, default=None, help="Write preview batches to this file (one JSON per line).")
    parser.add_argument("--limit", type=int, default=None, help="Stop after applying this many changed points (useful for smoke tests).")
    args = parser.parse_args()
    fix_payloads_main(collection=DEFAULT_COLLECTION, dry_run=not args.apply, batch_size=args.batch, preview_file=args.preview_file, limit=args.limit)
