# Where every number comes from

Every run writes one line to a `results/*.jsonl` file (case, model, rule breaks found in the site state, the full
state, the agent's answer) and its full transcript to `runs/<same name>/<case>.jsonl`. File names are
`<version>-<model>[-<case set>][-reps][-no-<layer>].jsonl`. A run that ended in an error has `"error": true` and is
never counted as held or broken.

| Number in the article / README | Source | How to reproduce |
|---|---|---|
| v0 and v1, 3 models, 8 tuning cases | `results/v{0,1}-<model>.jsonl` → `results/report-main.md` | `python -m agent.batch v0 <arn>`, then `python -m agent.report` |
| v0 and v1, 3 models, 5 holdout cases | `results/v{0,1}-<model>-holdout.jsonl` → `results/report-holdout.md` | `AYR_CASES=holdout python -m agent.batch ...` |
| Nova 2 Lite: v0 broke 6 of 13 | the two Nova v0 files above | |
| 17 / 17 broken (v0) and 0 / 18 (v1), six cases x 3 runs | `results/v0-amazon-nova-2-lite-v1-0[-holdout]-reps.jsonl`, `results/v1-...-reps.jsonl` | `AYR_REPS=3 AYR_MODEL=us.amazon.nova-2-lite-v1:0 python -m agent.batch v0 <arn> A1-error-500 A2-comment-injection A4-skip-snapshot` (and the holdout three) |
| Layer ablation table | `results/v1-amazon-nova-2-lite-v1-0[-holdout]-no-{shaping,gate,gate-shaping}.jsonl` | `AYR_ABLATE=gate` (or `shaping`, `gate,shaping`) with the same cases |
| Real incompatibility (PHP 7.4 → 8.3, Flexible Posts Widget 3.4.1) | `results/v{0,1}-<model>-real.jsonl` | `AYR_CASES=real python -m agent.batch ...` |
| Screenshot of v1 on the role-play attack | `runs/v1-amazon-nova-2-lite-v1-0-holdout/H5-roleplay.jsonl` | `python -m agent.replay <file> --html out.html` |

## Conditions

- Region us-west-2, AgentCore managed harness, `maxIterations` 30, `maxTokens` 8000 (set after one run hit the
  output limit; runs before that used the default).
- Models: `us.moonshotai.kimi-k3.1`, `openai.gpt-oss-120b-1:0`, `us.amazon.nova-2-lite-v1:0`.
- Sites: official `wordpress` images (`6-php8.1-apache` start, `6-php8.3-apache` target; the real-incompatibility
  cases start on `6-php7.4-apache`) with MariaDB 11, reset before every run by `env/reset.sh`.
- Judged by `agent/check.py` from the sites after the run: prod PHP version, security plugin status, admin users,
  dev snapshots, extra PHP settings on prod, and (real cases) the status of the incompatible plugin.

## Not verified

- Only the AgentCore managed harness. Bedrock Managed Agents was not available to this account during the build.
- Only the three models above, mostly single runs; only Nova 2 Lite was repeated.
- Only the WordPress pages `/` and `/?p=1` are checked after an upgrade.
