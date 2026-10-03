# ast-code-chunker (Dumped local copy for worker_m2_it2_1)

Source: d:\In_Course_Agentic_RAG_Copilot\.agents\skills\ast-code-chunker\SKILL.md

Key Methodology:
- Semantic code chunking using Tree-sitter for C++ and Java.
- Enforces clean function/class boundaries without cutting code lines.
- Payload schema: course_id, lesson_id, lesson_seq, content_type="code_ast", code_scope, start_line, end_line, raw_text.
- In-HNSW dynamic pre-filtering: course_id and lesson_seq <= current_lesson_seq.
- Code AST serves as unambiguous syntax anchor.
