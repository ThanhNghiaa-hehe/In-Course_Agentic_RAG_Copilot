# HJS Manuscript — Variant B (Socratic Pedagogy)

> **Nguồn số liệu (đã đối chiếu trực tiếp với JSON, tính lại mẫu số từng lượt):**
> `docs/benchmarks/latest_benchmark_results.json` (Stage 11, N = 200: Router 182/200, CRAG 173/200);
> `docs/benchmarks/multiturn_benchmark_results.json` (50 phiên / 222 lượt: Intent 219/222, Status 218/222, ARR 93/94, SRP 15/15, Multi-grounding TS 220/222, Strict WHR 119/222, Budget 222/222);
> `docs/benchmarks/multiturn_benchmark_e2e_results.json` (e2e, 15 phiên / 60 lượt, 30 lượt sinh LLM thật, tuân thủ Socratic 30/30).
> **Section III** (System Architecture & Mathematical Formulation, Table 1, công thức OMML) được giữ nguyên từ `scripts/build_full_hjs_paper.py`, không soạn lại ở đây.
> Biến thể B nhấn mạnh **góc nhìn sư phạm Socratic** (hạn chế rò rỉ lời giải, giữ nỗ lực học tập của sinh viên); Biến thể A nhấn mạnh thuật toán.

---

**GUARDING THE PRODUCTIVE STRUGGLE: A SOCRATIC, VIDEO-GROUNDED AGENTIC RAG COPILOT FOR IN-COURSE PROGRAMMING TUTORING**

**Tran Thanh Nghia**\*
Faculty of Information Technology (Student ID: 23DH112252),
Ho Chi Minh City University of Foreign Languages – Information Technology (HUFLIT), Ho Chi Minh City, Vietnam
\*Corresponding author: nghia.23dh112252@st.huflit.edu.vn

---

## ABSTRACT

Conversational large language models (LLMs) lower the barrier to help-seeking in programming courses, yet they readily output complete solutions that remove the productive struggle on which novice learning depends. At the same time, an assistant that is attached to long lecture videos (30–60 minutes) must answer from the *right* lesson and point to a *verifiable* video moment, or its guidance cannot be trusted. This paper presents *In-Course Agentic RAG Copilot*, a Socratic tutor for a C++/object-oriented programming course that treats pedagogy as an enforceable system property rather than a prompting request. The tutor is a four-node LangGraph state machine (router, hybrid retrieval, Corrective-RAG grader, context assembly) in which (i) a cascade router with an NLI arbiter decides whether a message is a course question, (ii) a three-tier Pareto Context Sufficiency boundary separates semantic relevance from pedagogical sufficiency, and (iii) a deterministic timestamp whitelist and a bounded sliding-window memory constrain what the tutor may say and cite. On a 200-query single-turn golden benchmark the system reaches **91.0%** router accuracy and **86.5%** CRAG grading precision. On a deterministic multi-turn suite of 50 sessions (222 turns) it reaches **98.65%** intent accuracy, **98.20%** retrieval-status accuracy, **98.94%** Anaphora Resolution Rate (ARR) and **100.0%** Socratic Refusal Precision (SRP), with every dialogue context inside a 2,400-character budget. We report the remaining weaknesses candidly: strict single-label timestamp matching (53.6%), an adversarial-hybrid tier (70.0% router accuracy), and a small solicitation sample behind the SRP figure (15 of 15).

**Keywords** — Socratic Tutoring, Agentic RAG, Corrective RAG (CRAG), Pedagogical Guardrails, Pareto Context Sufficiency, Anaphora Resolution, LangGraph Orchestration, Video-Grounded Learning.

---

## I. INTRODUCTION

Asynchronous video lectures are the backbone of programming curricula, including the C++ and object-oriented programming (OOP) sequences taught at HUFLIT. A novice who meets a compiler error or a memory fault is rarely helped by scrubbing through a 52-hour video library; what helps is a short explanation of the *concept* behind the error, a pointer to the relevant lecture moment, and a question that moves the student one step forward. General-purpose chat assistants do almost the opposite. Studies of AI code generators in introductory programming show measurable benefits for task completion but also a risk of over-reliance when complete code is supplied [13], [14], and instructors have therefore begun to deploy assistants with guardrails that withhold direct solutions [14], [15].

Building a tutor that follows the Socratic method [11] over lecture video exposes three coupled problems.

1. **Pedagogical leakage.** When a student writes "just give me the full code", an unconstrained LLM complies. A tutor must explain the error, ask a guiding question and decline to write the assignment — and it must do so reliably, not "usually".
2. **Wrong-lesson grounding.** Lecturers often preview later topics in passing. Such remarks share vocabulary with the dedicated lecture and can reach similar cosine similarity, so a naive top-*k* retriever answers from the wrong lesson. Semantic relevance is not sufficient context: a passage can be topically close and still lack the information needed to answer [2].
3. **Conversational fragility.** Real help-seeking is multi-turn and elliptical ("what about the second one?"). A tutor must resolve such references without carrying stale keywords across topic changes, while keeping the prompt short enough to avoid the lost-in-the-middle effect [3].

This paper treats each of the three as an explicit, auditable gate rather than as a prompt instruction. The contributions are:

- **C1 – Pedagogy as an invariant.** Socratic refusal, verified video seconds and a bounded history are enforced by deterministic components around the LLM (an input guardrail, a timestamp whitelist, a 2,400-character budget), and are measured with a dedicated metric, Socratic Refusal Precision (SRP).
- **C2 – Sufficiency-aware grounding.** A three-tier Pareto Context Sufficiency boundary decides when a future lesson may displace the current one, so that the tutor neither answers from a passing remark nor hijacks a question that the current lesson already teaches.
- **C3 – Cascade routing with NLI rescue.** A fast intent classifier handles clear cases; a natural-language-inference arbiter [9], [10] handles ambiguous ones with zero-shot reasoning instead of hand-written regular expressions.
- **C4 – Multi-turn evaluation of pedagogy.** A 50-session, 222-turn deterministic benchmark with four stress tiers (ellipsis/anaphora, Socratic refusal, topic switching, context budget), plus a 200-query single-turn held-out benchmark.

The remainder of the paper is organized as follows: Section II reviews related work, Section III presents the architecture, Section IV the experimental setup, Section V the results, Section VI the discussion, limitations and conclusion, Section VII the acknowledgments and Section VIII the references.

---

## II. RELATED WORK

### A. LLM Assistants in Programming Education

Empirical studies show that code-generating models help novices finish tasks but can encourage dependence on generated code [13], and that LLM-written code explanations are useful in a web-development e-book while also raising concerns about accuracy [12]. In response, systems such as CodeHelp [14] and CodeAid [15] place guardrails between the student and the model — for example, blocking complete solutions and returning explanations or hints instead — and report classroom deployments in which educators control how much help is revealed. Our work shares this goal but differs in two respects: the tutor is grounded in a specific lecture-video corpus with verifiable time anchors, and refusal behaviour is evaluated turn by turn on multi-turn dialogues rather than on isolated prompts.

### B. Socratic Questioning

Socratic questioning prioritizes learner inquiry over answers: the teacher clarifies, probes assumptions and evidence, and asks the learner to extend the reasoning [11]. For a software tutor this translates into three operational requirements — diagnose the concept behind an error, return a guiding question, and never produce the full solution. We therefore measure refusal precision (SRP) rather than only answer relevance.

### C. Retrieval-Augmented Generation, Corrective RAG and Sufficient Context

RAG conditions a generator on retrieved passages [4]. Corrective RAG (CRAG) of Yan *et al.* [1] adds a lightweight evaluator that places retrieval into one of three confidence states — *Correct*, *Ambiguous* or *Incorrect* — before generation; we adopt this three-state formulation and note that it is unrelated to the similarly named Meta CRAG benchmark. Joren *et al.* [2] showed that relevance and sufficiency are separable: an insufficient but relevant context pushes the LLM to hallucinate rather than abstain. Our Pareto boundary applies this separation to lectures, where a spoken preview of a later topic is relevant but not instructive.

### D. Hybrid Retrieval and Intent Routing

Dense multilingual embeddings [5] capture paraphrase, whereas BM25 [7] rewards exact identifiers (`virtual`, `std::vector`) that matter for code questions and for noisy Whisper transcripts [6]. We combine both in one Qdrant query with In-HNSW filtering [8], so that the constraint `course_id` and `lesson_seq ≤ current` is applied during graph traversal. For routing, entailment-based zero-shot classification [9], built on DeBERTa-style encoders [10], provides a principled second opinion for low-confidence queries, which lets the first-stage classifier stay fast.

### E. Long-Context Degradation

Models under-use information placed in the middle of long prompts [3]. Multi-turn tutoring accumulates history, so we cap the history budget and place the strongest evidence at the edges of the context (U-shaped layout).

---

## IV. EXPERIMENTAL SETUP

### A. Corpus and Pipeline Configuration

The testbed covers **83 lessons** across C++, OOP and data structures, with more than 52 hours of lecture video and over 12,000 lines of illustrative code. Transcripts are produced with `faster-whisper` [6] using domain hotword biasing and Silero VAD (threshold 0.35, `speech_pad_ms` = 400, `condition_on_previous_text` = False). Documents are embedded with `intfloat/multilingual-e5-large` [5] (1,024 dimensions, `passage:` / `query:` prefixes) and `Qdrant/bm25`; code is chunked at AST boundaries with Tree-sitter. Top-10 candidates are re-ranked by a cross-encoder on CPU, with logistic sigmoid normalization. Dialogue memory is a sliding window of *k* = 5 turns with a 2,400-character history budget, managed by a LangGraph `MemorySaver` checkpointer keyed by session.

### B. Benchmarks

Two independent suites are used. Neither is used to tune thresholds in this study; the single-turn set is the frozen held-out set of the router decontamination protocol (maximum Jaccard similarity to the training corpus 0.6842 < 0.70).

- **Stage 11 Golden Benchmark (single-turn, N = 200).** Four tiers: *In-Scope Technical* (80), *Out-of-Lesson* (40), *Adversarial Hybrid* (40) and *Chit-Chat / Out-of-Domain* (40).
- **Deterministic Multi-Turn Benchmark (50 sessions, 222 turns).** Four stress tiers: *Ellipsis & Anaphora* (15 sessions, 60 turns), *Socratic Refusal* (15, 60), *Topic Switching* (10, 42) and *Context Budget* (10, 60). The retrieval-mode run uses no remote LLM. A separate end-to-end run (15 sessions, 60 turns, **30 live LLM generations** on a remote GPU) measures whether generated answers comply with the Socratic policy.

### C. Metrics

Let $\mathbb{1}[\cdot]$ denote the indicator function and $N$ the number of evaluated cases or turns.

$$\text{Acc}_{\text{intent}} = \frac{1}{N}\sum_{i=1}^{N}\mathbb{1}\left[\hat{y}_i = y_i\right] \tag{4.1}$$

$$\text{SRP} = \frac{\#\{\text{solicitations refused without code leakage}\}}{\#\{\text{solicitations}\}} \tag{4.2}$$

$$\text{ARR} = \frac{\#\{\text{elliptical follow-ups whose reformulated query recovers the target}\}}{\#\{\text{elliptical follow-ups}\}} \tag{4.3}$$

- **Router accuracy / intent accuracy** — Eq. (4.1) on the routed intent.
- **CRAG precision / retrieval-status accuracy** — correctness of the grader state (`grounded`, `out_of_lesson`, `coverage_gap`).
- **Anaphora Resolution Rate (ARR)** — Eq. (4.3).
- **Socratic Refusal Precision (SRP)** — Eq. (4.2): the fraction of turns that solicit a full solution and are answered by an explanation or hint with no complete code.
- **Timestamp safety** — emitted `<timestamp>` tags that are whitelisted and within tolerance, or absent when none is warranted. **Strict WHR** (whitelist hit rate, ±30 s) additionally requires proximity to the single annotated reference second.
- **Context budget compliance** — dialogue history ≤ 2,400 characters.

### D. Protocol

All metrics are read from the JSON artifacts produced by the benchmark runners, without manual transcription, and denominators were recomputed from per-turn records (Section V). A long lecture can teach one concept at several moments (theory, demonstration, exercise); a deviation |Δt| > 30 s from the single annotated second is therefore reported as a single-label annotation discrepancy, not as a hallucination, and we report both strict WHR and the multi-grounding safety rate.

---

## V. EXPERIMENTAL RESULTS

### A. Single-Turn Results (Stage 11, N = 200)

**Table 2. Stage 11 Golden Benchmark by tier (N = 200).**

| Tier | N | Router OK | Router Acc. | CRAG OK | CRAG Acc. | Avg. latency (ms) |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| In-Scope Technical | 80 | 80 | 100.0% | 79 | 98.8% | 5,499.3 |
| Out-of-Lesson | 40 | 40 | 100.0% | 37 | 92.5% | 6,163.5 |
| Adversarial Hybrid | 40 | 28 | 70.0% | 22 | 55.0% | 5,894.5 |
| Chit-Chat / OOD | 40 | 34 | 85.0% | 35 | 87.5% | 1,423.5 |
| **Overall** | **200** | **182** | **91.0%** | **173** | **86.5%** | **4,896.0** |

Router accuracy is **91.0%** (182/200) and CRAG precision **86.5%** (173/200). Routing is perfect on in-scope and out-of-lesson queries (120/120), the failure mode that the Pareto boundary targets. Timestamp safety is 87.0% (174/200) and strict timestamp accuracy 85.0% (170/200). Errors concentrate in the adversarial-hybrid tier, where one message mixes a course concept with an off-topic or manipulative framing; it accounts for 12 of the 18 router errors.

### B. Multi-Turn Results (50 Sessions, 222 Turns)

**Table 3. Deterministic multi-turn benchmark (retrieval mode).**

| Metric | Count | Result | Target |
| :--- | ---: | ---: | ---: |
| Intent classification accuracy | 219 / 222 | **98.65%** | ≥ 90.0% |
| Retrieval-status accuracy | 218 / 222 | **98.20%** | ≥ 85.0% |
| Anaphora Resolution Rate (ARR) | 93 / 94 | **98.94%** | ≥ 90.0% |
| Socratic Refusal Precision (SRP) | 15 / 15 | **100.0%** | 100.0% |
| Multi-grounding timestamp safety | 220 / 222 | 99.1% | ≥ 90.0% |
| Strict whitelist hit rate (±30 s) | 119 / 222 | 53.6% | — |
| Context budget compliance | 222 / 222 | **100.0%** | 100.0% |
| Max history observed | — | 895 chars | ≤ 2,400 |

**Table 4. Multi-turn results by stress tier.**

| Tier | Sessions / Turns | Intent | Status | Multi-grounding TS | Budget | ARR / SRP |
| :--- | :---: | ---: | ---: | ---: | ---: | :---: |
| 1. Ellipsis & Anaphora | 15 / 60 | 100.0% | 100.0% | 100.0% | 100.0% | ARR 100.0% |
| 2. Socratic Refusal | 15 / 60 | 100.0% | 100.0% | 100.0% | 100.0% | SRP 100.0% |
| 3. Topic Switching | 10 / 42 | 92.86% | 92.86% | 95.24% | 100.0% | — |
| 4. Context Budget | 10 / 60 | 100.0% | 98.33% | 100.0% | 100.0% | — |

### C. Pedagogical Compliance (End-to-End Run)

In the end-to-end run (15 sessions, 60 turns) the tutor produced 30 live LLM generations; all 30 complied with the Socratic policy (compliance 100.0%) and the input guardrail needed no intervention. This run reports intent accuracy 98.33%, status accuracy 98.33%, ARR 96.67% and a maximum history of 1,097 characters, still within the 2,400-character budget. The two runs use different tier compositions and sample sizes and should not be pooled.

### D. Discussion of Results

**Socratic refusal.** SRP is 100.0% on all 15 solicitation turns of the retrieval run and every generated answer in the end-to-end run was compliant. The sample is small, however: 15 solicitations and 30 generations support the claim that refusal worked in this benchmark, not that leakage is impossible.

**Anaphora and topic switching.** ARR of 98.94% shows that context-aware query formulation recovers the technical target of pronominal and elliptical follow-ups. Topic switching is the weakest tier (92.86%): after a change of subject, the previous turn still biases reformulation in a few cases, which is the direction of future work on context-isolation.

**Pareto gating.** Perfect routing of out-of-lesson queries together with 98.8% CRAG precision on in-scope queries indicates that the stratified margins avoid both failure directions: future lessons are not swallowed by an old lesson's passing commentary, and current-lesson questions are not hijacked by later lectures.

**Strict versus multi-grounding timestamps.** Strict WHR is 53.6%, whereas multi-grounding safety is 99.1%. The gap reflects that a concept recurs at several moments while the benchmark stores one reference second; every emitted tag nevertheless passes the deterministic whitelist, so the gap does not indicate fabricated moments.

**Latency.** The first-stage router adds negligible cost (P50 0.02 ms on the held-out set). Average single-turn latency is 4.9 s; multi-turn P50/P95 are 5.8 s and 15.0 s with a heavy tail (P99 59.1 s, maximum 138.7 s) attributed to re-ranker and cold-start effects — acceptable for an asynchronous tutor, not for real-time interaction.

---

## VI. DISCUSSION AND CONCLUSION

### A. Discussion

Three lessons follow. First, pedagogical behaviour is more reliable when enforced as a deterministic invariant around the LLM (input guardrail, whitelist, bounded memory) than when requested through the prompt alone; the measured refusal and timestamp-safety rates are properties of the pipeline, not of one prompt. Second, a tutor over lecture video needs a notion of *sufficiency* distinct from relevance: with a flat threshold, a spoken preview in an early lecture is indistinguishable from teaching, and a stratified margin resolves this without lesson-specific rules. Third, multi-turn evaluation is necessary for educational RAG: single-turn accuracy (91.0%) says little about ellipsis, topic switches or history growth, which the multi-turn suite exposes (98.65% intent accuracy, with the weakest tier at 92.86%).

### B. Limitations

1. **Adversarial hybrid queries** remain the main error source (70.0% router accuracy, 55.0% CRAG precision).
2. **Strict single-label timestamp matching** is 53.6%; a multi-reference annotation scheme is needed to measure timestamp accuracy faithfully.
3. **Small refusal sample.** SRP rests on 15 solicitation turns and Socratic compliance on 30 generations; larger and adversarially authored sets are required.
4. **Latency tail** of the multi-turn run (P99 59.1 s) is too high for synchronous use.
5. **No learning-outcome evidence.** The suites are deterministic and synthetic; they measure system behaviour, not whether students learn more. The corpus is one institution's C++/OOP/data-structure course in Vietnamese–English speech, and generalization to other languages, courses and cohorts is untested.

### C. Conclusion

We presented a Socratic, video-grounded agentic RAG copilot that enforces pedagogy through a cascade router, true hybrid retrieval with In-HNSW pre-filtering, a three-tier Pareto Context Sufficiency boundary and a stateful LangGraph orchestration with a deterministic timestamp whitelist. It reached 91.0% router accuracy and 86.5% CRAG precision on 200 single-turn queries, and 98.65% intent accuracy, 98.20% retrieval-status accuracy, 98.94% ARR and 100.0% SRP over 222 multi-turn turns. Future work includes multi-reference timestamp annotation, targeted training for adversarial hybrid queries, larger adversarial refusal test sets, latency reduction of the re-ranking stage, and a controlled classroom study of learning outcomes.

---

## VII. ACKNOWLEDGMENTS

The author sincerely thanks M.Sc. Tieu Phung Mai Suong, Faculty of Information Technology, Ho Chi Minh City University of Foreign Languages – Information Technology (HUFLIT), for her valuable academic guidance, constructive feedback and dedicated supervision throughout this research. The author also thanks the Faculty of Information Technology, HUFLIT, for providing institutional research facilities.

---

## VIII. REFERENCES

[1] S.-Q. Yan, J.-C. Gu, Y. Zhu, and Z.-H. Ling, "Corrective retrieval augmented generation," *arXiv preprint* arXiv:2401.15884, 2024.

[2] H. Joren, J. Zhang, C.-S. Ferng, D.-C. Juan, A. Taly, and C. Rashtchian, "Sufficient context: A new lens on retrieval augmented generation systems," in *Proc. Int. Conf. Learn. Represent. (ICLR)*, Singapore, 2025.

[3] N. F. Liu, K. Lin, J. Hewitt, A. Paranjape, M. Bevilacqua, F. Petroni, and P. Liang, "Lost in the middle: How language models use long contexts," *Trans. Assoc. Comput. Linguist.*, vol. 12, pp. 157–173, 2024.

[4] P. Lewis *et al.*, "Retrieval-augmented generation for knowledge-intensive NLP tasks," in *Proc. Adv. Neural Inf. Process. Syst. (NeurIPS)*, vol. 33, 2020, pp. 9459–9474.

[5] L. Wang, N. Yang, X. Huang, L. Yang, R. Majumder, and F. Wei, "Multilingual E5 text embeddings: A technical report," *arXiv preprint* arXiv:2402.05672, 2024.

[6] A. Radford, J. W. Kim, T. Xu, G. Brockman, C. McLeavey, and I. Sutskever, "Robust speech recognition via large-scale weak supervision," in *Proc. Int. Conf. Mach. Learn. (ICML)*, 2023, pp. 28492–28518.

[7] S. Robertson and H. Zaragoza, "The probabilistic relevance framework: BM25 and beyond," *Found. Trends Inf. Retr.*, vol. 3, no. 4, pp. 333–389, 2009.

[8] Y. A. Malkov and D. A. Yashunin, "Efficient and robust approximate nearest neighbor search using hierarchical navigable small world graphs," *IEEE Trans. Pattern Anal. Mach. Intell.*, vol. 42, no. 4, pp. 824–836, Apr. 2020.

[9] W. Yin, J. Hay, and D. Roth, "Benchmarking zero-shot text classification: Datasets, evaluation and entailment approach," in *Proc. Conf. Empirical Methods Natural Lang. Process. (EMNLP-IJCNLP)*, Hong Kong, 2019, pp. 3914–3923.

[10] P. He, J. Gao, and W. Chen, "DeBERTaV3: Improving DeBERTa using ELECTRA-style pre-training with gradient-disentangled embedding sharing," in *Proc. Int. Conf. Learn. Represent. (ICLR)*, 2023.

[11] R. Paul and L. Elder, *The Thinker's Guide to The Art of Socratic Questioning*. Dillon Beach, CA, USA: Foundation for Critical Thinking, 2006.

[12] S. MacNeil *et al.*, "Experiences from using code explanations generated by large language models in a web software development e-book," in *Proc. 54th ACM Tech. Symp. Comput. Sci. Educ. (SIGCSE)*, 2023, pp. 931–937.

[13] M. Kazemitabaar, J. Chow, C. K. T. Ma, B. J. Ericson, D. Weintrop, and T. Grossman, "Studying the effect of AI code generators on supporting novice learners in introductory programming," in *Proc. CHI Conf. Human Factors Comput. Syst. (CHI)*, 2023.

[14] M. Liffiton, B. E. Sheese, J. Savelka, and P. Denny, "CodeHelp: Using large language models with guardrails for scalable support in programming classes," in *Proc. 23rd Koli Calling Int. Conf. Comput. Educ. Res.*, 2023.

[15] M. Kazemitabaar, R. Ye, X. Wang, A. Z. Henley, P. Denny, M. Craig, and T. Grossman, "CodeAid: Evaluating a classroom deployment of an LLM-based programming assistant that balances student and educator needs," in *Proc. CHI Conf. Human Factors Comput. Syst. (CHI)*, 2024.

---

## KHỐI SONG NGỮ TIẾNG VIỆT — TRANG 8

**BẢO VỆ NỖ LỰC HỌC TẬP CÓ CHỦ ĐÍCH: TRỢ GIẢNG AGENTIC RAG THEO PHƯƠNG PHÁP SOCRATIC, NEO VÀO VIDEO BÀI GIẢNG CHO GIẢNG DẠY LẬP TRÌNH TRONG KHÓA HỌC**

**Trần Thành Nghĩa**
Khoa Công nghệ Thông tin (MSSV: 23DH112252), Trường Đại học Ngoại ngữ – Tin học Thành phố Hồ Chí Minh (HUFLIT)

**TÓM TẮT** — Các mô hình ngôn ngữ lớn (LLM) dạng hội thoại giúp sinh viên dễ xin trợ giúp khi học lập trình, nhưng chúng thường đưa ngay lời giải hoàn chỉnh, làm mất đi quá trình vật lộn có chủ đích vốn cần thiết cho người mới học. Đồng thời, một trợ giảng gắn với các video bài giảng dài (30–60 phút) phải trả lời đúng bài học và chỉ ra đúng mốc video kiểm chứng được. Bài báo trình bày In-Course Agentic RAG Copilot, trợ giảng Socratic cho khóa C++/lập trình hướng đối tượng, coi sư phạm là thuộc tính hệ thống được cưỡng chế chứ không chỉ là yêu cầu trong câu lệnh nhắc. Hệ thống là đồ thị trạng thái LangGraph bốn nút (định tuyến, truy xuất lai, thẩm định CRAG, lắp ráp ngữ cảnh), trong đó (i) bộ định tuyến tầng kết hợp bộ phân xử NLI quyết định tin nhắn có phải câu hỏi khóa học hay không, (ii) ngưỡng đủ ngữ cảnh Pareto ba phân tầng tách bạch độ tương quan ngữ nghĩa với độ đầy đủ thông tin sư phạm, và (iii) danh sách trắng mốc thời gian có tính xác định cùng bộ nhớ cửa sổ trượt có giới hạn kiểm soát nội dung trợ giảng được phép nói và trích dẫn. Trên bộ Golden Benchmark 200 câu đơn lượt, hệ thống đạt độ chính xác định tuyến **91,0%** và độ chuẩn xác CRAG **86,5%**. Trên bộ đa lượt xác định gồm 50 phiên (222 lượt), hệ thống đạt độ chính xác ý định **98,65%**, độ chính xác trạng thái truy xuất **98,20%**, tỷ lệ giải quyết hồi chỉ (ARR) **98,94%** và độ chính xác từ chối giải bài hộ (SRP) **100,0%**, mọi ngữ cảnh hội thoại đều nằm trong ngân sách 2.400 ký tự. Chúng tôi trình bày trung thực các hạn chế còn lại: tỷ lệ khớp mốc thời gian nghiêm ngặt một nhãn (53,6%), nhóm câu hỏi lai đối kháng (độ chính xác định tuyến 70,0%) và cỡ mẫu nhỏ đằng sau chỉ số SRP (15/15).

**Từ khóa** — Dạy học Socratic, Agentic RAG, Corrective RAG (CRAG), Rào chắn sư phạm, Đủ ngữ cảnh Pareto, Giải quyết hồi chỉ, Điều phối LangGraph, Học tập neo theo video.

**LỜI CẢM ƠN** — Tác giả chân thành cảm ơn ThS. Tiếu Phùng Mai Sương, Khoa Công nghệ Thông tin, Trường Đại học Ngoại ngữ – Tin học TP.HCM (HUFLIT), đã tận tình hướng dẫn, góp ý và đồng hành trong suốt quá trình thực hiện nghiên cứu này. Tác giả cũng cảm ơn Khoa Công nghệ Thông tin, HUFLIT đã hỗ trợ cơ sở vật chất nghiên cứu.

---

## TIỂU SỬ TÁC GIẢ / AUTHOR BIOGRAPHY

| | |
| :--- | :--- |
| **English** | **Tran Thanh Nghia** is an undergraduate student (Student ID: 23DH112252) at the Faculty of Information Technology, Ho Chi Minh City University of Foreign Languages – Information Technology (HUFLIT), Vietnam. His research interests include retrieval-augmented generation, educational AI tutoring, speech-to-text for lecture video, and conversational agent orchestration. He designed and implemented the In-Course Agentic RAG Copilot described in this paper under the supervision of M.Sc. Tieu Phung Mai Suong. Email: nghia.23dh112252@st.huflit.edu.vn. |
| **Tiếng Việt** | **Trần Thành Nghĩa** là sinh viên (MSSV: 23DH112252) Khoa Công nghệ Thông tin, Trường Đại học Ngoại ngữ – Tin học TP.HCM (HUFLIT). Hướng nghiên cứu quan tâm: sinh văn bản tăng cường truy xuất (RAG), trợ giảng AI trong giáo dục, nhận dạng tiếng nói cho video bài giảng và điều phối tác tử hội thoại. Tác giả thiết kế và hiện thực hệ thống In-Course Agentic RAG Copilot trình bày trong bài báo, dưới sự hướng dẫn của ThS. Tiếu Phùng Mai Sương. Email: nghia.23dh112252@st.huflit.edu.vn. |
