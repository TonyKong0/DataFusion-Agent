# Evaluation page operations design

## Goal

Let a developer or collaborator prepare the local Online Retail II benchmark and run bounded evaluations from `/evaluation`, without copying shell commands. Each checkout downloads the source workbook into ignored `backend/data/benchmarks/`, imports only the dedicated benchmark schemas, and runs against that machine's configured local MySQL and model account.

## User flow

The page is a focused local evaluation workbench. It shows workbook presence and checksum, MySQL reachability, and actual row counts for `retail_bench_1k` and `retail_bench_10k`.

1. **下载并校验数据** downloads the pinned UCI-derived workbook revision and verifies its recorded SHA-256. The download stays outside Git.
2. **预览样本** scans the local workbook and shows source and selected row counts. It does not write to MySQL.
3. **导入基准库** requires an explicit click after preview. It creates or populates only `retail_bench_1k` and `retail_bench_10k`; it refuses to overwrite non-empty tables unless a separate future workflow is intentionally added.
4. **数据库冒烟检查** executes the fixed 10 read-only reference SQL cases on both sample sizes and reports query success without calling an LLM.
5. **真实评测** lets the operator choose the retail 1k/10k benchmark or the existing labeled 10-question NL2SQL + 10-question RAG suite, set a repetition count where applicable, and enter a positive maximum API-request count before starting. There is no automatic API call. The result shows completion, per-case accuracy/latency, token usage when available, unreported usage, and the saved report path.
6. **其他能力指标** runs the 110-question cross-source routing/planning suite with 45 synthetic-tool tasks, and the 100-case controlled multi-document/version/table/chart/image suite; both use no paid API calls and state their synthetic/fixture scope. The optional OHR-Bench v2 15-question material suite requires a locally provided `pdfs.zip` and an explicit API request cap.

The interface presents one active job at a time, with phase, latest safe progress text, terminal state, category-level metrics, scope limitations, token use, and saved report paths. Historical comparison, stale regression summaries, and failure-analysis cards are omitted so the page focuses on current local workflows. Layout follows the current evaluation page styles and remains usable on narrow screens.

## Backend boundary

Extend the evaluation router with a local-workbench status endpoint, a start-job endpoint with a strict operation enum and validated numeric options, and a job-status endpoint. Run only repository-owned scripts with `sys.executable` and argument arrays; never accept shell text or arbitrary file paths from the browser. A process-local lock allows one operation at a time. Poll captured progress and save generated evaluation reports under ignored `backend/data/evaluation/` so a local test does not overwrite tracked historical evidence.

Mutating endpoints (download, import, and live evaluation) accept requests only from loopback clients because this workbench acts on the server's local filesystem, MySQL credentials, and model key. Apply uses fixed schema names and the existing importer safeguards. Live runs require an explicit API-request cap. This cap bounds HTTP attempts including retries, not dollars; show that distinction beside the control.

## Errors and recovery

Report clear states for missing workbook, checksum mismatch, insufficient source rows, MySQL unavailable, missing or incomplete schema, an already populated benchmark table, missing RAG demo document, missing/invalid OHR archive, unavailable local BGE-M3 weights, absent model credentials, request-budget exhaustion, subprocess failure, and server restart. A failed download leaves no trusted workbook; a failed import must never delete Chinook or other schemas. Job state is in memory, so a server restart marks the previous job as unavailable and the operator can inspect actual database readiness before retrying.

## Verification

- API tests cover fixed operation allowlists, option validation, loopback restrictions, concurrent-job rejection, progress/status transitions, and scripts running with zero API requests in preview/smoke mode.
- Integration checks confirm download checksum, preview source/sample counts, dedicated database row counts, and the ten labeled reference queries on both sizes.
- UI checks cover download → preview → explicit import → smoke → bounded live run, errors, progress polling, responsive layout, and no implicit model invocation.
- Existing backend full suite and frontend production build remain required. No real API evaluation runs as part of automated tests.

## Scope

This iteration covers the UCI retail benchmark, labeled 10+10 suite, controlled offline cross-source/multimodal suites, and optional OHR-Bench live evaluation. OHR-Bench PDFs remain local research-only data and are not downloaded automatically or included in Git. The page does not expose arbitrary SQL, arbitrary scripts, schema replacement, or shell commands.
