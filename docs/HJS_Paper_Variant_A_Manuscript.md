# HJS Manuscript — Variant A (Algorithmic Architecture)

> **Nguồn số liệu (đã đối chiếu trực tiếp với JSON):** `docs/benchmarks/latest_benchmark_results.json` (Stage 11, run 2026-11-14 01:50–02:07), `docs/benchmarks/multiturn_benchmark_results.json` (50 sessions / 222 turns), `docs/benchmarks/multiturn_benchmark_e2e_results.json` (e2e LLM, 15 sessions / 60 turns), `docs/benchmarks/decontaminated_generalization_benchmark_report.md`.
> **Section III** (System Architecture & Mathematical Formulation, Table 1, các công thức OMML) được giữ nguyên từ `scripts/build_full_hjs_paper.py` và không soạn lại ở đây.

---

**PARETO-SUFFICIENT AGENTIC RAG WITH AST-VIDEO SYNCHRONIZATION FOR SOCRATIC IN-COURSE PROGRAMMING TUTORING: AN ALGORITHMIC ARCHITECTURE**

**Tran Thanh Nghia**\*
Faculty of Information Technology (Student ID: 23DH112252),
Ho Chi Minh City University of Foreign Languages – Information Technology (HUFLIT), Ho Chi Minh City, Vietnam
\*Corresponding author: nghia.23dh112252@st.huflit.edu.vn

---

## ABSTRACT

In programming e-learning, long lecture videos (30–60 minutes) cause acute retrieval degradation: introductory lessons containing casual spoken commentary frequently outrank dedicated downstream lectures, while general-purpose conversational LLMs tend to leak complete solutions to students. This paper presents *In-Course Agentic RAG Copilot*, a Socratic tutoring system orchestrated as a four-node LangGraph state machine (router, hybrid retrieval, Corrective-RAG grader, context assembly). We formalize a three-tier Pareto Context Sufficiency boundary, motivated by the sufficient-context analysis of retrieval-augmented generation, that separates semantic relevance from pedagogical sufficiency and regulates when a future lesson may displace the current one. The system combines a cascade intent router (ONNX INT8 small language model with an mDeBERTa-v3 NLI arbiter), true hybrid retrieval (Multilingual E5-Large + BM25) under dynamic In-HNSW pre-filtering, and a deterministic timestamp whitelist that links answers to verified video seconds. On a 200-query single-turn golden benchmark the system reaches **91.0%** router accuracy and **86.5%** CRAG grading precision. On a deterministic multi-turn suite of 50 sessions (222 turns) it reaches **98.65%** intent accuracy, **98.20%** retrieval-status accuracy, **98.94%** Anaphora Resolution Rate (ARR) and **100.0%** Socratic Refusal Precision (SRP), with all dialogue contexts remaining within the 2,400-character budget. We also report the limitations that remain, notably strict single-label timestamp matching (53.6%) and the adversarial-hybrid tier (70.0% router accuracy).

**Keywords** — Agentic RAG, Corrective RAG (CRAG), Pareto Context Sufficiency, Fast-Path SLM Router, Natural Language Inference, LangGraph Orchestration, Socratic Tutoring, Video-Code Synchronization.

---

## I. INTRODUCTION

Asynchronous video lectures are the backbone of modern computer-science curricula, including the C++, object-oriented programming (OOP) and data-structure sequences taught at HUFLIT. A novice facing a compiler error or a memory fault, however, must scrub through a 30–60 minute recording to find the few seconds that explain the concept in question. Locating that moment is a retrieval problem; deciding what to tell the student once it is found is a pedagogical one.

Deploying a generic LLM assistant on top of such a course fails in two structurally different ways.

1. **Retrieval-side failure: old-lesson dominance.** Lecturers routinely preview later topics in passing ("we will see inheritance in a later lesson"). Such spoken remarks share vocabulary with the dedicated lecture and can attain similar cosine similarity, so a naive top-k or `argmax` retriever answers from the wrong lesson. Semantic relevance is not the same as sufficient context: a passage may be topically close and still lack the information needed to answer [2].
2. **Generation-side failure: solution leakage.** Commercial assistants readily emit full solution code, which removes the productive struggle that programming education depends on [13], [14]. A tutor must instead explain the error, ask a guiding question and refuse to write the assignment.

A third, practical constraint is lexical mismatch between spoken Whisper transcripts [7] and formal syntax, which makes lexical and dense retrieval complementary rather than interchangeable.

This paper addresses these problems with an architecture that treats every design decision as an explicit, auditable gate. The contributions are fourfold:

- **C1 – Cascade semantic router.** An ONNX INT8 small language model handles high-confidence intents at sub-millisecond cost, and an mDeBERTa-v3 natural-language-inference (NLI) arbiter [12], [15] rescues ambiguous queries with zero-shot reasoning instead of hand-written regular expressions.
- **C2 – AST-to-Video synchronization.** Tree-sitter code scopes are bound to lecture seconds, so that code explanations carry a verified video anchor.
- **C3 – Three-tier Pareto Context Sufficiency.** A stratified inequality decides when a future lesson may displace the current lesson, replacing a flat threshold that either swallows future questions or lets old lessons win.
- **C4 – Stateful, budgeted orchestration.** A LangGraph state machine with a sliding window of *k* = 5 turns, a 2,400-character history budget and a deterministic timestamp whitelist, evaluated on 200 single-turn and 222 multi-turn queries.

The remainder of the paper is organized as follows. Section II reviews related work, Section III presents the architecture, Section IV the experimental setup, Section V the results, and Section VI the discussion, limitations and conclusion.

---

## II. RELATED WORK

### A. RETRIEVAL-AUGMENTED GENERATION, CORRECTIVE RAG AND CONTEXT SUFFICIENCY

Retrieval-augmented generation (RAG) conditions a generator on externally retrieved passages and has evolved from a single retrieve-then-read pass [4] to modular pipelines with pre-retrieval, retrieval and post-retrieval stages [5]. Corrective RAG (CRAG) of Yan *et al.* [1] adds a lightweight evaluator that scores retrieved documents and routes the system into one of three confidence states — *Correct*, *Ambiguous* or *Incorrect* — before generation. We adopt this three-state formulation for our grader; it should not be confused with the similarly named Meta CRAG benchmark.

Joren *et al.* [2] showed that retrieval quality and answer sufficiency are separable: a context can be relevant yet insufficient, and an LLM then hallucinates rather than abstains. This distinction is central to our setting. A lecture passage that merely *mentions* a later topic obtains a relevance score but does not teach it. Our Pareto boundary operationalizes this idea by requiring a future lesson to exceed the current lesson by a margin that depends on how much local evidence the current lesson already provides.

### B. HYBRID RETRIEVAL AND EMBEDDING

Dense multilingual embeddings such as E5 [6] capture paraphrase and cross-lingual similarity, whereas BM25 [8] rewards exact identifiers (`std::vector`, `virtual`), which matter for code-related questions and for noisy transcripts. We combine both in a single Qdrant query with In-HNSW filtering [9], so the educational constraint (`course_id` and `lesson_seq ≤ current`) is applied inside graph traversal instead of after it. Cross-encoder scores are mapped to [0, 1] with a logistic sigmoid, a monotone calibration in the spirit of Platt scaling [10], [11].

### C. INTENT ROUTING AND NLI-BASED RESCUE

Routing every query through the full RAG pipeline wastes latency on greetings and off-topic questions. Fast supervised classifiers are accurate on clean cases but degrade near class boundaries. Entailment-based zero-shot classification [12], built on DeBERTa-style encoders [15], provides a principled second opinion: the query is the premise and a natural-language hypothesis describes the target intent. Our cascade invokes this arbiter only for low-confidence cases, preserving the speed of the first stage while avoiding brittle keyword rules.

### D. SOCRATIC TUTORS AND LONG-CONTEXT DEGRADATION

Socratic questioning [13] prioritizes learner inquiry over answers, and studies of LLM-generated code explanations in introductory courses [14] highlight both their benefit and the risk of over-reliance. Maintaining such dialogue across turns exposes the "lost-in-the-middle" effect [3], in which models under-use information placed in the middle of long prompts. We mitigate this with a U-shaped context layout (top-1, top-3, top-2) and a pruned sliding-window history.

---

## IV. EXPERIMENTAL SETUP

### A. Corpus

The testbed covers **83 lessons** across C++, OOP and data structures, comprising more than 52 hours of lecture video and over 12,000 lines of illustrative code. Transcripts were produced with `faster-whisper` using domain hotword biasing and Silero VAD (threshold 0.35, `speech_pad_ms` = 400, `condition_on_previous_text` = False). Documents are embedded with `intfloat/multilingual-e5-large` (1,024 dimensions, `passage:` / `query:` prefixes) and `Qdrant/bm25`; code is chunked at AST boundaries with Tree-sitter. Top-10 candidates are re-ranked by a cross-encoder running on CPU.

### B. Benchmarks

Two independent suites are used. Neither is used to tune thresholds in this study; the single-turn set is the frozen held-out set of the router decontamination protocol (maximum Jaccard similarity to the training corpus 0.6842 < 0.70).

- **Stage 11 Golden Benchmark (single-turn, N = 200).** Four tiers: *In-Scope Technical* (80), *Out-of-Lesson* (40), *Adversarial Hybrid* (40) and *Chit-Chat / Out-of-Domain* (40).
- **Deterministic Multi-Turn Benchmark (50 sessions, 222 turns).** Four stress tiers: *Ellipsis & Anaphora* (15 sessions, 60 turns), *Socratic Refusal* (15, 60), *Topic Switching* (10, 42) and *Context Budget* (10, 60). The retrieval-mode run uses no remote LLM. A separate *end-to-end* run (15 sessions, 60 turns, 30 live LLM generations on a remote GPU) measures Socratic compliance.

### C. Metrics

Let $\mathbb{1}[\cdot]$ be the indicator function and $N$ the number of evaluated cases (or turns).

$$\text{Acc}_{\text{intent}} = \frac{1}{N}\sum_{i=1}^{N}\mathbb{1}\left[\hat{y}_i = y_i\right] \tag{4.1}$$

$$\text{SRP} = \frac{\#\{\text{solicitations refused without code leakage}\}}{\#\{\text{solicitations}\}} \tag{4.2}$$

- **Router accuracy / Intent accuracy** — Eq. (4.1) on the routed intent.
- **CRAG precision / Retrieval-status accuracy** — correctness of the grader state (`grounded`, `out_of_lesson`, `coverage_gap`).
- **Anaphora Resolution Rate (ARR)** — fraction of elliptical or pronominal follow-ups whose reformulated query recovers the correct technical target.
- **Socratic Refusal Precision (SRP)** — Eq. (4.2).
- **Timestamp safety** — emitted `<timestamp>` tags that are whitelisted and within tolerance, or absent when none is warranted. **Strict WHR** (whitelist hit rate, ±30 s) additionally requires proximity to the single annotated reference second.
- **Context budget compliance** — dialogue history ≤ 2,400 characters.

### D. Protocol

All metrics are read from the JSON artifacts produced by the benchmark runners, with no manual transcription. Because a long lecture can teach one concept at several moments (theory, demonstration, exercise), a deviation |Δt| > 30 s from the single annotated second is reported separately as a single-label annotation discrepancy, not as a hallucination; we therefore report both strict WHR and the multi-grounding safety rate.

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

Router accuracy is **91.0%** (182/200) and CRAG precision **86.5%** (173/200). The system is perfect on in-scope and out-of-lesson routing (120/120), which is the failure mode the Pareto boundary targets. Timestamp safety is 87.0% (174/200) and strict timestamp accuracy 85.0% (170/200). Errors concentrate in the adversarial-hybrid tier, where a single query mixes a course concept with an off-topic or manipulative framing; it accounts for 12 of the 18 router errors.

### B. Multi-Turn Results (50 Sessions, 222 Turns)

**Table 3. Deterministic multi-turn benchmark.**

| Metric | Result | Target |
| :--- | ---: | ---: |
| Intent classification accuracy | **98.65%** | ≥ 90.0% |
| Retrieval-status accuracy | **98.20%** | ≥ 85.0% |
| Anaphora Resolution Rate (ARR) | **98.94%** | ≥ 90.0% |
| Socratic Refusal Precision (SRP) | **100.0%** | 100.0% |
| Multi-grounding timestamp safety | 99.1% | ≥ 90.0% |
| Strict whitelist hit rate (±30 s) | 53.6% | — |
| Context budget compliance | **100.0%** | 100.0% |
| Max history observed | 895 chars | ≤ 2,400 |

**Table 4. Multi-turn results by stress tier.**

| Tier | Sessions / Turns | Intent | Status | Multi-grounding TS | Budget | ARR / SRP |
| :--- | :---: | ---: | ---: | ---: | ---: | :---: |
| 1. Ellipsis & Anaphora | 15 / 60 | 100.0% | 100.0% | 100.0% | 100.0% | ARR 100.0% |
| 2. Socratic Refusal | 15 / 60 | 100.0% | 100.0% | 100.0% | 100.0% | SRP 100.0% |
| 3. Topic Switching | 10 / 42 | 92.86% | 92.86% | 95.24% | 100.0% | — |
| 4. Context Budget | 10 / 60 | 100.0% | 98.33% | 100.0% | 100.0% | — |

Anaphora Resolution reaches 98.94% overall, showing that context-aware query formulation recovers technical targets from pronouns and elliptical follow-ups without cross-turn keyword pollution. Socratic Refusal Precision is **100.0%** on the solicitation turns of the retrieval run, and in the end-to-end run all 30 live LLM generations were compliant (compliance 100.0%, no guardrail intervention required). Topic switching is the weakest tier (92.86%): after a change of subject the previous turn still biases reformulation in a small number of cases.

### C. Discussion of Results

**Pareto gating.** Perfect routing on the out-of-lesson tier together with 98.8% CRAG precision on in-scope queries indicates that the stratified margins avoid both failure directions: future lessons are not swallowed by an old lesson with passing commentary, and current-lesson questions are not hijacked by later lectures.

**Latency.** The first-stage SLM router adds negligible cost (P50 0.02 ms on the held-out set), so latency is dominated by retrieval, CPU re-ranking and, in end-to-end mode, remote generation. Average single-turn latency is 4.9 s; multi-turn P50/P95 are 5.8 s and 15.0 s, with a heavy tail (P99 59.1 s, maximum 138.7 s) that we attribute to re-ranker and cold-start effects. This is acceptable for an asynchronous tutor but not for real-time interaction.

**Strict versus multi-grounding timestamps.** Strict WHR is only 53.6%, whereas multi-grounding safety is 99.1%. The gap reflects that concepts recur across a lecture and the benchmark stores a single reference second; it does not indicate fabricated moments, because every emitted tag passes the deterministic whitelist.

---

## VI. DISCUSSION AND CONCLUSION

### A. Discussion

The results support three design conclusions. First, educational RAG needs a notion of *sufficiency* separate from relevance: with a flat threshold, passing remarks in an early lecture are indistinguishable from teaching. A stratified margin that depends on the confidence of the current lesson resolves this without lesson-specific rules. Second, a cascade router that delegates ambiguous cases to an NLI arbiter replaces brittle regular expressions and keeps the common path under a millisecond. Third, pedagogical guarantees (Socratic refusal, verified timestamps, bounded history) are most reliable when enforced as deterministic invariants around the LLM instead of being requested through prompting.

### B. Limitations

1. **Adversarial hybrid queries** remain the main error source (70.0% router accuracy, 55.0% CRAG precision).
2. **Strict single-label timestamp matching** is 53.6%; a multi-reference annotation scheme is needed to measure timestamp accuracy more faithfully.
3. **Latency tail** of the multi-turn run (P99 59.1 s) is too high for synchronous use.
4. **Scope.** The corpus is one institution's C++/OOP/data-structure course in Vietnamese–English speech; generalization to other languages, courses and student cohorts, and to human learning outcomes, is untested. The Socratic compliance check covers 30 generations, a small sample.
5. The multi-turn suite is deterministic and synthetic; it complements but does not replace a user study.

### C. Conclusion

We presented an agentic RAG architecture for Socratic in-course programming tutoring that unifies a cascade intent router, true hybrid retrieval with In-HNSW pre-filtering, a three-tier Pareto Context Sufficiency boundary and a stateful LangGraph orchestration with a deterministic timestamp whitelist. It achieved 91.0% router accuracy and 86.5% CRAG precision on 200 single-turn queries, and 98.65% intent accuracy, 98.20% retrieval-status accuracy, 98.94% ARR and 100.0% SRP on 222 multi-turn turns. Future work includes multi-reference timestamp annotation, targeted training for adversarial hybrid queries, latency reduction of the re-ranking stage, and a controlled classroom study of learning outcomes.

---

## VII. ACKNOWLEDGMENTS

The author sincerely thanks M.Sc. Tieu Phung Mai Suong, Faculty of Information Technology, Ho Chi Minh City University of Foreign Languages – Information Technology (HUFLIT), for her valuable academic guidance, constructive feedback and dedicated supervision throughout this research. The author also thanks the Faculty of Information Technology, HUFLIT, for providing institutional research facilities.

---

## VIII. REFERENCES

[1] S.-Q. Yan, J.-C. Gu, Y. Zhu, and Z.-H. Ling, "Corrective retrieval augmented generation," *arXiv preprint* arXiv:2401.15884, 2024.

[2] H. Joren, J. Zhang, C.-S. Ferng, D.-C. Juan, A. Taly, and C. Rashtchian, "Sufficient context: A new lens on retrieval augmented generation systems," in *Proc. Int. Conf. Learn. Represent. (ICLR)*, Singapore, 2025.

[3] N. F. Liu, K. Lin, J. Hewitt, A. Paranjape, M. Bevilacqua, F. Petroni, and P. Liang, "Lost in the middle: How language models use long contexts," *Trans. Assoc. Comput. Linguist.*, vol. 12, pp. 157–173, 2024.

[4] P. Lewis *et al.*, "Retrieval-augmented generation for knowledge-intensive NLP tasks," in *Proc. Adv. Neural Inf. Process. Syst. (NeurIPS)*, vol. 33, 2020, pp. 9459–9474.

[5] Y. Gao *et al.*, "Retrieval-augmented generation for large language models: A survey," *arXiv preprint* arXiv:2312.10997, 2023.

[6] L. Wang, N. Yang, X. Huang, L. Yang, R. Majumder, and F. Wei, "Multilingual E5 text embeddings: A technical report," *arXiv preprint* arXiv:2402.05672, 2024.

[7] A. Radford, J. W. Kim, T. Xu, G. Brockman, C. McLeavey, and I. Sutskever, "Robust speech recognition via large-scale weak supervision," in *Proc. Int. Conf. Mach. Learn. (ICML)*, 2023, pp. 28492–28518.

[8] S. Robertson and H. Zaragoza, "The probabilistic relevance framework: BM25 and beyond," *Found. Trends Inf. Retr.*, vol. 3, no. 4, pp. 333–389, 2009.

[9] Y. A. Malkov and D. A. Yashunin, "Efficient and robust approximate nearest neighbor search using hierarchical navigable small world graphs," *IEEE Trans. Pattern Anal. Mach. Intell.*, vol. 42, no. 4, pp. 824–836, Apr. 2020.

[10] J. C. Platt, "Probabilistic outputs for support vector machines and comparisons to regularized likelihood methods," in *Advances in Large Margin Classifiers*, A. J. Smola *et al.*, Eds. Cambridge, MA, USA: MIT Press, 1999, pp. 61–74.

[11] C. Guo, G. Pleiss, Y. Sun, and K. Q. Weinberger, "On calibration of modern neural networks," in *Proc. Int. Conf. Mach. Learn. (ICML)*, 2017, pp. 1321–1330.

[12] W. Yin, J. Hay, and D. Roth, "Benchmarking zero-shot text classification: Datasets, evaluation and entailment approach," in *Proc. Conf. Empirical Methods Natural Lang. Process. (EMNLP-IJCNLP)*, Hong Kong, 2019, pp. 3914–3923.

[13] R. Paul and L. Elder, *The Thinker's Guide to The Art of Socratic Questioning*. Dillon Beach, CA, USA: Foundation for Critical Thinking, 2006.

[14] S. MacNeil *et al.*, "Experiences from using code explanations generated by large language models in a web software development e-book," in *Proc. 54th ACM Tech. Symp. Comput. Sci. Educ. (SIGCSE)*, 2023, pp. 931–937.

[15] P. He, J. Gao, and W. Chen, "DeBERTaV3: Improving DeBERTa using ELECTRA-style pre-training with gradient-disentangled embedding sharing," in *Proc. Int. Conf. Learn. Represent. (ICLR)*, 2023.

---

## KHỐI SONG NGỮ TIẾNG VIỆT — TRANG 8

**KIẾN TRÚC AGENTIC RAG ĐẠT NGƯỠNG ĐỦ NGỮ CẢNH PARETO KẾT HỢP ĐỒNG BỘ AST–VIDEO CHO TRỢ GIẢNG LẬP TRÌNH THEO PHƯƠNG PHÁP SOCRATIC: THIẾT KẾ GIẢI THUẬT**

**Trần Thành Nghĩa**
Khoa Công nghệ Thông tin (MSSV: 23DH112252), Trường Đại học Ngoại ngữ – Tin học Thành phố Hồ Chí Minh (HUFLIT)

**TÓM TẮT** — Trong giáo dục lập trình trực tuyến dựa trên video bài giảng dài (30–60 phút), bài giảng nhập môn có lời nói nhắc lướt thường được truy xuất lấn át các bài giảng chuyên sâu ở phía sau, trong khi các mô hình ngôn ngữ lớn đa dụng dễ tiết lộ lời giải hoàn chỉnh cho sinh viên. Bài báo trình bày In-Course Agentic RAG Copilot, hệ thống trợ giảng Socratic được điều phối bằng đồ thị trạng thái LangGraph gồm bốn nút (định tuyến, truy xuất lai, thẩm định CRAG, lắp ráp ngữ cảnh). Chúng tôi hình thức hóa ngưỡng đủ ngữ cảnh Pareto ba phân tầng, tách bạch độ tương quan ngữ nghĩa với độ đầy đủ thông tin sư phạm, để quyết định khi nào bài học tương lai được phép thay thế bài học hiện tại. Hệ thống kết hợp bộ định tuyến tầng (SLM ONNX INT8 cùng bộ phân xử NLI mDeBERTa-v3), truy xuất lai True Hybrid (Multilingual E5-Large + BM25) với lọc trước In-HNSW và danh sách trắng mốc thời gian có tính xác định. Trên bộ Golden Benchmark 200 câu đơn lượt, hệ thống đạt độ chính xác định tuyến **91,0%** và độ chuẩn xác CRAG **86,5%**. Trên bộ đa lượt xác định gồm 50 phiên (222 lượt), hệ thống đạt độ chính xác ý định **98,65%**, độ chính xác trạng thái truy xuất **98,20%**, tỷ lệ giải quyết hồi chỉ (ARR) **98,94%** và độ chính xác từ chối giải bài hộ (SRP) **100,0%**, đồng thời mọi ngữ cảnh hội thoại đều nằm trong ngân sách 2.400 ký tự. Bài báo cũng nêu các hạn chế còn tồn tại, nổi bật là tỷ lệ khớp mốc thời gian nghiêm ngặt một nhãn (53,6%) và nhóm câu hỏi lai đối kháng (độ chính xác định tuyến 70,0%).

**Từ khóa** — Agentic RAG, Corrective RAG (CRAG), Đủ ngữ cảnh Pareto, Định tuyến SLM, Suy luận ngôn ngữ tự nhiên (NLI), Điều phối LangGraph, Phương pháp Socratic.

**LỜI CẢM ƠN** — Tác giả chân thành cảm ơn ThS. Tiếu Phùng Mai Sương, Khoa Công nghệ Thông tin, Trường Đại học Ngoại ngữ – Tin học TP.HCM (HUFLIT), đã tận tình hướng dẫn, góp ý và đồng hành trong suốt quá trình thực hiện nghiên cứu này. Tác giả cũng cảm ơn Khoa Công nghệ Thông tin, HUFLIT đã hỗ trợ cơ sở vật chất nghiên cứu.

---

## TIỂU SỬ TÁC GIẢ / AUTHOR BIOGRAPHY

| | |
| :--- | :--- |
| **English** | **Tran Thanh Nghia** is an undergraduate student (Student ID: 23DH112252) at the Faculty of Information Technology, Ho Chi Minh City University of Foreign Languages – Information Technology (HUFLIT), Vietnam. His research interests include retrieval-augmented generation, educational AI tutoring, speech-to-text for lecture video, and conversational agent orchestration. He designed and implemented the In-Course Agentic RAG Copilot described in this paper under the supervision of M.Sc. Tieu Phung Mai Suong. Email: nghia.23dh112252@st.huflit.edu.vn. |
| **Tiếng Việt** | **Trần Thành Nghĩa** là sinh viên (MSSV: 23DH112252) Khoa Công nghệ Thông tin, Trường Đại học Ngoại ngữ – Tin học TP.HCM (HUFLIT). Hướng nghiên cứu quan tâm: sinh văn bản tăng cường truy xuất (RAG), trợ giảng AI trong giáo dục, nhận dạng tiếng nói cho video bài giảng và điều phối tác tử hội thoại. Tác giả thiết kế và hiện thực hệ thống In-Course Agentic RAG Copilot trình bày trong bài báo, dưới sự hướng dẫn của ThS. Tiếu Phùng Mai Sương. Email: nghia.23dh112252@st.huflit.edu.vn. |
