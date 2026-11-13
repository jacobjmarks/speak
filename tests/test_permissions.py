import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from speak import permissions


class PermissionTest(unittest.TestCase):
    """The setup flow reports required permissions that are not yet granted."""

    def test_missing_permissions_reports_only_ungranted_required_items(self):
        required = (permissions.Permission("mic", "Mic", "", ""), permissions.Permission("keys", "Keys", "", ""))
        with patch.object(permissions, "REQUIRED", required), \
                patch.object(permissions, "granted", side_effect=lambda item: item == "mic"):
            self.assertEqual([required[1]], permissions.missing())

    def test_input_monitoring_falls_back_to_settings_when_macos_wont_prompt(self):
        quartz = SimpleNamespace(CGRequestListenEventAccess=Mock(return_value=False))
        with patch.dict(sys.modules, {"Quartz": quartz}), \
                patch.object(permissions, "open_settings") as open_settings:
            permissions.request("input_monitoring")
        open_settings.assert_called_once_with("input_monitoring")

    def test_input_monitoring_request_does_not_open_settings_when_granted(self):
        quartz = SimpleNamespace(CGRequestListenEventAccess=Mock(return_value=True))
        with patch.dict(sys.modules, {"Quartz": quartz}), \
                patch.object(permissions, "open_settings") as open_settings:
            permissions.request("input_monitoring")
        open_settings.assert_not_called()


if __name__ == "__main__":
    unittest.main()
