"""Test-GPU.bat helper: is the graphics card really used by Ollama and ComfyUI? Prints an English / ASCII verdict (the Windows console garbles Persian).

  checks: NVIDIA driver, environment variables that hide the GPU, how InstAI starts ComfyUI (no --cpu, GPU python), PyTorch in ComfyUI's OWN python
          (torch.cuda.is_available()), the running ComfyUI's device, Ollama's log, whether the model InstAI picks fits the card,
          and a short real run of that model with the GPU utilization sampled while it runs.
  Nothing is changed. Exit code: 0 = GPU used, 1 = not used, 2 = partly / not conclusive.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "instai.settings")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")


def main() -> int:
    import django

    django.setup()
    from instai.core import gpu_diag

    print("GPU check (about 20-60 seconds; a model may be loaded for the trial run) ...", flush=True)
    result = gpu_diag.deep_check(probe="--no-torch" not in sys.argv)
    if "--no-run" not in sys.argv:
        trial = gpu_diag.probe_ollama()
        if trial:
            result["checks"].append(trial)
            result = {**result, **gpu_diag.summarize(result["checks"])}
    print()
    print(gpu_diag.ascii_report(result))
    return {"yes": 0, "no": 1}.get(result["gpu_used"], 2)


if __name__ == "__main__":
    sys.exit(main())
