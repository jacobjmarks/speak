import threading

from tests.ui import QtTestCase
from speak.ui.bridge import Bridge


class LiveTextDeliveryTest(QtTestCase):
    """Live text from ASR threads reaches the UI as the newest transcript, not one UI update per ASR update."""

    def test_a_burst_from_a_worker_thread_is_delivered_once_as_its_latest_text(self):
        bridge = Bridge()
        delivered = []
        bridge.live.connect(delivered.append)

        def burst(prefix):
            for i in range(500):
                bridge.on_live_text(f"{prefix}{i}")

        for prefix in ("a", "b"):
            worker = threading.Thread(target=burst, args=(prefix,))
            worker.start()
            worker.join()
            self.app.processEvents()

        self.assertEqual(["a499", "b499"], delivered)
