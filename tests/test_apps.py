"""Opening an app on a TV box: what is accepted as an app, the commands sent, and reading the box's reply.

The replies are the living room Google TV Streamer's own, 18 Oct 2026 (androidtv.adb_command)."""
import unittest

from _load import apps

OPENED = """ arg: "-p"
 arg: "dce.euroleague"
data="android.intent.category.LEANBACK_LAUNCHER"
Events injected: 1
## Network stats: elapsed time=47ms (0ms mobile, 0ms wifi, 47ms not connected)"""
MISSING = """** No activities found to run, monkey aborted."""


class Apps(unittest.TestCase):
    def test_package_names_and_links_only(self):
        for ok in ("no.tv2.sumo", "dce.euroleague", "premierplayer.premiersports.com.premierplayer", "air.ITVMobilePlayer",
                   "https://play.tv2.no/direkte", "nrktv://program/abc"):
            self.assertTrue(apps.valid_app(ok), ok)
        for bad in ("", "dazn", "com.dazn; reboot", "com.dazn && rm -rf /", "$(reboot)", "no.tv2.sumo 1",
                    "https://x.no/a b", "https://x.no/'; reboot'", "javascript:alert(1)", "com..dazn", ".com.dazn"):
            self.assertFalse(apps.valid_app(bad), bad)

    def test_commands(self):
        self.assertEqual(apps.open_commands("no.tv2.sumo"), [
            "monkey -p no.tv2.sumo -c android.intent.category.LEANBACK_LAUNCHER 1",
            "monkey -p no.tv2.sumo -c android.intent.category.LAUNCHER 1"])
        self.assertEqual(apps.open_commands("https://play.tv2.no/direkte"),
                         ["am start -a android.intent.action.VIEW -d 'https://play.tv2.no/direkte'"])
        with self.assertRaises(ValueError):
            apps.open_commands("com.dazn; reboot")

    def test_reading_the_reply(self):
        self.assertTrue(apps.opened(OPENED))
        self.assertFalse(apps.opened(MISSING))
        self.assertTrue(apps.not_installed(MISSING))
        self.assertTrue(apps.opened("Starting: Intent { act=android.intent.action.VIEW dat=https://play.tv2.no/... }"))
        self.assertFalse(apps.opened("Error: Activity not started, unable to resolve Intent"))
        self.assertFalse(apps.opened(None))


if __name__ == "__main__":
    unittest.main()
