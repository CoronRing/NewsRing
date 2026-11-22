# Agent Laws over MCP, Gradient-Free Weight Edits, and DOS Harnesses

*2026-11-22 · 8 stories*

![Top AI stories for 2026-11-22](https://coronring.github.io/NewsRing/today.png)

Today's digest covers European legal tooling delivered directly over MCP, along with research showing open models editing their own weights without backprop. We also look at security incidents across inference providers, multi-agent orchestration updates, and an agent harness running on an 8088.

## Across AI today

- **OpenAI tests GPT-6 Astra on financial research tasks** Pre-release evaluations with Hebbia showed GPT-6 Astra gained in source coverage, citation relevance, and presentation quality. ([openai.com](https://openai.com/business/customer-stories/hebbia))
- **Apple releases Depth Pro 2 for 3D depth estimation** Depth Pro 2 estimates dense metric depth for full-resolution images and videos with improved temporal consistency and sharp boundaries. ([huggingface.co](https://huggingface.co/papers/2611.26603))
- **Mod_wsgi creator launches AI-assisted Rust server Muru** Muru is a new AI-assisted Rust server designed for running ASGI and WSGI Python applications in production. ([simonwillison.net](https://simonwillison.net/2026/Nov/21/muru/))

## 1. Pandex Serves European Law to Agents via MCP

Pandex has launched an official API and MCP server delivering 2.8 million legal documents across the EU and seven European countries. The platform integrates with existing tools like Claude, Cursor, and Zed, linking 37 million citations directly to their text. It provides past versions and effective dates for legislation alongside court decisions, though a few sources remain partially restricted by Cloudflare challenges or browser checks. While in beta, agents can make up to 1,000 free requests per day, giving developers a turnkey way to ground legal workflows in official sources.

**Why it matters:** It provides a standardized MCP server and API for retrieval-augmented legal workflows across European jurisdictions.

[pandex.io](https://www.pandex.io) · [discussion](https://news.ycombinator.com/item?id=50593481) · via Hacker News (AI)

## 2. OpenRouter Offboards Inference Providers Following Security Report

OpenRouter announced actions taken following a security report by Dragos that exposed compromised data handling and failed privacy policies among third-party inference providers. In response, OpenRouter off-boarded three providers, removed 125 endpoints from Zero Data Retention eligibility, and notified affected customers. Specific announcements from providers like Together revealed past prompt leakage events from June and July 2026. OpenRouter is now integrating the researchers' testing methods into its ongoing network verification pipeline to continuously validate network paths and data retention claims.

**Why it matters:** Real-world data leaks and zero-data-retention failures across third-party API providers highlight concrete security risks for production agent deployments.

[openrouter.ai](https://openrouter.ai/blog/announcements/data-processing-incidents-on-inference-providers/) · [discussion](https://news.ycombinator.com/item?id=50595554) · via Hacker News (AI)

## 3. Self-Rewriting LLMs Edit Their Own Weights Without Gradients

Researchers demonstrated that a 27B parameter open language model can directly edit its own network weights through reasoning alone, requiring zero gradients or traditional training infrastructure. Given its weights, graded outputs, and execution capabilities, the model diagnosed its failure modes and boosted its accuracy by 6.6 percentage points on 490 unseen test problems across eight self-improvement sessions. The mechanism also repaired a damaged copy of itself, lifting its performance on unseen image benchmarks from 7% to 70% accuracy without ever accessing the undamaged weights. Notably, this self-editing capability emerged only at scale, as smaller 2B to 9B models either failed to make edits or broke themselves.

**Why it matters:** Gradient-free weight self-editing offers a novel mechanism for open-weight models to self-adapt and repair without retraining infrastructure.

[huggingface.co](https://huggingface.co/papers/2611.21885) · [huggingface.co](https://huggingface.co/papers/2611.26408) · via HF Daily Papers

## 4. ClawDOS Runs an Autonomous Coding Agent on an IBM PC XT

ClawDOS is a native 176 KB DOS harness that runs an autonomous Claude-powered coding agent directly on an IBM PC XT with an 8088 CPU and 640K of RAM. The 8088 executes all logic, parses streamed API responses, and drives 18 local tools including Turbo C and GW-BASIC, relying on a bridge PC solely to offload TLS. To handle memory constraints during builds, ClawDOS saves its state to disk, exits RAM to grant Turbo C 450K of free memory, and resumes the conversation once compilation finishes. The system maintains persistent state and memory across power cycles, demonstrating tool execution and screenshot capture on 1980s hardware.

**Why it matters:** Operating inside severe hardware and memory constraints demonstrates extreme harness optimization and native tool-use orchestration.

[ricapar.net](http://ricapar.net/ClawDOS/) · [discussion](https://news.ycombinator.com/item?id=50586292) · via Hacker News (AI)

## 5. FlashMorph2 Optimizes Transformer Conversion into Hybrid Attention

FlashMorph2 introduces an on-policy layer selection and weight adaptation method to convert pretrained full-attention Transformers into hybrid attention architectures. By evaluating sampled discrete hybrid architectures end-to-end with their own hidden states and jointly optimizing layer-selection scores with model weights, it resolves off-policy mismatches found in earlier conversion techniques. Benchmarks across Qwen3 models show gains of +2.42 points on RULER and +1.08 points on LongBench over FlashMorph. The entire selection process completes in 0.72 to 3.57 GPU hours for models ranging from 0.6B to 8B parameters.

**Why it matters:** Fast on-policy layer selection provides an efficient path to optimize inference engines for long-context workloads.

[huggingface.co](https://huggingface.co/papers/2611.24809) · via HF Daily Papers

## 6. AWS Quick Adds Multi-Agent Orchestration and Chat-Built Flows

AWS has updated its Quick workspace with native multi-agent orchestration that allows several specialized agents to work on a single prompt simultaneously and merge their results into one response. Users can now build, run, and refine multi-step flows entirely in chat, incorporating deterministic steps and handling longer-running workflows with larger data volumes. The web app update introduces a unified home screen for daily briefings, cross-device skill sync, and background execution after browser tabs close. Additionally, AWS expanded integration connectors to include Meta ads and Amplitude alongside governance controls for content safety.

**Why it matters:** AWS is introducing native multi-agent collaboration and deterministic workflow orchestration into its enterprise agent platform.

[aws.amazon.com](https://aws.amazon.com/blogs/machine-learning/new-in-aws-quick-more-capable-flows-an-updated-web-experience-and-agents-that-work-together/) · via AWS Machine Learning

## 7. Transformers v5.24.0 Adds Inkling 2 Mini, Apertus 1.5, and Architecture Updates

Hugging Face released Transformers v5.24.0, introducing official model implementations for Inkling 2 Mini, Apertus 1.5, Dory, HY4-VL, Omnilingual ASR, Lara Mini, SarvamMLA, and SarvamMoE. Inkling 2 Mini features a 24-layer decoder that loops over middle layers three times with NVFP4 and MXFP8 quantization, while Dory implements looped latent-recurrent sliding-window and full attention. Apertus 1.5 integrates text with EMU3.5 vision and WavTokenizer audio encoders into a shared input vocabulary. The release also introduces a breaking change by unifying past_key_values and cache_params under a single cache parameter.

**Why it matters:** New framework support brings looped architectures, multimodal audio/vision pipelines, and a breaking cache API change to open-weight models.

[github.com](https://github.com/huggingface/transformers/releases/tag/v5.24.0) · via Transformers releases

## 8. OpenAI Argues Pretraining Perplexity Is the Primary Benchmark for Emergent Capabilities

OpenAI published internal pretraining perplexity data spanning from GPT-3.5 to current models, advocating for cross-entropy loss on held-out datasets as a primary benchmark for AI progress and safety pacing. The post traces how drops in log-perplexity from ~0.99 down to ~0.76 correlate directly with emergent latent capabilities, including context learning, chain-of-thought reasoning, and frontier mathematics problem solving. OpenAI suggests that as models reach the ~0.68 to 0.7 log-perplexity window, further qualitative leaps in capabilities will emerge. The authors argue that while downstream task benchmarks saturate quickly, tracking compression efficiency remains a durable indicator across model generations.

**Why it matters:** Using cross-entropy loss as a standardized benchmark directly impacts how model progress and capabilities are evaluated over task-based benchmarks.

[openai.com](https://openai.com/index/perplexity-and-intelligence/) · [discussion](https://news.ycombinator.com/item?id=50601525) · via Hacker News front page

## Quick hits

- A new Show HN project flips the script by placing human players in the role of a subagent executing tasks for an LLM. ([github.com](https://github.com/gulivan/worker755))
- Release b12633 of llama.cpp fixes non-zero clear issues on WebGPU and non-UMA devices in ggml. ([github.com](https://github.com/ggml-org/llama.cpp/releases/tag/b12633))
- Creator of mod_WSGI Graham Dumpleton launched Muru, an AI-assisted Rust server designed to run ASGI and WSGI Python web applications in production. ([simonwillison.net](https://simonwillison.net/2026/Nov/21/muru/))
- Mathematicians are making progress on a human-only proposed proof of the Generalized Riemann Hypothesis without using AI. ([simonwillison.net](https://simonwillison.net/2026/Nov/20/ravi-vakil/))
- New research suggests RL post-training in diffusion transformers operates primarily through activation steering to improve visual quality and prompt adherence. ([huggingface.co](https://huggingface.co/papers/2611.26627))

Keep your context clear and your memory uncorrupted until tomorrow.

---

Written by [NewsRing](https://github.com/CoronRing/NewsRing). Get your own feed, in your own tone.

<sub>35 of 35 sources read. 95 candidates, 95 reviewed, gemini/gemini-3.8-flash, 57s, 3 model calls, $0.1434.</sub>
