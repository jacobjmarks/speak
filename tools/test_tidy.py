import unittest
from types import SimpleNamespace
from unittest.mock import patch

from speak import config, tidy


class TidyPlanningTest(unittest.TestCase):
    def setUp(self):
        self.settings = {**config.DEFAULTS, "tidy": "auto"}
        self.gpu = patch.multiple(tidy, _gpu=None)
        self.gpu.start()
        self.addCleanup(self.gpu.stop)

    def test_auto_uses_actual_model_size_plus_headroom(self):
        with patch.object(tidy, "_gpu", tidy.Gpu("Vulkan0", "NVIDIA RTX", 3999)):
            plan = tidy.plan(self.settings)
            self.assertEqual(config.SMALL_MODEL, plan.model_id)
            self.assertEqual("Vulkan0", plan.device)
        with patch.object(tidy, "_gpu", tidy.Gpu("Vulkan0", "NVIDIA RTX", 4000)):
            plan = tidy.plan(self.settings)
            self.assertEqual(config.LARGE_MODEL, plan.model_id)
            self.assertEqual("Vulkan0", plan.device)
        with patch.object(tidy, "_gpu", tidy.Gpu("Vulkan0", "NVIDIA RTX", 1003)):
            self.assertEqual("Vulkan0", tidy.plan(self.settings).device)
        with patch.object(tidy, "_gpu", tidy.Gpu("Vulkan0", "NVIDIA RTX", 1002)):
            self.assertIsNone(tidy.plan(self.settings).device)

    def test_probe_picks_gpu_with_most_free_memory(self):
        output = SimpleNamespace(stdout=(
            "Available devices:\n"
            "  Vulkan0: GPU A (10051 MiB, 9000 MiB free)\n"
            "  Vulkan1: GPU B (16000 MiB, 12000 MiB free)\n"
        ), stderr="")
        with patch.object(tidy.subprocess, "run", return_value=output):
            tidy.probe("llama-server")
        self.assertEqual("Vulkan1", tidy.gpu().device)
    def test_probe_prefers_dedicated_gpu_and_auto_skips_integrated(self):
        listing = SimpleNamespace(stdout=(
            "Available devices:\n"
            "  Vulkan0: dGPU (10051 MiB, 9000 MiB free)\n"
            "  Vulkan1: iGPU (32000 MiB, 30000 MiB free)\n"
        ), stderr="")
        bench = SimpleNamespace(stdout="", stderr=(
            "ggml_vulkan: 0 = dGPU (NVIDIA) | uma: 0 | fp16: 1\n"
            "ggml_vulkan: 1 = iGPU (AMD) | uma: 1 | fp16: 1\n"
        ))
        with patch.object(tidy.subprocess, "run", side_effect=[listing, bench]):
            tidy.probe("llama-server")
        self.assertEqual("Vulkan0", tidy.gpu().device)
        self.assertEqual("Vulkan0", tidy.plan(self.settings).device)

    def test_auto_ignores_only_integrated_gpu_but_forced_gpu_uses_it(self):
        with patch.object(tidy, "_gpu", tidy.Gpu("Vulkan0", "iGPU", 30000, True)):
            self.assertIsNone(tidy.plan(self.settings).device)
            self.settings["cleanup_device"] = "gpu"
            self.assertEqual("Vulkan0", tidy.plan(self.settings).device)
    def test_specific_device_is_forced_even_if_integrated(self):
        gpus = [tidy.Gpu("Vulkan0", "dGPU", 9000), tidy.Gpu("Vulkan1", "iGPU", 30000, True)]
        with patch.multiple(tidy, _gpu=gpus[0], _gpus=gpus):
            self.settings["cleanup_device"] = "Vulkan1"
            self.assertEqual("Vulkan1", tidy.plan(self.settings).device)
            self.settings["cleanup_device"] = "Vulkan9"
            plan = tidy.plan(self.settings)
            self.assertIsNone(plan.device)
            self.assertIn("not found", plan.summary)
    def test_best_cpu_threshold_uses_same_model_budget(self):
        self.settings.update(tidy="best", cleanup_device="cpu")
        with patch.object(tidy.platform_utils, "available_memory_mb", return_value=3999):
            self.assertEqual(config.SMALL_MODEL, tidy.plan(self.settings).model_id)
        with patch.object(tidy.platform_utils, "available_memory_mb", return_value=4000):
            self.assertEqual(config.LARGE_MODEL, tidy.plan(self.settings).model_id)

    def test_forced_gpu_falls_back_when_selected_model_does_not_fit(self):
        self.settings["cleanup_device"] = "gpu"
        with patch.object(tidy, "_gpu", tidy.Gpu("Vulkan0", "NVIDIA RTX", 1000)):
            plan = tidy.plan(self.settings)
        self.assertIsNone(plan.device)
        self.assertIn("doesn't have enough free memory", plan.summary)


if __name__ == "__main__":
    unittest.main()
