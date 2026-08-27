#!/usr/bin/env python3
"""Find and remove visually similar images with dupeGuru picture-block semantics.

The scanner is intentionally two-step. ``scan`` writes an auditable JSONL deletion
manifest. ``apply`` only unlinks entries whose file metadata still matches that
manifest.

Set ``DUPEGURU_ROOT`` and ``DUPEGURU_THRESHOLD_PERCENT`` to select the image
directory and similarity threshold for a run.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import cv2
import numpy as np


ROOT = Path(os.environ.get("DUPEGURU_ROOT", "/hdd/extracted_frames_4fps/images"))
OUTPUT_DIR = ROOT.parent
BLOCKS_PER_SIDE = 15
THRESHOLD_PERCENT = int(os.environ.get("DUPEGURU_THRESHOLD_PERCENT", "85"))
MAX_TOTAL_DIFF = (100 - THRESHOLD_PERCENT) * BLOCKS_PER_SIDE * BLOCKS_PER_SIDE
WORKERS = min(8, os.cpu_count() or 1)
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
RUN_PREFIX = f"{ROOT.name}_dupeguru_{THRESHOLD_PERCENT}_similarity"
MANIFEST = OUTPUT_DIR / f"{RUN_PREFIX}_delete_manifest.jsonl"
SUMMARY = OUTPUT_DIR / f"{RUN_PREFIX}_summary.json"
APPLY_SUMMARY = OUTPUT_DIR / f"{RUN_PREFIX}_apply_summary.json"
PROJECTION_COUNT = 4
PROJECTION_SEED = 20260722
_projection_rng = np.random.default_rng(PROJECTION_SEED)
PROJECTION_SIGNS = _projection_rng.choice(
    np.array([-1, 1], dtype=np.int32),
    size=(PROJECTION_COUNT, BLOCKS_PER_SIDE * BLOCKS_PER_SIDE * 3),
)
PROJECTION_NEIGHBORS = tuple(product((-1, 0, 1), repeat=PROJECTION_COUNT))


def descriptor_task(index: int, path_text: str) -> tuple[int, np.ndarray | None, tuple[int, int] | None, int, int, str | None]:
    """Build dupeGuru's 15x15 block-color descriptor for one image."""
    cv2.setNumThreads(1)
    path = Path(path_text)
    try:
        image = cv2.imread(path_text, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("OpenCV could not decode the image")
        height, width = image.shape[:2]
        block_height = height // BLOCKS_PER_SIDE
        block_width = width // BLOCKS_PER_SIDE
        if not block_height or not block_width:
            raise ValueError(f"image is smaller than {BLOCKS_PER_SIDE} pixels in one dimension")

        # dupeGuru uses floor(width / 15) x floor(height / 15) tiles and floor
        # average RGB values. The integral image computes those same means fast.
        # CV_64F prevents integral-value overflow for high-resolution PNGs.
        integral = cv2.integral(image, sdepth=cv2.CV_64F)
        y0 = np.arange(BLOCKS_PER_SIDE) * block_height
        x0 = np.arange(BLOCKS_PER_SIDE) * block_width
        y1 = y0 + block_height
        x1 = x0 + block_width
        totals = (
            integral[y1[:, None], x1[None, :]]
            - integral[y0[:, None], x1[None, :]]
            - integral[y1[:, None], x0[None, :]]
            + integral[y0[:, None], x0[None, :]]
        )
        descriptor = (totals // (block_height * block_width)).reshape(-1, 3).astype(np.int16)
        stat = path.stat()
        return index, descriptor, (width, height), stat.st_size, stat.st_mtime_ns, None
    except Exception as exc:
        return index, None, None, 0, 0, f"{type(exc).__name__}: {exc}"


def atomic_write_json(path: Path, value: Any) -> None:
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, ensure_ascii=True, indent=2)
        handle.write("\n")
        temporary_path = Path(handle.name)
    temporary_path.replace(path)


def source_name(path: Path) -> str:
    relative = path.relative_to(ROOT)
    return relative.parts[0] if len(relative.parts) > 1 else "."


def projection_key(descriptor: np.ndarray) -> tuple[int, ...]:
    """Return a lossless-candidate index key for an L1 similarity range query."""
    projected = PROJECTION_SIGNS @ descriptor.reshape(-1).astype(np.int32)
    return tuple(int(value // MAX_TOTAL_DIFF) for value in projected)


def scan() -> int:
    paths = sorted(
        path
        for path in ROOT.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )
    if not paths:
        print(f"No supported images found under {ROOT}", file=sys.stderr)
        return 1

    print(f"Collecting descriptors for {len(paths):,} images with {WORKERS} workers...", flush=True)
    descriptors = np.empty((len(paths), BLOCKS_PER_SIDE * BLOCKS_PER_SIDE, 3), dtype=np.int16)
    dimensions: list[tuple[int, int] | None] = [None] * len(paths)
    sizes = [0] * len(paths)
    mtimes = [0] * len(paths)
    errors: list[dict[str, str]] = []

    completed = 0
    with ProcessPoolExecutor(max_workers=WORKERS) as executor:
        futures = [executor.submit(descriptor_task, index, str(path)) for index, path in enumerate(paths)]
        for future in as_completed(futures):
            index, descriptor, dimension, size, mtime_ns, error = future.result()
            completed += 1
            if error:
                errors.append({"path": str(paths[index]), "error": error})
            else:
                descriptors[index] = descriptor
                dimensions[index] = dimension
                sizes[index] = size
                mtimes[index] = mtime_ns
            if completed % 1000 == 0 or completed == len(paths):
                print(f"  descriptors: {completed:,}/{len(paths):,}", flush=True)

    print("Selecting a retained representative for each direct-similarity group...", flush=True)
    representative_buckets: dict[tuple[int, int], dict[tuple[int, ...], list[int]]] = {}
    deletions: list[dict[str, Any]] = []
    kept_count = 0
    skipped_count = 0
    exact_candidate_comparisons = 0
    maximum_candidate_count = 0

    for index, path in enumerate(paths):
        dimension = dimensions[index]
        if dimension is None:
            skipped_count += 1
            continue
        buckets = representative_buckets.setdefault(dimension, {})
        if MAX_TOTAL_DIFF:
            key = projection_key(descriptors[index])
            candidate_indices = [
                candidate_index
                for delta in PROJECTION_NEIGHBORS
                for candidate_index in buckets.get(tuple(value + offset for value, offset in zip(key, delta)), ())
            ]
        else:
            key = tuple(int(value) for value in descriptors[index].reshape(-1))
            candidate_indices = buckets.get(key, [])

        maximum_candidate_count = max(maximum_candidate_count, len(candidate_indices))
        exact_candidate_comparisons += len(candidate_indices)
        if candidate_indices:
            candidate_descriptors = descriptors[candidate_indices]
            total_differences = np.abs(candidate_descriptors - descriptors[index]).sum(axis=(1, 2), dtype=np.int64)
            matched_positions = np.flatnonzero(total_differences <= MAX_TOTAL_DIFF)
        else:
            total_differences = np.empty(0, dtype=np.int64)
            matched_positions = np.empty(0, dtype=np.int64)

        if len(matched_positions):
            minimum_difference = int(total_differences[matched_positions].min())
            best_position = min(
                (candidate_indices[int(position)], int(position))
                for position in matched_positions
                if int(total_differences[int(position)]) == minimum_difference
            )[1]
            reference_index = candidate_indices[best_position]
            total_difference = minimum_difference
            similarity_percent = 100 - (total_difference // (BLOCKS_PER_SIDE * BLOCKS_PER_SIDE))
            deletions.append(
                {
                    "action": "delete",
                    "path": str(path),
                    "reference_path": str(paths[reference_index]),
                    "similarity_percent": similarity_percent,
                    "total_color_difference": total_difference,
                    "size": sizes[index],
                    "mtime_ns": mtimes[index],
                }
            )
        else:
            buckets.setdefault(key, []).append(index)
            kept_count += 1

        if (index + 1) % 2000 == 0 or index + 1 == len(paths):
            print(f"  decisions: {index + 1:,}/{len(paths):,}; delete candidates: {len(deletions):,}", flush=True)

    deleted_by_source = Counter(source_name(Path(record["path"])) for record in deletions)
    kept_by_source = Counter(source_name(path) for index, path in enumerate(paths) if dimensions[index] is not None)
    for record in deletions:
        kept_by_source[source_name(Path(record["path"]))] -= 1

    with NamedTemporaryFile("w", encoding="utf-8", dir=MANIFEST.parent, delete=False) as handle:
        for record in deletions:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")
        temporary_manifest = Path(handle.name)
    temporary_manifest.replace(MANIFEST)

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "root": str(ROOT),
        "manifest": str(MANIFEST),
        "algorithm": "dupeGuru picture blocks: 15x15 floor-average color tiles, same dimensions only",
        "threshold_percent": THRESHOLD_PERCENT,
        "max_total_color_difference": MAX_TOTAL_DIFF,
        "total_images": len(paths),
        "valid_images": len(paths) - len(errors),
        "kept_images": kept_count,
        "delete_candidates": len(deletions),
        "candidate_bytes": sum(record["size"] for record in deletions),
        "exact_candidate_comparisons": exact_candidate_comparisons,
        "maximum_candidates_for_one_image": maximum_candidate_count,
        "candidate_index": {
            "method": "four signed L1 projections with exact final block comparison",
            "projection_seed": PROJECTION_SEED,
        },
        "unreadable_or_skipped_images": skipped_count,
        "errors": errors,
        "delete_candidates_by_source": dict(sorted(deleted_by_source.items())),
        "kept_images_by_source": dict(sorted(kept_by_source.items())),
    }
    atomic_write_json(SUMMARY, summary)

    print(f"Wrote manifest: {MANIFEST}")
    print(f"Wrote summary: {SUMMARY}")
    print(
        f"Scan complete: {len(deletions):,} delete candidates, {kept_count:,} retained images, "
        f"{summary['candidate_bytes'] / (1024 ** 3):.2f} GiB eligible for deletion."
    )
    return 0


def apply() -> int:
    if not MANIFEST.exists():
        print(f"Manifest does not exist: {MANIFEST}", file=sys.stderr)
        return 1

    root_resolved = ROOT.resolve()
    deleted = 0
    skipped_missing = 0
    skipped_changed = 0
    skipped_invalid = 0
    failed: list[dict[str, str]] = []

    records = []
    with MANIFEST.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    print(f"Applying {len(records):,} deletions from {MANIFEST}...", flush=True)
    for position, record in enumerate(records, start=1):
        path = Path(record["path"])
        try:
            resolved = path.resolve(strict=False)
            if not resolved.is_relative_to(root_resolved) or path.suffix.lower() not in IMAGE_EXTENSIONS:
                skipped_invalid += 1
                continue
            try:
                stat = path.stat()
            except FileNotFoundError:
                skipped_missing += 1
                continue
            if stat.st_size != record["size"] or stat.st_mtime_ns != record["mtime_ns"]:
                skipped_changed += 1
                continue
            path.unlink()
            deleted += 1
        except Exception as exc:
            failed.append({"path": str(path), "error": f"{type(exc).__name__}: {exc}"})
        if position % 1000 == 0 or position == len(records):
            print(f"  apply: {position:,}/{len(records):,}; deleted: {deleted:,}", flush=True)

    apply_summary = {
        "applied_at_utc": datetime.now(timezone.utc).isoformat(),
        "manifest": str(MANIFEST),
        "deleted": deleted,
        "skipped_missing": skipped_missing,
        "skipped_changed": skipped_changed,
        "skipped_invalid": skipped_invalid,
        "failed": failed,
    }
    atomic_write_json(APPLY_SUMMARY, apply_summary)
    print(
        f"Apply complete: deleted {deleted:,}; missing {skipped_missing:,}; changed {skipped_changed:,}; "
        f"invalid {skipped_invalid:,}; failed {len(failed):,}."
    )
    return 0 if not failed else 2


def main() -> int:
    global ROOT, OUTPUT_DIR, THRESHOLD_PERCENT, MAX_TOTAL_DIFF, WORKERS
    global RUN_PREFIX, MANIFEST, SUMMARY, APPLY_SUMMARY

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("scan", "apply"))
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="Image directory to scan recursively (default: DUPEGURU_ROOT or %(default)s)",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=THRESHOLD_PERCENT,
        help=(
            "Delete candidates whose dupeGuru-style similarity reaches this percentage "
            "(default: DUPEGURU_THRESHOLD_PERCENT or %(default)s)"
        ),
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=WORKERS,
        help="Descriptor worker processes (default: %(default)s)",
    )
    arguments = parser.parse_args()

    ROOT = arguments.root.expanduser().resolve()
    OUTPUT_DIR = ROOT.parent
    THRESHOLD_PERCENT = arguments.threshold
    MAX_TOTAL_DIFF = (100 - THRESHOLD_PERCENT) * BLOCKS_PER_SIDE * BLOCKS_PER_SIDE
    WORKERS = arguments.workers
    RUN_PREFIX = f"{ROOT.name}_dupeguru_{THRESHOLD_PERCENT}_similarity"
    MANIFEST = OUTPUT_DIR / f"{RUN_PREFIX}_delete_manifest.jsonl"
    SUMMARY = OUTPUT_DIR / f"{RUN_PREFIX}_summary.json"
    APPLY_SUMMARY = OUTPUT_DIR / f"{RUN_PREFIX}_apply_summary.json"

    if not ROOT.is_dir():
        print(f"Image directory does not exist: {ROOT}", file=sys.stderr)
        return 1
    if not 1 <= THRESHOLD_PERCENT <= 100:
        print(f"Threshold must be between 1 and 100: {THRESHOLD_PERCENT}", file=sys.stderr)
        return 1
    if WORKERS < 1:
        print(f"Workers must be at least 1: {WORKERS}", file=sys.stderr)
        return 1
    return scan() if arguments.command == "scan" else apply()


if __name__ == "__main__":
    raise SystemExit(main())
