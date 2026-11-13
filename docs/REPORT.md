# The Relay: Two-Page Report

## 1. What I built and why
I built a Python asyncio RAG pipeline with a single shared gateway. The decision that shaped it most was **the gateway owns all rate-limit state and admission control**. Without it, every request retries independently, leading to the retry storms seen in Section 6. The pipeline has 5 steps: Understand (LLM), Retrieve (Tool), Decide (Code), Draft (LLM), Verify (Code).

## 2. The real service and my stand-in
**Real limits found:** 8,000 TPM, 1,000 RPD, 30 RPM (from live headers). 429s return `retry-after: 2` and daily reset headers.
**Stand-in calibration:** The stand-in mimics Groq's wire format. Its latency is UNCALIBRATED (invented). Where it differs most: it cannot simulate Groq's queue time or the exact 429 edge-case behaviour. The invariant checker proved the pipeline handles the stand-in's 429s correctly.

## 3. Results
All stand-in runs are marked UNCALIBRATED. Real runs are marked GROQ.
| Load Shape | Backend | p50 TTFT | p95 Total | Failures | Given Up |
|---|---|---|---|---|---|
| Steady | Stand-in | 0.18s | 0.18s | 0 | 0 |
| Burst | Stand-in | 0.18s | 0.18s | 0 | 0 |
| Overload | Stand-in | 0.18s | 0.81s | 40 | 0 |
| 1 Call | Groq | 0.29s | 0.49s | 0 | 0 |

**Number we couldn't have guessed:** The provider's TPM counter and the dashboard disagree. A call charged 156 tokens to the TPM bucket but the dashboard showed 117. Also, reasoning tokens eat the completion cap: a cap of 5 returned 3 reasoning tokens and empty content.
**Quality & Tokens:** Evaluated 30 questions. The 900/150 chunking was the best (50% recall).

## 4. Where the time goes
A slow request (overload) spent 80% of its time in WAITING (queue) and RETRYING (backoff). The delay came entirely *before* the first token. The pipeline's own latency (retrieval + verification) was < 50ms.

## 5. When a limit is hit
**Minute limit:** Bursting 40 requests produced a 429 after 1 success. The gateway caught the `retry-after: 2` and queued the rest. Nobody was turned away; they just waited 2 seconds.
**Day limit:** The gateway refuses locally before sending. The user gets a `PassagesOnly` reply with the 3 best chunks and a message "The model is busy; here are the passages that would answer this."

## 6. Retries
**Policy:** Managed (backoff + jitter + retry budget). 
**Case where retrying made it worse:** In an isolated test, a naive loop (no backoff, ignores 429) sent 489 requests and crashed the Python interpreter with a `RecursionError`. The managed gateway sent 1 request and failed cleanly.

## 7. What the person sees
At 3pm, daily budget is gone. The person sees the retrieved passages from the papers with a message: "I could not spend the budget to answer; here are the passages that would."

## 8. What I'm unsure about, what I left out, what I learned
**Least certain assumption:** The stand-in's latency. If it's wrong, all stand-in TTFT numbers are meaningless.
**Deliberately not built:** A semantic (embedding) cache, and a persistent queue (Redis). Both add complexity and cost without proving the core trade-off.
**New to me:** The difference between RPD (Requests Per Day) and TPM (Tokens Per Minute). I learned that token limits bind much faster than request limits for RAG.

## Retrieval: quality versus cost
Tested 600/100, 900/150, and 1200/200. At fixed k, 1200 won. At equal character budget (3600 chars), 900/150 won (50% recall, 0.41 MRR). 900/150 is the chosen setting. When the limit is close, I reduce k from 4 to 2.

## How this library misleads a naive retriever
1. **PDF extraction damage:** Tables become broken text. Question: "What is the BLEU score?" retrieves the wrong row.
2. **Shared vocabulary:** "Attention" exists in both Transformer and Moshi. A question about Moshi might retrieve a Transformer chunk.
3. **Near-miss:** Asking about a benchmark not in the papers still retrieves *some* chunk due to word overlap, prompting the gate to let it through.

## Your feedback on Vaani
I used Vaani for 10 minutes. It felt very fast and conversational. The UI was clean. One thing that confused me was the lack of context when I asked a follow-up question. I would change the onboarding to explain how it handles memory.

## How I worked with the assistant
*(Chat logs are in docs/CHAT_LOG/)*
**Three prompts that mattered most:**
1. The initial master prompt defining the constraints (speed vs cheap vs truth).
2. The prompt to build the invariant checker, which caught the backend field collision.
3. The prompt to build the stand-in server, which allowed us to test 240 overload requests for free.

**One thing it got wrong that I caught:** It wrote a test that passed for the wrong reason because the regex matched a neighbouring line. I tightened it to same-line matching, which immediately found 5 undocumented nulls in the YAML.
**One decision where I overruled it:** The assistant wanted to drop the run-level `backend` field entirely to avoid collisions. I overruled it: the field is critical for separating real vs. stand-in data. We kept the field and renamed the per-attempt one to `attempt_backend`.
