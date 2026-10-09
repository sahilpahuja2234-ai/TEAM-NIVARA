<<<<<<< HEAD
# NIVARA-AGNITA-2026 

[![CI](https://github.com/sahilpahuja2234-ai/TEAM-NIVARA/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/sahilpahuja2234-ai/TEAM-NIVARA/actions/workflows/ci.yml)
[![CD](https://github.com/sahilpahuja2234-ai/TEAM-NIVARA/actions/workflows/cd.yml/badge.svg?branch=main)](https://github.com/sahilpahuja2234-ai/TEAM-NIVARA/actions/workflows/cd.yml)

## DevSecOps: CI/CD, scoring and reports

**CI** (`.github/workflows/ci.yml`) runs on every push and on pull requests to `main`: tests, Trivy (dependencies and images) and Gitleaks (secrets). A pull request cannot merge until CI passes. **CD** (`cd.yml`) runs on pushes to `main` only.

**Security score (0 to 100)** is deterministic: each control is `detected` (1.0), `partial` (0.5) or `missed` (0.0), averaged per dimension, then weighted:

| Dimension | Weight |
|---|---|
| Detection coverage | 30% |
| Application controls | 20% |
| API authorization | 15% |
| Supply chain | 15% |
| Secrets | 10% |
| Configuration | 10% |

`final_score = round(sum(weight x average(controls in dimension)) x 100)`. Full details are in [`docs/scoring.md`](docs/scoring.md).

### Run it locally

```bash
docker compose up --build        # frontend http://localhost:3000, backend http://localhost:8000
python scripts/reset_twin.py     # reset the twin to the clean seeded state (asks first; --yes to skip)
python scripts/generate_report.py RUN_ID -f html -o report.html
```

Security tools run on demand:

```bash
docker compose --profile security run --rm trivy image nivara-backend:latest
docker compose --profile security run --rm gitleaks
```

## 5-minute demo script

Expected result for scenario S07 (Price/Coupon Manipulation): **before 61, after 92 (+31)**.

| Time | Step | What to say or show |
|---|---|---|
| 0:00 | **Reset** | Run `python scripts/reset_twin.py --yes` so the twin starts clean. Open the bookstore at `localhost:3000`. |
| 0:15 | **Create** | Browse and search books, add one to the cart, apply a coupon, check out. This is a believable shop before any attack. |
| 1:15 | **Security Lab** | Switch to the lab, show the scenarios S01 to S07, choose **S07 Price/Coupon Manipulation**. |
| 1:45 | **Attack and observe** | Click Run, wait for the run to finish, show the findings and the **before score (61)**. |
| 2:45 | **Fix** | Open the recommended fix, explain it, click Apply Fix. |
| 3:30 | **Replay** | Replay the same attack. It is now blocked. Show the **after score (92)** and the +31 improvement. |
| 4:15 | **Report** | Generate and download the HTML report (the same one `scripts/generate_report.py` produces). |
| 4:40 | **CI proof** | Open the GitHub Actions run: tests, Trivy and Gitleaks gates, and the pull request requirement. |

If the UI misbehaves on stage, the CLI fallback is `python scripts/generate_report.py RUN_ID -f html -o report.html`.
=======
TIME START
>>>>>>> 579b1ad7c47ddd6cba00a4f5ed0686a52f358389

