import tempfile
import unittest
from pathlib import Path

from PIL import Image

import cc_training_materials as app


class BoxTests(unittest.TestCase):
    def test_box_round_trip(self):
        box = app.Box.from_line("0 0.500000 0.400000 0.200000 0.100000", 1)
        self.assertEqual(box.cls_id, 0)
        self.assertEqual(box.to_line(), "0 0.500000 0.400000 0.200000 0.100000")

    def test_box_rejects_invalid_width(self):
        with self.assertRaisesRegex(ValueError, "宽高无效"):
            app.Box.from_line("0 0.5 0.5 0 0.2", 4)

    def test_payload_rejects_unknown_class(self):
        with self.assertRaisesRegex(app.AppError, "不在当前类别配置"):
            app.Box.from_payload({"cls_id": 4, "xc": 0.5, "yc": 0.5, "w": 0.2, "h": 0.2}, {0})


class DatasetStateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.project = self.base / "cc_training_materials_dataset"
        self.source_a = self.base / "camera-a"
        self.source_b = self.base / "camera-b"
        self.source_a.mkdir()
        self.source_b.mkdir()
        Image.new("RGB", (80, 60), "white").save(self.source_a / "same-name.jpg")
        Image.new("RGB", (100, 50), "black").save(self.source_b / "same-name.jpg")
        self.dataset = app.DatasetState()
        self.dataset.create(str(self.project))

    def tearDown(self):
        self.temporary.cleanup()

    def test_multiple_sources_keep_duplicate_names_separate(self):
        first = self.dataset.add_source(str(self.source_a))["added"]["id"]
        second = self.dataset.add_source(str(self.source_b))["added"]["id"]
        names = self.dataset.all_image_names()
        self.assertEqual(names, [f"{first}/same-name.jpg", f"{second}/same-name.jpg"])
        self.assertNotEqual(self.dataset.label_path(names[0]), self.dataset.label_path(names[1]))

    def test_manual_and_prediction_statuses(self):
        source_id = self.dataset.add_source(str(self.source_a))["added"]["id"]
        name = f"{source_id}/same-name.jpg"
        box = {"cls_id": 0, "xc": 0.5, "yc": 0.5, "w": 0.4, "h": 0.3}

        predicted = self.dataset.write_boxes(name, [box], "prediction", reviewed=False)
        self.assertTrue(predicted["entry"]["pending"])
        self.assertEqual(predicted["entry"]["box_count"], 1)

        manual = self.dataset.write_boxes(name, [box], "manual", reviewed=True)
        self.assertFalse(manual["entry"]["pending"])
        self.assertTrue(manual["entry"]["reviewed"])

    def test_empty_saved_label_counts_as_labeled_negative_sample(self):
        source_id = self.dataset.add_source(str(self.source_a))["added"]["id"]
        name = f"{source_id}/same-name.jpg"
        self.dataset.write_boxes(name, [], "manual", reviewed=True)
        entry = self.dataset.image_entry(name)
        self.assertTrue(entry["has_label"])
        self.assertEqual(entry["box_count"], 0)
        self.assertEqual(self.dataset.label_path(name).read_text(encoding="utf-8"), "")

    def test_existing_label_is_backed_up_before_replacement(self):
        source_id = self.dataset.add_source(str(self.source_a))["added"]["id"]
        name = f"{source_id}/same-name.jpg"
        first = {"cls_id": 0, "xc": 0.5, "yc": 0.5, "w": 0.4, "h": 0.3}
        second = {"cls_id": 0, "xc": 0.2, "yc": 0.2, "w": 0.1, "h": 0.1}
        self.dataset.write_boxes(name, [first], "manual", reviewed=True)
        backup = self.project / app.WORK_DIRNAME / "backups" / "test" / "labels"
        self.dataset.write_boxes(name, [second], "prediction", reviewed=False, backup_dir=backup)
        backup_file = backup / source_id / "same-name.txt"
        self.assertTrue(backup_file.is_file())
        self.assertIn("0.400000 0.300000", backup_file.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
