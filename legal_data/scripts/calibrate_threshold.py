import json
import random
import statistics
import time
from pathlib import Path
from collections import defaultdict
import sys
import os

# Ensure we can import from current directory
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from retrieve_v2 import SafeRetriever, resolve_current_index
from evaluate_retrieval_v2 import evaluate_case

ROOT = Path("c:/Users/dang khoa/Desktop/dacs")
EVAL_DIR = ROOT / "legal_data" / "eval"
CASES_PATH = EVAL_DIR / "retrieval_cases.jsonl"
SPLIT_PATH = EVAL_DIR / "calibration_split.json"
REPORT_PATH = EVAL_DIR / "threshold_calibration_report.json"

THRESHOLDS = [0.01, 0.03, 0.05, 0.07, 0.10, 0.15, 0.20]

def load_cases():
    cases = []
    with open(CASES_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                cases.append(json.loads(line))
    return cases

def split_cases(cases, ratio=0.7, seed=42):
    random.seed(seed)
    by_category = defaultdict(list)
    for c in cases:
        by_category[c.get("category", "none")].append(c)
    
    calibration = []
    regression = []
    for cat, items in by_category.items():
        random.shuffle(items)
        split_idx = max(1, int(len(items) * ratio))
        calibration.extend(items[:split_idx])
        regression.extend(items[split_idx:])
        
    return calibration, regression

def evaluate_subset(cases, retriever, top_k=5):
    metrics = []
    for c in cases:
        res = evaluate_case(retriever, c, top_k)
        metrics.append({
            "id": c["id"],
            "category": c["category"],
            "expected_retrievable": c["retrievable"],
            "actual_accepted": res["actual_accepted"],
            "doc_recall": res["doc_recall_at_k"],
            "mrr": res["reciprocal_rank"]
        })
    return metrics

def compute_summary(metrics):
    positives = [m for m in metrics if m["expected_retrievable"]]
    negatives = [m for m in metrics if not m["expected_retrievable"]]
    
    recall_list = [m["doc_recall"] for m in positives if m["doc_recall"] is not None]
    mrr_list = [m["mrr"] for m in positives if m["mrr"] is not None]
    
    avg_recall = statistics.fmean(recall_list) if recall_list else 0.0
    avg_mrr = statistics.fmean(mrr_list) if mrr_list else 0.0
    
    frr = sum(1 for m in positives if not m["actual_accepted"]) / len(positives) if positives else 0.0
    far = sum(1 for m in negatives if m["actual_accepted"]) / len(negatives) if negatives else 0.0
    
    return {
        "recall_at_5": avg_recall,
        "mrr": avg_mrr,
        "false_reject_rate": frr,
        "false_accept_rate": far
    }

def main():
    print("Loading cases...")
    cases = load_cases()
    
    if SPLIT_PATH.exists():
        print("Loading existing split...")
        splits = json.loads(SPLIT_PATH.read_text(encoding="utf-8"))
        calib_ids = set(splits["calibration_ids"])
        calibration = [c for c in cases if c["id"] in calib_ids]
        regression = [c for c in cases if c["id"] not in calib_ids]
    else:
        print("Creating new split...")
        calibration, regression = split_cases(cases)
        SPLIT_PATH.write_text(json.dumps({
            "calibration_ids": [c["id"] for c in calibration],
            "regression_ids": [c["id"] for c in regression]
        }, indent=2), encoding="utf-8")
        
    print(f"Calibration size: {len(calibration)}, Regression size: {len(regression)}")
    
    results = {}
    best_threshold = None
    min_far = 1.0
    best_mrr = 0.0
    
    for th in THRESHOLDS:
        print(f"\\nSweeping threshold {th}...")
        retriever = SafeRetriever(min_rerank_score=th)
        metrics = evaluate_subset(calibration, retriever)
        summary = compute_summary(metrics)
        results[str(th)] = summary
        
        print(f"FAR: {summary['false_accept_rate']:.2f}, FRR: {summary['false_reject_rate']:.2f}, MRR: {summary['mrr']:.4f}")
        
        # Selection logic: prioritize lowest FAR. If tie, prioritize highest MRR without spiking FRR.
        if summary["false_accept_rate"] < min_far:
            min_far = summary["false_accept_rate"]
            best_threshold = th
            best_mrr = summary["mrr"]
        elif summary["false_accept_rate"] == min_far:
            if summary["mrr"] > best_mrr:
                best_threshold = th
                best_mrr = summary["mrr"]
            elif summary["mrr"] == best_mrr and summary["false_reject_rate"] <= results[str(best_threshold)]["false_reject_rate"]:
                 best_threshold = th

    print(f"\\nBest threshold selected: {best_threshold}")
    
    print(f"\\nRunning confirmation on Regression set with threshold {best_threshold}...")
    final_retriever = SafeRetriever(min_rerank_score=best_threshold)
    reg_metrics = evaluate_subset(regression, final_retriever)
    reg_summary = compute_summary(reg_metrics)
    
    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "index_dir": str(resolve_current_index()),
        "splits": {
            "calibration_count": len(calibration),
            "regression_count": len(regression)
        },
        "calibration_sweep": results,
        "selected_threshold": best_threshold,
        "selection_reason": "Lowest False Accept Rate (FAR) while maintaining optimal MRR on Calibration set.",
        "regression_results": reg_summary,
        "recommendation": f"Thay đổi LEGAL_RAG_MIN_RERANK_SCORE từ 0.05 thành {best_threshold}." if best_threshold != 0.05 else "Giữ nguyên 0.05, đã có căn cứ qua đánh giá."
    }
    
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\\nReport saved to {REPORT_PATH}")

if __name__ == '__main__':
    main()
