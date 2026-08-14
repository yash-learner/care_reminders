#!/usr/bin/env python

"""Standalone parser tests (no Django / CARE)."""

import sys
import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from care_reminders.active_window import ActiveWindow
from care_reminders.dosage_parser import DosageParser


class DosageParserTest(unittest.TestCase):
    def parse(self, instruction, dose_quantity=1):
        return DosageParser(instruction, dose_quantity=dose_quantity).parse()

    def test_maps_1_0_0_morning_only(self):
        result = self.parse(
            {
                "text": "1-0-0",
                "as_needed_boolean": False,
                "timing": {"code": {"code": "AM", "display": "Every morning"}},
            }
        )
        self.assertFalse(result.as_needed)
        self.assertEqual(["morning"], [slot.day_part for slot in result.slots])
        self.assertEqual(Decimal("1"), result.slots[0].dose_amount)

    def test_maps_1_1_1_to_morning_noon_night(self):
        result = self.parse({"text": "1-1-1", "as_needed_boolean": False})
        self.assertEqual(["morning", "noon", "night"], [slot.day_part for slot in result.slots])

    def test_maps_1_0_1_to_morning_and_night(self):
        result = self.parse({"text": "1-0-1", "as_needed_boolean": False})
        self.assertEqual(["morning", "night"], [slot.day_part for slot in result.slots])

    def test_maps_1_1_1_1_to_four_day_parts(self):
        result = self.parse({"text": "1-1-1-1", "as_needed_boolean": False})
        self.assertEqual(
            ["morning", "noon", "evening", "night"],
            [slot.day_part for slot in result.slots],
        )

    def test_applies_fractional_man_slot_values(self):
        result = self.parse({"text": "1/2-0-1", "as_needed_boolean": False}, dose_quantity=2)
        self.assertEqual(["morning", "night"], [slot.day_part for slot in result.slots])
        self.assertEqual(Decimal("1"), result.slots[0].dose_amount)
        self.assertEqual(Decimal("2"), result.slots[-1].dose_amount)

    def test_treats_sos_and_as_needed_as_prn(self):
        sos = self.parse({"text": "SOS", "as_needed_boolean": False})
        prn = self.parse({"as_needed_boolean": True})
        self.assertTrue(sos.as_needed)
        self.assertEqual([], sos.slots)
        self.assertTrue(prn.as_needed)
        self.assertEqual([], prn.slots)

    def test_maps_bid_display_variants(self):
        morning_noon = self.parse(
            {
                "as_needed_boolean": False,
                "timing": {"code": {"code": "BID", "display": "Morning and noon"}},
            }
        )
        noon_night = self.parse(
            {
                "as_needed_boolean": False,
                "timing": {"code": {"code": "BID", "display": "Noon and night"}},
            }
        )
        self.assertEqual(["morning", "noon"], [slot.day_part for slot in morning_noon.slots])
        self.assertEqual(["noon", "night"], [slot.day_part for slot in noon_night.slots])

    def test_maps_hourly_fhir_codes_to_interval_slots(self):
        result = self.parse(
            {
                "as_needed_boolean": False,
                "timing": {"code": {"code": "Q6H", "display": "Every 6 hours"}},
            }
        )
        self.assertEqual(["interval"], [slot.day_part for slot in result.slots])
        self.assertEqual(6, result.slots[0].interval_hours)

    def test_maps_stat_to_a_one_off_slot(self):
        result = self.parse({"text": "STAT", "as_needed_boolean": False})
        self.assertEqual(["stat"], [slot.day_part for slot in result.slots])

    def test_prefers_man_text_over_bid_code(self):
        result = self.parse(
            {
                "text": "1-0-1",
                "as_needed_boolean": False,
                "timing": {"code": {"code": "BID", "display": "Two times a day"}},
            }
        )
        self.assertEqual(["morning", "night"], [slot.day_part for slot in result.slots])


class ActiveWindowTest(unittest.TestCase):
    def test_authored_on_plus_bounds_duration(self):
        authored = datetime.fromisoformat("2026-03-17T18:03:10.434000+00:00")
        window = ActiveWindow(
            {
                "authored_on": authored.isoformat(),
                "status": "active",
                "dosage_instruction": [
                    {
                        "timing": {
                            "repeat": {
                                "frequency": 1,
                                "period": "1",
                                "period_unit": "d",
                                "bounds_duration": {"value": "5", "unit": "d"},
                            }
                        }
                    }
                ],
            }
        ).call()
        self.assertEqual(authored, window.start)
        delta_hours = (window.end - window.start).total_seconds() / 3600
        self.assertAlmostEqual(5 * 24, delta_hours, places=0)


if __name__ == "__main__":
    unittest.main()
