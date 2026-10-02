"""Xuất đường cong PGD từ một experiment làm dữ liệu cho demo landing.

Cách dùng: python scripts/export_demo_data.py <experiment_id> <email> > /tmp/curve.json
"""

import getpass
import json
import sys

import requests

API = "http://localhost:8000"  # Đổi theo cổng API đang chạy.


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(
            "Cách dùng: python scripts/export_demo_data.py <experiment_id> <email>"
        )

    exp_id, email = sys.argv[1], sys.argv[2]
    session = requests.Session()

    response = session.post(
        f"{API}/auth/login",
        json={"email": email, "password": getpass.getpass()},
    )
    response.raise_for_status()

    response = session.get(f"{API}/experiments/{exp_id}")
    response.raise_for_status()
    experiment = response.json()

    response = session.get(f"{API}/experiments/{exp_id}/runs")
    response.raise_for_status()
    runs = response.json()

    points = sorted(
        [
            {
                "level": run["level"],
                "relative_drop": round(run["metrics"]["relative_drop"], 3),
            }
            for run in runs
            if run["attack_spec"]["name"] == "pgd_linf"
            and run["status"] == "completed"
            and run.get("scope", "full") == "full"
            and run.get("metrics") is not None
            and run["metrics"].get("relative_drop") is not None
        ],
        key=lambda point: point["level"],
    )

    search = next(
        (
            result
            for result in experiment.get("search_results", [])
            if result.get("status") in ("found", "non_monotonic")
        ),
        None,
    )

    json.dump(
        {
            "points": points,
            "breaking_point": search["breaking_point"] if search else None,
            "threshold": search["threshold"] if search else 0.2,
            "experiment_id": exp_id,
            "model": experiment["model"]["name"],
            "slice_size": experiment["slice"]["size"],
        },
        sys.stdout,
        ensure_ascii=False,
        indent=2,
    )
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
