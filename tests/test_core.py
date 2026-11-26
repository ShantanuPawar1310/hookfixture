import hashlib
import json
import random
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from hookfixture import create_scenario, load_events, verify_scenario, write_scenario


EVENTS = [
    {"type": "invoice.created", "data": {"invoice_id": "inv_demo", "amount_minor": 1500}},
    {"type": "invoice.paid", "data": {"invoice_id": "inv_demo", "amount_minor": 1500}},
]


class ScenarioTests(unittest.TestCase):
    def test_same_input_produces_same_scenario(self):
        self.assertEqual(create_scenario(EVENTS, copies=3, order="shuffle", seed=7),
                         create_scenario(EVENTS, copies=3, order="shuffle", seed=7))

    def test_duplicate_deliveries_preserve_identity_and_body(self):
        deliveries = create_scenario(EVENTS, copies=3).deliveries
        self.assertEqual(len(deliveries), 6)
        self.assertEqual([d.copy for d in deliveries[:3]], [1, 2, 3])
        self.assertEqual(deliveries[0].event, deliveries[2].event)
        self.assertNotEqual(deliveries[0].event["id"], deliveries[3].event["id"])

    def test_reverse_changes_delivery_order_not_event_times(self):
        original = create_scenario(EVENTS, copies=2).deliveries
        reverse = create_scenario(EVENTS, copies=2, order="reverse").deliveries
        self.assertEqual(reverse, original[::-1])
        self.assertGreater(reverse[0].event["created_at"], reverse[-1].event["created_at"])

    def test_seed_changes_order_without_changing_event_ids(self):
        a = create_scenario(EVENTS, copies=10, order="shuffle", seed=1)
        b = create_scenario(EVENTS, copies=10, order="shuffle", seed=2)
        self.assertNotEqual(a.deliveries, b.deliveries)
        self.assertEqual({d.event["id"] for d in a.deliveries}, {d.event["id"] for d in b.deliveries})

    def test_shuffle_does_not_modify_global_random_state(self):
        before = random.getstate()
        create_scenario(EVENTS, order="shuffle", seed=12)
        self.assertEqual(before, random.getstate())

    def test_input_data_is_detached(self):
        events = [{"type": "demo", "data": {"nested": [1]}}]
        scenario = create_scenario(events)
        events[0]["data"]["nested"].append(2)
        self.assertEqual(scenario.deliveries[0].event["data"], {"nested": [1]})

    def test_explicit_id_preserved_and_timezone_normalized(self):
        scenario = create_scenario([{
            "id": "evt_user", "type": "demo", "created_at": "2026-01-01T05:30:00+05:30", "data": {},
        }])
        self.assertEqual(scenario.deliveries[0].event["id"], "evt_user")
        self.assertEqual(scenario.deliveries[0].event["created_at"], "2026-01-01T00:00:00Z")

    def test_identical_source_bodies_still_get_distinct_ids(self):
        scenario = create_scenario([EVENTS[0], EVENTS[0]])
        self.assertNotEqual(scenario.deliveries[0].event["id"], scenario.deliveries[1].event["id"])

    def test_invalid_sources_and_options_are_rejected(self):
        cases = [([], {}), ([None], {}), ([{"data": {}}], {}),
                 ([{"type": "demo", "data": []}], {}),
                 ([{"type": "demo", "data": {}, "unexpected": 1}], {}),
                 ([{"id": "", "type": "demo", "data": {}}], {}),
                 ([{"type": "demo", "data": {"number": float("nan")}}], {}),
                 (EVENTS, {"copies": 0}), (EVENTS, {"copies": True}),
                 (EVENTS, {"copies": 101}), (EVENTS, {"seed": True}),
                 (EVENTS, {"order": "invalid"}), (EVENTS, {"start": "2026-01-01"})]
        for events, options in cases:
            with self.subTest(events=events, options=options), self.assertRaises(ValueError):
                create_scenario(events, **options)

    def test_duplicate_source_ids_rejected(self):
        event = {"id": "same", "type": "demo", "data": {}}
        with self.assertRaisesRegex(ValueError, "Repeated source"):
            create_scenario([event, event])

    def test_total_delivery_limit(self):
        with self.assertRaisesRegex(ValueError, "exceeds"):
            create_scenario(EVENTS * 51, copies=100)


class FilesystemTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def build(self, name="out"):
        return write_scenario(create_scenario(EVENTS, copies=2, order="shuffle", seed=7), self.root / name)

    def edit_manifest(self, manifest, edit):
        data = json.loads(manifest.read_text())
        edit(data)
        manifest.write_text(json.dumps(data))

    def test_round_trip_and_exact_counts(self):
        manifest = self.build()
        self.assertEqual(asdict(verify_scenario(manifest)), {"deliveries": 4, "unique_events": 2, "duplicates": 2})

    def test_repeated_builds_are_byte_for_byte_equal(self):
        first, second = self.build("one").parent, self.build("two").parent
        self.assertEqual({p.name: p.read_bytes() for p in first.iterdir()},
                         {p.name: p.read_bytes() for p in second.iterdir()})

    def test_existing_output_is_preserved(self):
        directory = self.root / "out"
        directory.mkdir()
        sentinel = directory / "keep.txt"
        sentinel.write_text("keep me")
        with self.assertRaises(FileExistsError):
            self.build()
        self.assertEqual(sentinel.read_text(), "keep me")

    def test_output_race_does_not_overwrite_an_empty_directory(self):
        scenario = create_scenario(EVENTS)
        from hookfixture import core
        real_verify = core.verify_scenario

        def competing_writer(path):
            (self.root / "out").mkdir()
            return real_verify(path)

        with patch.object(core, "verify_scenario", side_effect=competing_writer):
            with self.assertRaises(FileExistsError):
                write_scenario(scenario, self.root / "out")
        self.assertEqual(list((self.root / "out").iterdir()), [])
        self.assertFalse(list(self.root.glob(".hookfixture-*")))

    def test_failed_staging_leaves_no_output(self):
        scenario = create_scenario(EVENTS)
        scenario.deliveries[0].event["type"] = ""
        with self.assertRaises(ValueError):
            write_scenario(scenario, self.root / "out")
        self.assertFalse((self.root / "out").exists())
        self.assertFalse(list(self.root.glob(".hookfixture-*")))

    def test_checksum_detects_modified_payload(self):
        manifest = self.build()
        fixture = next(manifest.parent.glob("0*.json"))
        fixture.write_text("{}")
        with self.assertRaisesRegex(ValueError, "Checksum mismatch"):
            verify_scenario(manifest)

    def test_manifest_cannot_reference_a_parent_path(self):
        manifest = self.build()
        self.edit_manifest(manifest, lambda m: m["deliveries"][0].update(file="../outside.json"))
        with self.assertRaisesRegex(ValueError, "filenames"):
            verify_scenario(manifest)

    def test_symlink_fixture_rejected(self):
        manifest = self.build()
        fixture = manifest.parent / "000001.json"
        outside = self.root / "outside.json"
        fixture.rename(outside)
        fixture.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "symlink"):
            verify_scenario(manifest)

    def test_missing_fixture_rejected(self):
        manifest = self.build()
        (manifest.parent / "000001.json").unlink()
        with self.assertRaises(FileNotFoundError):
            verify_scenario(manifest)

    def test_manifest_metadata_corruption_rejected(self):
        cases = [
            lambda m: m.update(format_version=2),
            lambda m: m.update(format_version=True),
            lambda m: m.update(seed="7"),
            lambda m: m.update(order="unknown"),
            lambda m: m["summary"].update(deliveries=99),
            lambda m: m["summary"].update(unique_events=True),
            lambda m: m["deliveries"][0].update(event_id="different"),
            lambda m: m["deliveries"][0].update(copy=True),
            lambda m: m["deliveries"][0].update(copy=3),
            lambda m: m["deliveries"].append(m["deliveries"][0]),
        ]
        for index, edit in enumerate(cases):
            with self.subTest(index=index):
                manifest = self.build(f"case{index}")
                self.edit_manifest(manifest, edit)
                with self.assertRaises(ValueError):
                    verify_scenario(manifest)

    def test_same_id_with_conflicting_bodies_rejected_even_with_updated_checksum(self):
        manifest = self.build()
        data = json.loads(manifest.read_text())
        first = data["deliveries"][0]
        record = next(r for r in data["deliveries"][1:] if r["event_id"] == first["event_id"])
        fixture = manifest.parent / record["file"]
        event = json.loads(fixture.read_text())
        event["data"]["amount_minor"] = 999
        raw = json.dumps(event).encode()
        fixture.write_bytes(raw)
        record["sha256"] = hashlib.sha256(raw).hexdigest()
        manifest.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "Conflicting payloads"):
            verify_scenario(manifest)

    def test_load_rejects_duplicate_keys_and_nonstandard_numbers(self):
        path = self.root / "input.json"
        for content in ('[{"type":"a","type":"b","data":{}}]', '[{"type":"a","data":{"x":NaN}}]', '{}'):
            with self.subTest(content=content):
                path.write_text(content)
                with self.assertRaises(ValueError):
                    load_events(path)

    def test_json_input_size_is_bounded(self):
        path = self.root / "input.json"
        path.write_text('[{"type":"a","data":{}}]')
        with patch("hookfixture.core.MAX_BYTES", 8):
            with self.assertRaisesRegex(ValueError, "exceeds"):
                load_events(path)
