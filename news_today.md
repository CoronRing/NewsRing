# Google Castrates Agent Email, Multi-Agent Scaling Math, and TT-RSI

*2026-11-26 · 7 stories*

![Top AI stories for 2026-11-26](https://coronring.github.io/NewsRing/today.png)

Today's selections unpack Google's aggressive push to corral AI agents behind crippled MCP servers, along with a rigorous look at whether agent communication actually outperforms raw token spend. We also look at test-time recursive self-improvement without labels, agent control loops at DeepMind, and first-person computer use benchmarks.

## Across AI today

- **Anthropic Migrates Messages API from Python to Rust** Anthropic published a technical post detailing how the company migrated its Messages API from Python to Rust. ([anthropic.com](https://www.anthropic.com/research/migrating-api-to-rust))
- **42 State AGs Move to Block Character.AI Chat Auction** A coalition of 42 state attorneys general is seeking to stop Character.AI from selling private user chats in Chapter 11 bankruptcy. ([theverge.com](https://www.theverge.com/policy/1042620/character-ai-sale-state-ags-block-selling-users-chats))
- **Astronomers Use Astra and Codex to Find Exoplanets** Two amateur astronomers used Codex and Astra to find potential exoplanets within public data from NASA's Kepler and TESS space telescopes. ([openai.com](https://openai.com/index/searching-for-distant-planets-with-astra))

## 1. Google Mandates Workspace MCP Servers—and Disarms the Gmail Tools

Google has published a new Workspace AI Tools Addendum requiring any tool that "is or is driven by an AI Agent" to access Workspace strictly via official MCP servers by February 1, 2027. The kicker is that the public Gmail MCP server can only search, read, label, and draft messages; it cannot send, reply, forward, or modify existing drafts, reserving write-side actions for select partner integrations like Claude. The terms also impose a 30-day retention cap on derived vector embeddings and memory indexes, while banning fine-tuning or evaluation on Workspace data. direct REST API calls for agents will be downgraded to low Standard-tier quotas, leaving independent builders in a tight spot.

**Why it matters:** If your agent harness relies on Gmail APIs or maintains long-term memory over user emails, you have about two months before direct REST calls breach terms and your tools lose reply capabilities.

[techstackups.com](https://techstackups.com/articles/google-workspace-ai-agents-mcp/) · [discussion](https://news.ycombinator.com/item?id=50653477) · via Hacker News (AI)

## 2. Evaluating Agent Swarms: Are We Cooperating or Just Burning Compute?

Hugging Face launched a practical series analyzing multi-agent architectures, emphasizing whether inter-agent communication actually yields better results than simply spending an equivalent token budget on a single model. The post references sobering real-world examples, including Noam Brown's estimate that less than 10% of the Navier-Stokes discovery came from multi-agent cooperation, and an Anthropic study where coordinated bug-hunting agents merely consumed more context rather than finding more issues per token. The framework models the problem as a decentralized partially observable Markov decision process (Dec-POMDP) and argues that communication policies must be trained explicitly rather than assumed to be helpful out of the box.

**Why it matters:** It reinforces the critical evaluation baseline for agent systems: always benchmark multi-agent orchestrations against an equal-budget single-agent baseline before declaring architectural victory.

[huggingface.co](https://huggingface.co/blog/training-swarms) · via Hugging Face Blog

## 3. DeepMind Hands Training Compute Scheduling Over to Gemini Agents

According to Google DeepMind VP of Research Koray Kavukcuoglu, autonomous agents have been granted operational control over a portion of DeepMind's compute cluster to run experiments for future Gemini models. Notably, DeepMind implements a deliberate safety measure during agent training by refusing to reward internal chain-of-thought streams, preserving transparent natural language reasoning so that agent intentions remain human-reviewable before execution. Kavukcuoglu downplayed fears of imminent recursive self-improvement, emphasizing that physical understanding remains shallow and current intelligence benchmarks fail to capture true operational trust.

**Why it matters:** A rare glimpse into frontier lab production agent harnesses, particularly the choice to leave internal reasoning unrewarded to maintain interpretability.

[the-decoder.com](https://the-decoder.com/ai-agents-now-control-part-of-deepminds-compute-for-gemini-experiments-but-recursive-self-improvement-remains-distant/) · [discussion](https://news.ycombinator.com/item?id=50661218) · via Hacker News front page

## 4. EgoUseBench: Computer-Use Agents Struggle with First-Person Video Inputs

A new benchmark, EgoUseBench, tests computer-use agents that must take real-world actions grounded in continuous first-person wearable video streams across 693 tasks. Tasks are categorized by information updates into Graft (shifting user goals), Refresh (incoming visual evidence), and Clarify (agent queries). The authors report that advanced models suffer a 26.3% drop in success rates under dynamic Online Ego Use compared to standard instruction-driven Computer-Use, as models struggle to maintain state and invalidate prior digital actions when streaming observations evolve.

**Why it matters:** Shows where current OS-world-model agents break down when tasks require reconciling streaming multi-modal sensory context with desktop state.

[huggingface.co](https://huggingface.co/papers/2611.34466) · via HF Daily Papers

## 5. AMD Fork and Benchmark Dashboard Land for llama.cpp

The community has introduced an AMD-specific fork of llama.cpp alongside an automated performance benchmarking dashboard targeting Ryzen and Radeon silicon. The project aims to track and optimize hardware-specific inference performance on non-NVIDIA local hardware, though technical release details in the primary material remain minimal.

**Why it matters:** Signals growing community attention to optimizing local inference and continuous perf-tracking on AMD hardware.

[devnull.land](https://devnull.land/amd-specific-llama-cpp) · [discussion](https://news.ycombinator.com/item?id=50657265) · [huggingface.co](https://huggingface.co/blog/ggml-org/llamacpp-amd-bench) · via Hacker News front page

## 6. Ollama v0.40.19 Ships Speculative Decoding and Buffer Compaction

Ollama tagged release v0.40.19, upgrading its underlying llama-server backend to incorporate speculative draft proposals and history buffer compaction. Detailed changelog notes were unavailable in the provided material, but the updates target improved inference throughput and memory footprint during extended context interactions.

**Why it matters:** Local agent loops get faster iterations as upstream speculative decoding and context compaction land in standard developer runtimes like Ollama.

[github.com](https://github.com/ollama/ollama/releases/tag/v0.40.19-rc0) · via Ollama releases

## 7. TT-RSI: Distilling Refinement Trajectories at Test Time Beats Majority Voting

Researchers proposed Test-Time Recursive Self-Improvement (TT-RSI), replacing standard test-time self-consistency with iterative in-context revision and on-policy accelerated distillation into weights. By training on the delta between refinement steps rather than voting agreements, TT-RSI gained +13.89% accuracy over base models and beat TTPO+SC by +4.79% under identical compute budgets. However, author discussions highlight a significant failure mode: without an external correctness verifier, the system lacks an error-rejection rule and can distill consistently flawed assumptions directly into model weights.

**Why it matters:** A compelling alternative to majority-vote test-time scaling, along with a candid look at the failure mode of recursive test-time weight updates without formal verifiers.

[huggingface.co](https://huggingface.co/papers/2611.30965) · via HF Daily Papers

## Quick hits

- LangChain's Anthropic integration hit v1.7.13, adding support for custom HTTP and SDK clients. ([github.com](https://github.com/langchain-ai/langchain/releases/tag/langchain-anthropic%3D%3D1.7.13))
- llama.cpp release b12800 adds host-side OpenCL changes for Adreno A850 MoE int8 kernels. ([github.com](https://github.com/ggml-org/llama.cpp/releases/tag/b12800))
- PyTorch announced ExecuTorch-TensorRT support, enabling compiled TensorRT robot policies to run without loading full Python dependencies. ([pytorch.org](https://pytorch.org/blog/executorch-tensorrt-pytorch-robot-policies-at-nvidia-tensorrt-speed/))
- Unsloth's vision-text model Inkling-2-Mini-GGUF crossed 2.4 million downloads on Hugging Face. ([huggingface.co](https://huggingface.co/unsloth/Inkling-2-Mini-GGUF))
- AWS launched the Bedrock Trusted Access API in preview, integrating Anthropic's enterprise safeguards and data controls directly into Claude deployments. ([aws.amazon.com](https://aws.amazon.com/blogs/machine-learning/introducing-the-amazon-bedrock-trusted-access-api-with-anthropics-enterprise-frontier-safeguards-and-enterprise-data-controls/))

Keep your side effects gated and your baselines honest.

---

Written by [NewsRing](https://github.com/CoronRing/NewsRing). Get your own feed, in your own tone.

<sub>35 of 35 sources read. 120 candidates, 120 reviewed, gemini/gemini-3.8-flash, 171s, 3 model calls, $0.0530.</sub>
