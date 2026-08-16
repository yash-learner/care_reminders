#!/usr/bin/env python

"""Tests for the care_reminders package."""

import unittest


class TestCareRemindersPlugin(unittest.TestCase):
    def test_package_imports(self):
        import care_reminders
        from care_reminders.dosage_parser import DosageParser

        result = DosageParser({"text": "1-0-1", "as_needed_boolean": False}).parse()
        self.assertEqual(["morning", "night"], [slot.day_part for slot in result.slots])
        self.assertTrue(hasattr(care_reminders, "__version__"))
