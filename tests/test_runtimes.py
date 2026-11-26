import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from speak import runtimes


class ManagedServerTest(unittest.TestCase):
    """A runtime is launched once when ready, reused by key, and stopped cleanly."""

    def test_start_reuses_matching_server_and_stop_terminates_it(self):
        class Process:
            def __init__(self, *_args, **_kwargs):
                self.exit_code = None
                self.terminated = False

            def poll(self):
                return self.exit_code

            def terminate(self):
                self.terminated = True
                self.exit_code = 0

            def wait(self, timeout):
                return self.exit_code

        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                pass

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "runtime"
            executable.touch()
            process = Process()
            server = runtimes.ManagedServer("test", root / "server.log", "/ready")
            with patch.object(runtimes, "free_port", return_value=9876), \
                    patch.object(runtimes.subprocess, "Popen", return_value=process) as popen, \
                    patch.object(runtimes.urllib.request, "urlopen", return_value=Response()), \
                    patch.object(runtimes, "tie_to_app"):
                self.assertTrue(server.start("model-a", executable, [], root, {}, timeout=1))
                self.assertTrue(server.running("model-a"))
                self.assertFalse(server.start("model-a", executable, [], root, {}))
                self.assertEqual(1, popen.call_count)
                server.stop()

        self.assertTrue(process.terminated)
        self.assertFalse(server.running("model-a"))

    def test_missing_runtime_fails_before_spawning(self):
        server = runtimes.ManagedServer("test", Path("unused.log"), "/ready")
        with patch.object(runtimes.subprocess, "Popen") as popen:
            with self.assertRaisesRegex(RuntimeError, "runtime is missing"):
                server.start("model", Path("missing-runtime"), [], Path("."), {})
        popen.assert_not_called()


class AsrServerLocalModelTest(unittest.TestCase):
    """A speech model .gguf pasted into the models folder is served by path, with no download or host check."""

    def test_pasted_gguf_is_served_by_path_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            models = Path(directory)
            (models / "cleanup").mkdir()
            (models / "cleanup" / "tidy.gguf").touch()
            pasted = models / "nemotron.q8_0.gguf"
            pasted.touch()
            server = runtimes.AsrServer()
            with patch.object(runtimes, "MODELS_DIR", models), \
                    patch.object(runtimes, "check_model_host") as host, \
                    patch.object(server, "start") as start:
                server.ensure("nemotron-3.5", lambda *_: None)

        host.assert_not_called()
        args = start.call_args.args[2]
        self.assertEqual(str(pasted), args[args.index("--asr-model") + 1])

    def test_without_pasted_file_the_model_name_is_used(self):
        with tempfile.TemporaryDirectory() as directory:
            server = runtimes.AsrServer()
            with patch.object(runtimes, "MODELS_DIR", Path(directory)), \
                    patch.object(runtimes, "check_model_host"), \
                    patch.object(server, "start") as start:
                server.ensure("nemotron-3.5", lambda *_: None)

        args = start.call_args.args[2]
        self.assertEqual("nemotron-3.5", args[args.index("--asr-model") + 1])

    def test_runtime_rejecting_the_model_file_is_recognised(self):
        with tempfile.TemporaryDirectory() as directory:
            server = runtimes.AsrServer()
            server.log_path = Path(directory) / "runtime.log"
            server.log_path.write_text(
                "nemo-speech serve: Unknown general.architecture='parakeet'. Supported: 'asr' (preferred).\n")
            self.assertIsInstance(server._exit_error(0), runtimes.UnsupportedModelError)
            server.log_path.write_text("something else broke\n")
            self.assertNotIsInstance(server._exit_error(0), runtimes.UnsupportedModelError)

    def test_rejected_pasted_gguf_explains_the_problem_when_nothing_is_downloaded(self):
        with tempfile.TemporaryDirectory() as directory:
            models = Path(directory)
            (models / "handy.gguf").touch()
            server = runtimes.AsrServer()
            with patch.object(runtimes, "MODELS_DIR", models), \
                    patch.object(runtimes, "check_model_host") as host, \
                    patch.object(server, "start", side_effect=runtimes.UnsupportedModelError("no")) as start, \
                    self.assertRaisesRegex(runtimes.ModelDownloadError, "handy.gguf"):
                server.ensure("nemotron-3.5", lambda *_: None)

        host.assert_not_called()
        self.assertEqual(1, start.call_count)

    def test_rejected_pasted_gguf_falls_back_to_the_downloaded_model(self):
        with tempfile.TemporaryDirectory() as directory:
            models = Path(directory)
            (models / "handy.gguf").touch()
            (models / "nvidia").mkdir()
            (models / "nvidia" / "nemotron.gguf").touch()
            server = runtimes.AsrServer()
            with patch.object(runtimes, "MODELS_DIR", models), \
                    patch.object(runtimes, "check_model_host") as host, \
                    patch.object(server, "start", side_effect=[runtimes.UnsupportedModelError("no"), True]) as start:
                server.ensure("nemotron-3.5", lambda *_: None)

        host.assert_not_called()
        args = start.call_args.args[2]
        self.assertEqual("nemotron-3.5", args[args.index("--asr-model") + 1])


if __name__ == "__main__":
    unittest.main()
