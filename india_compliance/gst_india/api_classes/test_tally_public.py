from unittest.mock import Mock, patch

import frappe
import requests
from frappe.tests import IntegrationTestCase

from india_compliance.gst_india.api_classes.tally_public import (
    CACHE_TTL_SECONDS,
    get_tally_gstin_info,
)


class TestTallyPublicGSTIN(IntegrationTestCase):
    gstin = "24AAUPV7468F1ZW"
    cache_key = f"tally_gstin_info:{gstin}"

    def tearDown(self):
        frappe.cache.delete_value(self.cache_key)

    @patch("india_compliance.gst_india.api_classes.tally_public.requests.post")
    def test_maps_tally_response_to_gstn_shape(self, post):
        response = Mock()
        response.json.return_value = {
            "status": 1,
            "validation_status": "VALID",
            "legal_name": "NALIN VORA",
            "trade_name": "SHALIBHADRA METAL CORPORATION",
            "gstin_status": "Active",
            "registration_type": "Regular",
            "business_constitution": "Proprietorship",
            "registration_date": "01/07/2017",
            "address": "Plot No. 420, National Highway No. 8",
            "district": "Vadodara",
            "state": "Gujarat",
            "pincode": "391243",
        }
        post.return_value = response

        result = get_tally_gstin_info(self.gstin)

        post.assert_called_once_with(
            "https://tallysolutions.com/wp-content/themes/tally/api/gstin-serach-api.php",
            data={"gstin": self.gstin},
            timeout=4,
        )
        self.assertEqual(result.gstin, self.gstin)
        self.assertEqual(result.lgnm, "NALIN VORA")
        self.assertEqual(result.tradeNam, "SHALIBHADRA METAL CORPORATION")
        self.assertEqual(result.ctb, "Proprietorship")
        self.assertEqual(result.dty, "Regular")
        self.assertEqual(result.sts, "Active")
        self.assertEqual(result.pradr.addr.bno, "Plot No. 420, National Highway No. 8")
        self.assertEqual(result.pradr.addr.dst, "Vadodara")
        self.assertEqual(result.pradr.addr.stcd, "Gujarat")
        self.assertEqual(result.pradr.addr.pncd, "391243")
        self.assertEqual(
            frappe.cache.get_value(self.cache_key)["lgnm"],
            "NALIN VORA",
        )

    @patch("india_compliance.gst_india.api_classes.tally_public.requests.post")
    def test_uses_180_day_cache(self, post):
        post.return_value = Mock(
            json=Mock(
                return_value={
                    "status": 1,
                    "validation_status": "VALID",
                    "legal_name": "TEST BUSINESS",
                    "gstin_status": "Active",
                    "registration_type": "Regular",
                }
            )
        )

        first = get_tally_gstin_info(self.gstin)
        second = get_tally_gstin_info(self.gstin)

        self.assertEqual(first.lgnm, second.lgnm)
        post.assert_called_once()
        self.assertEqual(CACHE_TTL_SECONDS, 60 * 60 * 24 * 180)

    @patch("india_compliance.gst_india.api_classes.tally_public.requests.post")
    def test_rejects_invalid_or_unavailable_response(self, post):
        post.return_value = Mock(
            json=Mock(return_value={"status": 0, "validation_status": "INVALID"})
        )
        self.assertIsNone(get_tally_gstin_info(self.gstin))

    @patch("india_compliance.gst_india.api_classes.tally_public.requests.post")
    def test_provider_failure_degrades_gracefully(self, post):
        post.side_effect = requests.Timeout("provider timeout")
        self.assertIsNone(get_tally_gstin_info(self.gstin))
