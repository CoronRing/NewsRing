# Dynamic Tool Loading, Harness Defaults, and Eval Resolution

*2026-11-19 · 9 stories*

![Top AI stories for 2026-11-19](https://coronring.github.io/NewsRing/today.png)

Today's highlights focus squarely on agent architecture and serving mechanics. Google and AWS are rolling out major harness-level improvements for tool schemas and execution lifecycles, while new research reveals why self-evolving agent loops so frequently hit a wall. On the infrastructure side, Cerebras and NVIDIA tackle the messy reality of production inference pipelines.

## Across AI today

- **Google DeepMind introduces Gemini 4 Neon** Google has expanded its Gemini 4 lineup with the introduction of Gemini 4 Neon. ([deepmind.google](https://deepmind.google/blog/introducing-gemini-4-neon/))
- **Gemini for macOS adds computer use to control desktop apps** The macOS app can now execute multi-step tasks across local files, desktop applications, and the web. ([theverge.com](https://www.theverge.com/tech/1037902/google-gemini-macos-ai-computer-use))
- **ChatGPT rolls out real-time Live Dictation globally** ChatGPT now transcribes audio as you speak across web, desktop, and mobile apps instead of waiting for recordings to finish. ([theverge.com](https://www.theverge.com/ai-artificial-intelligence/1037634/openai-chatgpt-live-dictation))

## 1. Gemini API introduces deferred tool schema retrieval

Google has added native Tool Retrieval to the Gemini API via its Interactions endpoint to tackle context bloat from massive toolsets. By passing a `tool_search` tool and setting `defer_loading: true`, developers can omit parameter schemas from the initial prompt while keeping names and descriptions visible. When the model invokes a deferred tool, the API fetches the full schema and emits the function call within the same request turn. Server-side retrieval works across Gemini 3.6 and Gemini 4 models, preserves prompt prefix caching across turns, supports remote MCP servers, and offers an optional client-side mode for private tool registries.

**Why it matters:** Stashing parameter schemas outside the context window fixes context bloat and degraded tool-selection accuracy when scaling agents up to dozens or hundreds of integrated tools.

[blog.google](https://blog.google/innovation-and-ai/technology/developers-tools/gemini-api-tool-retrieval/) · via Google AI Blog

## 2. Bedrock AgentCore adopts open-source Strands harness defaults

Amazon Bedrock has updated its AgentCore harness to run on the open-source Strands harness foundation, packaging agent execution inside kernel-isolated microVMs. The update brings deterministic lifecycle hooks into the loop, allowing developers to enforce custom guardrails, permission checks, and notifications at specific checkpoints. Managed defaults now include proactive context summarization, context offloading for bulky tool returns, automatic prompt caching on Anthropic models via Bedrock Converse, and built-in tools for planning (`todo_write`), granular filesystem handling, web retrieval, and internal subagent delegation.

**Why it matters:** Lifecycle hooks provide a clean, deterministic mechanism to intercept tool calls and enforce policy without wrestling with non-deterministic agent loop implementations.

[aws.amazon.com](https://aws.amazon.com/blogs/machine-learning/amazon-bedrock-agentcore-harness-adds-strands-harness-defaults-built-in-tools-and-lifecycle-hooks/) · via AWS Machine Learning

## 3. OpenAI evaluates coding agents on research engineering tasks

OpenAI has published an evaluation analyzing how coding agents accelerate internal AI research workloads. The research assesses the jagged boundaries of autonomous execution, examining where model performance remains uneven and detailing specific operational failure modes. The paper looks closely at the implications of these uneven performance limits on the viability of recursive self-improvement loops in production engineering environments.

**Why it matters:** Understanding the failure boundaries and uneven capabilities of coding agents is critical for building realistic harnesses that don't fail when handed autonomous research or engineering tasks.

[openai.com](https://openai.com/index/research-acceleration-jagged-frontier) · via OpenAI News

## 4. Gemini for Mac adds background desktop computer-use

Google has released computer-use capabilities within the Gemini Mac application, letting the model execute multi-step GUI workflows across desktop software, local files, and the browser. Unlike approaches that hijack user input, Gemini runs inside an isolated background window with a live chat preview, leaving the user's primary desktop and cursor unaffected. The interface requires explicit app permission grants, supports mid-task pausing, and prompts for confirmation before executing consequential actions.

**Why it matters:** Running OS-level automation in an isolated background window sidesteps the frustrating UI lockouts typical of desktop computer-use agents.

[blog.google](https://blog.google/innovation-and-ai/products/gemini-app/computer-use-mac/) · [theverge.com](https://www.theverge.com/tech/1037902/google-gemini-macos-ai-computer-use) · via Google Gemini Blog

## 5. Why agent self-evolution stalls: the Resolution Hypothesis

A paper studying agent self-evolution across seven methods and six models (spanning over 1,000 runs and 10 million LLM calls) argues that recursive improvement stalls due to noisy evaluations rather than poor candidate generation. The authors show that score distributions across mainstream benchmarks are frequently multimodal rather than Gaussian. Because evaluator noise exceeds the margins of improvement, artifact selection performs no better than random choice, compounding errors across rounds; similarly, method-level differences of a few percentage points are often smaller than the variance between two runs of the same technique.

**Why it matters:** It explains why LLM-based self-improvement loops fail to bootstrap: your proposer is likely generating viable improvements, but your benchmark and LLM judge lack the resolution to distinguish them from noise.

[huggingface.co](https://huggingface.co/papers/2611.23068) · via HF Daily Papers

## 6. Building robust streaming tool parsers in Rust with NVIDIA Dynamo

NVIDIA shared architectural details on building low-latency tool-calling parsers in Rust using `frontend-crates`, the components powering NVIDIA Dynamo. The post details the operational headaches of processing streaming tokens, including mid-stream syntax truncation, semantic mismatches like unauthorized tools, and boundary recognition without markup leakage. To ensure reliable extraction without masking raw model outputs, the system relies on language-neutral YAML fixtures in a shared Conformance Corpus covering interleaved, malformed, and streaming token cases across multiple model families.

**Why it matters:** Production agent frameworks frequently break on malformed streaming tool calls and marker leaks, making formal conformance testbeds and low-level Rust parsers essential infrastructure.

[developer.nvidia.com](https://developer.nvidia.com/blog/build-tool-calling-parsers-in-rust-with-ai-agents/) · via NVIDIA Developer

## 7. QDA uses closed-loop coding agents to optimize LLM quantization

Researchers have introduced QDA, a framework where an LLM agent designs and refines post-training quantization (PTQ) schemes in an autonomous loop. To bypass lengthy benchmark runs, QDA scores candidate configurations in minutes using KL divergence against unquantized reasoning traces, backed by long-generation tests to catch pathological failure modes like repetition loops. Across four reasoning models, QDA improved accuracy over strong public baselines by up to 2.2 points at W3A16, and recovered 98.3% of FP8 accuracy on GLM-5.3-Flash at NVFP4 with zero inference kernel overhead.

**Why it matters:** Combining rapid proxy metrics with a stackable quantization library shows how agents can effectively navigate complex, hardware-specific optimization spaces that usually demand human experts.

[huggingface.co](https://huggingface.co/papers/2611.23388) · via HF Daily Papers

## 8. Cerebras pairs GPUs with Wafer-Scale Engines for disaggregated serving

Cerebras has deployed a disaggregated inference architecture in production that offloads the prompt processing (prefill) phase to GPUs—specifically AMD Instinct chips—while dedicating Cerebras Wafer-Scale Engines exclusively to autoregressive decode. Leveraging the massive SRAM capacity and memory bandwidth of the CS-3 system for decode while offloading compute-heavy prefill yielded a 5x improvement in throughput per megawatt compared to an aggregated CS-3 deployment. The architecture communicates intermediate KV cache state over RDMA via Cerebras' KV Portal software, supporting integrations with vLLM and SGLang.

**Why it matters:** Decoupling memory-bandwidth-bound decode from compute-bound prefill across distinct hardware architectures represents the next major efficiency leap for ultra-low-latency agent serving.

[cerebras.ai](https://www.cerebras.ai/blog/cerebras-launches-disaggregated-inference) · [discussion](https://news.ycombinator.com/item?id=50540472) · via Hacker News (AI)

## 9. MAI releases Code 2 and Code 2 Flash for enterprise coding tasks

MAI has launched MAI Code 2 and Code 2 Flash, two models optimized specifically for common enterprise coding workflows like multi-file edits, repo reasoning, and debugging. Benchmarked across DeepSWE 1.1, Terminal Bench 2.1, SWE-Atlas, and FrontierCode v1.1, MAI claims Code 2 delivers 98% of GPT-6.1 Sol's performance at 40% of the cost, while intentionally avoiding tuning for long-horizon agentic or scientific problems. MAI Code 2 Flash targets high-volume tasks such as rapid edits and inline explanations, with specialized variants already deployed across Microsoft 365 and FabricIQ products.

**Why it matters:** The deliberate decision to optimize for narrow, high-frequency repository edits over open-ended long-horizon agency offers a pragmatic, cost-effective alternative for daily software tasks.

[microsoft.ai](https://microsoft.ai/news/introducing-mai-code-2-and-mai-code-2-flash/) · [discussion](https://news.ycombinator.com/item?id=50535885) · via Hacker News (AI)

## Quick hits

- LangChain OpenAI 1.8.5 fixes streamed Responses tool call argument preservation and standardizes message-finish event reasons. ([github.com](https://github.com/langchain-ai/langchain/releases/tag/langchain-openai%3D%3D1.8.5))
- Llama.cpp build b12555 adds OpenCL support for dp4a in decomposed flash attention and int8 KQ matrix multiplication. ([github.com](https://github.com/ggml-org/llama.cpp/releases/tag/b12555))
- Amazon Bedrock AgentCore payments now allows agents to purchase x402-enabled APIs and tools from AWS Marketplace directly via the developer's AWS bill. ([aws.amazon.com](https://aws.amazon.com/blogs/machine-learning/enable-ai-agents-to-pay-for-aws-marketplace-x402-products-with-amazon-bedrock-agentcore-payments/))
- Fuck Your AI Safeguards ([ounapuu.ee](https://ounapuu.ee/posts/2026/11/19/unsafeguards/))
- SageMaker AI inference endpoints now automatically monitor for latency drift, idle GPUs, and sub-optimal serving configurations. ([aws.amazon.com](https://aws.amazon.com/blogs/machine-learning/amazon-sagemaker-ai-now-detects-latency-drift-idle-gpus-and-missed-optimizations-on-your-inference-endpoints/))
- Cloudflare's Workers AI team has open-sourced the weights for extraction models Clairic and Clairic-flash. ([blog.cloudflare.com](https://blog.cloudflare.com/open-clairic/))

May your schemas stay cached and your eval variance stay low.

---

Written by [NewsRing](https://github.com/CoronRing/NewsRing). Get your own feed, in your own tone.

<sub>35 of 35 sources read. 151 candidates, 80 reviewed, gemini/gemini-3.8-flash, 819s, 6 model calls, $0.1232.</sub>
