"""Compatibility entry point with JSON-safe OCR coordinates."""

import ocr_official_labor_pdfs as pipeline


def json_safe_order_lines(result: list) -> list[dict]:
    rows = []
    for box, text, confidence in result:
        if not text.strip():
            continue
        x = int(min(point[0] for point in box))
        y = int(min(point[1] for point in box))
        height = int(max(point[1] for point in box) - y)
        rows.append({
            "x": x,
            "y": y,
            "height": height,
            "text": text.strip(),
            "confidence": float(confidence),
        })
    rows.sort(key=lambda row: (round(row["y"] / max(row["height"], 1)), row["x"]))
    return rows


if __name__ == "__main__":
    pipeline.order_lines = json_safe_order_lines
    pipeline.main()
