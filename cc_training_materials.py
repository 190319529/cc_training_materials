#!/usr/bin/env python3
"""Local web workspace for preparing and pre-labeling YOLO datasets."""

from __future__ import annotations

import argparse
import json
import math
import mimetypes
import os
import random
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

try:
    import yaml
except ImportError:  # pragma: no cover - handled by the API at runtime
    yaml = None


APP_NAME = "cc_training_materials"
APP_VERSION = "2.12.0"
APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "cc_training_materials_web"
DEDUP_SCRIPT = APP_DIR / "image_similarity_dedup.py"
CONFIG_FILENAME = ".cc_training_materials.json"
WORK_DIRNAME = ".cc_training_materials"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
MODEL_EXTENSIONS = {".pt"}
VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v", ".wmv", ".flv"}
DEFAULT_CLASSES = {0: "目标"}
WEATHER_TYPES = {"sunny", "strong_sun", "cloudy", "overcast", "fog", "rain", "snow", "night"}
WEATHER_IMAGES_DIRNAME = "weather_augmented"
TRAINING_SCOPES = {"incremental_replay", "incremental", "all_reviewed"}
DEDUP_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


class AppError(Exception):
    def __init__(self, message: str, status: int = HTTPStatus.BAD_REQUEST):
        super().__init__(message)
        self.status = int(status)


class JobCancelled(Exception):
    """Stop a background job without reporting it as a failure."""


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def ensure_float(value: Any, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise AppError(f"{name} 必须是数字") from exc
    if not math.isfinite(number):
        raise AppError(f"{name} 必须是有限数字")
    return number


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


@dataclass(frozen=True)
class Box:
    cls_id: int
    xc: float
    yc: float
    w: float
    h: float

    @classmethod
    def from_payload(cls, value: dict[str, Any], known_classes: set[int]) -> "Box":
        try:
            cls_id = int(value["cls_id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise AppError("标注框缺少有效的类别 ID") from exc
        if cls_id not in known_classes:
            raise AppError(f"类别 ID {cls_id} 不在当前类别配置中")

        xc = ensure_float(value.get("xc"), "中心点 X")
        yc = ensure_float(value.get("yc"), "中心点 Y")
        width = ensure_float(value.get("w"), "宽度")
        height = ensure_float(value.get("h"), "高度")
        if not (0 <= xc <= 1 and 0 <= yc <= 1):
            raise AppError("标注框中心点必须位于图片范围内")
        if not (0 < width <= 1 and 0 < height <= 1):
            raise AppError("标注框宽高必须大于 0 且不超过图片")
        epsilon = 1e-5
        if xc - width / 2 < -epsilon or xc + width / 2 > 1 + epsilon:
            raise AppError("标注框横向超出图片范围")
        if yc - height / 2 < -epsilon or yc + height / 2 > 1 + epsilon:
            raise AppError("标注框纵向超出图片范围")
        return cls(cls_id, xc, yc, width, height)

    @classmethod
    def from_line(cls, line: str, line_number: int) -> "Box":
        parts = line.split()
        if len(parts) != 5:
            raise ValueError(f"第 {line_number} 行不是 5 列 YOLO 格式")
        try:
            cls_id = int(parts[0])
            values = [float(item) for item in parts[1:]]
        except ValueError as exc:
            raise ValueError(f"第 {line_number} 行包含无效数字") from exc
        if any(not math.isfinite(item) for item in values):
            raise ValueError(f"第 {line_number} 行包含非有限数字")
        xc, yc, width, height = values
        if cls_id < 0 or not (0 <= xc <= 1 and 0 <= yc <= 1):
            raise ValueError(f"第 {line_number} 行的类别或中心点无效")
        if not (0 < width <= 1 and 0 < height <= 1):
            raise ValueError(f"第 {line_number} 行的宽高无效")
        return cls(cls_id, xc, yc, width, height)

    def to_dict(self) -> dict[str, Any]:
        return {"cls_id": self.cls_id, "xc": self.xc, "yc": self.yc, "w": self.w, "h": self.h}

    def to_line(self) -> str:
        return f"{self.cls_id} {self.xc:.6f} {self.yc:.6f} {self.w:.6f} {self.h:.6f}"


class DatasetState:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.root: Path | None = None
        self.labels_dir: Path | None = None
        self.sources: list[dict[str, Any]] = []
        self.classes: dict[int, str] = dict(DEFAULT_CLASSES)
        self.metadata: dict[str, Any] = self._new_metadata()

    @staticmethod
    def _new_metadata() -> dict[str, Any]:
        return {
            "app": APP_NAME,
            "version": APP_VERSION,
            "classes": {"0": "目标"},
            "sources": [],
            "images": {},
        }

    def require_open(self) -> tuple[Path, list[dict[str, Any]], Path]:
        with self.lock:
            if self.root is None or self.labels_dir is None:
                raise AppError("请先选择数据集根目录", HTTPStatus.CONFLICT)
            return self.root, list(self.sources), self.labels_dir

    def open(self, raw_path: str) -> dict[str, Any]:
        if not raw_path or not isinstance(raw_path, str):
            raise AppError("数据集路径不能为空")
        root = Path(raw_path).expanduser().resolve()
        if not root.is_dir():
            raise AppError("所选数据集目录不存在")
        labels_dir = root / "labels"
        labels_dir.mkdir(parents=True, exist_ok=True)

        with self.lock:
            self.root = root
            self.labels_dir = labels_dir.resolve()
            self.metadata = self._load_metadata(root)
            self.sources = self._load_sources(root, self.metadata)
            self.classes = self._classes_from_metadata(self.metadata)
            if self.classes == DEFAULT_CLASSES:
                detected = self._load_classes_from_yaml(root)
                if detected:
                    self.classes = detected
                    self.metadata["classes"] = {str(key): value for key, value in detected.items()}
            self._save_metadata_locked()
        return self.summary()

    def create(self, raw_path: str) -> dict[str, Any]:
        if not raw_path or not isinstance(raw_path, str):
            raise AppError("项目路径不能为空")
        root = Path(raw_path).expanduser().resolve()
        if root.exists() and not root.is_dir():
            raise AppError("项目路径已被文件占用")
        root.mkdir(parents=True, exist_ok=True)
        (root / "labels").mkdir(parents=True, exist_ok=True)
        return self.open(str(root))

    def _load_metadata(self, root: Path) -> dict[str, Any]:
        path = root / CONFIG_FILENAME
        if not path.exists():
            return self._new_metadata()
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError("root must be an object")
            value.setdefault("app", APP_NAME)
            value.setdefault("version", APP_VERSION)
            value.setdefault("classes", {"0": "目标"})
            value.setdefault("sources", [])
            value.setdefault("images", {})
            return value
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise AppError(f"无法读取 {CONFIG_FILENAME}: {exc}") from exc

    @staticmethod
    def _classes_from_metadata(metadata: dict[str, Any]) -> dict[int, str]:
        raw = metadata.get("classes", {})
        try:
            result = {int(key): str(value).strip() for key, value in raw.items() if str(value).strip()}
        except (AttributeError, TypeError, ValueError):
            return dict(DEFAULT_CLASSES)
        if sorted(result) != list(range(len(result))):
            return dict(DEFAULT_CLASSES)
        return result or dict(DEFAULT_CLASSES)

    @staticmethod
    def _load_classes_from_yaml(root: Path) -> dict[int, str] | None:
        if yaml is None:
            return None
        for name in ("data.yaml", "dataset.yaml", "cc_training_materials.yaml"):
            path = root / name
            if not path.is_file():
                continue
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                names = data.get("names")
                if isinstance(names, list):
                    result = {idx: str(value).strip() for idx, value in enumerate(names)}
                elif isinstance(names, dict):
                    result = {int(key): str(value).strip() for key, value in names.items()}
                else:
                    continue
                if result and sorted(result) == list(range(len(result))) and all(result.values()):
                    return result
            except (OSError, ValueError, TypeError, AttributeError):
                continue
        return None

    @staticmethod
    def _has_direct_images(path: Path) -> bool:
        try:
            return any(child.is_file() and child.suffix.lower() in IMAGE_EXTENSIONS for child in path.iterdir())
        except (OSError, PermissionError):
            return False

    def _load_sources(self, root: Path, metadata: dict[str, Any]) -> list[dict[str, Any]]:
        sources: list[dict[str, Any]] = []
        raw_sources = metadata.get("sources", [])
        if isinstance(raw_sources, list):
            for item in raw_sources:
                if not isinstance(item, dict):
                    continue
                source_id = str(item.get("id", "")).strip()
                raw_path = item.get("path")
                if not isinstance(raw_path, str) or not raw_path:
                    continue
                path = Path(raw_path).expanduser()
                if not path.is_absolute():
                    path = root / path
                path = path.resolve()
                if path.is_dir() and not any(existing["id"] == source_id for existing in sources):
                    raw_labels_path = item.get("labels_path")
                    labels_path = None
                    if isinstance(raw_labels_path, str) and raw_labels_path.strip():
                        labels_path = Path(raw_labels_path).expanduser()
                        if not labels_path.is_absolute():
                            labels_path = root / labels_path
                        labels_path = labels_path.resolve()
                    sources.append({"id": source_id, "path": path, "labels_path": labels_path})
        if sources:
            return sources

        conventional = (root / "images").resolve()
        if conventional.is_dir():
            sources = [{"id": "", "path": conventional}]
        elif self._has_direct_images(root):
            sources = [{"id": "", "path": root}]
        metadata["sources"] = [self._source_for_storage(root, item) for item in sources]
        return sources

    @staticmethod
    def _source_for_storage(root: Path, source: dict[str, Any]) -> dict[str, str]:
        path = Path(source["path"])
        try:
            stored_path = path.relative_to(root).as_posix()
        except ValueError:
            stored_path = str(path)
        result = {"id": str(source["id"]), "path": stored_path}
        labels_path = source.get("labels_path")
        if labels_path:
            labels = Path(labels_path)
            try:
                result["labels_path"] = labels.relative_to(root).as_posix()
            except ValueError:
                result["labels_path"] = str(labels)
        return result

    @staticmethod
    def _source_alias(path: Path, used: set[str]) -> str:
        base = re.sub(r"[^A-Za-z0-9._-]+", "_", path.name).strip("._-") or "source"
        candidate = base
        number = 2
        while candidate in used:
            candidate = f"{base}_{number}"
            number += 1
        return candidate

    def add_source(self, raw_path: str, raw_labels_path: str | None = None) -> dict[str, Any]:
        root, _, _ = self.require_open()
        if not raw_path or not isinstance(raw_path, str):
            raise AppError("图片目录不能为空")
        path = Path(raw_path).expanduser().resolve()
        if not path.is_dir():
            raise AppError("图片目录不存在")
        labels_path = None
        if isinstance(raw_labels_path, str) and raw_labels_path.strip():
            labels_path = Path(raw_labels_path).expanduser().resolve()
            if not labels_path.is_dir():
                raise AppError("外部标注目录不存在")
        image_count = sum(
            1 for candidate in path.rglob("*") if candidate.is_file() and candidate.suffix.lower() in IMAGE_EXTENSIONS
        )
        if image_count == 0:
            raise AppError("所选目录中没有支持的图片")
        with self.lock:
            for item in self.sources:
                existing = Path(item["path"]).resolve()
                if existing == path:
                    raise AppError("该图片目录已经添加")
                if is_relative_to(existing, path) or is_relative_to(path, existing):
                    raise AppError("该图片目录与已添加目录重叠，不能重复添加")
            source_id = self._source_alias(path, {str(item["id"]) for item in self.sources})
            self.sources.append({"id": source_id, "path": path, "labels_path": labels_path})
            self.metadata["sources"] = [self._source_for_storage(root, item) for item in self.sources]
            self._save_metadata_locked()
        result = self.summary()
        result["added"] = {
            "id": source_id,
            "path": str(path),
            "labels_path": str(labels_path) if labels_path else None,
            "image_count": image_count,
        }
        return result

    def remove_source(self, source_id: str, raw_path: str) -> dict[str, Any]:
        clean_id = source_id.strip() if isinstance(source_id, str) else ""
        clean_path = Path(raw_path).expanduser().resolve() if isinstance(raw_path, str) and raw_path.strip() else None
        if not clean_id and clean_path is None:
            raise AppError("图片目录标识不能为空")
        with self.lock:
            root, _, _ = self.require_open()
            index = next(
                (
                    position
                    for position, item in enumerate(self.sources)
                    if (clean_id and str(item["id"]) == clean_id)
                    or (not clean_id and clean_path is not None and Path(item["path"]).resolve() == clean_path)
                ),
                None,
            )
            if index is None:
                raise AppError("图片目录不在当前项目中", HTTPStatus.NOT_FOUND)
            removed = self.sources.pop(index)
            self.metadata["sources"] = [self._source_for_storage(root, item) for item in self.sources]
            self._save_metadata_locked()
        result = self.summary()
        result["removed"] = {"id": str(removed["id"]), "path": str(removed["path"])}
        return result

    def _weather_images_root_locked(self) -> Path:
        root, _, _ = self.require_open()
        preferred = (root / WEATHER_IMAGES_DIRNAME).resolve()
        for source in self.sources:
            source_root = Path(source["path"]).resolve()
            if is_relative_to(preferred, source_root):
                return preferred

        default_source = next((source for source in self.sources if not str(source["id"])), None)
        if default_source is not None:
            return (Path(default_source["path"]).resolve() / WEATHER_IMAGES_DIRNAME).resolve()

        existing = next(
            (source for source in self.sources if Path(source["path"]).resolve() == preferred),
            None,
        )
        if existing is None:
            source_id = self._source_alias(preferred, {str(source["id"]) for source in self.sources})
            self.sources.append({"id": source_id, "path": preferred, "labels_path": None})
            self.metadata["sources"] = [self._source_for_storage(root, source) for source in self.sources]
        return preferred

    def sync_weather_review(
        self,
        review_dir: Path,
        manifest: dict[str, Any],
        approved_ids: set[str],
    ) -> dict[str, int]:
        with self.lock:
            _, _, labels_dir = self.require_open()
            items = [item for item in manifest.get("items", []) if isinstance(item, dict)]
            needs_storage = bool(approved_ids) or any(item.get("dataset_name") for item in items)
            weather_root = self._weather_images_root_locked() if needs_storage else None
            review_target = weather_root / str(manifest.get("id", "weather")) if weather_root else None
            added = 0
            removed = 0
            retained = 0
            created_paths: list[Path] = []
            images = self.metadata.setdefault("images", {})
            ordered_items = sorted(
                items,
                key=lambda item: str(item.get("id", "")) not in approved_ids,
            )

            try:
                for item in ordered_items:
                    item_id = str(item.get("id", ""))
                    dataset_name = str(item.get("dataset_name", ""))
                    if item_id not in approved_ids:
                        if dataset_name:
                            metadata = images.get(dataset_name, {})
                            if (
                                isinstance(metadata, dict)
                                and metadata.get("origin") == "weather"
                                and metadata.get("weather_review_id") == manifest.get("id")
                            ):
                                try:
                                    self.image_path(dataset_name).unlink(missing_ok=True)
                                except AppError:
                                    pass
                                label_relative = Path(*PurePosixPath(dataset_name).parts).with_suffix(".txt")
                                label_path = (labels_dir / label_relative).resolve()
                                if is_relative_to(label_path, labels_dir):
                                    label_path.unlink(missing_ok=True)
                                images.pop(dataset_name, None)
                                removed += 1
                            item.pop("dataset_name", None)
                        continue

                    if review_target is None:
                        raise AppError("天气增强图片目录不可用")
                    source_image = (review_dir / str(item.get("image_file", ""))).resolve()
                    source_label = (review_dir / str(item.get("label_file", ""))).resolve()
                    if (
                        not is_relative_to(source_image, review_dir.resolve())
                        or not is_relative_to(source_label, review_dir.resolve())
                        or not source_image.is_file()
                        or not source_label.is_file()
                    ):
                        raise AppError("已审核天气素材缺失，请重新生成")

                    source_stem = PurePosixPath(str(item.get("source_name", "image"))).stem
                    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", source_stem).strip("._-") or "image"
                    weather = str(item.get("weather", "weather"))
                    target_image = review_target / f"{safe_stem[:96]}__{weather}__{item_id}.jpg"
                    target_image.parent.mkdir(parents=True, exist_ok=True)
                    image_created = not target_image.exists()
                    if image_created:
                        try:
                            os.link(source_image, target_image)
                        except OSError:
                            shutil.copy2(source_image, target_image)
                        created_paths.append(target_image)

                    relative_name = self.relative_image_name(target_image)
                    target_label = self.label_path(relative_name)
                    target_label.parent.mkdir(parents=True, exist_ok=True)
                    label_created = not target_label.exists()
                    if label_created:
                        shutil.copy2(source_label, target_label)
                        created_paths.append(target_label)

                    previous = images.get(relative_name, {})
                    previous = previous if isinstance(previous, dict) else {}
                    images[relative_name] = {
                        **previous,
                        "source": previous.get("source", "weather"),
                        "origin": "weather",
                        "weather_type": weather,
                        "weather_review_id": manifest.get("id"),
                        "weather_source_name": str(item.get("source_name", "")),
                        "reviewed": True,
                        "updated_at": previous.get("updated_at") or now_iso(),
                    }
                    item["dataset_name"] = relative_name
                    if image_created or label_created:
                        added += 1
                    else:
                        retained += 1
            except Exception:
                for path in reversed(created_paths):
                    path.unlink(missing_ok=True)
                raise

            self._save_metadata_locked()
            return {"added": added, "removed": removed, "retained": retained, "total": len(approved_ids)}

    def _save_metadata_locked(self) -> None:
        if self.root is None:
            return
        self.metadata["app"] = APP_NAME
        self.metadata["version"] = APP_VERSION
        atomic_write_text(
            self.root / CONFIG_FILENAME,
            json.dumps(self.metadata, ensure_ascii=False, indent=2) + "\n",
        )

    def set_classes(
        self,
        values: list[dict[str, Any]],
        class_id_map: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(values, list) or not values:
            raise AppError("至少需要配置一个目标类别")
        parsed: dict[int, str] = {}
        for item in values:
            try:
                class_id = int(item["id"])
                name = str(item["name"]).strip()
            except (KeyError, TypeError, ValueError) as exc:
                raise AppError("类别配置格式无效") from exc
            if class_id < 0 or not name:
                raise AppError("类别 ID 不能为负数，类别名称不能为空")
            if class_id in parsed:
                raise AppError(f"类别 ID {class_id} 重复")
            parsed[class_id] = name
        if sorted(parsed) != list(range(len(parsed))):
            raise AppError("类别 ID 必须从 0 开始连续排列")

        with self.lock:
            self.require_open()
            previous_classes = dict(self.classes)
            previous_metadata = dict(self.metadata)
            next_classes = dict(sorted(parsed.items()))
            explicit_mapping = self._parse_class_id_map(class_id_map, previous_classes, next_classes)
            mapping = self._class_id_mapping(previous_classes, next_classes, explicit_mapping)
            label_changes = self._plan_class_label_migration(mapping)
            backups: list[tuple[Path, Path]] = []
            try:
                if label_changes:
                    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                    migration_root = self.root / WORK_DIRNAME / "class_migrations" / stamp
                    for label_path, content in label_changes:
                        relative = label_path.relative_to(self.labels_dir)
                        backup_path = migration_root / "labels" / relative
                        backup_path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(label_path, backup_path)
                        backups.append((label_path, backup_path))
                        atomic_write_text(label_path, content)
                self.classes = next_classes
                self.metadata["classes"] = {str(key): value for key, value in self.classes.items()}
                self._save_metadata_locked()
            except Exception:
                for label_path, backup_path in backups:
                    shutil.copy2(backup_path, label_path)
                self.classes = previous_classes
                self.metadata = previous_metadata
                raise
        return self.summary()

    @staticmethod
    def _class_id_mapping(
        previous: dict[int, str],
        next_classes: dict[int, str],
        explicit: dict[int, int] | None = None,
    ) -> dict[int, int]:
        """Match renamed/reordered classes without guessing across duplicate names."""
        next_by_name: dict[str, int] = {}
        duplicate_names: set[str] = set()
        for class_id, name in next_classes.items():
            if name in next_by_name:
                duplicate_names.add(name)
            else:
                next_by_name[name] = class_id
        mapping: dict[int, int] = {}
        for old_id, old_name in previous.items():
            if explicit and old_id in explicit:
                mapping[old_id] = explicit[old_id]
                continue
            if old_name in next_by_name and old_name not in duplicate_names:
                mapping[old_id] = next_by_name[old_name]
            elif old_id in next_classes:
                mapping[old_id] = old_id
        return mapping

    @staticmethod
    def _parse_class_id_map(
        value: dict[str, Any] | None,
        previous: dict[int, str],
        next_classes: dict[int, str],
    ) -> dict[int, int]:
        if value in (None, {}):
            return {}
        if not isinstance(value, dict):
            raise AppError("类别编号映射格式无效")
        mapping: dict[int, int] = {}
        targets: set[int] = set()
        for raw_old, raw_new in value.items():
            try:
                old_id = int(raw_old)
                new_id = int(raw_new)
            except (TypeError, ValueError) as exc:
                raise AppError("类别编号映射格式无效") from exc
            if old_id not in previous or new_id not in next_classes:
                raise AppError("类别编号映射包含不存在的类别")
            if old_id in mapping or new_id in targets:
                raise AppError("类别编号映射不能重复")
            mapping[old_id] = new_id
            targets.add(new_id)
        return mapping

    def _plan_class_label_migration(
        self,
        mapping: dict[int, int],
    ) -> list[tuple[Path, str]]:
        """Validate and prepare all label rewrites before changing any file."""
        _, _, labels_dir = self.require_open()
        changes: list[tuple[Path, str]] = []
        label_paths = {
            self.label_path(name)
            for name in self.all_image_names()
            if self.label_path(name).is_file()
        }
        for label_path in sorted(label_paths):
            try:
                lines = label_path.read_text(encoding="utf-8").splitlines()
            except OSError as exc:
                raise AppError(f"标签文件读取失败：{label_path.name}: {exc}") from exc
            rewritten: list[str] = []
            changed = False
            for line_number, line in enumerate(lines, start=1):
                if not line.strip():
                    rewritten.append("")
                    continue
                parts = line.split()
                try:
                    old_id = int(parts[0])
                except (IndexError, ValueError) as exc:
                    raise AppError(f"标签文件 {label_path.name} 第 {line_number} 行类别编号无效") from exc
                if old_id not in mapping:
                    raise AppError(
                        f"类别 {old_id} 已被标签 {label_path.name} 使用，不能直接删除；"
                        "请先修改或删除这些标注框"
                    )
                new_id = mapping[old_id]
                rewritten.append(" ".join([str(new_id), *parts[1:]]))
                changed = changed or new_id != old_id
            if changed:
                changes.append((label_path, "\n".join(rewritten) + ("\n" if rewritten else "")))
        return changes

    def summary(self) -> dict[str, Any]:
        with self.lock:
            return {
                "open": self.root is not None,
                "root": str(self.root) if self.root else None,
                "classes": [{"id": key, "name": value} for key, value in self.classes.items()],
                "sources": [
                    {
                        "id": str(item["id"]),
                        "path": str(item["path"]),
                        "labels_path": str(item["labels_path"]) if item.get("labels_path") else None,
                    }
                    for item in self.sources
                ],
            }

    def image_path(self, relative_name: str) -> Path:
        _, sources, _ = self.require_open()
        if not relative_name or not isinstance(relative_name, str):
            raise AppError("图片路径不能为空")
        pure = PurePosixPath(relative_name)
        if pure.is_absolute() or ".." in pure.parts:
            raise AppError("图片路径无效")
        explicit_sources = [item for item in sources if item["id"]]
        default_sources = [item for item in sources if not item["id"]]
        for source in explicit_sources + default_sources:
            source_root = Path(source["path"]).resolve()
            source_id = str(source["id"])
            if source_id:
                if not pure.parts or pure.parts[0] != source_id:
                    continue
                relative_parts = pure.parts[1:]
            else:
                relative_parts = pure.parts
            if not relative_parts:
                continue
            candidate = (source_root / Path(*relative_parts)).resolve()
            if (
                is_relative_to(candidate, source_root)
                and candidate.is_file()
                and candidate.suffix.lower() in IMAGE_EXTENSIONS
            ):
                return candidate
        raise AppError("图片不存在", HTTPStatus.NOT_FOUND)

    def label_path(self, relative_name: str) -> Path:
        _, sources, labels_dir = self.require_open()
        image_path = self.image_path(relative_name)
        source_root = None
        source_labels = labels_dir
        for source in sources:
            candidate_root = Path(source["path"]).resolve()
            if is_relative_to(image_path, candidate_root):
                source_root = candidate_root
                raw_labels = source.get("labels_path")
                if raw_labels:
                    source_labels = Path(raw_labels).resolve()
                break
        if source_root is None:
            raise AppError("图片来源不存在")
        if source.get("labels_path"):
            relative = image_path.relative_to(source_root).with_suffix(".txt")
        else:
            relative = Path(*PurePosixPath(relative_name).parts).with_suffix(".txt")
        candidate = (source_labels / relative).resolve()
        if not is_relative_to(candidate, source_labels):
            raise AppError("标签路径无效")
        return candidate

    def relative_image_name(self, image_path: Path) -> str:
        _, sources, _ = self.require_open()
        resolved = image_path.resolve()
        for source in sources:
            source_root = Path(source["path"]).resolve()
            if is_relative_to(resolved, source_root):
                relative = resolved.relative_to(source_root).as_posix()
                return f"{source['id']}/{relative}" if source["id"] else relative
        raise AppError("图片不属于当前数据集")

    def all_image_names(self) -> list[str]:
        _, sources, _ = self.require_open()
        names: list[str] = []
        for source in sources:
            source_root = Path(source["path"])
            prefix = f"{source['id']}/" if source["id"] else ""
            names.extend(
                prefix + path.relative_to(source_root).as_posix()
                for path in source_root.rglob("*")
                if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
            )
        return sorted(names, key=lambda item: item.casefold())

    def read_boxes(self, relative_name: str) -> tuple[list[Box], list[str]]:
        label_path = self.label_path(relative_name)
        if not label_path.exists():
            return [], []
        boxes: list[Box] = []
        warnings: list[str] = []
        try:
            lines = label_path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise AppError(f"标签文件读取失败: {exc}") from exc
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                boxes.append(Box.from_line(line.strip(), line_number))
            except ValueError as exc:
                warnings.append(str(exc))
        return boxes, warnings

    def _image_meta(self, relative_name: str) -> dict[str, Any]:
        images = self.metadata.setdefault("images", {})
        value = images.get(relative_name, {})
        return value if isinstance(value, dict) else {}

    def image_entry(self, relative_name: str) -> dict[str, Any]:
        label_path = self.label_path(relative_name)
        metadata = self._image_meta(relative_name)
        has_label = label_path.is_file()
        box_count = 0
        invalid = False
        if has_label:
            boxes, warnings = self.read_boxes(relative_name)
            box_count = len(boxes)
            invalid = bool(warnings)
        source = metadata.get("source", "existing" if has_label else None)
        is_weather = metadata.get("origin") == "weather"
        reviewed = bool(metadata.get("reviewed", False))
        pending = bool(has_label and source == "prediction" and not reviewed)
        return {
            "path": relative_name,
            "name": PurePosixPath(relative_name).name,
            "has_label": has_label,
            "box_count": box_count,
            "source": source,
            "is_weather": is_weather,
            "weather_type": metadata.get("weather_type") if is_weather else None,
            "weather_source_name": metadata.get("weather_source_name") if is_weather else None,
            "reviewed": reviewed,
            "pending": pending,
            "invalid": invalid,
            "updated_at": metadata.get("updated_at"),
        }

    def list_images(
        self,
        filter_name: str,
        search: str,
        sort_name: str,
        offset: int,
        limit: int,
    ) -> dict[str, Any]:
        names = self.all_image_names()
        search_value = search.strip().casefold()
        entries: list[dict[str, Any]] = []
        stats = {
            "total": 0,
            "unlabeled": 0,
            "labeled": 0,
            "pending": 0,
            "reviewed": 0,
            "weather": 0,
            "invalid": 0,
        }
        for name in names:
            entry = self.image_entry(name)
            stats["total"] += 1
            stats["labeled" if entry["has_label"] else "unlabeled"] += 1
            stats["pending"] += int(entry["pending"])
            stats["reviewed"] += int(entry["reviewed"])
            stats["weather"] += int(entry["is_weather"])
            stats["invalid"] += int(entry["invalid"])
            if search_value and search_value not in name.casefold():
                continue
            if filter_name == "unlabeled" and entry["has_label"]:
                continue
            if filter_name == "labeled" and not entry["has_label"]:
                continue
            if filter_name == "pending" and not entry["pending"]:
                continue
            if filter_name == "reviewed" and not entry["reviewed"]:
                continue
            if filter_name == "weather" and not entry["is_weather"]:
                continue
            entries.append(entry)
        if sort_name == "boxes_asc":
            entries.sort(key=lambda item: (item["box_count"], item["path"].casefold()))
        elif sort_name == "boxes_desc":
            entries.sort(key=lambda item: (-item["box_count"], item["path"].casefold()))
        elif sort_name == "weather_first":
            entries.sort(
                key=lambda item: (
                    not item["is_weather"],
                    -item["box_count"],
                    item["path"].casefold(),
                )
            )
        else:
            entries.sort(key=lambda item: item["path"].casefold())
        return {
            "items": entries[offset : offset + limit],
            "offset": offset,
            "limit": limit,
            "filtered": len(entries),
            "stats": stats,
        }

    def move_image_to_trash(self, relative_name: str) -> dict[str, Any]:
        with self.lock:
            root, _, labels_dir = self.require_open()
            image_path = self.image_path(relative_name)
            label_path = self.label_path(relative_name)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            trash_root = root / WORK_DIRNAME / "trash" / stamp
            relative_path = Path(*PurePosixPath(relative_name).parts)
            trash_image = trash_root / "images" / relative_path
            trash_label = (trash_root / "labels" / relative_path).with_suffix(".txt")
            trash_image.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(image_path), str(trash_image))
            moved_label = False
            if label_path.is_file():
                trash_label.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(label_path), str(trash_label))
                moved_label = True
            images = self.metadata.setdefault("images", {})
            previous = images.get(relative_name, {})
            images[relative_name] = {
                **(previous if isinstance(previous, dict) else {}),
                "deleted_at": now_iso(),
                "original_image": str(image_path),
                "trash_image": str(trash_image),
                "trash_label": str(trash_label) if moved_label else None,
            }
            self._save_metadata_locked()
        return {
            "image": relative_name,
            "trash_dir": str(trash_root),
            "label_moved": moved_label,
        }

    def labels_payload(self, relative_name: str) -> dict[str, Any]:
        boxes, warnings = self.read_boxes(relative_name)
        entry = self.image_entry(relative_name)
        return {"boxes": [box.to_dict() for box in boxes], "warnings": warnings, "entry": entry}

    def write_boxes(
        self,
        relative_name: str,
        raw_boxes: list[dict[str, Any]],
        source: str,
        reviewed: bool,
        backup_dir: Path | None = None,
    ) -> dict[str, Any]:
        if not isinstance(raw_boxes, list):
            raise AppError("标注框数据必须是列表")
        with self.lock:
            known_classes = set(self.classes)
            boxes = [Box.from_payload(item, known_classes) for item in raw_boxes]
            label_path = self.label_path(relative_name)
            if backup_dir is not None and label_path.exists():
                relative_label = Path(*PurePosixPath(relative_name).parts).with_suffix(".txt")
                backup_path = backup_dir / relative_label
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(label_path, backup_path)
            content = "\n".join(box.to_line() for box in boxes)
            if content:
                content += "\n"
            atomic_write_text(label_path, content)
            images = self.metadata.setdefault("images", {})
            previous = images.get(relative_name, {})
            previous = previous if isinstance(previous, dict) else {}
            images[relative_name] = {
                **previous,
                "source": source,
                "reviewed": bool(reviewed),
                "updated_at": now_iso(),
            }
            self._save_metadata_locked()
        return self.labels_payload(relative_name)


class JobManager:
    def __init__(self, dataset: DatasetState) -> None:
        self.dataset = dataset
        self.lock = threading.RLock()
        self.cancel_event = threading.Event()
        self.cancel_action: Callable[[], None] | None = None
        self.thread: threading.Thread | None = None
        self.started_monotonic: float | None = None
        self.serial = 0
        self.state: dict[str, Any] = self._idle_state()

    @staticmethod
    def _idle_state() -> dict[str, Any]:
        return {
            "id": 0,
            "kind": None,
            "status": "idle",
            "progress": 0,
            "phase": None,
            "phase_progress": 0,
            "current": 0,
            "total": 0,
            "epoch": 0,
            "epochs": 0,
            "batch": 0,
            "batches": 0,
            "elapsed_seconds": 0,
            "eta_seconds": None,
            "metrics": {},
            "cancel_requested": False,
            "message": "空闲",
            "current_image": None,
            "error": None,
            "result": None,
            "started_at": None,
            "finished_at": None,
        }

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            snapshot = dict(self.state)
            if snapshot["status"] == "running" and self.started_monotonic is not None:
                snapshot["elapsed_seconds"] = round(time.monotonic() - self.started_monotonic)
            return snapshot

    def is_running(self) -> bool:
        with self.lock:
            return self.state["status"] == "running"

    def update(self, **values: Any) -> None:
        with self.lock:
            self.state.update(values)

    def start(self, kind: str, target: Callable[[], dict[str, Any] | None], message: str) -> dict[str, Any]:
        with self.lock:
            if self.state["status"] == "running":
                raise AppError("已有任务正在运行", HTTPStatus.CONFLICT)
            self.serial += 1
            self.cancel_event.clear()
            self.cancel_action = None
            self.started_monotonic = time.monotonic()
            self.state = self._idle_state()
            self.state.update(
                {
                    "id": self.serial,
                    "kind": kind,
                    "status": "running",
                    "message": message,
                    "started_at": now_iso(),
                }
            )

            def runner() -> None:
                try:
                    result = target() or {}
                    if self.cancel_event.is_set():
                        self.update(status="cancelled", message="任务已取消", result=result)
                    else:
                        self.update(status="completed", progress=100, message="任务已完成", result=result)
                except JobCancelled:
                    self.update(status="cancelled", message="任务已取消")
                except Exception as exc:  # noqa: BLE001 - task failures must reach the web UI
                    traceback.print_exc()
                    self.update(status="failed", message="任务失败", error=str(exc))
                finally:
                    with self.lock:
                        elapsed = round(time.monotonic() - self.started_monotonic) if self.started_monotonic else 0
                        self.cancel_action = None
                    self.update(elapsed_seconds=elapsed, eta_seconds=None, finished_at=now_iso())

            self.thread = threading.Thread(target=runner, name=f"{APP_NAME}-{kind}", daemon=True)
            self.thread.start()
            return dict(self.state)

    def set_cancel_action(self, action: Callable[[], None]) -> None:
        with self.lock:
            self.cancel_action = action
            cancel_requested = self.cancel_event.is_set()
        if cancel_requested:
            action()

    def cancel(self) -> dict[str, Any]:
        with self.lock:
            if self.state["status"] != "running":
                raise AppError("当前没有可取消的任务", HTTPStatus.CONFLICT)
            if self.state["cancel_requested"]:
                return self.snapshot()
            self.cancel_event.set()
            self.state.update(
                cancel_requested=True,
                message="正在停止：等待当前批次完成",
                eta_seconds=None,
            )
            cancel_action = self.cancel_action
        if cancel_action is not None:
            try:
                cancel_action()
            except Exception:  # noqa: BLE001 - cancellation should remain available even if a library hook fails
                traceback.print_exc()
        return self.snapshot()


class ModelService:
    def __init__(self, dataset: DatasetState, jobs: JobManager) -> None:
        self.dataset = dataset
        self.jobs = jobs
        self.model_lock = threading.RLock()
        self.cached_model_path: Path | None = None
        self.cached_model: Any = None

    @staticmethod
    def _ultralytics_yolo() -> Any:
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise AppError("缺少 ultralytics，请先执行 pip install -r requirements.txt") from exc
        return YOLO

    @staticmethod
    def validate_model_path(raw_path: Any) -> Path:
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise AppError("请选择 YOLO 权重文件")
        path = Path(raw_path).expanduser().resolve()
        if not path.is_file() or path.suffix.lower() not in MODEL_EXTENSIONS:
            raise AppError("YOLO 权重文件不存在或不是 .pt 文件")
        return path

    def latest_trained_model(self) -> Path | None:
        try:
            root, _, _ = self.dataset.require_open()
        except AppError:
            return None
        candidates: list[Path] = []
        runs_dir = root / "runs"
        if runs_dir.is_dir():
            for path in runs_dir.glob("*/weights/best.pt"):
                try:
                    if path.is_file() and path.stat().st_size > 0:
                        candidates.append(path.resolve())
                except OSError:
                    continue
        if not candidates:
            return None
        return max(candidates, key=lambda path: (path.stat().st_mtime, str(path)))

    @staticmethod
    def _entry_updated_timestamp(entry: dict[str, Any]) -> float | None:
        raw_value = entry.get("updated_at")
        if not isinstance(raw_value, str) or not raw_value:
            return None
        try:
            return datetime.fromisoformat(raw_value).timestamp()
        except ValueError:
            return None

    def _training_selection(self, model_path: Path, scope: str) -> dict[str, Any]:
        if scope not in TRAINING_SCOPES:
            raise AppError("训练数据范围无效")
        cutoff_timestamp = model_path.stat().st_mtime
        reviewed_names: list[str] = []
        incremental_names: list[str] = []
        weather_names: set[str] = set()
        skipped_pending = 0
        skipped_unreviewed = 0
        for name in self.dataset.all_image_names():
            if not self.dataset.label_path(name).is_file():
                continue
            entry = self.dataset.image_entry(name)
            if not entry["reviewed"]:
                skipped_pending += int(entry["pending"])
                skipped_unreviewed += 1
                continue
            reviewed_names.append(name)
            if entry["is_weather"]:
                weather_names.add(name)
            updated_timestamp = self._entry_updated_timestamp(entry)
            if updated_timestamp is not None and updated_timestamp > cutoff_timestamp:
                incremental_names.append(name)

        incremental_set = set(incremental_names)
        historical_names = [name for name in reviewed_names if name not in incremental_set]
        incremental_base_names = [name for name in incremental_names if name not in weather_names]
        historical_base_names = [name for name in historical_names if name not in weather_names]
        replay_names: list[str] = []
        if scope == "all_reviewed":
            selected_names = list(reviewed_names)
        elif scope == "incremental":
            selected_names = list(incremental_names)
        else:
            if incremental_base_names and historical_base_names:
                replay_count = min(
                    len(historical_base_names),
                    max(20, math.ceil(len(incremental_base_names) * 0.25)),
                )
                replay_names = random.Random(91).sample(historical_base_names, replay_count)

                represented_classes: set[int] = set()
                for name in [*incremental_names, *replay_names]:
                    boxes, warnings = self.dataset.read_boxes(name)
                    if not warnings:
                        represented_classes.update(box.cls_id for box in boxes)
                missing_classes = set(self.dataset.classes) - represented_classes
                if missing_classes:
                    replay_set = set(replay_names)
                    for name in historical_base_names:
                        if name in replay_set:
                            continue
                        boxes, warnings = self.dataset.read_boxes(name)
                        if warnings:
                            continue
                        found = {box.cls_id for box in boxes} & missing_classes
                        if found:
                            replay_names.append(name)
                            replay_set.add(name)
                            missing_classes -= found
                        if not missing_classes:
                            break
            selected_names = [*incremental_names, *replay_names]

        cutoff = datetime.fromtimestamp(cutoff_timestamp).astimezone().isoformat(timespec="seconds")
        return {
            "scope": scope,
            "model_path": str(model_path),
            "cutoff": cutoff,
            "reviewed_total": len(reviewed_names),
            "incremental_images": len(incremental_names),
            "historical_images": len(historical_names),
            "replay_images": len(replay_names),
            "weather_images": len(weather_names & set(selected_names)),
            "selected_images": len(selected_names),
            "skipped_pending": skipped_pending,
            "skipped_unreviewed": skipped_unreviewed,
            "selected_names": sorted(selected_names),
        }

    def training_plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        model_path = self.validate_model_path(payload.get("model_path"))
        scope = str(payload.get("training_scope", "incremental_replay"))
        plan = self._training_selection(model_path, scope)
        return {key: value for key, value in plan.items() if key != "selected_names"}

    def load_model(self, model_path: Path) -> Any:
        with self.model_lock:
            if self.cached_model is None or self.cached_model_path != model_path:
                self.cached_model = self._ultralytics_yolo()(str(model_path))
                self.cached_model_path = model_path
            return self.cached_model

    def _prediction_options(self, payload: dict[str, Any]) -> tuple[Path, float, list[int], Any]:
        model_path = self.validate_model_path(payload.get("model_path"))
        confidence = ensure_float(payload.get("confidence", 0.35), "置信度")
        if not 0.01 <= confidence <= 0.99:
            raise AppError("置信度必须在 0.01 到 0.99 之间")
        raw_classes = payload.get("class_ids")
        known = sorted(self.dataset.classes)
        if raw_classes is None or raw_classes == []:
            class_ids = known
        else:
            try:
                class_ids = sorted({int(item) for item in raw_classes})
            except (TypeError, ValueError) as exc:
                raise AppError("筛选类别格式无效") from exc
            if any(item not in known for item in class_ids):
                raise AppError("筛选类别不在当前类别配置中")
        device = payload.get("device")
        if device in (None, "", "auto"):
            device = None
        return model_path, confidence, class_ids, device

    @staticmethod
    def result_boxes(result: Any) -> list[dict[str, Any]]:
        image_height, image_width = result.orig_shape
        boxes: list[dict[str, Any]] = []
        for detection in result.boxes:
            cls_id = int(detection.cls.item())
            x1, y1, x2, y2 = (float(value) for value in detection.xyxy[0].tolist())
            x1 = min(max(x1, 0.0), float(image_width))
            x2 = min(max(x2, 0.0), float(image_width))
            y1 = min(max(y1, 0.0), float(image_height))
            y2 = min(max(y2, 0.0), float(image_height))
            if x2 <= x1 or y2 <= y1:
                continue
            boxes.append(
                {
                    "cls_id": cls_id,
                    "confidence": float(detection.conf.item()),
                    "xc": ((x1 + x2) / 2) / image_width,
                    "yc": ((y1 + y2) / 2) / image_height,
                    "w": (x2 - x1) / image_width,
                    "h": (y2 - y1) / image_height,
                }
            )
        return boxes

    @staticmethod
    def create_weather_variant(source: Path, target: Path, weather: str, seed: int) -> None:
        try:
            from PIL import Image, ImageDraw, ImageEnhance, ImageOps
        except ImportError as exc:
            raise AppError("天气增强需要 Pillow，请先执行 pip install -r requirements.txt") from exc

        randomizer = random.Random(seed)
        with Image.open(source) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")

        def channel_tint(value: Any, red: float, green: float, blue: float) -> Any:
            channels = value.split()
            factors = (red, green, blue)
            adjusted = [
                channel.point([min(255, round(level * factor)) for level in range(256)])
                for channel, factor in zip(channels, factors)
            ]
            return Image.merge("RGB", adjusted)

        if weather == "sunny":
            image = ImageEnhance.Brightness(image).enhance(randomizer.uniform(1.08, 1.22))
            image = ImageEnhance.Contrast(image).enhance(randomizer.uniform(1.04, 1.14))
            image = ImageEnhance.Color(image).enhance(randomizer.uniform(1.05, 1.18))
            image = channel_tint(image, 1.04, 1.01, 0.96)
        elif weather == "strong_sun":
            image = ImageEnhance.Brightness(image).enhance(randomizer.uniform(1.22, 1.42))
            image = ImageEnhance.Contrast(image).enhance(randomizer.uniform(1.14, 1.32))
            image = ImageEnhance.Color(image).enhance(randomizer.uniform(1.02, 1.12))
            image = channel_tint(image, 1.07, 1.02, 0.92)
        elif weather == "cloudy":
            image = ImageEnhance.Brightness(image).enhance(randomizer.uniform(0.88, 1.0))
            image = ImageEnhance.Contrast(image).enhance(randomizer.uniform(0.84, 0.96))
            image = ImageEnhance.Color(image).enhance(randomizer.uniform(0.72, 0.9))
            image = channel_tint(image, 0.96, 0.99, 1.05)
        elif weather == "overcast":
            image = ImageEnhance.Brightness(image).enhance(randomizer.uniform(0.68, 0.86))
            image = ImageEnhance.Contrast(image).enhance(randomizer.uniform(0.78, 0.92))
            image = ImageEnhance.Color(image).enhance(randomizer.uniform(0.5, 0.72))
            image = channel_tint(image, 0.91, 0.97, 1.08)
        elif weather == "fog":
            image = ImageEnhance.Contrast(image).enhance(randomizer.uniform(0.58, 0.78))
            fog_color = Image.new("RGB", image.size, (210, 218, 220))
            image = Image.blend(image, fog_color, randomizer.uniform(0.16, 0.34))
        elif weather == "rain":
            image = ImageEnhance.Brightness(image).enhance(randomizer.uniform(0.68, 0.88))
            image = ImageEnhance.Color(image).enhance(randomizer.uniform(0.62, 0.82))
            image = channel_tint(image, 0.91, 0.98, 1.09)
            overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)
            width, height = image.size
            streaks = max(80, min(420, width * height // 26000))
            for _ in range(streaks):
                x = randomizer.randrange(max(1, width))
                y = randomizer.randrange(max(1, height))
                length = randomizer.randint(max(7, height // 180), max(12, height // 75))
                slant = max(2, length // 4)
                draw.line(
                    (x, y, x + slant, y + length),
                    fill=(205, 220, 230, randomizer.randint(35, 85)),
                    width=max(1, width // 1800),
                )
            image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
        elif weather == "snow":
            image = ImageEnhance.Brightness(image).enhance(randomizer.uniform(1.02, 1.18))
            image = ImageEnhance.Color(image).enhance(randomizer.uniform(0.58, 0.8))
            image = channel_tint(image, 0.95, 1.0, 1.07)
            overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)
            width, height = image.size
            flakes = max(100, min(520, width * height // 22000))
            for _ in range(flakes):
                radius = randomizer.randint(1, max(2, width // 850))
                x = randomizer.randrange(max(1, width))
                y = randomizer.randrange(max(1, height))
                alpha = randomizer.randint(55, 145)
                draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(245, 248, 250, alpha))
            image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
        elif weather == "night":
            image = ImageEnhance.Brightness(image).enhance(randomizer.uniform(0.24, 0.46))
            image = ImageEnhance.Contrast(image).enhance(randomizer.uniform(1.05, 1.22))
            image = ImageEnhance.Color(image).enhance(randomizer.uniform(0.52, 0.78))
            image = channel_tint(image, 0.82, 0.93, 1.12)
            noise = Image.effect_noise(image.size, randomizer.uniform(5, 12)).convert("RGB")
            image = Image.blend(image, noise, randomizer.uniform(0.025, 0.055))
        else:
            raise AppError(f"不支持的天气增强类型: {weather}")

        target.parent.mkdir(parents=True, exist_ok=True)
        image.save(target, format="JPEG", quality=92, subsampling=0)

    @staticmethod
    def _weather_settings(payload: dict[str, Any]) -> tuple[list[str], float]:
        weather_ratio = ensure_float(payload.get("weather_ratio", 0.0), "天气增强比例")
        raw_weather = payload.get("weather_types", [])
        if not isinstance(raw_weather, list):
            raise AppError("天气增强类型格式无效")
        weather_types = list(dict.fromkeys(str(item) for item in raw_weather))
        if any(item not in WEATHER_TYPES for item in weather_types):
            raise AppError("包含不支持的天气增强类型")
        if not 0 <= weather_ratio <= 1:
            raise AppError("天气增强比例必须在 0% 到 100% 之间")
        if not weather_types:
            weather_ratio = 0.0
        return weather_types, weather_ratio

    def _weather_reviews_root(self) -> Path:
        root, _, _ = self.dataset.require_open()
        return root / WORK_DIRNAME / "weather_reviews"

    def _weather_review_dir(self, review_id: str) -> Path:
        if not re.fullmatch(r"weather_[0-9]{8}_[0-9]{6}_[0-9]{6}", review_id):
            raise AppError("天气素材审核编号无效")
        reviews_root = self._weather_reviews_root().resolve()
        review_dir = (reviews_root / review_id).resolve()
        if not is_relative_to(review_dir, reviews_root):
            raise AppError("天气素材审核路径无效")
        return review_dir

    def _load_weather_review(self, review_id: str) -> tuple[Path, dict[str, Any]]:
        review_dir = self._weather_review_dir(review_id)
        manifest_path = review_dir / "manifest.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise AppError("天气审核素材不存在，请重新生成", HTTPStatus.NOT_FOUND) from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise AppError(f"无法读取天气审核素材: {exc}") from exc
        if not isinstance(manifest, dict) or manifest.get("id") != review_id:
            raise AppError("天气审核素材清单无效")
        return review_dir, manifest

    def latest_weather_review_id(self) -> str | None:
        reviews_root = self._weather_reviews_root()
        if not reviews_root.is_dir():
            return None
        candidates = [path for path in reviews_root.glob("weather_*/manifest.json") if path.is_file()]
        if not candidates:
            return None
        latest = max(candidates, key=lambda path: path.stat().st_mtime_ns)
        return latest.parent.name

    def weather_review_payload(self, review_id: str | None) -> dict[str, Any]:
        clean_id = review_id.strip() if isinstance(review_id, str) else ""
        if not clean_id:
            clean_id = self.latest_weather_review_id() or ""
        if not clean_id:
            raise AppError("尚未生成天气审核素材", HTTPStatus.NOT_FOUND)
        review_dir, manifest = self._load_weather_review(clean_id)
        materialized_now = False
        if manifest.get("confirmed") and manifest.get("materialization_version") != 1:
            approved_for_migration = {str(item) for item in manifest.get("approved_ids", [])}
            materialized = self.dataset.sync_weather_review(
                review_dir,
                manifest,
                approved_for_migration,
            )
            manifest["materialization_version"] = 1
            manifest["materialized"] = materialized
            materialized_now = True
            atomic_write_text(
                review_dir / "manifest.json",
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            )
        approved = set(str(item) for item in manifest.get("approved_ids", []))
        items = []
        for raw_item in manifest.get("items", []):
            if not isinstance(raw_item, dict):
                continue
            item_id = str(raw_item.get("id", ""))
            items.append(
                {
                    "id": item_id,
                    "source_name": str(raw_item.get("source_name", "")),
                    "original_name": PurePosixPath(str(raw_item.get("source_name", ""))).name,
                    "weather": str(raw_item.get("weather", "")),
                    "boxes": raw_item.get("boxes", []),
                    "original_predictions": raw_item.get("original_predictions", []),
                    "weather_predictions": raw_item.get("weather_predictions", []),
                    "analysis": raw_item.get("analysis", {}),
                    "approved": item_id in approved,
                }
            )
        return {
            "id": clean_id,
            "analysis_version": manifest.get("analysis_version"),
            "materialization_version": manifest.get("materialization_version"),
            "created_at": manifest.get("created_at"),
            "model_path": manifest.get("model_path"),
            "training_scope": manifest.get("training_scope"),
            "validation_ratio": manifest.get("validation_ratio"),
            "weather_types": manifest.get("weather_types", []),
            "weather_ratio": manifest.get("weather_ratio"),
            "confirmed": bool(manifest.get("confirmed")),
            "approved_count": len(approved),
            "materialized_count": int(manifest.get("materialized", {}).get("total", 0)),
            "materialized": manifest.get("materialized", {}),
            "materialized_now": materialized_now,
            "total": len(items),
            "summary": manifest.get("summary", {}),
            "items": items,
        }

    def weather_review_image_path(self, review_id: str, item_id: str) -> Path:
        review_dir, manifest = self._load_weather_review(review_id)
        item = next(
            (value for value in manifest.get("items", []) if str(value.get("id", "")) == item_id),
            None,
        )
        if not isinstance(item, dict):
            raise AppError("天气素材不存在", HTTPStatus.NOT_FOUND)
        image_path = (review_dir / str(item.get("image_file", ""))).resolve()
        if not is_relative_to(image_path, review_dir.resolve()) or not image_path.is_file():
            raise AppError("天气素材文件不存在", HTTPStatus.NOT_FOUND)
        return image_path

    def save_weather_review(self, payload: dict[str, Any]) -> dict[str, Any]:
        review_id = str(payload.get("review_id", ""))
        review_dir, manifest = self._load_weather_review(review_id)
        raw_approved = payload.get("approved_ids")
        if not isinstance(raw_approved, list):
            raise AppError("天气素材审核结果格式无效")
        known_ids = {str(item.get("id", "")) for item in manifest.get("items", [])}
        approved_ids = list(dict.fromkeys(str(item) for item in raw_approved))
        if any(item not in known_ids for item in approved_ids):
            raise AppError("审核结果包含未知天气素材")
        manifest["approved_ids"] = approved_ids
        manifest["confirmed"] = True
        manifest["confirmed_at"] = now_iso()
        manifest["materialized"] = self.dataset.sync_weather_review(
            review_dir,
            manifest,
            set(approved_ids),
        )
        manifest["materialization_version"] = 1
        atomic_write_text(
            review_dir / "manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        )
        return self.weather_review_payload(review_id)

    @staticmethod
    def _normalized_iou(first: dict[str, Any], second: dict[str, Any]) -> float:
        first_x1 = float(first["xc"]) - float(first["w"]) / 2
        first_y1 = float(first["yc"]) - float(first["h"]) / 2
        first_x2 = float(first["xc"]) + float(first["w"]) / 2
        first_y2 = float(first["yc"]) + float(first["h"]) / 2
        second_x1 = float(second["xc"]) - float(second["w"]) / 2
        second_y1 = float(second["yc"]) - float(second["h"]) / 2
        second_x2 = float(second["xc"]) + float(second["w"]) / 2
        second_y2 = float(second["yc"]) + float(second["h"]) / 2
        intersection_width = max(0.0, min(first_x2, second_x2) - max(first_x1, second_x1))
        intersection_height = max(0.0, min(first_y2, second_y2) - max(first_y1, second_y1))
        intersection = intersection_width * intersection_height
        union = float(first["w"]) * float(first["h"]) + float(second["w"]) * float(second["h"]) - intersection
        return intersection / union if union > 0 else 0.0

    @classmethod
    def _weather_gap_analysis(
        cls,
        ground_truth: list[dict[str, Any]],
        original_predictions: list[dict[str, Any]],
        weather_predictions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        match_iou = 0.5
        match_confidence = 0.25
        false_positive_confidence = 0.35
        original_hits = 0
        weather_hits = 0
        misses = 0
        wrong_classes = 0
        confidence_drops: list[float] = []
        minimum_weather_iou = 1.0

        def best_prediction(
            target: dict[str, Any],
            predictions: list[dict[str, Any]],
            same_class: bool,
        ) -> tuple[dict[str, Any] | None, float]:
            candidates = [
                (prediction, cls._normalized_iou(target, prediction))
                for prediction in predictions
                if (int(prediction["cls_id"]) == int(target["cls_id"])) == same_class
            ]
            return max(candidates, key=lambda item: item[1]) if candidates else (None, 0.0)

        for target in ground_truth:
            original_match, original_iou = best_prediction(target, original_predictions, True)
            weather_match, weather_iou = best_prediction(target, weather_predictions, True)
            wrong_match, wrong_iou = best_prediction(target, weather_predictions, False)
            original_confidence = float(original_match.get("confidence", 0)) if original_match else 0.0
            weather_confidence = float(weather_match.get("confidence", 0)) if weather_match else 0.0
            if original_iou >= match_iou and original_confidence >= match_confidence:
                original_hits += 1
            if weather_iou >= match_iou and weather_confidence >= match_confidence:
                weather_hits += 1
            else:
                misses += 1
            minimum_weather_iou = min(minimum_weather_iou, weather_iou)
            if wrong_match and wrong_iou >= match_iou and float(wrong_match.get("confidence", 0)) >= match_confidence:
                wrong_classes += 1
            if original_iou >= match_iou and original_confidence >= match_confidence:
                confidence_drops.append(max(0.0, original_confidence - weather_confidence))

        false_positives = 0
        for prediction in weather_predictions:
            if float(prediction.get("confidence", 0)) < false_positive_confidence:
                continue
            maximum_overlap = max(
                (cls._normalized_iou(target, prediction) for target in ground_truth),
                default=0.0,
            )
            if maximum_overlap < 0.2:
                false_positives += 1

        max_confidence_drop = max(confidence_drops, default=0.0)
        reasons: list[str] = []
        if misses:
            reasons.append(f"漏检 {misses}")
        if wrong_classes:
            reasons.append(f"类别错误 {wrong_classes}")
        if max_confidence_drop >= 0.2:
            reasons.append(f"置信度下降 {max_confidence_drop:.2f}")
        if false_positives:
            reasons.append(f"新增误检 {false_positives}")
        if ground_truth and 0 < minimum_weather_iou < match_iou:
            reasons.append(f"框偏移 IoU {minimum_weather_iou:.2f}")
        score = (
            misses * 100
            + wrong_classes * 80
            + false_positives * 45
            + max(0.0, max_confidence_drop - 0.1) * 100
            + max(0.0, match_iou - minimum_weather_iou) * 60
        )
        return {
            "hard": bool(reasons),
            "score": round(score, 2),
            "reasons": reasons,
            "ground_truth": len(ground_truth),
            "original_hits": original_hits,
            "weather_hits": weather_hits,
            "misses": misses,
            "wrong_classes": wrong_classes,
            "false_positives": false_positives,
            "max_confidence_drop": round(max_confidence_drop, 4),
            "minimum_weather_iou": round(minimum_weather_iou if ground_truth else 1.0, 4),
        }

    @staticmethod
    def _weather_review_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "total": len(items),
            "hard": 0,
            "ground_truth": 0,
            "original_hits": 0,
            "weather_hits": 0,
            "false_positives": 0,
            "by_weather": {},
        }
        for item in items:
            analysis = item.get("analysis", {})
            summary["hard"] += int(bool(analysis.get("hard")))
            summary["ground_truth"] += int(analysis.get("ground_truth", 0))
            summary["original_hits"] += int(analysis.get("original_hits", 0))
            summary["weather_hits"] += int(analysis.get("weather_hits", 0))
            summary["false_positives"] += int(analysis.get("false_positives", 0))
            weather = str(item.get("weather", ""))
            weather_summary = summary["by_weather"].setdefault(
                weather,
                {"total": 0, "hard": 0, "ground_truth": 0, "weather_hits": 0},
            )
            weather_summary["total"] += 1
            weather_summary["hard"] += int(bool(analysis.get("hard")))
            weather_summary["ground_truth"] += int(analysis.get("ground_truth", 0))
            weather_summary["weather_hits"] += int(analysis.get("weather_hits", 0))
        ground_truth_count = summary["ground_truth"]
        summary["original_recall"] = round(summary["original_hits"] / ground_truth_count, 4) if ground_truth_count else None
        summary["weather_recall"] = round(summary["weather_hits"] / ground_truth_count, 4) if ground_truth_count else None
        return summary

    def start_weather_review(self, payload: dict[str, Any]) -> dict[str, Any]:
        model_path = self.validate_model_path(payload.get("model_path"))
        validation_ratio = ensure_float(payload.get("validation_ratio", 0.2), "验证集比例")
        if not 0.05 <= validation_ratio <= 0.5:
            raise AppError("验证集比例必须在 5% 到 50% 之间")
        weather_types, weather_ratio = self._weather_settings(payload)
        if not weather_types or weather_ratio <= 0:
            raise AppError("请至少选择一种天气并设置新增素材比例")
        device = payload.get("device")
        if device in (None, "", "auto"):
            device = None
        training_scope = str(payload.get("training_scope", "incremental_replay"))
        selection = self._training_selection(model_path, training_scope)
        annotated = [
            name
            for name in selection["selected_names"]
            if not self.dataset.image_entry(name)["is_weather"]
        ]
        if len(annotated) < 2:
            raise AppError("当前训练范围至少需要 2 张已复核图片")
        shuffled = list(annotated)
        random.Random(42).shuffle(shuffled)
        validation_count = max(1, min(len(shuffled) - 1, round(len(shuffled) * validation_ratio)))
        training_names = sorted(shuffled[validation_count:])
        weather_count = min(len(training_names), round(len(training_names) * weather_ratio))
        if weather_count == 0:
            raise AppError("当前比例没有产生天气审核素材")
        selected_names = random.Random(73).sample(training_names, weather_count)
        weather_order = list(weather_types)
        random.Random(74).shuffle(weather_order)
        weather_plan = [
            (name, weather_order[index % len(weather_order)])
            for index, name in enumerate(selected_names)
        ]
        review_id = f"weather_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{time.time_ns() % 1_000_000:06d}"
        reviews_root = self._weather_reviews_root()
        review_dir = self._weather_review_dir(review_id)

        def task() -> dict[str, Any]:
            reviews_root.mkdir(parents=True, exist_ok=True)
            review_dir.mkdir(parents=True, exist_ok=False)
            items: list[dict[str, Any]] = []
            try:
                self.jobs.update(
                    phase="weather_review",
                    phase_progress=0,
                    current=0,
                    total=len(weather_plan),
                    progress=0,
                    message="正在加载当前模型",
                )
                model = self.load_model(model_path)
                for index, (source_name, weather) in enumerate(weather_plan, start=1):
                    if self.jobs.cancel_event.is_set():
                        raise JobCancelled
                    item_id = f"weather_{index:05d}"
                    source_image = self.dataset.image_path(source_name)
                    source_label = self.dataset.label_path(source_name)
                    image_file = Path("images") / f"{item_id}.jpg"
                    label_file = Path("labels") / f"{item_id}.txt"
                    self.create_weather_variant(source_image, review_dir / image_file, weather, seed=9100 + index)
                    (review_dir / label_file).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_label, review_dir / label_file)
                    boxes, warnings = self.dataset.read_boxes(source_name)
                    if warnings:
                        raise AppError(f"{source_name}: {warnings[0]}")
                    self.jobs.update(
                        current=index - 1,
                        current_image=source_name,
                        message=f"检测原图与天气图 {index}/{len(weather_plan)}",
                    )
                    with self.model_lock:
                        results = model.predict(
                            source=[str(source_image), str(review_dir / image_file)],
                            conf=0.05,
                            device=device,
                            verbose=False,
                        )
                    original_predictions = self.result_boxes(results[0]) if len(results) > 0 else []
                    weather_predictions = self.result_boxes(results[1]) if len(results) > 1 else []
                    original_predictions = [
                        prediction for prediction in original_predictions if prediction["cls_id"] in self.dataset.classes
                    ]
                    weather_predictions = [
                        prediction for prediction in weather_predictions if prediction["cls_id"] in self.dataset.classes
                    ]
                    ground_truth = [box.to_dict() for box in boxes]
                    analysis = self._weather_gap_analysis(
                        ground_truth,
                        original_predictions,
                        weather_predictions,
                    )
                    items.append(
                        {
                            "id": item_id,
                            "source_name": source_name,
                            "weather": weather,
                            "image_file": image_file.as_posix(),
                            "label_file": label_file.as_posix(),
                            "boxes": ground_truth,
                            "original_predictions": original_predictions,
                            "weather_predictions": weather_predictions,
                            "analysis": analysis,
                        }
                    )
                    self.jobs.update(
                        phase="weather_review",
                        phase_progress=round(index / len(weather_plan) * 100, 1),
                        current=index,
                        total=len(weather_plan),
                        progress=round(index / len(weather_plan) * 100, 1),
                        current_image=source_name,
                        message=f"生成天气审核素材 {index}/{len(weather_plan)}",
                    )
                items.sort(
                    key=lambda item: (
                        not bool(item.get("analysis", {}).get("hard")),
                        -float(item.get("analysis", {}).get("score", 0)),
                        str(item.get("id", "")),
                    )
                )
                summary = self._weather_review_summary(items)
                manifest = {
                    "id": review_id,
                    "analysis_version": 1,
                    "created_at": now_iso(),
                    "dataset_root": str(self.dataset.require_open()[0]),
                    "model_path": str(model_path),
                    "training_scope": training_scope,
                    "validation_ratio": validation_ratio,
                    "weather_types": weather_types,
                    "weather_ratio": weather_ratio,
                    "device": device,
                    "inference_confidence": 0.05,
                    "training_names": training_names,
                    "approved_ids": [item["id"] for item in items if item["analysis"]["hard"]],
                    "confirmed": False,
                    "summary": summary,
                    "items": items,
                }
                atomic_write_text(
                    review_dir / "manifest.json",
                    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                )
                for old_review in reviews_root.iterdir():
                    if old_review.is_dir() and old_review != review_dir:
                        shutil.rmtree(old_review, ignore_errors=True)
                return {
                    "review_id": review_id,
                    "generated": len(items),
                    "hard": summary["hard"],
                    "original_recall": summary["original_recall"],
                    "weather_recall": summary["weather_recall"],
                }
            except Exception:
                shutil.rmtree(review_dir, ignore_errors=True)
                raise

        return self.jobs.start("weather_review", task, "准备天气审核素材")

    def predict_one(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.jobs.is_running():
            raise AppError("后台任务运行期间不能执行单张预标注", HTTPStatus.CONFLICT)
        relative_name = str(payload.get("image", ""))
        image_path = self.dataset.image_path(relative_name)
        model_path, confidence, class_ids, device = self._prediction_options(payload)
        model = self.load_model(model_path)
        with self.model_lock:
            results = model.predict(
                source=str(image_path),
                conf=confidence,
                classes=class_ids,
                device=device,
                verbose=False,
            )
        if not results:
            return {"boxes": []}
        boxes = [item for item in self.result_boxes(results[0]) if item["cls_id"] in self.dataset.classes]
        return {"boxes": boxes, "model_path": str(model_path)}

    def start_bulk_prediction(self, payload: dict[str, Any]) -> dict[str, Any]:
        model_path, confidence, class_ids, device = self._prediction_options(payload)
        scope = str(payload.get("scope", "unlabeled"))
        overwrite = str(payload.get("overwrite", "skip_existing"))
        if scope not in {"unlabeled", "pending", "all"}:
            raise AppError("批量范围无效")
        if overwrite not in {"skip_existing", "replace_predictions", "replace_all"}:
            raise AppError("标签覆盖策略无效")

        names = self.dataset.all_image_names()
        targets: list[str] = []
        for name in names:
            entry = self.dataset.image_entry(name)
            if scope == "unlabeled" and entry["has_label"]:
                continue
            if scope == "pending" and not entry["pending"]:
                continue
            if entry["has_label"]:
                if overwrite == "skip_existing":
                    continue
                if overwrite == "replace_predictions" and entry["source"] != "prediction":
                    continue
            targets.append(name)
        if not targets:
            raise AppError("当前范围内没有可自动标注的图片")

        root, _, _ = self.dataset.require_open()
        backup_dir: Path | None = None
        if overwrite != "skip_existing":
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_dir = root / WORK_DIRNAME / "backups" / stamp / "labels"

        def task() -> dict[str, Any]:
            model = self.load_model(model_path)
            self.jobs.update(total=len(targets), message="正在加载模型")
            predicted = 0
            total_boxes = 0
            for index, name in enumerate(targets, start=1):
                if self.jobs.cancel_event.is_set():
                    break
                image_path = self.dataset.image_path(name)
                self.jobs.update(
                    current=index - 1,
                    progress=int((index - 1) / len(targets) * 100),
                    current_image=name,
                    message=f"正在处理 {PurePosixPath(name).name}",
                )
                with self.model_lock:
                    results = model.predict(
                        source=str(image_path),
                        conf=confidence,
                        classes=class_ids,
                        device=device,
                        verbose=False,
                    )
                raw_boxes = self.result_boxes(results[0]) if results else []
                raw_boxes = [item for item in raw_boxes if item["cls_id"] in self.dataset.classes]
                self.dataset.write_boxes(
                    name,
                    raw_boxes,
                    source="prediction",
                    reviewed=False,
                    backup_dir=backup_dir,
                )
                predicted += 1
                total_boxes += len(raw_boxes)
                self.jobs.update(current=index, progress=int(index / len(targets) * 100))
            return {
                "processed": predicted,
                "boxes": total_boxes,
                "backup_dir": str(backup_dir) if backup_dir and backup_dir.exists() else None,
                "model_path": str(model_path),
            }

        return self.jobs.start("prediction", task, "准备批量自动标注")

    def start_training(self, payload: dict[str, Any]) -> dict[str, Any]:
        if yaml is None:
            raise AppError("缺少 PyYAML，请先执行 pip install -r requirements.txt")
        model_path = self.validate_model_path(payload.get("model_path"))
        try:
            epochs = int(payload.get("epochs", 15))
            image_size = int(payload.get("image_size", 640))
            batch = int(payload.get("batch", 16))
        except (TypeError, ValueError) as exc:
            raise AppError("训练参数必须是整数") from exc
        validation_ratio = ensure_float(payload.get("validation_ratio", 0.2), "验证集比例")
        weather_types, weather_ratio = self._weather_settings(payload)
        weather_review_id = str(payload.get("weather_review_id", "")).strip()
        if not 1 <= epochs <= 500:
            raise AppError("训练轮数必须在 1 到 500 之间")
        if not 32 <= image_size <= 2048 or image_size % 32 != 0:
            raise AppError("图片尺寸必须是 32 到 2048 之间的 32 倍数")
        if not 1 <= batch <= 256:
            raise AppError("Batch 必须在 1 到 256 之间")
        if not 0.05 <= validation_ratio <= 0.5:
            raise AppError("验证集比例必须在 5% 到 50% 之间")
        device = payload.get("device")
        if device in (None, "", "auto"):
            device = None

        root, _, _ = self.dataset.require_open()
        training_scope = str(payload.get("training_scope", "incremental_replay"))
        selection = self._training_selection(model_path, training_scope)
        annotated = list(selection["selected_names"])
        base_annotated = [name for name in annotated if not self.dataset.image_entry(name)["is_weather"]]
        weather_training_names = [name for name in annotated if self.dataset.image_entry(name)["is_weather"]]
        class_box_count = {class_id: 0 for class_id in self.dataset.classes}
        problems: list[str] = []
        for name in annotated:
            boxes, warnings = self.dataset.read_boxes(name)
            if warnings:
                problems.append(f"{name}: {warnings[0]}")
            for box in boxes:
                if box.cls_id not in class_box_count:
                    problems.append(f"{name}: 类别 ID {box.cls_id} 不在当前配置中")
                else:
                    class_box_count[box.cls_id] += 1
        if problems:
            preview = "；".join(problems[:5])
            raise AppError(f"训练前请修正无效标签：{preview}")
        if len(base_annotated) < 2:
            if training_scope.startswith("incremental"):
                raise AppError(
                    f"所选模型生成后只有 {len(base_annotated)} 张新增非天气已复核图片，至少需要 2 张"
                )
            raise AppError("至少需要 2 张非天气已复核图片才能划分训练集和验证集")
        if sum(class_box_count.values()) == 0:
            raise AppError("本次训练图片中没有任何标注框")
        missing_classes = [self.dataset.classes[key] for key, count in class_box_count.items() if count == 0]
        if missing_classes and training_scope == "all_reviewed":
            raise AppError(f"以下类别没有任何标注框：{', '.join(missing_classes)}")

        shuffled = list(base_annotated)
        random.Random(42).shuffle(shuffled)
        validation_count = max(1, min(len(shuffled) - 1, round(len(shuffled) * validation_ratio)))
        validation_names = sorted(shuffled[:validation_count])
        base_training_names = sorted(shuffled[validation_count:])
        training_names = sorted([*base_training_names, *weather_training_names])
        work_dir = root / WORK_DIRNAME
        split_dir = work_dir / "splits"
        split_dir.mkdir(parents=True, exist_ok=True)
        training_manifest = split_dir / "train.txt"
        validation_manifest = split_dir / "val.txt"
        atomic_write_text(
            training_manifest,
            "\n".join(str(self.dataset.image_path(name)) for name in training_names) + "\n",
        )
        atomic_write_text(
            validation_manifest,
            "\n".join(str(self.dataset.image_path(name)) for name in validation_names) + "\n",
        )
        dataset_view = work_dir / "dataset_view"
        prepared_images = 0
        prepare_total = len(training_names) + len(validation_names)

        def materialize_split(split_name: str, split_images: list[str]) -> None:
            nonlocal prepared_images
            for relative_name in split_images:
                if self.jobs.cancel_event.is_set():
                    raise JobCancelled
                source_image = self.dataset.image_path(relative_name)
                source_label = self.dataset.label_path(relative_name)
                relative_path = Path(*PurePosixPath(relative_name).parts)
                target_image = dataset_view / "images" / split_name / relative_path
                target_label = (dataset_view / "labels" / split_name / relative_path).with_suffix(".txt")
                target_image.parent.mkdir(parents=True, exist_ok=True)
                target_label.parent.mkdir(parents=True, exist_ok=True)
                try:
                    os.link(source_image, target_image)
                except OSError:
                    try:
                        target_image.symlink_to(source_image)
                    except OSError:
                        shutil.copy2(source_image, target_image)
                shutil.copy2(source_label, target_label)
                prepared_images += 1
                phase_progress = prepared_images / prepare_total * 100
                self.jobs.update(
                    phase="preparing",
                    phase_progress=round(phase_progress, 1),
                    current=prepared_images,
                    total=prepare_total,
                    progress=round(phase_progress * 0.12, 1),
                    message=f"准备训练数据 {prepared_images}/{prepare_total}",
                )

        if weather_ratio > 0:
            if not weather_review_id:
                raise AppError("请先生成并审核天气增强素材")
            _, weather_review = self._load_weather_review(weather_review_id)
            context_matches = (
                weather_review.get("materialization_version") == 1
                and weather_review.get("model_path") == str(model_path)
                and weather_review.get("training_scope") == training_scope
                and abs(float(weather_review.get("validation_ratio", -1)) - validation_ratio) < 1e-9
                and list(weather_review.get("weather_types", [])) == weather_types
                and abs(float(weather_review.get("weather_ratio", -1)) - weather_ratio) < 1e-9
                and list(weather_review.get("training_names", [])) == base_training_names
            )
            if not context_matches:
                raise AppError("训练参数或训练数据已变化，请重新生成天气审核素材", HTTPStatus.CONFLICT)
            if not weather_review.get("confirmed"):
                raise AppError("请先确认天气素材审核结果", HTTPStatus.CONFLICT)
        yaml_path = root / "cc_training_materials.yaml"
        yaml_payload = {
            "path": str(dataset_view),
            "train": "images/train",
            "val": "images/val",
            "names": dict(self.dataset.classes),
        }
        atomic_write_text(yaml_path, yaml.safe_dump(yaml_payload, allow_unicode=True, sort_keys=False))
        run_name = f"cc_training_materials_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        def task() -> dict[str, Any]:
            self.jobs.update(
                phase="preparing",
                phase_progress=0,
                current=0,
                total=prepare_total,
                epoch=0,
                epochs=epochs,
                batch=0,
                batches=0,
                metrics={},
                message="正在准备训练数据",
            )
            if dataset_view.exists():
                shutil.rmtree(dataset_view)
            materialize_split("train", training_names)
            materialize_split("val", validation_names)
            generated_weather = len(weather_training_names)
            if self.jobs.cancel_event.is_set():
                raise JobCancelled
            self.jobs.update(
                phase="initializing",
                phase_progress=0,
                current=0,
                total=epochs,
                progress=12,
                message="正在加载模型并初始化训练器",
            )
            YOLO = self._ultralytics_yolo()
            model = YOLO(str(model_path))
            self.cached_model = None
            self.cached_model_path = None

            batch_state = {"current": 0, "total": 0}
            training_started = time.monotonic()

            def cancel_if_requested(target: Any) -> None:
                if self.jobs.cancel_event.is_set():
                    if hasattr(target, "stop"):
                        target.stop = True
                    self.jobs.update(
                        phase="cancelling",
                        message="正在停止：当前批次已完成",
                        eta_seconds=None,
                        cancel_requested=True,
                    )
                    raise JobCancelled

            def trainer_metrics(trainer: Any, include_validation: bool = False) -> dict[str, float]:
                metrics: dict[str, float] = {}
                loss_items = getattr(trainer, "tloss", None)
                if loss_items is not None:
                    try:
                        raw_losses = trainer.label_loss_items(loss_items)
                        metrics.update({key.removeprefix("train/"): float(value) for key, value in raw_losses.items()})
                    except (AttributeError, TypeError, ValueError):
                        pass
                if include_validation:
                    aliases = {
                        "metrics/precision(B)": "precision",
                        "metrics/recall(B)": "recall",
                        "metrics/mAP50(B)": "map50",
                        "metrics/mAP50-95(B)": "map50_95",
                    }
                    for key, alias in aliases.items():
                        try:
                            metrics[alias] = float(trainer.metrics[key])
                        except (KeyError, TypeError, ValueError):
                            continue
                return {key: round(value, 5) for key, value in metrics.items() if math.isfinite(value)}

            def pretrain_ready(trainer: Any) -> None:
                cancel_if_requested(trainer)
                batch_state["total"] = max(1, len(trainer.train_loader))
                self.jobs.update(
                    phase="initializing",
                    phase_progress=100,
                    batches=batch_state["total"],
                    progress=14,
                    message=f"训练器初始化完成，每轮 {batch_state['total']} 个批次",
                )

            def epoch_started(trainer: Any) -> None:
                cancel_if_requested(trainer)
                batch_state["current"] = 0
                batch_state["total"] = max(1, len(trainer.train_loader))
                current_epoch = int(trainer.epoch) + 1
                self.jobs.update(
                    phase="training",
                    phase_progress=0,
                    current=current_epoch,
                    total=epochs,
                    epoch=current_epoch,
                    epochs=epochs,
                    batch=0,
                    batches=batch_state["total"],
                    message=f"开始训练第 {current_epoch}/{epochs} 轮",
                )

            def batch_finished(trainer: Any) -> None:
                cancel_if_requested(trainer)
                batch_state["current"] += 1
                current_epoch = int(trainer.epoch) + 1
                total_batches = batch_state["total"] or max(1, len(trainer.train_loader))
                current_batch = min(batch_state["current"], total_batches)
                completed_batches = (current_epoch - 1) * total_batches + current_batch
                all_batches = max(1, epochs * total_batches)
                training_ratio = min(1.0, completed_batches / all_batches)
                elapsed = max(0.001, time.monotonic() - training_started)
                eta = elapsed * (1 - training_ratio) / training_ratio if training_ratio > 0 else None
                self.jobs.update(
                    phase="training",
                    phase_progress=round(current_batch / total_batches * 100, 1),
                    current=current_epoch,
                    total=epochs,
                    epoch=current_epoch,
                    epochs=epochs,
                    batch=current_batch,
                    batches=total_batches,
                    progress=round(min(98, 14 + training_ratio * 84), 1),
                    eta_seconds=round(eta) if eta is not None else None,
                    metrics=trainer_metrics(trainer),
                    message=f"训练第 {current_epoch}/{epochs} 轮，批次 {current_batch}/{total_batches}",
                )

            def epoch_finished(trainer: Any) -> None:
                cancel_if_requested(trainer)
                current_epoch = int(trainer.epoch) + 1
                self.jobs.update(
                    phase="validating",
                    phase_progress=0,
                    epoch=current_epoch,
                    current=current_epoch,
                    message=f"正在验证第 {current_epoch}/{epochs} 轮",
                )

            def validation_batch(validator: Any) -> None:
                cancel_if_requested(validator)

            def fit_epoch_finished(trainer: Any) -> None:
                cancel_if_requested(trainer)
                current_epoch = int(trainer.epoch) + 1
                self.jobs.update(
                    phase="training",
                    phase_progress=100,
                    current=current_epoch,
                    total=epochs,
                    epoch=current_epoch,
                    progress=round(min(98, 14 + current_epoch / epochs * 84), 1),
                    metrics=trainer_metrics(trainer, include_validation=True),
                    message=f"第 {current_epoch}/{epochs} 轮完成",
                )

            def model_saving(trainer: Any) -> None:
                cancel_if_requested(trainer)
                self.jobs.update(phase="saving", message="正在保存本轮模型权重")

            def training_finished(trainer: Any) -> None:
                cancel_if_requested(trainer)
                self.jobs.update(phase="finishing", phase_progress=100, progress=99, message="正在整理训练结果")

            def request_trainer_stop() -> None:
                trainer = getattr(model, "trainer", None)
                if trainer is not None:
                    trainer.stop = True

            model.add_callback("on_pretrain_routine_end", pretrain_ready)
            model.add_callback("on_train_epoch_start", epoch_started)
            model.add_callback("on_train_batch_end", batch_finished)
            model.add_callback("on_train_epoch_end", epoch_finished)
            model.add_callback("on_val_batch_end", validation_batch)
            model.add_callback("on_fit_epoch_end", fit_epoch_finished)
            model.add_callback("on_model_save", model_saving)
            model.add_callback("on_train_end", training_finished)
            self.jobs.set_cancel_action(request_trainer_stop)
            cancel_if_requested(model)
            model.train(
                data=str(yaml_path),
                epochs=epochs,
                imgsz=image_size,
                batch=batch,
                device=device,
                workers=0,
                patience=max(12, min(50, epochs // 4)),
                project=str(root / "runs"),
                name=run_name,
                exist_ok=False,
                verbose=True,
            )
            save_dir = Path(model.trainer.save_dir).resolve()
            best_path = save_dir / "weights" / "best.pt"
            return {
                "run_dir": str(save_dir),
                "best_model": str(best_path) if best_path.exists() else None,
                "train_images": len(training_names),
                "validation_images": len(validation_names),
                "weather_images": generated_weather,
                "weather_types": weather_types,
                "skipped_pending": selection["skipped_pending"],
                "yaml_path": str(yaml_path),
                "training_scope": training_scope,
                "training_cutoff": selection["cutoff"],
                "incremental_images": selection["incremental_images"],
                "replay_images": selection["replay_images"],
                "selected_images": selection["selected_images"],
            }

        return self.jobs.start("training", task, "准备模型训练")

    def start_dataset_export(self, payload: dict[str, Any]) -> dict[str, Any]:
        if yaml is None:
            raise AppError("缺少 PyYAML，无法生成 dataset.yaml")
        root, sources, _ = self.dataset.require_open()
        default_output = root.parent / "yolo_dataset_9_1"
        raw_output = payload.get("output_path")
        output = Path(str(raw_output)).expanduser().resolve() if raw_output else default_output.resolve()
        if output == Path("/") or output == root or is_relative_to(output, root) or is_relative_to(root, output):
            raise AppError("导出目录不能与数据集根目录重叠")
        for source in sources:
            source_root = Path(source["path"]).resolve()
            if output == source_root or is_relative_to(output, source_root) or is_relative_to(source_root, output):
                raise AppError("导出目录不能与图片来源目录重叠")
        if output.exists() and not output.is_dir():
            raise AppError("导出路径已被文件占用")
        if output.exists() and not bool(payload.get("overwrite", False)):
            raise AppError("导出目录已存在，请确认覆盖后重试", HTTPStatus.CONFLICT)

        eligible: list[str] = []
        skipped_unlabeled: list[str] = []
        weather_names: set[str] = set()
        for name in self.dataset.all_image_names():
            label_path = self.dataset.label_path(name)
            if not label_path.is_file():
                skipped_unlabeled.append(name)
                continue
            eligible.append(name)
            entry = self.dataset.image_entry(name)
            if entry["is_weather"]:
                weather_names.add(name)
        if len(eligible) < 10:
            raise AppError("至少需要 10 张带标签图片才能按 9:1 导出")

        shuffled = sorted(eligible)
        random.Random(42).shuffle(shuffled)
        validation_target = max(1, round(len(eligible) * 0.1))
        validation_names = sorted(shuffled[:validation_target])
        validation_set = set(validation_names)
        training_names = sorted(name for name in eligible if name not in validation_set)
        export_indexes = {name: index for index, name in enumerate(sorted(eligible), start=1)}

        def export_filename(name: str) -> str:
            source_name = PurePosixPath(name).name
            safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(source_name).stem).strip("._-") or "image"
            extension = PurePosixPath(name).suffix.lower()
            return f"{export_indexes[name]:06d}__{safe_stem[:120]}{extension}"

        output.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        stage = output.parent / f".{output.name}.building_{stamp}"
        backup = output.parent / f".{output.name}.previous_{stamp}"

        def task() -> dict[str, Any]:
            copied = 0
            total = len(eligible)

            def copy_split(split: str, names: list[str]) -> None:
                nonlocal copied
                for name in names:
                    if self.jobs.cancel_event.is_set():
                        raise JobCancelled
                    source_image = self.dataset.image_path(name)
                    source_label = self.dataset.label_path(name)
                    export_name = export_filename(name)
                    target_image = stage / "images" / split / export_name
                    target_label = stage / "labels" / split / Path(export_name).with_suffix(".txt")
                    target_image.parent.mkdir(parents=True, exist_ok=True)
                    target_label.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        os.link(source_image, target_image)
                    except OSError:
                        shutil.copy2(source_image, target_image)
                    shutil.copy2(source_label, target_label)
                    copied += 1
                    progress = copied / total * 100
                    self.jobs.update(
                        phase="exporting",
                        phase_progress=round(progress, 1),
                        current=copied,
                        total=total,
                        progress=round(progress, 1),
                        current_image=name,
                        message=f"导出 {split} 图片 {copied}/{total}",
                    )

            try:
                stage.mkdir(parents=True, exist_ok=False)
                copy_split("train", training_names)
                copy_split("val", validation_names)
                yaml_payload = {
                    "path": str(output),
                    "train": "images/train",
                    "val": "images/val",
                    "names": dict(self.dataset.classes),
                }
                atomic_write_text(
                    stage / "dataset.yaml",
                    yaml.safe_dump(yaml_payload, allow_unicode=True, sort_keys=False),
                )
                summary = {
                    "created_at": now_iso(),
                    "source_dataset": str(root),
                    "output": str(output),
                    "ratio": "9:1",
                    "layout": "flat",
                    "seed": 42,
                    "total": len(eligible),
                    "train": len(training_names),
                    "val": len(validation_names),
                    "weather_train": len(weather_names - validation_set),
                    "weather_val": len(weather_names & validation_set),
                    "skipped_unlabeled": len(skipped_unlabeled),
                }
                atomic_write_text(
                    stage / "split_summary.json",
                    json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                )
                mapping = [
                    {
                        "source": name,
                        "split": "val" if name in validation_set else "train",
                        "export_name": export_filename(name),
                    }
                    for name in sorted(eligible)
                ]
                atomic_write_text(
                    stage / "file_mapping.json",
                    json.dumps(mapping, ensure_ascii=False, indent=2) + "\n",
                )

                replaced = output.exists()
                if replaced:
                    output.rename(backup)
                try:
                    stage.rename(output)
                except Exception:
                    if backup.exists() and not output.exists():
                        backup.rename(output)
                    raise
                if backup.exists():
                    shutil.rmtree(backup, ignore_errors=True)
                return {**summary, "replaced": replaced, "dataset_yaml": str(output / "dataset.yaml")}
            except Exception:
                if stage.exists():
                    shutil.rmtree(stage, ignore_errors=True)
                raise

        return self.jobs.start("export", task, "准备按 9:1 导出数据集")


class VideoService:
    def __init__(self, jobs: JobManager) -> None:
        self.jobs = jobs

    @staticmethod
    def _interval(payload: dict[str, Any]) -> int:
        try:
            interval = int(payload.get("interval_ms", 250))
        except (TypeError, ValueError) as exc:
            raise AppError("抽帧间隔必须是整数毫秒") from exc
        if not 10 <= interval <= 60_000:
            raise AppError("抽帧间隔必须在 10 到 60000 毫秒之间")
        return interval

    @staticmethod
    def _output_dir(video_path: Path) -> Path:
        safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", video_path.stem).strip("._-") or "video"
        base = video_path.parent / f"{safe_stem}_frames"
        if not base.exists():
            return base
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        candidate = video_path.parent / f"{safe_stem}_frames_{stamp}"
        number = 2
        while candidate.exists():
            candidate = video_path.parent / f"{safe_stem}_frames_{stamp}_{number}"
            number += 1
        return candidate

    def start(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.jobs.is_running():
            raise AppError("已有后台任务正在运行", HTTPStatus.CONFLICT)
        raw_path = payload.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise AppError("视频文件不能为空")
        video_path = Path(raw_path).expanduser().resolve()
        if not video_path.is_file() or video_path.suffix.lower() not in VIDEO_EXTENSIONS:
            raise AppError("所选文件不存在或不是支持的视频格式")
        interval_ms = self._interval(payload)
        output_dir = self._output_dir(video_path)

        def task() -> dict[str, Any]:
            try:
                import cv2
            except ImportError as exc:
                raise AppError("缺少 OpenCV，无法抽取视频帧，请先安装 opencv-python-headless") from exc

            capture = cv2.VideoCapture(str(video_path))
            if not capture.isOpened():
                capture.release()
                raise AppError("无法打开视频文件，请检查格式或文件权限")
            saved = 0
            frame_index = 0
            next_capture_ms = 0.0
            fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
            total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            try:
                output_dir.mkdir(parents=True, exist_ok=False)
                self.jobs.update(
                    phase="video_extract",
                    phase_progress=0,
                    current=0,
                    total=total_frames,
                    progress=0,
                    current_image=str(video_path),
                    message=f"正在抽取视频帧（每 {interval_ms} ms 一帧）",
                )
                while True:
                    if self.jobs.cancel_event.is_set():
                        raise JobCancelled
                    ok, frame = capture.read()
                    if not ok:
                        break
                    frame_index += 1
                    if fps > 0:
                        timestamp_ms = (frame_index - 1) / fps * 1000.0
                    else:
                        timestamp_ms = float(frame_index - 1) * interval_ms
                    if timestamp_ms + 1e-6 >= next_capture_ms:
                        output_name = f"{video_path.stem}_{frame_index:08d}_{int(round(timestamp_ms)):010d}ms.png"
                        output_path = output_dir / output_name
                        written = cv2.imwrite(
                            str(output_path),
                            frame,
                            [cv2.IMWRITE_PNG_COMPRESSION, 3],
                        )
                        if not written:
                            raise AppError(f"PNG 写入失败: {output_path}")
                        saved += 1
                        while next_capture_ms <= timestamp_ms + 1e-6:
                            next_capture_ms += interval_ms
                    if total_frames > 0:
                        progress = min(99.0, frame_index / total_frames * 100)
                        phase_progress = min(100.0, progress)
                    else:
                        progress = 0
                        phase_progress = 0
                    self.jobs.update(
                        current=frame_index,
                        phase_progress=round(phase_progress, 1),
                        progress=round(progress, 1),
                        message=f"抽取视频帧 {frame_index}/{total_frames or '?'}，已生成 {saved} 张",
                    )
            except Exception:
                shutil.rmtree(output_dir, ignore_errors=True)
                raise
            finally:
                capture.release()
            if saved == 0:
                shutil.rmtree(output_dir, ignore_errors=True)
                raise AppError("视频中没有成功生成图片帧")
            return {
                "video_path": str(video_path),
                "output_dir": str(output_dir),
                "interval_ms": interval_ms,
                "frames": saved,
                "fps": round(fps, 3) if fps > 0 else None,
            }

        return self.jobs.start("video_extract", task, "准备抽取视频 PNG 帧")


class SourceDedupService:
    def __init__(self, dataset: DatasetState, jobs: JobManager) -> None:
        self.dataset = dataset
        self.jobs = jobs
        self.lock = threading.Lock()
        self.process_lock = threading.RLock()
        self.process: subprocess.Popen[str] | None = None
        self.cancel_event = threading.Event()

    def is_running(self) -> bool:
        return self.lock.locked()

    @staticmethod
    def _threshold(payload: dict[str, Any]) -> int:
        try:
            threshold = int(payload.get("threshold", 90))
        except (TypeError, ValueError) as exc:
            raise AppError("相似度阈值必须是 1 到 100 的整数") from exc
        if not 1 <= threshold <= 100:
            raise AppError("相似度阈值必须是 1 到 100 的整数")
        return threshold

    def _candidate(self, raw_path: Any) -> tuple[Path, int]:
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise AppError("图片目录不能为空")
        path = Path(raw_path).expanduser().resolve()
        if not path.is_dir():
            raise AppError("图片目录不存在")
        _, sources, _ = self.dataset.require_open()
        for item in sources:
            existing = Path(item["path"]).resolve()
            if existing == path:
                raise AppError("该图片目录已经添加")
            if is_relative_to(existing, path) or is_relative_to(path, existing):
                raise AppError("该图片目录与已添加目录重叠，禁止扫描或删除", HTTPStatus.CONFLICT)
        image_count = sum(
            1
            for candidate in path.rglob("*")
            if candidate.is_file() and candidate.suffix.lower() in DEDUP_IMAGE_EXTENSIONS
        )
        if image_count == 0:
            raise AppError("所选目录中没有 JPG、JPEG 或 PNG 图片")
        return path, image_count

    @staticmethod
    def _output_paths(path: Path, threshold: int) -> tuple[Path, Path, Path]:
        prefix = f"{path.name}_dupeguru_{threshold}_similarity"
        return (
            path.parent / f"{prefix}_summary.json",
            path.parent / f"{prefix}_delete_manifest.jsonl",
            path.parent / f"{prefix}_apply_summary.json",
        )

    @staticmethod
    def _read_json(path: Path, label: str) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AppError(f"无法读取{label}: {exc}") from exc
        if not isinstance(value, dict):
            raise AppError(f"{label}格式无效")
        return value

    def _run(self, command: str, path: Path, threshold: int) -> None:
        if not DEDUP_SCRIPT.is_file():
            raise AppError(f"相似图片去重脚本不存在: {DEDUP_SCRIPT}", HTTPStatus.INTERNAL_SERVER_ERROR)
        arguments = [
            sys.executable,
            str(DEDUP_SCRIPT),
            command,
            "--root",
            str(path),
            "--threshold",
            str(threshold),
        ]
        if command == "scan":
            arguments.extend(["--workers", str(min(8, os.cpu_count() or 1))])
        self.cancel_event.clear()
        process = subprocess.Popen(
            arguments,
            cwd=APP_DIR,
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        with self.process_lock:
            self.process = process
        try:
            while process.poll() is None:
                if self.cancel_event.is_set():
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    raise AppError("相似度扫描已停止", HTTPStatus.CONFLICT)
                time.sleep(0.15)
            stderr = process.communicate()[1] or ""
        finally:
            with self.process_lock:
                if self.process is process:
                    self.process = None
        if self.cancel_event.is_set():
            raise AppError("相似度扫描已停止", HTTPStatus.CONFLICT)
        if process.returncode != 0:
            details = stderr.strip().splitlines()
            message = details[-1] if details else "未知错误"
            raise AppError(f"相似图片去重失败: {message[:600]}", HTTPStatus.INTERNAL_SERVER_ERROR)

    def cancel(self) -> dict[str, Any]:
        with self.process_lock:
            process = self.process
            if process is None or process.poll() is not None:
                return {"cancelled": False, "message": "当前没有正在运行的扫描"}
            self.cancel_event.set()
            process.terminate()
            return {"cancelled": True, "message": "正在停止相似度扫描"}

    @staticmethod
    def _validate_scan(summary: dict[str, Any], path: Path, threshold: int) -> None:
        try:
            summary_root = Path(str(summary["root"])).resolve()
            summary_threshold = int(summary["threshold_percent"])
        except (KeyError, TypeError, ValueError) as exc:
            raise AppError("扫描结果缺少目录或阈值信息") from exc
        if summary_root != path or summary_threshold != threshold:
            raise AppError("扫描结果与当前目录或阈值不一致，请重新扫描", HTTPStatus.CONFLICT)

    def scan(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.jobs.is_running():
            raise AppError("后台任务运行期间不能扫描图片目录", HTTPStatus.CONFLICT)
        if not self.lock.acquire(blocking=False):
            raise AppError("已有图片目录正在扫描或去重", HTTPStatus.CONFLICT)
        try:
            path, image_count = self._candidate(payload.get("path"))
            threshold = self._threshold(payload)
            self._run("scan", path, threshold)
            summary_path, manifest_path, _ = self._output_paths(path, threshold)
            summary = self._read_json(summary_path, "扫描结果")
            self._validate_scan(summary, path, threshold)
            summary["source_image_count"] = image_count
            summary["manifest"] = str(manifest_path)
            return summary
        finally:
            self.lock.release()

    def apply_and_add(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.jobs.is_running():
            raise AppError("后台任务运行期间不能删除相似图片", HTTPStatus.CONFLICT)
        if not self.lock.acquire(blocking=False):
            raise AppError("已有图片目录正在扫描或去重", HTTPStatus.CONFLICT)
        try:
            path, _ = self._candidate(payload.get("path"))
            threshold = self._threshold(payload)
            summary_path, manifest_path, apply_summary_path = self._output_paths(path, threshold)
            summary = self._read_json(summary_path, "扫描结果")
            self._validate_scan(summary, path, threshold)
            if not manifest_path.is_file():
                raise AppError("删除清单不存在，请重新扫描", HTTPStatus.CONFLICT)
            self._run("apply", path, threshold)
            apply_summary = self._read_json(apply_summary_path, "删除结果")
            dataset = self.dataset.add_source(
                str(path),
                payload.get("labels_path") if isinstance(payload.get("labels_path"), str) else None,
            )
            return {"dataset": dataset, "scan": summary, "apply": apply_summary}
        finally:
            self.lock.release()


DATASET = DatasetState()
JOBS = JobManager(DATASET)
MODELS = ModelService(DATASET, JOBS)
VIDEOS = VideoService(JOBS)
SOURCE_DEDUP = SourceDedupService(DATASET, JOBS)


class RequestHandler(BaseHTTPRequestHandler):
    server_version = f"{APP_NAME}/{APP_VERSION}"

    def log_message(self, format_string: str, *args: Any) -> None:
        print(f"[{self.log_date_time_string()}] {format_string % args}")

    def _send_json(self, payload: Any, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, exc: Exception) -> None:
        if isinstance(exc, AppError):
            status = exc.status
            message = str(exc)
        else:
            traceback.print_exc()
            status = HTTPStatus.INTERNAL_SERVER_ERROR
            message = f"服务器内部错误: {exc}"
        self._send_json({"error": message}, status)

    def _read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise AppError("请求长度无效") from exc
        if length <= 0:
            return {}
        if length > 4 * 1024 * 1024:
            raise AppError("请求内容过大", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        try:
            value = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AppError("请求不是有效的 JSON") from exc
        if not isinstance(value, dict):
            raise AppError("请求 JSON 必须是对象")
        return value

    def _serve_static(self, request_path: str) -> None:
        relative = "index.html" if request_path == "/" else request_path.lstrip("/")
        candidate = (STATIC_DIR / relative).resolve()
        if not is_relative_to(candidate, STATIC_DIR.resolve()) or not candidate.is_file():
            raise AppError("页面资源不存在", HTTPStatus.NOT_FOUND)
        content = candidate.read_bytes()
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8" if content_type.startswith("text/") else content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(content)

    @staticmethod
    def _query_int(query: dict[str, list[str]], name: str, default: int, minimum: int, maximum: int) -> int:
        try:
            value = int(query.get(name, [str(default)])[0])
        except ValueError as exc:
            raise AppError(f"查询参数 {name} 无效") from exc
        return min(max(value, minimum), maximum)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)
            if path == "/api/health":
                self._send_json({"app": APP_NAME, "version": APP_VERSION, "ok": True})
            elif path == "/api/config":
                try:
                    import ultralytics

                    ultralytics_version = ultralytics.__version__
                except ImportError:
                    ultralytics_version = None
                local_models = sorted(
                    (path for path in APP_DIR.glob("*.pt") if path.name.casefold() != "yolo26n.pt"),
                    key=lambda item: item.name.casefold(),
                )
                latest_trained_model = MODELS.latest_trained_model()
                default_model = latest_trained_model or (local_models[0].resolve() if local_models else None)
                self._send_json(
                    {
                        "app": APP_NAME,
                        "version": APP_VERSION,
                        "dataset": DATASET.summary(),
                        "job": JOBS.snapshot(),
                        "ultralytics": ultralytics_version,
                        "default_model": str(default_model) if default_model else None,
                        "latest_trained_model": str(latest_trained_model) if latest_trained_model else None,
                    }
                )
            elif path == "/api/filesystem":
                self._send_json(self._filesystem(query))
            elif path == "/api/training/plan":
                self._send_json(
                    MODELS.training_plan(
                        {
                            "model_path": query.get("model_path", [""])[0],
                            "training_scope": query.get("training_scope", ["incremental_replay"])[0],
                        }
                    )
                )
            elif path == "/api/weather/review":
                self._send_json(MODELS.weather_review_payload(query.get("id", [""])[0]))
            elif path == "/api/weather/image":
                self._serve_local_image(
                    MODELS.weather_review_image_path(
                        query.get("review_id", [""])[0],
                        query.get("item_id", [""])[0],
                    )
                )
            elif path == "/api/images":
                filter_name = query.get("filter", ["all"])[0]
                if filter_name not in {"all", "unlabeled", "labeled", "pending", "reviewed", "weather"}:
                    raise AppError("图片筛选条件无效")
                sort_name = query.get("sort", ["boxes_desc"])[0]
                if sort_name not in {"name", "boxes_asc", "boxes_desc", "weather_first"}:
                    raise AppError("图片排序条件无效")
                offset = self._query_int(query, "offset", 0, 0, 10_000_000)
                limit = self._query_int(query, "limit", 500, 1, 2000)
                search = query.get("search", [""])[0]
                self._send_json(DATASET.list_images(filter_name, search, sort_name, offset, limit))
            elif path == "/api/image":
                self._serve_image(query.get("path", [""])[0])
            elif path == "/api/labels":
                self._send_json(DATASET.labels_payload(query.get("image", [""])[0]))
            elif path == "/api/job":
                self._send_json(JOBS.snapshot())
            elif path.startswith("/api/"):
                raise AppError("接口不存在", HTTPStatus.NOT_FOUND)
            else:
                self._serve_static(path)
        except Exception as exc:  # noqa: BLE001
            self._send_error(exc)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        try:
            path = urlparse(self.path).path
            payload = self._read_json()
            if path == "/api/dataset/open":
                if JOBS.is_running():
                    raise AppError("后台任务运行期间不能切换数据集", HTTPStatus.CONFLICT)
                if SOURCE_DEDUP.is_running():
                    raise AppError("图片目录扫描期间不能切换数据集", HTTPStatus.CONFLICT)
                self._send_json(DATASET.open(str(payload.get("path", ""))))
            elif path == "/api/dataset/create":
                if JOBS.is_running():
                    raise AppError("后台任务运行期间不能切换数据集", HTTPStatus.CONFLICT)
                if SOURCE_DEDUP.is_running():
                    raise AppError("图片目录扫描期间不能切换数据集", HTTPStatus.CONFLICT)
                self._send_json(DATASET.create(str(payload.get("path", ""))), HTTPStatus.CREATED)
            elif path == "/api/sources":
                if JOBS.is_running():
                    raise AppError("后台任务运行期间不能添加图片目录", HTTPStatus.CONFLICT)
                if SOURCE_DEDUP.is_running():
                    raise AppError("已有图片目录正在扫描或去重", HTTPStatus.CONFLICT)
                self._send_json(
                    DATASET.add_source(
                        str(payload.get("path", "")),
                        payload.get("labels_path") if isinstance(payload.get("labels_path"), str) else None,
                    ),
                    HTTPStatus.CREATED,
                )
            elif path == "/api/sources/dedup/scan":
                self._send_json(SOURCE_DEDUP.scan(payload))
            elif path == "/api/sources/dedup/cancel":
                self._send_json(SOURCE_DEDUP.cancel())
            elif path == "/api/sources/dedup/apply":
                self._send_json(SOURCE_DEDUP.apply_and_add(payload), HTTPStatus.CREATED)
            elif path == "/api/sources/remove":
                if JOBS.is_running():
                    raise AppError("后台任务运行期间不能移除图片目录", HTTPStatus.CONFLICT)
                if SOURCE_DEDUP.is_running():
                    raise AppError("图片目录扫描期间不能移除图片目录", HTTPStatus.CONFLICT)
                self._send_json(
                    DATASET.remove_source(
                        str(payload.get("source_id", "")),
                        str(payload.get("path", "")),
                    )
                )
            elif path == "/api/classes":
                if JOBS.is_running():
                    raise AppError("后台任务运行期间不能修改类别", HTTPStatus.CONFLICT)
                self._send_json(
                    DATASET.set_classes(
                        payload.get("classes"),
                        payload.get("class_id_map"),
                    )
                )
            elif path == "/api/labels":
                if JOBS.is_running():
                    raise AppError("后台任务运行期间不能保存标签", HTTPStatus.CONFLICT)
                result = DATASET.write_boxes(
                    str(payload.get("image", "")),
                    payload.get("boxes"),
                    source="manual",
                    reviewed=bool(payload.get("reviewed", True)),
                )
                self._send_json(result)
            elif path == "/api/images/delete":
                if JOBS.is_running():
                    raise AppError("后台任务运行期间不能移出图片", HTTPStatus.CONFLICT)
                self._send_json(DATASET.move_image_to_trash(str(payload.get("image", ""))))
            elif path == "/api/predict/one":
                self._send_json(MODELS.predict_one(payload))
            elif path == "/api/jobs/predict":
                if SOURCE_DEDUP.is_running():
                    raise AppError("图片目录扫描期间不能启动批量标注", HTTPStatus.CONFLICT)
                self._send_json(MODELS.start_bulk_prediction(payload), HTTPStatus.ACCEPTED)
            elif path == "/api/weather/review/start":
                if SOURCE_DEDUP.is_running():
                    raise AppError("图片目录扫描期间不能生成天气素材", HTTPStatus.CONFLICT)
                self._send_json(MODELS.start_weather_review(payload), HTTPStatus.ACCEPTED)
            elif path == "/api/weather/review/save":
                if JOBS.is_running():
                    raise AppError("后台任务运行期间不能保存天气审核结果", HTTPStatus.CONFLICT)
                self._send_json(MODELS.save_weather_review(payload))
            elif path == "/api/jobs/train":
                if SOURCE_DEDUP.is_running():
                    raise AppError("图片目录扫描期间不能启动训练", HTTPStatus.CONFLICT)
                self._send_json(MODELS.start_training(payload), HTTPStatus.ACCEPTED)
            elif path == "/api/jobs/export":
                if SOURCE_DEDUP.is_running():
                    raise AppError("图片目录扫描期间不能导出数据集", HTTPStatus.CONFLICT)
                self._send_json(MODELS.start_dataset_export(payload), HTTPStatus.ACCEPTED)
            elif path == "/api/jobs/video":
                if SOURCE_DEDUP.is_running():
                    raise AppError("图片目录扫描期间不能添加视频", HTTPStatus.CONFLICT)
                self._send_json(VIDEOS.start(payload), HTTPStatus.ACCEPTED)
            elif path == "/api/jobs/cancel":
                self._send_json(JOBS.cancel())
            else:
                raise AppError("接口不存在", HTTPStatus.NOT_FOUND)
        except Exception as exc:  # noqa: BLE001
            self._send_error(exc)

    def _filesystem(self, query: dict[str, list[str]]) -> dict[str, Any]:
        kind = query.get("kind", ["directory"])[0]
        if kind not in {"directory", "model", "video"}:
            raise AppError("文件浏览类型无效")
        raw_path = query.get("path", [""])[0].strip()
        if raw_path:
            current = Path(raw_path).expanduser().resolve()
        elif DATASET.root:
            current = DATASET.root
        else:
            current = Path("/hdd" if Path("/hdd").is_dir() else Path.home()).resolve()
        if current.is_file():
            current = current.parent
        if not current.is_dir():
            raise AppError("浏览路径不存在")
        entries: list[dict[str, Any]] = []
        try:
            children = sorted(current.iterdir(), key=lambda item: (not item.is_dir(), item.name.casefold()))
        except PermissionError as exc:
            raise AppError("没有权限读取该目录", HTTPStatus.FORBIDDEN) from exc
        for child in children:
            try:
                if child.is_dir():
                    if child.name.startswith("."):
                        continue
                    entries.append({"name": child.name, "path": str(child.resolve()), "type": "directory"})
                elif kind == "model" and child.is_file() and child.suffix.lower() in MODEL_EXTENSIONS:
                    entries.append(
                        {
                            "name": child.name,
                            "path": str(child.resolve()),
                            "type": "file",
                            "file_type": "PT",
                            "size": child.stat().st_size,
                        }
                    )
                elif kind == "video" and child.is_file() and child.suffix.lower() in VIDEO_EXTENSIONS:
                    entries.append(
                        {
                            "name": child.name,
                            "path": str(child.resolve()),
                            "type": "file",
                            "file_type": "VIDEO",
                            "size": child.stat().st_size,
                        }
                    )
            except (OSError, PermissionError):
                continue
        parent = current.parent if current.parent != current else None
        return {
            "kind": kind,
            "current": str(current),
            "parent": str(parent) if parent else None,
            "entries": entries,
        }

    def _serve_local_image(self, path: Path) -> None:
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        stat = path.stat()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(stat.st_size))
        self.send_header("Cache-Control", "private, max-age=60")
        self.send_header("Last-Modified", self.date_time_string(stat.st_mtime))
        self.end_headers()
        with path.open("rb") as handle:
            shutil.copyfileobj(handle, self.wfile)

    def _serve_image(self, relative_name: str) -> None:
        self._serve_local_image(DATASET.image_path(relative_name))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="cc_training_materials local web workspace")
    parser.add_argument("--host", default="127.0.0.1", help="listen address (default: 127.0.0.1)")
    parser.add_argument("--port", default=8765, type=int, help="listen port (default: 8765)")
    parser.add_argument("--dataset", help="open this dataset when the server starts")
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser automatically")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not STATIC_DIR.is_dir():
        raise SystemExit(f"Missing web assets: {STATIC_DIR}")
    if args.dataset:
        DATASET.open(args.dataset)
    server = ThreadingHTTPServer((args.host, args.port), RequestHandler)
    server.daemon_threads = True
    url_host = "127.0.0.1" if args.host in {"0.0.0.0", "::"} else args.host
    url = f"http://{url_host}:{args.port}"
    print(f"{APP_NAME} {APP_VERSION}")
    print(f"Open {url}")
    print("Press Ctrl+C to stop")
    if not args.no_browser:
        threading.Timer(0.7, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("\nStopping server")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
