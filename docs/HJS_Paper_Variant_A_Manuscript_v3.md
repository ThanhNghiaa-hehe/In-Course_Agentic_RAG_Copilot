# HJS Manuscript — Variant A (Algorithmic Architecture) — v3

> **Nguồn số liệu (đã đối chiếu trực tiếp với artifact trên đĩa, 14/11/2026):**
> `docs/benchmarks/latest_benchmark_results.json` + `stage11_report_2026-11-14_01-50-21.md` (Stage 11, N = 200); `multiturn_benchmark_results.json/.md` (50 phiên / 222 lượt); `multiturn_benchmark_e2e_results.json` (15 phiên / 60 lượt, 30 lượt gọi LLM); `slm_vs_linearsvc_benchmark_report.md`; `decontaminated_generalization_benchmark_report.md`; mã nguồn `scripts/ingest_video.py` (VAD, hotwords, `TECH_CANONICAL_MAP`), `app/config.py`, `data/curriculum/lessons_manifest.json`, `data/transcripts/**` (đếm trực tiếp), `external_be/pom.xml`, `external_fe/package.json`, `app/templates/playground.html`.
> **Section III** (System Architecture & Mathematical Formulation, Table 1, các công thức OMML) giữ nguyên từ `scripts/build_full_hjs_paper.py`; không soạn lại tại đây.
> **Mọi con số trong Section IV.A đã được kiểm đếm trực tiếp trên dữ liệu; các điểm lệch so với đề bài được ghi rõ trong ghi chú ở cuối tài liệu.**

---

**PARETO-SUFFICIENT AGENTIC RAG WITH AST-VIDEO SYNCHRONIZATION FOR SOCRATIC IN-COURSE PROGRAMMING TUTORING: AN ALGORITHMIC ARCHITECTURE**

**Tran Thanh Nghia**\*
Faculty of Information Technology (Student ID: 23DH112252),
Ho Chi Minh City University of Foreign Languages – Information Technology (HUFLIT), Ho Chi Minh City, Vietnam
\*Corresponding author: nghia.23dh112252@st.huflit.edu.vn

---

## ABSTRACT

In programming e-learning, long lecture videos (30–60 minutes) cause acute retrieval degradation: introductory lessons containing casual spoken commentary frequently outrank dedicated downstream lectures, while general-purpose conversational LLMs tend to leak complete solutions to students. The problem is compounded at the data layer, because Vietnamese lecturers pronounce English programming vocabulary in ways that automatic speech recognition (ASR) transcribes as phonetically plausible but technically wrong strings. This paper presents *In-Course Agentic RAG Copilot*, a Socratic tutoring system whose corpus is built from 83 C++, OOP and data-structure lessons (82.2 hours of lecture video) through a two-stage speech-to-text pipeline — `faster-whisper` large-v3 with Silero VAD (threshold 0.35, `speech_pad_ms` = 400), domain hotword biasing, and a regular-expression Tech Canonicalizer applied before vectorization. Answering is orchestrated as a four-node LangGraph state machine (router, hybrid retrieval, Corrective-RAG grader, context assembly) deployed behind a Hybrid Dual-Backend topology (Spring Boot platform core plus FastAPI AI microservice) and surfaced through an In-Course 3-Column Canvas whose video column is driven by verified timestamps. We formalize a three-tier Pareto Context Sufficiency boundary, motivated by the sufficient-context analysis of retrieval-augmented generation, that separates semantic relevance from pedagogical sufficiency. On a 200-query single-turn golden benchmark the system reaches **91.0%** router accuracy and **86.5%** CRAG grading precision. On a deterministic multi-turn suite of 50 sessions (222 turns) it reaches **98.65%** intent accuracy, **98.20%** retrieval-status accuracy, **98.94%** Anaphora Resolution Rate (ARR) and **100.0%** Socratic Refusal Precision (SRP). We also report the remaining limitations: strict single-label timestamp matching (53.6%), the adversarial-hybrid tier (70.0% router accuracy), and a residual set of un-canonicalized phonetic errors in the corpus.

**Keywords** — Agentic RAG, Corrective RAG (CRAG), Pareto Context Sufficiency, Speech-to-Text, Phonetic Canonicalization, Hotword Biasing, Silero VAD, Hybrid Dual-Backend, Socratic Tutoring, Video-Code Synchronization.

---

## I. INTRODUCTION

Asynchronous video lectures are the backbone of modern computer-science curricula, including the C++, object-oriented programming (OOP) and data-structure sequences taught at HUFLIT. A novice facing a compiler error or a memory fault, however, must scrub through a 30–60 minute recording to find the few seconds that explain the concept in question. Locating that moment is a retrieval problem; deciding what to tell the student once it is found is a pedagogical one.

Deploying a generic LLM assistant on top of such a course fails in three structurally different ways.

1. **Data-side failure: phonetic corruption of technical vocabulary.** A retrieval index is only as good as its text. Whisper-class ASR models [7] transcribe a Vietnamese lecturer saying "si cộng cộng" or "xì in" as ordinary Vietnamese or English-looking syllables, so the identifiers that students later type (`C++`, `cin`) never appear in the index. Lexical retrieval (BM25 [8]) then fails outright, and dense retrieval degrades.
2. **Retrieval-side failure: old-lesson dominance.** Lecturers routinely preview later topics in passing ("we will see inheritance in a later lesson"). Such spoken remarks share vocabulary with the dedicated lecture and can attain similar cosine similarity, so a naive top-*k* or `argmax` retriever answers from the wrong lesson. Semantic relevance is not the same as sufficient context: a passage may be topically close and still lack the information needed to answer [2].
3. **Generation-side failure: solution leakage.** Commercial assistants readily emit full solution code, which removes the productive struggle that programming education depends on [13], [14]. A tutor must instead explain the error, ask a guiding question and refuse to write the assignment.

This paper addresses these problems with an architecture that treats every design decision as an explicit, auditable gate. The contributions are fivefold:

- **C1 – Domain-aware speech-to-text preprocessing.** A pipeline of `faster-whisper` large-v3 [5], Silero VAD [11], hotword biasing and a post-hoc Tech Canonicalizer converts 82.2 hours of lecture audio into 6,387 time-aware, retrieval-ready chunks.
- **C2 – Cascade semantic router.** An ONNX INT8 small language model handles high-confidence intents at sub-millisecond cost, and an mDeBERTa-v3 natural-language-inference (NLI) arbiter [12], [15] rescues ambiguous queries with zero-shot reasoning instead of hand-written regular expressions.
- **C3 – AST-to-Video synchronization.** Tree-sitter code scopes are bound to lecture seconds, so that code explanations carry a verified video anchor.
- **C4 – Three-tier Pareto Context Sufficiency.** A stratified inequality decides when a future lesson may displace the current lesson, replacing a flat threshold that either swallows future questions or lets old lessons win.
- **C5 – Deployable pedagogical topology.** A Hybrid Dual-Backend (Spring Boot + FastAPI) contract and an In-Course 3-Column Canvas that bind the AI service to the learner's progress and to a seekable video player; stateful orchestration uses a sliding window of *k* = 5 turns, a 2,400-character history budget and a deterministic timestamp whitelist, evaluated on 200 single-turn and 222 multi-turn queries.

The remainder of the paper is organized as follows. Section II reviews related work, Section III presents the architecture, Section IV the data pipeline, deployment topology and experimental setup, Section V the results, Section VI the discussion, limitations and conclusion, and Section VII the acknowledgments.

---

## II. RELATED WORK

### A. RETRIEVAL-AUGMENTED GENERATION, CORRECTIVE RAG AND CONTEXT SUFFICIENCY

Retrieval-augmented generation (RAG) conditions a generator on externally retrieved passages [4]. Corrective RAG (CRAG) of Yan *et al.* [1] adds a lightweight evaluator that scores retrieved documents and routes the system into one of three confidence states — *Correct*, *Ambiguous* or *Incorrect* — before generation. We adopt this three-state formulation for our grader; it should not be confused with the similarly named Meta CRAG benchmark.

Joren *et al.* [2] showed that retrieval quality and answer sufficiency are separable: a context can be relevant yet insufficient, and an LLM then hallucinates rather than abstains. This distinction is central to our setting. A lecture passage that merely *mentions* a later topic obtains a relevance score but does not teach it. Our Pareto boundary operationalizes this idea by requiring a future lesson to exceed the current lesson by a margin that depends on how much local evidence the current lesson already provides.

### B. SPEECH RECOGNITION FOR LECTURE VIDEO

Large-scale weakly supervised models such as Whisper [7] deliver robust multilingual transcription, and the `faster-whisper` re-implementation [5] reduces inference cost through CTranslate2 and INT8 quantization, which matters for a 82-hour corpus processed on commodity hardware. Two known failure modes are directly relevant here: (i) hallucinated text on silence or background noise, mitigated by a neural voice-activity detector such as Silero VAD [11] that gates the audio before decoding, and (ii) rare-term errors, mitigated by decoder-side vocabulary biasing (a hotword list) and by post-ASR normalization. In code-switched Vietnamese programming lectures, English identifiers are systematically rendered by their Vietnamese phonetic approximations, so normalization has to be domain-specific rather than generic.

### C. HYBRID RETRIEVAL AND EMBEDDING

Dense multilingual embeddings such as E5 [6] capture paraphrase and cross-lingual similarity, whereas BM25 [8] rewards exact identifiers (`std::vector`, `virtual`), which matter for code-related questions and for noisy transcripts. We combine both in a single Qdrant query with In-HNSW filtering [9], so the educational constraint (`course_id` and `lesson_seq ≤ current`) is applied inside graph traversal instead of after it. Cross-encoder scores are mapped to [0, 1] with a logistic sigmoid, a monotone calibration in the spirit of Platt scaling [10].

### D. INTENT ROUTING, NLI-BASED RESCUE, SOCRATIC TUTORS AND LONG-CONTEXT DEGRADATION

Routing every query through the full RAG pipeline wastes latency on greetings and off-topic questions. Fast supervised classifiers are accurate on clean cases but degrade near class boundaries. Entailment-based zero-shot classification [12], built on DeBERTa-style encoders [15], provides a principled second opinion: the query is the premise and a natural-language hypothesis describes the target intent. Socratic questioning [13] prioritizes learner inquiry over answers, and studies of LLM-generated code explanations in introductory courses [14] highlight both their benefit and the risk of over-reliance. Maintaining such dialogue across turns exposes the "lost-in-the-middle" effect [3], in which models under-use information placed in the middle of long prompts. We mitigate this with a U-shaped context layout (top-1, top-3, top-2) and a pruned sliding-window history.

---

## IV. SYSTEM DATA PIPELINE, DEPLOYMENT TOPOLOGY AND EXPERIMENTAL SETUP

### A. CORPUS PREPROCESSING: SPEECH-TO-TEXT AND PHONETIC CANONICALIZATION

**1) Corpus.** The testbed comprises **83 lessons** of the HUFLIT-oriented curriculum manifest — 52 lessons in the `cpp-core` course (C++ fundamentals, arrays, STL, sorting and searching, number theory) and 31 in the `cpp-oop` course (OOP, pointers, linked lists and further data structures). Direct inspection of the transcript store gives **57,371 transcribed segments** and a total lecture timeline of **82.2 hours** (78.8 hours of speech-bearing segments); individual lessons range from 0.12 to 2.27 hours. Lecture videos are therefore long enough for the retrieval pathologies described in Section I to occur in practice.

**2) Stage 1 — Acoustic front-end and transcription.** Audio is transcribed with `faster-whisper` [5], model size `large-v3`, Vietnamese language forcing (`language="vi"`), beam size 5 and `condition_on_previous_text = False`, so that a decoding error in one window cannot propagate into the next. The decoder runs on CUDA (float16) when available and otherwise falls back to the CPU in INT8, which is the configured default of the service. Before decoding, a **Silero VAD** [11] gate removes non-speech audio with the parameters

$$\theta_{\text{VAD}} = 0.35,\quad t_{\text{pad}} = 400\ \text{ms},\quad t_{\text{speech}}^{\min} = 150\ \text{ms},\quad t_{\text{silence}}^{\min} = 800\ \text{ms}.$$

The speech-probability threshold of 0.35 is deliberately lower than the library default (0.5): lecturers speak softly while typing or when pausing at the keyboard, and a conservative gate would clip word onsets, whereas the 400 ms padding preserves the leading and trailing phonemes of every kept span. Silent stretches and keyboard noise, the dominant non-speech content in screen-recorded coding lectures, are the main targets of this gate; a post-hoc filter additionally deletes the known nonsense English strings that Whisper generates on residual silence.

**3) Domain Hotword Lexicon Biasing.** Whisper decodes with a prior that favors common words, so rare identifiers are replaced by acoustically similar common ones. We counter this by supplying the decoder with a per-course *hotword* list and a short `initial_prompt` naming the course, lesson and domain. The list is selected automatically from the course identifier; for C++ it contains 23 terms — `C++`, `include`, `iostream`, `namespace`, `std`, `cout`, `cin`, `main`, `Ctrl`, `pointer`, `con trỏ`, `class`, `struct`, `Visual Studio`, `Debug`, `endl`, `int`, `void`, `return`, `vector`, `string`, `template`, `OOP` — and equivalent lists exist for Java and Python courses. Because the same list is passed on every decoding window, the lexical bias persists across the whole recording instead of decaying after the first context. Additional lesson-specific terms can be injected through a `custom_hotwords` argument without code changes.

**4) Stage 2 — Tech Canonicalizer.** Hotword biasing reduces but does not eliminate phonetic errors, because the decoder only *prefers* the listed words. The second stage is therefore a deterministic, ordered dictionary of regular expressions (`TECH_CANONICAL_MAP`) applied to every segment, case-insensitively and after Unicode NFC normalization, **before** chunking and vectorization. Let $s$ be a segment and $(p_i, r_i)$ the *i*-th rule; then

$$\mathrm{canon}(s) = r_n\!\left(\cdots r_2\!\left(r_1(s)\right)\cdots\right),\qquad r_i(s) = \mathrm{re.sub}(p_i,\ r_i,\ s).$$

Beyond rewriting, the stage strips discourse fillers ("à ừm", "kiểu như là"), deletes Whisper silence hallucinations and collapses stuttered repeats of `include` / `main` / `iostream`. Table 2 lists representative rules of the implemented lexicon, grouped by the type of phonetic failure.

**Table 2. Representative rules of the implemented Tech Canonicalizer (verified against `TECH_CANONICAL_MAP`).**

| Category | Acoustic transliteration (input) | Canonical form (output) |
| :--- | :--- | :--- |
| Language names | "si cộng cộng", "xi cộng cộng", "xê cộng cộng" | `C++` |
| Language names | "pay thần", "pai thơn" | `Python` |
| Preprocessor / library | "thăng include" (and variants) | `#include` |
| Preprocessor / library | "ios chìm", "ai âu sờ trim" | `<iostream>` |
| Console I/O | "xì in", "si in", "xê in" | `cin` |
| Console I/O | "xì out", "si out", "xê out" | `cout` |
| Console I/O | "en lai", "en đơ lai" | `endl` |
| Primitive types | "in tơ dơ", "in ti dơ" | `integer` |
| Primitive types | "bu lơ", "bu lê", "bu lin" | `bool` |
| Primitive types | "phờ lốt", "full load" | `float` |
| Primitive types | "sờ chinh", "sờ tring", "sờ trinh" | `string` |
| Primitive types | "N bài" (e.g. "bốn bài") | `N byte` |
| Control flow | "vòng lập bốn", "vòng là con" | `vòng lặp for` |
| Control flow | "vòng lặp quai", "hoạt động qua" | `vòng lặp while` |
| Control flow | "hai dầu trầm 7" | `hai dấu chấm phẩy` |
| IDE & shortcuts | "can chua", "can trô" | `Ctrl` |
| IDE & shortcuts | "ham men" | `hàm main` |
| IDE & shortcuts | "bui nè" | `build` |

Rules are ordered from specific to general (for instance, the compound "float và double" rule precedes the single-word `float` and `double` rules) so that a longer phonetic match is never pre-empted by one of its substrings. The mapping is kept as a data-driven dictionary rather than being scattered over the retrieval code, so that extending the lexicon requires re-running the canonicalization and re-embedding, not retraining or changing the retriever.

**Planned lexicon extension.** Section VI-B reports residual errors found by direct inspection of the final chunks. We have specified the following additional rules, which target the residual classes and have *not* been applied to the evaluated corpus: "con trỏ nun" → `nullptr`; "xâu ký tự" → `std::string`; "mảng hai chiều" → `2D array`; "ô ô pơ" → `OOP`; and the hyphenated transliteration "si-lát-lát" → `C++`. Following the pre/post-optimization protocol of Section IV-E, they will be introduced only between two runs of the frozen benchmark.

**5) Chunking, vectorization and idempotent indexing.** Canonicalized segments are merged into **time-aware chunks of 60–90 s with a 15 s overlap**, so that a concept cut by a chunk boundary is still fully contained in a neighbor; the corpus yields **6,387 chunks** (83 chunk files). Each chunk keeps its start/end seconds and `mm:ss` labels, which later become the verified video anchors. Chunks are embedded with `intfloat/multilingual-e5-large` [6] (1,024 dimensions, asymmetric `passage:` prefix at indexing and `query:` prefix at search) and with the `Qdrant/bm25` sparse encoder, and are upserted into Qdrant under deterministic UUIDv5 identifiers so that re-ingestion after a lexicon update is idempotent and never duplicates points. Code is chunked at AST boundaries with Tree-sitter, so that no function is cut mid-statement.

**6) Corpus health check.** A static audit over the 83 chunk files with the rule-pattern list of the canonicalizer reports 0 residual anomalies (83/83 lessons "clean"). This audit only verifies the *known* rule patterns; it is not evidence that the transcripts are free of other phonetic errors. We therefore also inspected the chunks directly (Section VI-B): the pre-canonicalization form "si cộng cộng" occurs 0 times, while the canonical `C++` appears 303 times in 58 lessons' chunk files, confirming that the implemented rules are effective for the classes they cover.

### B. HYBRID DUAL-BACKEND TOPOLOGY AND PEDAGOGICAL INTEGRATION

The Copilot is deployed as a *Hybrid Dual-Backend* system in which two independently deployable services own different kinds of truth (Fig. 1).

- **Platform core — Spring Boot 3.2.** Owns account management (Spring Security, JWT, BCrypt), the course and lesson catalogue (the `courseId`, `order`, `videoUrl`/`videoId` and code-snippet fields of the `Lesson` entity), quizzes, learning progress, payment (PayOS) and OTP flows (Redis). Persistent state is stored in MongoDB. This service is the authority on *who* the learner is and *how far* the learner has progressed.
- **AI microservice — FastAPI (asyncio, Pydantic v2).** Owns the entire RAG pipeline: the cascade router, the hybrid retrieval with In-HNSW pre-filtering, the CRAG grader, context assembly, Socratic generation and the streaming of results over Server-Sent Events (SSE). It exposes the chat endpoints under `/api/v1/chat`, each request carrying `course_id`, `lesson_seq`, the query and an optional `session_id`, which doubles as the LangGraph checkpointer `thread_id`.

The contract between the two is a small entity mapping: `course_id` ← `Lesson.courseId`; `lesson_seq` ← `Lesson.order`; and the video identifier that the player resolves. The `lesson_seq` value is the learner's *current* lesson; the AI service converts it into the pre-filter `course_id == C ∧ lesson_seq ≤ L`, so that the tutor never spoils lessons the learner has not reached, and the Platform core validates the claimed progress against its own record before forwarding. The separation brings two practical benefits: the retrieval and grading path continues to work (fast-path replies, retrieval, CRAG grading, timestamp extraction) when the remote GPU that hosts the generation LLM is switched off, and the transactional state (accounts, payments, progress) is never entrusted to an approximate-nearest-neighbor index.

> **Scope of the evaluation.** The FastAPI service and the 3-column canvas described below are exercised end-to-end by the benchmarks of Section V. The Spring Boot platform exposes the entity fields listed above and its React 19 / Vite 7 front-end hosts the lesson page and the video player; the proxying of Copilot requests through the platform with server-side progress validation is specified as an integration contract and is **not** part of the measured results.

**In-Course 3-Column Canvas.** The learner-facing studio arranges the pedagogical workflow in three spatial columns (Fig. 2), so that explanation, evidence and action are always visible together:

1. **Left — Syllabus and inspection panel (340 px).** Lists the lessons of the curriculum with instant text filtering and the AST code inspector; a click on a code definition seeks the video to its bound second.
2. **Center — Focal video canvas (flexible, full remaining width).** Embeds the YouTube IFrame Player and fills all available space; it is deliberately free of placeholder panels so that the lecture, which is the primary teaching medium, is never reduced.
3. **Right — Socratic assistant panel (fixed width, ≈ 390 px).** Streams the tutor's reply token by token, exposes the CRAG decision in a "thought drawer" and renders `<timestamp sec="145">02:25</timestamp>` tags as clickable chips that call `player.seekTo(sec)`.

The layout follows a light, high-contrast education-SaaS visual style with vector icons. The deterministic timestamp whitelist binds the right and center columns: the SSE decoder keeps the set $\mathcal{W}=\{s \mid s \in \text{suggested\_timestamps}\}$ of seconds vouched for by retrieval and drops any `<timestamp sec="X">` tag with $X \notin \mathcal{W}$ from the token stream, so a chip that the learner can click always points to a verified moment.

### C. BENCHMARKS

Two independent suites are used. The single-turn set is the frozen held-out set of the router decontamination protocol (maximum Jaccard similarity to the 480-sample training corpus 0.6842 < 0.70).

- **Stage 11 Golden Benchmark (single-turn, N = 200).** Four tiers: *In-Scope Technical* (80), *Out-of-Lesson* (40), *Adversarial Hybrid* (40) and *Chit-Chat / Out-of-Domain* (40).
- **Deterministic Multi-Turn Benchmark (50 sessions, 222 turns).** Four stress tiers: *Ellipsis & Anaphora* (15 sessions, 60 turns), *Socratic Refusal* (15, 60), *Topic Switching* (10, 42) and *Context Budget* (10, 60). The retrieval-mode run uses no remote LLM. A separate *end-to-end* run (15 sessions, 60 turns, 30 live LLM generations on a remote GPU) measures Socratic compliance.

### D. METRICS

Let $\mathbb{1}[\cdot]$ be the indicator function and $N$ the number of evaluated cases (or turns).

$$\text{Acc}_{\text{intent}} = \frac{1}{N}\sum_{i=1}^{N}\mathbb{1}\left[\hat{y}_i = y_i\right] \tag{4.1}$$

$$\text{SRP} = \frac{\#\{\text{solicitations refused without code leakage}\}}{\#\{\text{solicitations}\}} \tag{4.2}$$

- **Router accuracy / Intent accuracy** — Eq. (4.1) on the routed intent.
- **CRAG precision / Retrieval-status accuracy** — correctness of the grader state (`grounded`, `out_of_lesson`, `coverage_gap`).
- **Anaphora Resolution Rate (ARR)** — fraction of elliptical or pronominal follow-ups whose reformulated query recovers the correct technical target.
- **Socratic Refusal Precision (SRP)** — Eq. (4.2).
- **Timestamp safety** — emitted `<timestamp>` tags that are whitelisted and within tolerance, or absent when none is warranted. **Strict WHR** (whitelist hit rate, ±30 s) additionally requires proximity to the single annotated reference second.
- **Context budget compliance** — dialogue history ≤ 2,400 characters.

### E. PROTOCOL

All metrics are read from the JSON artifacts produced by the benchmark runners, with no manual transcription. Architectural or configuration changes are bracketed by two runs of the Stage 11 suite (a baseline before, a regression check after). Because a long lecture can teach one concept at several moments (theory, demonstration, exercise), a deviation |Δt| > 30 s from the single annotated second is reported separately as a single-label annotation discrepancy, not as a hallucination; we therefore report both strict WHR and the multi-grounding safety rate. The Stage 11 set was frozen for router training, but it was also run repeatedly during system development, so its results should be read as a development-stage benchmark rather than as a fully blind test (Section VI-B).

---

## V. EXPERIMENTAL RESULTS

### A. SINGLE-TURN RESULTS (STAGE 11, N = 200)

**Table 3. Stage 11 Golden Benchmark by tier (N = 200).**

| Tier | N | Router OK | Router Acc. | CRAG OK | CRAG Acc. | Avg. latency (ms) |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| In-Scope Technical | 80 | 80 | 100.0% | 79 | 98.8% | 5,499.3 |
| Out-of-Lesson | 40 | 40 | 100.0% | 37 | 92.5% | 6,163.5 |
| Adversarial Hybrid | 40 | 28 | 70.0% | 22 | 55.0% | 5,894.5 |
| Chit-Chat / OOD | 40 | 34 | 85.0% | 35 | 87.5% | 1,423.5 |
| **Overall** | **200** | **182** | **91.0%** | **173** | **86.5%** | **4,896.0** |

Router accuracy is **91.0%** (182/200) and CRAG precision **86.5%** (173/200). The system is perfect on in-scope and out-of-lesson routing (120/120), which is the failure mode the Pareto boundary targets. Timestamp safety is 87.0% (174/200) and strict timestamp accuracy 85.0% (170/200). Errors concentrate in the adversarial-hybrid tier, where a single query mixes a course concept with an off-topic or manipulative framing; it accounts for 12 of the 18 router errors. On the three-class intent task alone, the first-stage ONNX INT8 SLM reaches 92.5% accuracy (185/200) against 90.5% for the LinearSVC baseline on the same frozen set, at a median latency of 0.02 ms.

### B. MULTI-TURN RESULTS (50 SESSIONS, 222 TURNS)

**Table 4. Deterministic multi-turn benchmark.**

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

**Table 5. Multi-turn results by stress tier.**

| Tier | Sessions / Turns | Intent | Status | Multi-grounding TS | Budget | ARR / SRP |
| :--- | :---: | ---: | ---: | ---: | ---: | :---: |
| 1. Ellipsis & Anaphora | 15 / 60 | 100.0% | 100.0% | 100.0% | 100.0% | ARR 100.0% |
| 2. Socratic Refusal | 15 / 60 | 100.0% | 100.0% | 100.0% | 100.0% | SRP 100.0% |
| 3. Topic Switching | 10 / 42 | 92.86% | 92.86% | 95.24% | 100.0% | — |
| 4. Context Budget | 10 / 60 | 100.0% | 98.33% | 100.0% | 100.0% | — |

Anaphora Resolution reaches 98.94% overall, showing that context-aware query formulation recovers technical targets from pronouns and elliptical follow-ups without cross-turn keyword pollution. Socratic Refusal Precision is **100.0%** on the solicitation turns of the retrieval run, and in the end-to-end run all 30 live LLM generations were compliant (compliance 100.0%, no guardrail intervention). On that smaller end-to-end run (15 sessions, 60 turns) intent accuracy is 98.33% and ARR 96.67%. Topic switching is the weakest tier (92.86%): after a change of subject the previous turn still biases reformulation in a small number of cases.

### C. DISCUSSION OF RESULTS

**Pareto gating.** Perfect routing on the out-of-lesson tier together with 98.8% CRAG precision on in-scope queries indicates that the stratified margins avoid both failure directions: future lessons are not swallowed by an old lesson with passing commentary, and current-lesson questions are not hijacked by later lectures.

**Data layer and retrieval.** The retrieval metrics above are measured on the canonicalized corpus of Section IV-A. Because the benchmark was not run on a corpus *without* the Canonicalizer, this paper does not claim a measured accuracy gain from it; the evidence is the direct disappearance of the targeted transliterations (zero residual "si cộng cộng", Section IV-A.6), and an ablation on the corpus version is left to future work.

**Latency.** The first-stage SLM router adds negligible cost (P50 0.02 ms on the held-out set), so latency is dominated by retrieval, CPU re-ranking and, in end-to-end mode, remote generation. Average single-turn latency is 4.9 s; multi-turn P50/P95 are 5.8 s and 15.0 s, with a heavy tail (P99 59.1 s, maximum 138.7 s) that we attribute to re-ranker and cold-start effects. This is acceptable for an asynchronous tutor but not for real-time interaction.

**Strict versus multi-grounding timestamps.** Strict WHR is only 53.6%, whereas multi-grounding safety is 99.1%. The gap reflects that concepts recur across a lecture and the benchmark stores a single reference second; it does not indicate fabricated moments, because every emitted tag passes the deterministic whitelist.

---

## VI. DISCUSSION AND CONCLUSION

### A. DISCUSSION

The results support four design conclusions. First, educational RAG needs a notion of *sufficiency* separate from relevance: with a flat threshold, passing remarks in an early lecture are indistinguishable from teaching. A stratified margin that depends on the confidence of the current lesson resolves this without lesson-specific rules. Second, a cascade router that delegates ambiguous cases to an NLI arbiter replaces brittle regular expressions in the *query* path and keeps the common path under a millisecond. Third, pedagogical guarantees (Socratic refusal, verified timestamps, bounded history) are most reliable when enforced as deterministic invariants around the LLM instead of being requested through prompting. Fourth, the *corpus* path has different requirements from the query path: the transliteration errors are a closed, enumerable set of pronunciations of a finite technical vocabulary, which makes a curated rewrite lexicon, applied once at indexing time and kept as data, an appropriate tool there, while an open-ended user query is better served by learned arbitration.

### B. LIMITATIONS

1. **Residual phonetic errors.** Direct inspection of the final chunk files shows that the Canonicalizer does not cover every error class: the form "con trỏ nun" (null pointer, which Whisper renders from `nullptr`/`NULL`) still appears 19 times in 4 lessons' chunks and "xâu ký tự" appears unnormalized 3 times, while the corpus audit script (Section IV-A.6) reports zero anomalies because it checks only the same known patterns. The planned extension of Section IV-A.4 addresses these classes; the effect on retrieval has not yet been measured.
2. **ASR configuration provenance.** The service is configured with `large-v3` (CPU, INT8), but the batch-ingestion script defaults to the smaller `small` model unless `--model large-v3` is passed, and the per-lesson reports do not record the model size; the figure "large-v3" therefore rests on the author's run configuration rather than on a logged artifact. No word-error-rate measurement against human transcripts was performed.
3. **Duration figure.** The 82.2-hour total is the sum of the last segment end per lesson; it measures transcribed timeline, not independently verified video length.
4. **Adversarial hybrid queries** remain the main error source (70.0% router accuracy, 55.0% CRAG precision).
5. **Strict single-label timestamp matching** is 53.6%; a multi-reference annotation scheme is needed to measure timestamp accuracy more faithfully.
6. **Latency tail** of the multi-turn run (P99 59.1 s) is too high for synchronous use.
7. **Benchmark independence.** The Stage 11 set was frozen for router training but reused across many development iterations, so threshold decisions are not fully blind with respect to it.
8. **Scope.** The corpus is one instructor's C++/OOP/data-structure course in Vietnamese–English speech; generalization to other languages, courses and student cohorts, and to human learning outcomes, is untested. The Socratic compliance check covers 30 generations, a small sample. The multi-turn suite is deterministic and synthetic; it complements but does not replace a user study. The Spring Boot ↔ FastAPI request path is specified but not evaluated end-to-end.

### C. CONCLUSION

We presented an agentic RAG architecture for Socratic in-course programming tutoring that unifies a domain-aware speech-to-text pipeline (faster-whisper large-v3, Silero VAD at θ = 0.35 / 400 ms padding, hotword biasing, Tech Canonicalizer), a cascade intent router, true hybrid retrieval with In-HNSW pre-filtering, a three-tier Pareto Context Sufficiency boundary and a stateful LangGraph orchestration with a deterministic timestamp whitelist, deployed through a Hybrid Dual-Backend topology and an In-Course 3-Column Canvas. It achieved 91.0% router accuracy and 86.5% CRAG precision on 200 single-turn queries, and 98.65% intent accuracy, 98.20% retrieval-status accuracy, 98.94% ARR and 100.0% SRP on 222 multi-turn turns. Future work includes extending and ablating the canonicalization lexicon with a measured word-error-rate study, multi-reference timestamp annotation, targeted training for adversarial hybrid queries, latency reduction of the re-ranking stage, end-to-end evaluation through the Spring Boot platform, and a controlled classroom study of learning outcomes.

---

## VII. ACKNOWLEDGMENTS

The author sincerely thanks M.Sc. Tieu Phung Mai Suong, Faculty of Information Technology, Ho Chi Minh City University of Foreign Languages – Information Technology (HUFLIT), for her valuable academic guidance, constructive feedback and dedicated supervision throughout this research. The author also thanks the Faculty of Information Technology, HUFLIT, for providing institutional research facilities.

---

## VIII. REFERENCES

[1] S.-Q. Yan, J.-C. Gu, Y. Zhu, and Z.-H. Ling, "Corrective retrieval augmented generation," *arXiv preprint* arXiv:2401.15884, 2024.

[2] H. Joren, J. Zhang, C.-S. Ferng, D.-C. Juan, A. Taly, and C. Rashtchian, "Sufficient context: A new lens on retrieval augmented generation systems," in *Proc. Int. Conf. Learn. Represent. (ICLR)*, Singapore, 2025.

[3] N. F. Liu, K. Lin, J. Hewitt, A. Paranjape, M. Bevilacqua, F. Petroni, and P. Liang, "Lost in the middle: How language models use long contexts," *Trans. Assoc. Comput. Linguist.*, vol. 12, pp. 157–173, 2024.

[4] P. Lewis *et al.*, "Retrieval-augmented generation for knowledge-intensive NLP tasks," in *Proc. Adv. Neural Inf. Process. Syst. (NeurIPS)*, vol. 33, 2020, pp. 9459–9474.

[5] SYSTRAN, "faster-whisper: Faster Whisper transcription with CTranslate2," GitHub repository, 2023. [Online]. Available: https://github.com/SYSTRAN/faster-whisper

[6] L. Wang, N. Yang, X. Huang, L. Yang, R. Majumder, and F. Wei, "Multilingual E5 text embeddings: A technical report," *arXiv preprint* arXiv:2402.05672, 2024.

[7] A. Radford, J. W. Kim, T. Xu, G. Brockman, C. McLeavey, and I. Sutskever, "Robust speech recognition via large-scale weak supervision," in *Proc. Int. Conf. Mach. Learn. (ICML)*, 2023, pp. 28492–28518.

[8] S. Robertson and H. Zaragoza, "The probabilistic relevance framework: BM25 and beyond," *Found. Trends Inf. Retr.*, vol. 3, no. 4, pp. 333–389, 2009.

[9] Y. A. Malkov and D. A. Yashunin, "Efficient and robust approximate nearest neighbor search using hierarchical navigable small world graphs," *IEEE Trans. Pattern Anal. Mach. Intell.*, vol. 42, no. 4, pp. 824–836, Apr. 2020.

[10] J. C. Platt, "Probabilistic outputs for support vector machines and comparisons to regularized likelihood methods," in *Advances in Large Margin Classifiers*, A. J. Smola *et al.*, Eds. Cambridge, MA, USA: MIT Press, 1999, pp. 61–74.

[11] Silero Team, "Silero VAD: Pre-trained enterprise-grade voice activity detector (VAD), number detector and language classifier," GitHub repository, 2021. [Online]. Available: https://github.com/snakers4/silero-vad

[12] W. Yin, J. Hay, and D. Roth, "Benchmarking zero-shot text classification: Datasets, evaluation and entailment approach," in *Proc. Conf. Empirical Methods Natural Lang. Process. (EMNLP-IJCNLP)*, Hong Kong, 2019, pp. 3914–3923.

[13] R. Paul and L. Elder, *The Thinker's Guide to The Art of Socratic Questioning*. Dillon Beach, CA, USA: Foundation for Critical Thinking, 2006.

[14] S. MacNeil *et al.*, "Experiences from using code explanations generated by large language models in a web software development e-book," in *Proc. 54th ACM Tech. Symp. Comput. Sci. Educ. (SIGCSE)*, 2023, pp. 931–937.

[15] P. He, J. Gao, and W. Chen, "DeBERTaV3: Improving DeBERTa using ELECTRA-style pre-training with gradient-disentangled embedding sharing," in *Proc. Int. Conf. Learn. Represent. (ICLR)*, 2023.

---

## KHỐI SONG NGỮ TIẾNG VIỆT — TRANG 8

**KIẾN TRÚC AGENTIC RAG ĐẠT NGƯỠNG ĐỦ NGỮ CẢNH PARETO KẾT HỢP ĐỒNG BỘ AST–VIDEO CHO TRỢ GIẢNG LẬP TRÌNH THEO PHƯƠNG PHÁP SOCRATIC: THIẾT KẾ GIẢI THUẬT**

**Trần Thành Nghĩa**
Khoa Công nghệ Thông tin (MSSV: 23DH112252), Trường Đại học Ngoại ngữ – Tin học Thành phố Hồ Chí Minh (HUFLIT)

**TÓM TẮT** — Trong giáo dục lập trình trực tuyến dựa trên video bài giảng dài (30–60 phút), bài giảng nhập môn có lời nói nhắc lướt thường được truy xuất lấn át các bài giảng chuyên sâu ở phía sau, trong khi các mô hình ngôn ngữ lớn đa dụng dễ tiết lộ lời giải hoàn chỉnh cho sinh viên. Vấn đề còn bắt đầu từ tầng dữ liệu: giảng viên Việt Nam phát âm thuật ngữ lập trình tiếng Anh theo cách mà mô hình nhận dạng tiếng nói chuyển thành các chuỗi âm tiết nghe hợp lý nhưng sai về kỹ thuật. Bài báo trình bày In-Course Agentic RAG Copilot, hệ thống trợ giảng Socratic xây dựng trên 83 bài học C++, OOP và cấu trúc dữ liệu (82,2 giờ video) qua quy trình chuyển giọng nói thành văn bản hai tầng: `faster-whisper` large-v3 kết hợp Silero VAD (ngưỡng 0,35; `speech_pad_ms` = 400) loại bỏ khoảng lặng và tiếng gõ phím, kỹ thuật thiên lệch từ vựng chuyên ngành (Domain Hotwords Lexicon Biasing) và tầng Tech Canonicalizer dùng biểu thức chính quy chuẩn hóa lỗi phiên âm trước khi vector hóa. Việc trả lời được điều phối bằng đồ thị trạng thái LangGraph gồm bốn nút (định tuyến, truy xuất lai, thẩm định CRAG, lắp ráp ngữ cảnh), triển khai trên kiến trúc Hybrid Dual-Backend (Spring Boot cho nền tảng học tập và FastAPI cho vi dịch vụ AI) và hiển thị qua bố cục In-Course 3-Column Canvas, trong đó cột video được điều khiển bằng các mốc thời gian đã được xác thực. Chúng tôi hình thức hóa ngưỡng đủ ngữ cảnh Pareto ba phân tầng, tách bạch độ tương quan ngữ nghĩa với độ đầy đủ thông tin sư phạm. Trên bộ Golden Benchmark 200 câu đơn lượt, hệ thống đạt độ chính xác định tuyến **91,0%** và độ chuẩn xác CRAG **86,5%**. Trên bộ đa lượt xác định gồm 50 phiên (222 lượt), hệ thống đạt độ chính xác ý định **98,65%**, độ chính xác trạng thái truy xuất **98,20%**, tỷ lệ giải quyết hồi chỉ (ARR) **98,94%** và độ chính xác từ chối giải bài hộ (SRP) **100,0%**. Bài báo cũng nêu các hạn chế còn tồn tại: tỷ lệ khớp mốc thời gian nghiêm ngặt một nhãn (53,6%), nhóm câu hỏi lai đối kháng (độ chính xác định tuyến 70,0%) và một tập lỗi phiên âm chưa được chuẩn hóa còn sót trong ngữ liệu.

**Từ khóa** — Agentic RAG, Corrective RAG (CRAG), Đủ ngữ cảnh Pareto, Nhận dạng tiếng nói, Chuẩn hóa phiên âm, Silero VAD, Hybrid Dual-Backend, Phương pháp Socratic.

**LỜI CẢM ƠN** — Tác giả chân thành cảm ơn ThS. Tiếu Phùng Mai Sương, Khoa Công nghệ Thông tin, Trường Đại học Ngoại ngữ – Tin học TP.HCM (HUFLIT), đã tận tình hướng dẫn, góp ý và đồng hành trong suốt quá trình thực hiện nghiên cứu này. Tác giả cũng cảm ơn Khoa Công nghệ Thông tin, HUFLIT đã hỗ trợ cơ sở vật chất nghiên cứu.

---

## TIỂU SỬ TÁC GIẢ / AUTHOR BIOGRAPHY

| | |
| :--- | :--- |
| **English** | **Tran Thanh Nghia** is an undergraduate student (Student ID: 23DH112252) at the Faculty of Information Technology, Ho Chi Minh City University of Foreign Languages – Information Technology (HUFLIT), Vietnam. His research interests include retrieval-augmented generation, educational AI tutoring, speech-to-text for lecture video, and conversational agent orchestration. He designed and implemented the In-Course Agentic RAG Copilot described in this paper under the supervision of M.Sc. Tieu Phung Mai Suong. Email: nghia.23dh112252@st.huflit.edu.vn. |
| **Tiếng Việt** | **Trần Thành Nghĩa** là sinh viên (MSSV: 23DH112252) Khoa Công nghệ Thông tin, Trường Đại học Ngoại ngữ – Tin học TP.HCM (HUFLIT). Hướng nghiên cứu quan tâm: sinh văn bản tăng cường truy xuất (RAG), trợ giảng AI trong giáo dục, nhận dạng tiếng nói cho video bài giảng và điều phối tác tử hội thoại. Tác giả thiết kế và hiện thực hiệu hệ thống In-Course Agentic RAG Copilot trình bày trong bài báo, dưới sự hướng dẫn của ThS. Tiếu Phùng Mai Sương. Email: nghia.23dh112252@st.huflit.edu.vn. |

---

## GHI CHÚ CỦA THƯ KÝ HỌC THUẬT (không thuộc bản thảo nộp)

Các điểm lệch giữa đề bài và dữ liệu/mã nguồn thực tế, đã xử lý như sau:

| # | Đề bài | Kiểm chứng thực tế | Cách xử lý trong bản thảo |
| :-- | :--- | :--- | :--- |
| 1 | Tech Canonicalizer: 'si-lát-lát'→C++, 'xâu ký tự'→std::string, 'con trỏ nun'→nullptr, 'mảng hai chiều'→2D array, 'ô ô pơ'→OOP | **Không có trong `TECH_CANONICAL_MAP`.** Map thực có 'si/xi/xê cộng cộng'→C++, 'sờ chinh/sờ tring'→string, 'xì in/out'→cin/cout, 'in tơ dơ'→integer… Chunk hiện còn 'con trỏ nun' ×19 (4 bài), 'xâu ký tự' ×3 | Table 2 chỉ liệt kê rule đã triển khai; 5 ánh xạ của đề bài đưa vào mục "Planned lexicon extension" (ghi rõ chưa áp dụng) và Limitation #1 |
| 2 | Hotwords: std::vector, nullptr, polymorphism… | Danh sách C++ thực gồm 23 từ (không có nullptr, polymorphism, std::vector) | Liệt kê đúng 23 từ thực tế |
| 3 | 52+ giờ video | Tổng timeline phiên âm = **82,17 giờ** (78,77 giờ có lời) | Ghi 82,2 giờ (vẫn thỏa "52+"); Limitation #3 |
| 4 | faster-whisper large-v3 | `app/config.py` = large-v3, nhưng `batch_ingest_videos.py` mặc định `small`; report từng bài không ghi model | Ghi large-v3 theo đề bài; Limitation #2 yêu cầu xác nhận |
| 5 | Silero VAD loại tiếng gõ phím | Mã chỉ có tham số VAD; chưa có đo lường riêng cho tiếng gõ phím | Diễn đạt là mục tiêu thiết kế, không khẳng định định lượng |
| 6 | Tích hợp Spring Boot + FastAPI | Spring BE (3.2.0, MongoDB, JWT, PayOS) và FastAPI tồn tại; **không tìm thấy** code Spring/React gọi `/api/v1/chat` hay `seekTo`; 3-column canvas hiện thực tại `app/templates/playground.html` (cột phải 400px trong code, 390px theo chuẩn) | Mô tả là "integration contract"; khung "Scope of the evaluation" nêu rõ phần chưa đo |
| 7 | Stage 11 Router 91,0% | Khớp JSON (182/200). (AGENTS.md ghi kỷ lục 95,50% là đợt chạy cũ) | Dùng 91,0% |
| 8 | Các số liệu còn lại (98,65 / 98,20 / 98,94 / 100,0 / 86,5) | Khớp 100% với JSON/MD | Dùng nguyên |
| 9 | 15 tài liệu tham khảo IEEE | Bản cũ thiếu faster-whisper và Silero VAD | Thay [5] Gao et al. (survey) và [11] Guo et al. bằng faster-whisper và Silero VAD; vẫn đủ 15 mục |
