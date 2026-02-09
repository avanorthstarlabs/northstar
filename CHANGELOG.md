# Changelog

## 2026-02-09T07:41:32Z
- Added proposal approval gate support + project slug in approved priorities.
- Dashboard now shows overview/summary/tech details/definition of done in proposals.
- Added per-project review actions and continue-work override prompts.

## 2026-02-07T15:51:19.407923+00:00
- Applied patch: dashboard_patch_2026-02-07T15-51-18.609474+00-00.diff

## 2026-02-07T16:25:55.432543+00:00
- Applied patch: dashboard_patch_2026-02-07T16-25-54.634728+00-00.diff

## 2026-02-07T16:32:28.850244+00:00
- Applied patch: dashboard_patch_2026-02-07T16-32-27.198528+00-00.diff


## 2026-02-07T16:40:00+00:00
- Outputs tab: clean labels, grouped project shortcuts, and one-click proposal opening.

## 2026-02-07T16:42:30+00:00
- Overview: added glassmorphic project tiles and a "Currently working on" section.

## 2026-02-07T16:47:30+00:00
- Applied black + neon green futuristic theme across the dashboard UI.

## 2026-02-07T16:52:30+00:00
- Overview: project tiles now show optional thumbnail previews if provided.

## 2026-02-07T16:56:30+00:00
- Overview: added optional "Open Preview" link for projects with a preview URL.

## 2026-02-07T17:00:00+00:00
- Simplified time formatting across dashboard panels.

## 2026-02-07T17:05:00+00:00
- Added cycle health indicator + latest patch name; improved activity feed on Projects tab.

## 2026-02-07T17:07:30+00:00
- Added Recent failures panel in Overview for last cycle errors.

## 2026-02-07T17:10:00+00:00
- Added Agent connection status card with activity description.

## 2026-02-07T17:12:30+00:00
- Added subtle pulse animation for active agent connection.

## 2026-02-07T17:15:30+00:00
- Display timestamps in PST (America/Los_Angeles) across dashboard views.

## 2026-02-07T17:18:30+00:00
- Added one-click copy buttons for recent failure logs.

## 2026-02-07T17:20:30+00:00
- Copy buttons now copy full error lines.

## 2026-02-07T17:28:00+00:00
- Recent failures: moved copy button to left and removed iframe background.

## 2026-02-07T17:33:00+00:00
- Replaced iframe copy button with native button + copy buffer (no white boxes).

## 2026-02-07T17:37:00+00:00
- Restored one-click copy with neon icon button for recent failures.

## 2026-02-07T19:00:00+00:00
- Recent failures: unified row layout with inline copy button and styled code block (no stray boxes).

## 2026-02-07T19:05:00+00:00
- Recent failures: truncated error container height for cleaner layout.

## 2026-02-07T19:10:00+00:00
- Recent failures: added bordered card container around truncated error text.

## 2026-02-07T19:14:00+00:00
- Copy button now flashes a checkmark and glow on click.

## 2026-02-07T19:20:00+00:00
- Added review approve/continue controls to Settings tab.

## 2026-02-07T19:25:00+00:00
- Added confirmation prompts for review actions.

## 2026-02-07T19:30:00+00:00
- Review controls now use modal confirmations.

## 2026-02-07T19:40:00+00:00
- Brief me: added timeout handling + Ollama reachability indicator + diagnostics test.

## 2026-02-07T20:00:00+00:00
- Overview: added Action required review controls when PENDING_HUMAN_REVIEW.

## 2026-02-07T20:10:00+00:00
- Fixed review modal handlers available on Overview and Settings.

## 2026-02-07T20:15:00+00:00
- Review modals now close immediately after action (rerun).

## 2026-02-07T20:25:00+00:00
- Brief me: warm-up ping + one-paragraph summary prompt.

## 2026-02-07T20:35:00+00:00
- Fixed activity feed helper scope by using global project changelog scanner.
## 2026-02-08T00:15:07.022149+00:00
- Applied patch: dashboard_patch_2026-02-08T00-15-00.667928+00-00.diff

## 2026-02-08T00:43:39.530667+00:00
- Applied patch: dashboard_patch_2026-02-08T00-43-34.241354+00-00.diff

## 2026-02-08T01:34:38.700123+00:00
- Applied patch: dashboard_patch_2026-02-08T01-34-33.418037+00-00.diff

## 2026-02-08T03:05:11.559969+00:00
- Applied patch: dashboard_patch_2026-02-08T03-05-05.264490+00-00.diff

## 2026-02-08T04:13:30Z
- Applied manual UX overhaul CSS/tabs updates and cleaned redundant styles.
- Normalized recent errors card styling and copy button layout.

## 2026-02-08T05:12:45Z
- Autopatch: accept full-file app.py fallback (BEGIN_APP_PY/END_APP_PY) to reduce model diff failures.

## 2026-02-08T05:20:10Z
- Autopatch: added retry hardening, safe file reads, and structured failure logging.

## 2026-02-08T05:27:30Z
- Autopatch: force full-file fallback on retry to avoid corrupt diffs.

## 2026-02-08T05:33:10Z
- Autopatch: allow higher token limits for full-file fallback to avoid truncation.

## 2026-02-08T05:39:20Z
- Autopatch: add API timeouts to avoid hanging runs.

## 2026-02-08T05:46:40Z
- Autopatch: configurable token budgets and more focused patch scope to reduce truncation.

## 2026-02-08T05:49:30Z
- Autopatch: fix token-budget loop indentation bug.

## 2026-02-08T06:01:10Z
- Autopatch: default OpenAI model set to gpt-5.2-codex when AUTOPATCH_MODEL not provided.

## 2026-02-08T06:07:40Z
- Autopatch: fall back to non-3way git apply when index mismatch blocks patching.

## 2026-02-08T06:16:30Z
- Dashboard: added credits/usage snapshot with provider/model display in Overview and Settings.
- Dashboard: fixed credit snapshot helper indentation.
- Dashboard: credit status now ignores older billing errors if a newer successful cycle exists.
## 2026-02-08T05:24:44.562580+00:00
- Applied patch: dashboard_patch_2026-02-08T05-24-38.914061+00-00.diff

## 2026-02-08T05:29:23.781456+00:00
- Applied patch: dashboard_patch_2026-02-08T05-29-17.177513+00-00.diff
## 2026-02-08T06:23:23.383498+00:00
- Applied patch: dashboard_patch_2026-02-08T06-23-16.883048+00-00.diff

## 2026-02-08T06:31:43.547619+00:00
- Applied patch: dashboard_patch_2026-02-08T06-31-37.071051+00-00.diff

## 2026-02-08T19:22:39.689250+00:00
- Applied patch: dashboard_patch_2026-02-08T19-22-38.016615+00-00.diff

## 2026-02-08T19:36:19.292892+00:00
- Applied patch: dashboard_patch_2026-02-08T19-36-17.608625+00-00.diff

## 2026-02-09T04:58:25.520407+00:00
- Applied patch: dashboard_patch_2026-02-09T04-58-22.621615+00-00.diff

## 2026-02-09T07:14:17.854871+00:00
- Applied patch: dashboard_patch_2026-02-09T07-14-15.915069+00-00.diff
## 2026-02-09T15:03:14.485300+00:00
- Applied patch: dashboard_patch_2026-02-09T15-03-12.682514+00-00.diff

