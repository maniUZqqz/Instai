# One PC, two programs: InstAI next to the NMarketing node agent (0.8.0)

The owner's GPU PC (RTX 3060, 12 GB) runs InstAI **and** NMarketing's processing agent (`processing-server`, started by its own START.bat).
They share one Ollama, one ComfyUI, the voice servers and one graphics card. This page is the contract; `instai/gpu/coexist.py`,
`instai/gpu/ollama_tune.py`, `instai/gpu/arbiter.py` and `instai/providers/comfy/launcher.py` enforce InstAI's half of it, and
`/api/gpu/coexist` (the "Coexistence" card on the Models page) shows the state.

## Ports (nothing is configured by hand)

| Port | What | Who starts it | InstAI's rule |
|---|---|---|---|
| 8765 (`INSTAI_PORT`) | InstAI's own server | InstAI | `scripts/bootstrap.py` takes the next free port (saved in `.env`) when another program holds it; a port the owner set himself is only reported |
| 11434 | Ollama | the owner / either program | one Ollama per PC; InstAI never starts a second one and never kills it |
| 8188 | ComfyUI | either program (`run_nvidia_gpu.bat`) | the one that answers is used; InstAI does not start ComfyUI while a `main.py` process of that folder is still booting (`coexist.comfy_booting`) |
| 5640 / 5641 / 5642 | MOSS-TTS / MOSS-SoundEffect / ACE-Step servers | either program | the same fixed ports as NMarketing: a server that already runs is used |
| 5620 | NMarketing's voice gateway | NMarketing | InstAI only reads it |

## The graphics card

1. **Wait, never fight.** Before a GPU job InstAI measures the VRAM used by programs other than Ollama and ComfyUI (nvidia-smi); if it is more than
   max(2.5 GB, 25 % of the card) the job shows "GPU busy: another program uses N GB" and waits (`gpu/arbiter.py`, wait code `gpu_busy`: waiting is not failing).
2. **Short stay.** InstAI asks Ollama to keep a model for 3 minutes after its last request (`INSTAI_OLLAMA_KEEP_ALIVE`, was 10 minutes), so the card is
   free again soon after InstAI stops.
3. **Give it back.** When InstAI has had no GPU work (running or waiting) for `INSTAI_GPU_RELEASE_AFTER` seconds (default 90), the worker asks ComfyUI to
   unload its models (`POST /free`, `coexist.release_idle`, once per quiet period). Ollama needs no help (rule 2).
4. **Switch occupants cleanly inside one job** (`arbiter.Lease.use`): the LLM is unloaded before ComfyUI starts and the other way round.
5. **Never kill what InstAI did not start** (ComfyUI, Ollama, voice servers of another program).

## Ollama completely on the GPU (the owner's models are never changed)

* Per request (`gpu/ollama_tune.plan`): `num_ctx` is the largest context (not below InstAI's default 8192) with which the whole model still fits in the VRAM that is
  free right now; `num_gpu` is 999 ("every layer") only when the numbers say it fits, never otherwise (forcing layers onto a card that cannot hold them makes
  Ollama fail instead of spilling to the CPU). `INSTAI_OLLAMA_NUM_GPU` / `INSTAI_OLLAMA_NUM_CTX` (the owner's own values) win; `INSTAI_OLLAMA_AUTOTUNE=0` switches the
  planning off. The job's live state shows `num_ctx` and `forced_gpu`, its log says when the context was reduced, and the queue says where the model really runs.
* Per Ollama server: `OLLAMA_FLASH_ATTENTION=1` and `OLLAMA_KV_CACHE_TYPE=q8_0` halve the cache that grows with the context. They are environment variables of
  the Ollama process: the **Apply Ollama settings** button saves them in the Windows user environment (`setx`, no administrator) and, only if the owner presses the
  second button and nothing is loaded (or he insists), restarts Ollama. Never done automatically.
* torch: ComfyUI's own python is checked by the deep GPU check (`core/gpu_diag.py`: CPU-only torch, `--cpu`, hidden CUDA variables); InstAI itself runs no torch.

## What NMarketing's agent can do to keep the peace (not done here: it is another lane's code)

The agent already unloads Ollama (`keep_alive 0`) and frees ComfyUI (`/free`) before its own GPU jobs (`ServiceManager.hand_over_vram`) and watches nvidia-smi, so the two
programs already coexist politely. If a hard guarantee is wanted later, a shared lease file is the smallest protocol that both sides can adopt:
`%ProgramData%\GpuShare\lease.json` = `{"holder": "instai|nm", "kind": "llm|comfy|voice", "pid": 123, "until": "<UTC ISO time>"}`; take it before a heavy job, refresh it
every 20 s, delete it afterwards, treat an expired or dead-pid lease as free. InstAI's `GPUArbiter.wait_until_free` is the single place where InstAI would read it.

## Tests

`tests/test_gpu_share.py` (plan, request options, keep-alive, the neighbour detection, the report, `release_idle`, port clash) and the Models page in
`tests_ui/test_qa_sweep.py`.
