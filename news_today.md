# Eval Brittleness, Harness-Tuned Adapters, and Agent Token Fraud

*2026-11-21 · 7 stories*

![Top AI stories for 2026-11-21](https://coronring.github.io/NewsRing/today.png)

Today's highlights focus on the fragile mechanics of agent evaluation, a practical recipe for training models directly inside target runtime harnesses, and distributed KV caching architecture for self-hosted agent fleets. We also examine real-world fraud vectors weaponizing agent loops in production and a bold mathematical claim made alongside Claude.

## Across AI today

- **Signal Blocks Mobile AI Agents from Reading Screens** Signal is restricting screenshots on Android and iOS to prevent system AI agents like Gemini and Siri from reading messages and on-screen data. ([theverge.com](https://www.theverge.com/ai-artificial-intelligence/1038390/signal-blocking-ai-agent-screenshots-mobile-app))
- **Canary Tests Expose Severe Data Leaks Across AI Pipelines** An audit planting unique, trackable canary secrets into two million prompts demonstrated that data sent through the AI supply chain fails to stay private. ([arstechnica.com](https://arstechnica.com/security/2026/11/a-leaky-ai-supply-chain-is-exposing-secret-user-data-at-an-alarming-rate/))
- **OpenAI Unveils Protections Against Adversarial Distillation** OpenAI detailed a multi-layered approach combining model training, safeguards, detection, and enforcement to prevent capability extraction. ([openai.com](https://openai.com/index/combatting-adversarial-distillation))

## 1. Why Public Benchmarks Fail Correct Agent Work

Eugene Yan analyzed twelve prominent public benchmarks across coding, knowledge work, and computer use, uncovering that eight had graders that actively failed correct solutions. Many benchmark suites enforce strict all-pass criteria where a single flawed assertion drops the entire score, while checks frequently evaluate unstated requirements—affecting 41 of 65 tasks in Terminal Bench 4.0 and 23 of 113 in DeepSWE. On the model side, the dominant failure modes are skipping end-state verification and failing basic instruction constraints.

**Why it matters:** If you rely on public evals to pick frontier or coding models, knowing how common false negatives and unstated constraints are is vital before trusting raw benchmark deltas.

[eugeneyan.com](https://eugeneyan.com/writing/public-evals) · via Eugene Yan

## 2. Hugging Face Introduces In-Harness RL Adapters

Hugging Face shared a recipe to optimize open models for specific agent runtimes by running reinforcement learning directly inside target harnesses rather than simulated abstraction loops. Testing Qwen3.8-27B across Pi, OpenCode, and Hermes Agent with Harbor tasks, they trained custom LoRA adapters using TRL's AsyncGRPOTrainer via a proxy capturing exact token emissions. On Terminal-Bench 2.1 under the Pi harness, the adapter boosted pass@1 from 39% to 55% while dropping average token usage from 2.9K down to 1.5K through crisper tool calls and less redundant reasoning.

**Why it matters:** Training directly against your production agent harness and tool interfaces eliminates distribution shift and cuts intermediate token bloat significantly.

[huggingface.co](https://huggingface.co/blog/harness-adapters-at-scale) · [huggingface.co](https://huggingface.co/harness-hub/Qwen3.8-27B-pi-adapted) · via Hugging Face Blog

## 3. AWS Automates Distributed KV Cache Tuning for Agents

AWS published an architectural guide and agent skill to evaluate and configure distributed KV caching for self-hosted vLLM and SGLang fleets via ElastiCache. By integrating an LMCache connector over RDMA-enabled nodes, servers can externalize prefix KV states across prolonged, multi-turn agent sessions. The accompanying skill uses a diagnostic tool named KVTrace to simulate access patterns, calculating whether context reuse offsets loading latency before generating infrastructure configurations.

**Why it matters:** Multi-turn agent loops with long prompt histories suffer severe TTFT penalties on self-hosted inference; externalized KV caches resolve cold prefill across routing changes.

[aws.amazon.com](https://aws.amazon.com/blogs/machine-learning/cut-self-hosted-llm-cost-and-latency-with-the-distributed-kv-caching-agent-skill/) · via AWS Machine Learning

## 4. Anthropic Researcher Claims GRH Proof With Claude

Anthropic researcher Levent Alpöge published a claimed proof of the Generalized Riemann Hypothesis developed in collaboration with Claude. Alpöge stated that the underlying method resolves the GRH and could extend to the Extended Riemann Hypothesis, noting that the arguments were formalized without assumptions. Alpöge highlighted Claude's velocity near the completion of the work, describing the model as outpacing him in the final stages of the proof.

**Why it matters:** If the formalization withstands peer review, it marks a significant validation of frontier LLM reasoning applied directly to open Millennium Prize problems.

[simonwillison.net](https://simonwillison.net/2026/Nov/20/levent-alpoge/) · [theverge.com](https://www.theverge.com/ai-artificial-intelligence/1010051/anthropic-riemann-hypothesis-millennium-prize-problem) · [alpo.ge](https://alpo.ge/remark.pdf) · via Simon Willison

## 5. Attackers Weaponize Agent Free Trials for Token Arbitrage

ChatPRD creator Claire Vo detailed emerging abuse patterns targeting her production product management agent, ultimately forcing the removal of free trials. Fraud rings weaponized automated sign-up loops and promo codes to tunnel external workloads through the agent to build gaming maps and resell tokens. Vo noted that attackers repeatedly sent probe prompts—such as SVGs of pelicans riding bicycles—specifically designed to fingerprint the underlying model family being exploited.

**Why it matters:** Exposing tool-enabled agents via generous free tiers invites immediate prompt tunneling and model fingerprinting attacks aimed at reselling your upstream tokens.

[simonwillison.net](https://simonwillison.net/2026/Nov/20/token-fraud-is-here-and-its-bad/) · via Simon Willison

## 6. LangChain Core 1.8.4 Normalizes Finish Events

LangChain released langchain-core 1.8.4 with two targeted framework updates. The release standardizes the finish reason format across distinct LLM providers on message-finish events and adds source metadata tagging to synthetic human-in-the-loop tool messages.

**Why it matters:** Standardizing finish reasons simplifies multi-provider agent orchestrators, while synthetic HITL tagging improves trace hygiene in human-in-the-loop flows.

[github.com](https://github.com/langchain-ai/langchain/releases/tag/langchain-core%3D%3D1.8.4) · via LangChain releases

## 7. Standard Bank Deploys Automated LLM-as-a-Judge Auditing

Standard Bank Group implemented an automated governance pipeline using Amazon Bedrock LLM judges orchestrated by AWS Step Functions. To approve generative use cases without manual risk bottlenecks, a pre-assessment agent on AWS Fargate extracts evidence from repositories and documentation into a 40-question Well-Architected lens. The pipeline directly stress-tests deployments with automated jailbreak probes and checks semantic consistency across reworded prompts via embedding models before escalating findings to human committees.

**Why it matters:** A concrete enterprise reference implementation for structuring LLM-as-a-judge pipelines to automate compliance, jailbreak scanning, and policy audits.

[aws.amazon.com](https://aws.amazon.com/blogs/machine-learning/how-standard-bank-group-automates-ai-risk-assessment-for-generative-ai/) · via AWS Machine Learning

## Quick hits

- llama.cpp release b12612 optimizes Vulkan MMVQ performance on AMD RDNA4 hardware for Q3_K, Q5_K, and IQ4_XS quantizations. ([github.com](https://github.com/ggml-org/llama.cpp/releases/tag/b12612))
- SageMaker HyperPod launched Global Inference Gateway, providing a single SigV4-authenticated endpoint that routes across multi-region clusters with automatic failover. ([aws.amazon.com](https://aws.amazon.com/blogs/machine-learning/introducing-amazon-sagemaker-hyperpod-global-inference-gateway-one-endpoint-across-regions-and-clusters/))
- NVIDIA introduced Dynamo to tackle worker inference rollout bottlenecks in reinforcement learning training pipelines. ([developer.nvidia.com](https://developer.nvidia.com/blog/reducing-rollout-bottlenecks-in-reinforcement-learning-with-nvidia-dynamo/))
- Ollama v0.40.17 adds support for Inkling 2 Mini, a 26B parameter (5.4B active) looped-layer vision and tool-calling model scoring 79.2% on benchmarks. ([github.com](https://github.com/ollama/ollama/releases/tag/v0.40.17))

May your test assertions pass without unstated requirements today.

---

Written by [NewsRing](https://github.com/CoronRing/NewsRing). Get your own feed, in your own tone.

<sub>35 of 35 sources read. 124 candidates, 124 reviewed, gemini/gemini-3.8-flash, 221s, 3 model calls, $0.0505.</sub>
