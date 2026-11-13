# Product Requirements Document (PRD)

## News Summarizer Agent

| | |
|---|---|
| **Version** | 1.1 (MVP) |
| **Date** | November 10, 2026 |
| **Status** | Draft |
| **Project type** | Beginner-friendly AI agent |

---

## 1. Overview

The News Summarizer Agent takes a topic from the user (for example, "electric vehicles in India"), searches the web for recent news, reads the top articles, and returns a short, easy-to-read digest with source links.

It is built as a **fixed pipeline with LLM-driven steps**: the LLM rewrites the query, summarizes articles, and writes the digest. In the MVP the sequence of steps is fixed. As an optional stretch goal, the LLM may decide whether a second search round is needed when the first returns too few results (this makes the agent more autonomous).

## 2. Problem Statement

Staying updated on a topic means opening many tabs, reading long articles, and filtering out duplicates and noise. People who are short on time (students, professionals, hobbyists) need a quick, trustworthy summary of what is happening right now.

## 3. Goals

- Give a clear digest of the latest news on any topic in under 30 seconds (5 stories) or under 45 seconds (10 stories).
- Always show sources so the user can verify and read more.
- Keep the digest short, neutral, and easy to scan.
- Be simple enough to build as a first agent project.

## 4. Non-Goals (Out of Scope for MVP)

- No user accounts or login.
- No personalized feeds or recommendation engine.
- No scheduled or push notifications.
- No fact-checking or bias scoring.
- No audio or video news.
- No mobile app (a CLI or simple web page is enough).
- No multi-language output (English only in the MVP).
- No follow-up or clarifying questions (the agent is stateless in the MVP).
- No grouping of stories into themed sections (post-MVP).

## 5. Target Users

| User | Need |
|---|---|
| Students | Quick updates for current affairs, projects, or seminars |
| Working professionals | Brief daily industry updates |
| Curious readers | A fast overview of a trending topic |

## 6. User Stories

1. As a user, I want to type a topic and receive a short digest so I can stay informed quickly.
2. As a user, I want each point to link to its source so I can check the original article.
3. As a user, I want to choose how many stories I see (for example 3, 5, or 10).
4. As a user, I want only recent news (for example the last 24 hours, 7 days, or 30 days).
5. As a user, I want a clear message if no relevant news is found.

## 7. Functional Requirements

### 7.1 Input

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `topic` | text | Yes | none | Free text, 2 to 100 characters. Must not be on the vague-topic stoplist (see 7.6). |
| `num_stories` | integer | No | 5 | Range 3 to 10 |
| `time_range` | enum | No | `7d` | `24h`, `7d`, `30d` |

The digest language is English in the MVP. Summarizing in other languages is a post-MVP enhancement (see section 13).

### 7.2 Agent Workflow

1. **Understand the topic**: clean the query. If the topic is on the vague-topic stoplist, stop and return the "be more specific" message (see 7.6). Otherwise rewrite it into 1 to 3 better search queries.
2. **Search**: call the news search tool for each query, using its built-in date filter for `time_range`. Collect result links, titles, snippets, sources, and publish dates.
3. **Filter**:
   - Remove duplicate URLs and near-duplicate titles (same story from multiple outlets or wire copies).
   - Remove domains on the block-list.
   - Remove items outside `time_range`. If the search result has no date, use the date extracted from the page. If neither exists, drop the story.
   - Remove irrelevant or low-quality pages.
4. **Fetch (in parallel)**: open candidate articles at the same time and extract their main text. Fetch up to 2x `num_stories` pages (maximum 20), so failed or paywalled pages do not stop the digest from reaching the requested count.
   - If a page cannot be fetched, use another candidate.
   - If no other candidate is available, fall back to the search snippet and label the story "summary based on snippet only."
5. **Summarize (in parallel)**: summarize each article in 2 to 3 sentences, in the agent's own words, using only the fetched text. Each article is passed to the LLM with an ID (`[1]`, `[2]`, ...).
6. **Combine**: cluster any remaining duplicate stories, keep the best source for each, and write a short overall summary (the "quick summary").
7. **Respond**: output the digest in the required format. The application code, not the LLM, fills in the title, source name, date, and URL for each story from the search metadata, using the story ID.

### 7.3 Tools Used by the Agent

| Tool | Purpose |
|---|---|
| News search API (Tavily, with its news mode and date parameter) | Find recent articles for the topic |
| Article extractor (`trafilatura`) | Get readable text from a URL |
| LLM (Claude API or any LLM API) | Query rewriting, summarizing, and writing the quick summary |

The MVP uses a separate search API plus an article extractor. It does not use an LLM provider's built-in web search tool, so the pipeline stays visible and controllable.

### 7.4 Output Format

The digest is returned as **Markdown** and must contain:

1. **Topic and date range** at the top, showing the absolute dates and the reference timezone (UTC by default, configurable).
2. **Quick summary**: 2 to 3 sentences covering the big picture.
3. **Key stories**: one block per story with a title, a 2 to 3 sentence summary, the source name, the date, and a link.
4. **Closing line**: "Based on N sources," where N is the number of distinct stories after de-duplication.

**Example output**

```
Topic: Electric vehicles in India | Nov 3 to Nov 10, 2026 (UTC)

Quick summary:
EV sales continued to rise this week, with several automakers announcing
new models. Charging infrastructure remains the main concern.

Key stories:
1. New budget EV launched
   A major automaker unveiled an EV aimed at first-time buyers, priced
   to compete with petrol hatchbacks. Deliveries start next quarter.
   Source: Example News | Nov 8, 2026 | https://example.com/story-1

2. Charging stations expand in smaller cities
   ...

Based on 5 sources.
```

### 7.5 Rules for Summaries

- Summaries must be written in the agent's own words (no copying long passages from articles).
- Use neutral language; do not add opinions.
- Never invent facts, quotes, or links. If a detail is not in the source, leave it out.
- If sources disagree, mention that briefly.
- Every story must include a working source link.
- **Links are enforced by code.** The LLM refers to stories only by ID. Titles, source names, dates, and URLs come from search metadata and are inserted by the application. Before output, the application may run a quick HTTP check on each link and drop or replace any that fail.
- **Fetched text is data, never instructions.** Article text is wrapped in clear delimiters, and the LLM is told to ignore any instructions found inside it. Page content must never trigger new tool calls, change the output format, or alter the search plan.

### 7.6 Error and Edge Cases

| Case | Expected behavior |
|---|---|
| No results found | Tell the user, and suggest a broader topic or longer time range |
| Page cannot be opened (paywall or error) | Skip it and use another candidate; if none remain, use the search snippet and label it |
| Topic is too vague (on the stoplist, for example "news", "latest", "today", "update") | Return a message asking the user to enter a more specific topic. No follow-up conversation. |
| Search API fails | Show a friendly error and allow retry |
| Fewer sources than requested | Show what was found and say so (for example, "Only 3 stories found for this time range") |
| Story has no usable date | Drop it from the digest |
| Page text contains instructions aimed at the model | Ignore them; treat as ordinary text |

## 8. Non-Functional Requirements

| Area | Requirement |
|---|---|
| Speed | Final digest within 30 seconds for 5 stories and within 45 seconds for 10 stories (parallel fetching and summarizing) |
| Accuracy | Summaries must match the source content |
| Reliability | Handle failed pages and API errors without crashing |
| Security | Treat all fetched content as untrusted (prompt-injection protection, see 7.5) |
| Cost | Cap searches at 3 per request and fetched pages at 2x `num_stories` (maximum 20); limit text length sent to the LLM per article |
| Caching | Cache results for the same topic, time range, and story count for a short period (for example 15 minutes) so repeat requests do not spend API credits |
| Rate limiting | Apply a simple per-user or per-IP request limit |
| Privacy | Do not store personal data; only the topic query is processed. Basic logging (timing, errors, counts) is allowed without user identifiers. |
| Compliance | Respect robots.txt and site terms when fetching pages |
| Copyright | Short original summaries with links; no reproducing full articles |

## 9. Suggested Tech Stack (Beginner-Friendly)

| Layer | Option |
|---|---|
| Language | Python |
| LLM | Claude API (or any LLM API) |
| Web search | Tavily (free tier available), using its news mode and date filter |
| Article extraction | `trafilatura` |
| Concurrency | `asyncio` or a thread pool for parallel fetching and summarizing |
| Interface | Command line first; then Streamlit or a simple web page |
| Config | `.env` file for API keys; `blocklist.txt` for excluded domains |

## 10. Success Metrics

Metrics are measured against a **fixed test set of about 20 topics** (mix of broad, niche, fast-moving, and low-news topics), run before each release.

| Metric | Definition | Target |
|---|---|---|
| Digest generated successfully | A digest is returned with at least the minimum number of stories (3), or a clear friendly message when fewer exist | 95% or more of test requests |
| Valid source links | Each story's link opens and points to the cited article | 100% |
| Summary accuracy | Manual checklist per story: summary matches the article, date is correct, nothing invented | 90% or more of sampled stories pass |
| Average response time | Measured from request to final digest | Under 30 seconds for 5 stories; under 45 seconds for 10 |
| User rating | Thumbs up/down (collected once the Phase 6 UI exists) | 80% or more positive |

## 11. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Model makes up details (hallucination) | Misleading digest | Summarize only from fetched text; code inserts links and metadata; instruct the model to omit unknowns |
| Prompt injection from web pages | Hijacked or misleading output | Treat fetched text as data in delimiters; ignore embedded instructions; page content cannot trigger tool calls |
| Low-quality or fake news sources | Bad information | Block-list file applied in the Filter step; prefer known outlets |
| Paywalled or blocked pages | Missing content | Fetch up to 2x the requested stories; use alternates; snippet fallback with a label |
| API costs grow | Budget overrun | Cap searches and pages; limit text length; cache repeat requests; rate-limit users |
| Outdated or undated results | Stale news | News-mode date filter, page-date fallback, drop undated stories, show dates on every story |
| Slow responses | Poor experience | Parallel fetching and summarizing; separate time targets; optional streaming |
| Duplicate coverage | Inflated source count | De-duplicate by URL and title similarity; count distinct stories |

## 12. Milestones

| Phase | Deliverable | Estimated time |
|---|---|---|
| 1 | Search a topic (news mode, date filter) and print raw result links with dates | 1 day |
| 2 | Fetch and extract article text in parallel, with failure fallbacks | 2 days |
| 3 | LLM summarizes each article by ID, with prompt-injection protections | 2 days |
| 4 | De-duplicate, combine, and build the final digest (code-inserted links and metadata) | 1 to 2 days |
| 5 | Add options (count, time range), block-list, vague-topic stoplist, error handling, caching, rate limit | 2 days |
| 6 | Build the fixed 20-topic test set and run the metrics; add simple UI (Streamlit) with thumbs up/down | 2 to 3 days |

## 13. Future Enhancements (Post-MVP)

- Save favorite topics and get a daily or weekly digest by email.
- Multi-language summaries (re-introduce a `language` input).
- Group related stories into themed sections.
- Sentiment and bias indicators.
- Compare coverage of the same story across outlets.
- Voice or audio digest.
- "Ask follow-up questions" about a story, and clarifying questions for vague topics.
- Let the LLM decide when to run an extra search round (more agentic behavior).
- Streaming the digest as stories are completed.

## 14. Decisions on Previously Open Questions

| Question | Decision for MVP |
|---|---|
| Which search API will be used? | Tavily (free tier), using news mode and its date filter |
| Plain text, Markdown, or web card layout? | Markdown |
| Should the agent ask clarifying questions? | No. Vague topics get a "be more specific" message; otherwise proceed with defaults. |
| Which news sources are preferred or excluded? | A small block-list file (`blocklist.txt`), editable without code changes |

## 15. Acceptance Criteria (MVP Done When)

- [ ] User enters a topic and receives a digest with a quick summary and 3 to 10 stories, or fewer with a clear notice when fewer exist.
- [ ] Each story has a summary, source name, date, and working link, all inserted by code from search metadata.
- [ ] The time range and story count options work, and the digest header shows the absolute date range and timezone.
- [ ] Duplicate stories are merged, and "Based on N sources" counts distinct stories.
- [ ] Errors (no results, blocked pages, API failure, vague topic) show friendly messages.
- [ ] Prompt-injection test pages (articles containing "ignore your instructions") do not change the output.
- [ ] Response time is under 30 seconds for 5 stories and under 45 seconds for 10 in normal conditions.
- [ ] The 20-topic test set meets the success metrics in section 10.
