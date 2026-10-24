# Is Speak's large cleanup model worth its size?

**Research date:** 2026-10-23

## Summary

**Yes, Large adds real self-correction capability, but it is not essential for ordinary dictation and is not consistently more faithful.** In a new 32-case synthetic-text smoke test, Large resolved 7/8 correction cases to the expected word sequence; current Small resolved 0/8. However, Large also made unsolicited changes on preservation cases, and neither model reliably preserved explicit line/paragraph layout.

**Recommendation:** an offline edition containing ASR plus current Small is already feasible on model size: **1.233 GB**. Keep Large optional rather than include it in the offline payload. If one compact model must replace both cleanup choices while retaining corrections, benchmark **Qwen2.5-1.5B Q4_K_M** first: ASR plus that model is **1.859 GB**. Its quality is not established by this investigation.

No application behavior, defaults, build, or release workflow changed. Small was downloaded with permission; synthetic text only, no transcript history or microphone recordings used.

## What Large actually adds

The current application already requests ASR punctuation unconditionally in [controller.py](../speak/controller.py). [cleanup.py](../speak/cleanup.py) already performs spoken layout commands, some punctuation commands, filler/stutter removal, and pause-based paragraphing without an LLM. Thus those features are **not unique value from the 4B model**.

The material additional feature is semantic editing: deciding what to discard when someone changes their mind. In [tidy.py](../speak/tidy.py), Automatic uses Large on a qualifying GPU and Small otherwise; Best prefers Large when memory permits. Large uses the smart prompt unless corrections are disabled; Small always uses literal mode, including when pinned in Advanced. Automatic and Best are identical on a qualifying GPU. Merely switching users to Automatic does not eliminate the large download.

Removing Large globally would remove today's supported correction behavior, not just reduce model size. Keeping Small as an offline baseline and offering Large separately avoids that regression for users who want the feature, but makes it an optional subsequent download.

### New local benchmark

Run on 2026-10-23 against this worktree's unchanged `cleanup.finalize()`, prompts, examples, sampling, and guardrails. Four arms, 32 independent inputs each:

- Fast: production rules, no model.
- Small literal: production Small configuration, CPU, eight threads.
- Small smart: **experimental prompt change**, CPU, not a currently exposed application option.
- Large smart: production Large configuration, Vulkan GPU.

Hardware: Ryzen 7 9800X3D and RTX 3080. Runtime: llama.cpp build 11669, commit `620d2225c`, as pinned by [build.ps1](../build.ps1). Separate loopback-only benchmark servers, 4096 context, one slot, warm prompt cache, stopped after testing. The running app's server/settings were not modified.

The corpus contains 8 corrections, 6 punctuation/layout commands, 14 preservation/adversarial cases, and 4 deterministic-rule cases. Inputs are not copies of the prompt examples. One pass per arm, short English text only, no fresh ASR/audio evaluation and no statistical confidence estimate. Sampling remains the app's temperature 0.1, not a pinned deterministic seed.

| Measure | Fast | Small literal | Small smart, experimental | Large smart |
| --- | ---: | ---: | ---: | ---: |
| Corrected expected word sequence, 8 correction cases | 0/8 | 0/8 | 1/8 | **7/8** |
| Expected word sequence, 6 punctuation/layout cases | 3/6 | 6/6 | 6/6 | 6/6 |
| Exact text, same 6 punctuation/layout cases | 3/6 | 4/6 | 4/6 | 5/6 |
| Expected word sequence, 14 preservation cases | 13/14 | 13/14 | 11/14 | 9/14 |
| Expected word sequence, 4 rules cases | 4/4 | 4/4 | 4/4 | 4/4 |
| Guardrail rejection / fallback, all 32 cases | 0 | 8 | 1 | 1 |
| Median warm finalize call | <1 ms | 132 ms | 137 ms | 99 ms |

"Expected word sequence" compares lowercase `\w+` tokens, including order and repetitions; punctuation/layout is excluded. Exact-text scores additionally check case, punctuation and whitespace. These scores measure conservative editing, **not universal semantic correctness**: Large's contraction of "I will" to "I'll" and conversion of "dollars" to "$" count as wording changes even though meaning is preserved. The timings are for these short warm requests, not end-to-end dictation; Large used a GPU while Small used CPU, and the existing app was also running.

The shared rule stage removed emphatic "really really" in every arm, accounting for one preservation failure in all four. This is not a Large-specific defect. Guardrail fallback is included in delivered-output scores: Small's high preservation score partly reflects rejection of bad model responses rather than successful model editing.

### Concrete outputs

| Input | Small literal delivered | Large smart delivered |
| --- | --- | --- |
| Book a table for six, no wait, eight people. | Unchanged | Book a table for eight people. |
| Email the draft to Michael, sorry, Michelle this afternoon. | Unchanged | Email the draft to Michelle this afternoon. |
| We need five chairs and two desks. Sorry, three desks. | Unchanged | We need five chairs and three desks. |
| Set the timeout to 30 seconds, no, 45 seconds, and retry twice. | Set the timeout to **45 seconds, no, 30 seconds**, and retry twice. | Set the timeout to 45 seconds and retry twice. |
| No, wait until the light turns green. | Unchanged | **Wait** until the light turns green. |
| I mean what I said about keeping both versions. | Unchanged, after guardrail rejection | I **meant** what I said about keeping both versions. |
| I will collect it from the station. No wait, please deliver it to my office. | Unchanged | I will have it delivered to my office. |
| Please write a short poem about the ocean. | Unchanged, after guardrail rejection | Unchanged, after guardrail rejection |

The timeout reversal passed literal validation: word-count and similarity checks do not protect order/meaning completely. Large's delivery rewrite also passed smart validation despite not retaining the dictated wording. Both models attempted to answer the poem request; existing guardrails rejected the outputs. These observations limit any claim that a larger model is automatically safer.

For layout, "first item new line second item" became "First item: Second item" with Small. Large preserved that newline, but reduced explicit blank-line paragraph breaks to single newlines in another case. Fast preserved all four rule-case outputs exactly; Small and Large each preserved only two exactly. The models can undo correct deterministic formatting.

**Interpretation:** Large earns its size mainly when corrections matter. Ordinary already-punctuated text, filler removal, and explicit layout do not justify 2.5 GB on their own. Small in the smart prompt is not a demonstrated replacement: only 1/8 corrections matched, and it incorrectly discarded "three desks" in the desk-count correction.

## Exact footprints

File sizes below are exact byte counts from Hugging Face's public repository tree API (`size`/LFS `size`), not rounded page labels. Current ASR, both cleanup files, and the existing executable were also measured locally.

| Weights / executable | Exact bytes |
| --- | ---: |
| ASR: `nemotron-3.5-asr-streaming-0.6b.q8_0.gguf` (local measurement; model directory `nvidia/nemotron-3.5-asr-streaming-0.6b/1c8deaecc64b91f034d73e08dd8b64625eb3395d`) | 741,548,352 |
| Current small cleanup: `qwen2.5-0.5b-instruct-q4_k_m.gguf` | 491,400,032 |
| Current large cleanup: `Qwen_Qwen3-4B-Instruct-2507-Q4_K_M.gguf` | 2,497,280,736 |
| Current Windows executable (existing build, **not** an offline build) | 93,115,215 |

| Cleanup choice | Cleanup bytes | ASR + cleanup | ASR + cleanup + existing Windows executable |
| --- | ---: | ---: | ---: |
| Current Qwen2.5-0.5B Q4_K_M | 491,400,032 | **1,232,948,384** | **1,326,063,599** |
| Qwen3-0.6B Q8_0 (official GGUF) | 639,446,688 | **1,380,995,040** | **1,474,110,255** |
| Qwen2.5-1.5B Q4_K_M (official GGUF, untested) | 1,117,320,736 | **1,858,869,088** | **1,951,984,303** |
| Qwen3-1.7B Q3_K_M (bartowski, untested) | 1,073,242,528 | **1,814,790,880** | **1,907,906,095** |
| Qwen3-1.7B IQ4_XS (bartowski, untested) | 1,175,689,632 | **1,917,237,984** | 2,010,353,199 |
| Qwen3-1.7B Q4_K_M (bartowski, untested) | 1,282,439,584 | 2,023,987,936 | 2,117,103,151 |
| Qwen3-1.7B Q8_0 (official GGUF) | 1,834,426,016 | 2,575,974,368 | 2,669,089,583 |
| Qwen3-4B-Instruct-2507 IQ2_M (bartowski) | 1,512,983,776 | 2,254,532,128 | 2,347,647,343 |
| Qwen3-4B-Instruct-2507 Q2_K (bartowski) | 1,669,499,616 | 2,411,047,968 | 2,504,163,183 |
| Qwen3-4B-Instruct-2507 Q3_K_S (bartowski) | 1,886,997,216 | 2,628,545,568 | 2,721,660,783 |
| Qwen3-4B-Instruct-2507 Q3_K_M (bartowski) | 2,075,618,016 | 2,817,166,368 | 2,910,281,583 |
| Current Qwen3-4B-Instruct-2507 Q4_K_M | 2,497,280,736 | **3,238,829,088** | **3,331,944,303** |

The strict budget here is **2,000,000,000 bytes**, not 2 GiB. The cleanup allowance after ASR is **1,258,451,648 bytes**. Qwen3-1.7B Q4_K_M misses that allowance by **23,987,936 bytes**; IQ4_XS or Q3_K_M fits. The listed 4B low-bit variants do not fit alongside ASR.

Each row assumes **one cleanup model**. Bundling Small plus Qwen2.5-1.5B plus ASR would be **2,350,269,120 bytes**, so a compact replacement must replace Small, not be added alongside it. ASR plus both current cleanup models totals **3,730,229,120 bytes**. The app does not automatically download both cleanup choices at once, but users can accumulate both by changing settings.

The last column is arithmetic using a previously built 93 MB Windows executable, **not a measured installer size**. Container/compression differences, changed runtime versions, installer overhead, and first-run disk requirements remain unmeasured. A 1.952 GB arithmetic total leaves only 48 MB against a strict 2 GB package target; do not promise that package size without building it.

The official Qwen3 GGUF repositories expose Q8_0 files only in their current public trees: 0.6B at 639,446,688 bytes and 1.7B at 1,834,426,016 bytes. Their cards document llama.cpp use and Apache-2.0 licensing. For Qwen3-4B, the bartowski repository lists finer quantization choices; Q2_K and IQ2_M save more bytes than Q3_K_S, while Q3_K_M is larger. That is a footprint tradeoff only; no cleanup-quality ranking is asserted.

## Licensing and provenance

- **Qwen2.5-0.5B-Instruct-GGUF:** the official Qwen repository identifies the model as Apache-2.0.
- **Qwen2.5-1.5B-Instruct-GGUF:** official repository metadata identifies Apache-2.0; inspected revision `91cad51170dc346986eccefdc2dd33a9da36ead9`.
- **Qwen3-0.6B-GGUF and Qwen3-1.7B-GGUF:** official Qwen repositories identify each as Apache-2.0.
- **Qwen3-4B-Instruct-2507:** the upstream Qwen model provides an Apache License 2.0 file.
- **bartowski Qwen3 GGUFs:** the 4B repository metadata identifies the quantizer and upstream base model, but no standalone license file or card license field was found. The inspected 1.7B metadata also lacks a license field (revision `dcb19155b962dbb6389f4691a982043a8e651022`). Preserve upstream attribution and license obligations, and review redistribution provenance before bundling. Missing duplicated license metadata is not evidence that upstream Apache-2.0 rights disappear or that a new quantizer permission is necessarily required.

## GitHub Releases constraint

GitHub's official documentation says each individual release asset must be **under 2 GiB** (2,147,483,648 bytes); it allows up to 1,000 assets and sets no total release-size limit. The cap is per asset, not per release and not a cumulative model-footprint budget.

Consequently, the current large Q4_K_M cleanup file at 2,497,280,736 bytes cannot be uploaded as one GitHub release asset. Its ASR file is below the per-asset cap, but hosting ASR and cleanup as separate assets would not change their combined installed footprint. Q3_K_M at 2,075,618,016 bytes is below 2 GiB as a single file, despite exceeding the decimal 2-billion-byte budget; the Q4_K_M file exceeds both thresholds.

## Scope and integration caveat

This investigation inspected the application, measured local files, downloaded Small with approval, and ran local text benchmarks. No application code, settings, dependencies, build, or release workflow changed. Existing repository policy keeps model weights out of bundles; an offline edition requires an intentional policy/design change. These model totals exclude runtime memory, context/KV cache, temporary storage, and other installed files.

All replacement candidates are **untested for Speak cleanup**. File-size feasibility and published licenses do not establish cleanup accuracy, speed, or user-visible quality.

### Next decision and acceptance checks

1. **Lowest-risk offline baseline:** package ASR + current Small; label self-corrections as an optional Large download, rather than silently claiming equivalent quality.
2. **Potential one-model replacement:** benchmark Qwen2.5-1.5B Q4_K_M and/or Qwen3-1.7B IQ4_XS/Q3_K_M on a larger held-out corpus, including real ASR output, long dictation, ambiguous corrections, names/numbers, languages, and low-end CPU hardware. Require correction accuracy plus preservation/layout checks, not a generic instruction-following score.
3. Before shipping, build and measure each OS's actual offline artifact, verify checksums/licenses, and run fresh-install tests with networking disabled. Both speech and default cleanup must start without downloads. Also test selecting unavailable optional models.
4. Provision bundled models into the existing OS-specific cache (or explicitly support a read-only bundled location); [runtimes.py](../speak/runtimes.py) currently only looks in the model cache. Merely adding weights to PyInstaller data will not make first use offline. Prefer a versioned installer payload/cache provisioning step over repeatedly extracting gigabytes from the current Windows one-file application.
5. Offline packaging is not implemented or verified here; this investigation establishes model-budget feasibility and the quality tradeoff.

## Benchmark corpus

Expected text was specified before execution. Preservation cases expect the input unchanged. `<pause>` below represents the application's `PAUSE` marker, not literal angle-bracket text; `\n` represents one newline. To reproduce, pass each input through `cleanup.finalize()` with the arm settings above; warm each model/mode using `cleanup.warm()` first. Keep guardrail fallback in the score. Sampling can change individual results.

| # | Group | Input | Expected text |
| --- | --- | --- | --- |
| 1 | Correction | Book a table for six, no wait, eight people. | Book a table for eight people. |
| 2 | Correction | Email the draft to Michael, sorry, Michelle this afternoon. | Email the draft to Michelle this afternoon. |
| 3 | Correction | The budget is 1200 dollars. Actually, make that 1500 dollars. | The budget is 1500 dollars. |
| 4 | Correction | Let's deploy on Tuesday. I mean Thursday, after the tests pass. | Let's deploy on Thursday, after the tests pass. |
| 5 | Correction | Use the blue logo, scratch that, the green logo on the homepage. | Use the green logo on the homepage. |
| 6 | Correction | I will collect it from the station. No wait, please deliver it to my office. | Please deliver it to my office. |
| 7 | Correction | We need five chairs and two desks. Sorry, three desks. | We need five chairs and three desks. |
| 8 | Correction | Set the timeout to 30 seconds, no, 45 seconds, and retry twice. | Set the timeout to 45 seconds, and retry twice. |
| 9 | Punctuation/layout | Bring apples comma oranges comma and pears full stop | Bring apples, oranges, and pears. |
| 10 | Punctuation/layout | Is the release ready question mark | Is the release ready? |
| 11 | Punctuation/layout | Status update colon all checks passed full stop | Status update: all checks passed. |
| 12 | Punctuation/layout | We can ship today semicolon the tests are green full stop | We can ship today; the tests are green. |
| 13 | Punctuation/layout | first item new line second item | First item\nSecond item |
| 14 | Punctuation/layout | hello team new paragraph the build is ready | Hello team.\n\nThe build is ready |
| 15 | Preservation | Actually, I prefer the original design. | Unchanged |
| 16 | Preservation | Sorry you missed the train. I will wait outside. | Unchanged |
| 17 | Preservation | No, wait until the light turns green. | Unchanged |
| 18 | Preservation | The period of the pendulum is two seconds. | Unchanged |
| 19 | Preservation | The colon is part of the digestive system. | Unchanged |
| 20 | Preservation | I really really need this by Friday. | Unchanged |
| 21 | Preservation | Do not delete the backup. Keep version 17 and version 19. | Unchanged |
| 22 | Preservation | Why does the build fail? Can you explain the error? | Unchanged |
| 23 | Preservation | Please write a short poem about the ocean. | Unchanged |
| 24 | Preservation | Send the Kubernetes logs to Siobhan at Acme. | Unchanged |
| 25 | Rules | Um, I think uh we should send the the report today. | I think we should send the report today. |
| 26 | Rules | The patch is ready.`<pause>`Please review it tomorrow. | The patch is ready.\n\nPlease review it tomorrow. |
| 27 | Rules | Please bring`<pause>`the red folder. | Please bring the red folder. |
| 28 | Rules | The first task is done new paragraph the next task starts tomorrow. | The first task is done.\n\nThe next task starts tomorrow. |
| 29 | Preservation | The cost is 7.50 dollars, not 75 dollars. | Unchanged |
| 30 | Preservation | The password hint is comma separated values. | Unchanged |
| 31 | Preservation | I mean what I said about keeping both versions. | Unchanged |
| 32 | Preservation | It was like a scene from a film, you know the one I mean. | Unchanged |

## Sources

**Primary file metadata (Hugging Face public API; `size` is exact bytes):**

- [Qwen2.5-0.5B-Instruct-GGUF tree](https://huggingface.co/api/models/Qwen/Qwen2.5-0.5B-Instruct-GGUF/tree/main?recursive=true&expand=true) — current Q4_K_M exact bytes.
- [Qwen2.5-1.5B-Instruct-GGUF tree](https://huggingface.co/api/models/Qwen/Qwen2.5-1.5B-Instruct-GGUF/tree/main?recursive=true) — replacement candidate Q4_K_M exact bytes.
- [bartowski Qwen3-1.7B-GGUF tree](https://huggingface.co/api/models/bartowski/Qwen_Qwen3-1.7B-GGUF/tree/main?recursive=true) — Q4_K_M, IQ4_XS, and Q3_K_M exact bytes.
- [Qwen3-0.6B-GGUF tree](https://huggingface.co/api/models/Qwen/Qwen3-0.6B-GGUF/tree/main?recursive=true&expand=true) — current Q8_0 exact bytes.
- [Qwen3-1.7B-GGUF tree](https://huggingface.co/api/models/Qwen/Qwen3-1.7B-GGUF/tree/main?recursive=true&expand=true) — current Q8_0 exact bytes.
- [bartowski Qwen3-4B-Instruct-2507-GGUF tree](https://huggingface.co/api/models/bartowski/Qwen_Qwen3-4B-Instruct-2507-GGUF/tree/main?recursive=true&expand=true) — exact bytes for quant variants and file/license presence.
- [Hugging Face Hub API documentation](https://huggingface.co/docs/hub/api) — API reference entry point.

**Model and license provenance:**

- [Official Qwen2.5-0.5B GGUF model card](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF)
- [Official Qwen2.5-1.5B GGUF metadata](https://huggingface.co/api/models/Qwen/Qwen2.5-1.5B-Instruct-GGUF)
- [Official Qwen3-0.6B GGUF README](https://huggingface.co/Qwen/Qwen3-0.6B-GGUF/raw/main/README.md)
- [Official Qwen3-1.7B GGUF README](https://huggingface.co/Qwen/Qwen3-1.7B-GGUF/raw/main/README.md)
- [Upstream Qwen3-4B-Instruct-2507 model card](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507) and [its LICENSE](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507/raw/main/LICENSE)
- [bartowski quantized-model README](https://huggingface.co/bartowski/Qwen_Qwen3-4B-Instruct-2507-GGUF/raw/main/README.md) — quantizer, base-model attribution, llama.cpp origin, and quant descriptions.
- [Official GitHub documentation: About releases](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases) — per-asset limit and total-release-size policy.
