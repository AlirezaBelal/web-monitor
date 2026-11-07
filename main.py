"""Command-line entry point for WebMonitor."""

import argparse
import sys
import time

from health import HealthRecord, HealthReporter
from notifications import build_notifier
from web_monitor import (
    ConfigurationError,
    MonitorError,
    MonitorSuiteConfig,
    WebMonitor,
)


def report_result(
    target_name: str,
    status: str,
    matched_elements: int,
    show_name: bool,
) -> None:
    prefix = f"[{target_name}] " if show_name else ""
    print(f"{prefix}Status: {status}; matched elements: {matched_elements}")


def build_monitors(suite: MonitorSuiteConfig, desktop_override: bool):
    show_name = len(suite.targets) > 1
    monitors = []
    try:
        for target in suite.targets:
            monitors.append(
                WebMonitor(
                    config=target,
                    notifier=build_notifier(
                        target,
                        desktop_override=desktop_override,
                        show_name=show_name,
                    ),
                )
            )
    except BaseException:
        for monitor in monitors:
            monitor.close()
        raise
    return monitors


def run_checks(monitors, show_name: bool) -> tuple[int, list[HealthRecord]]:
    """Run every configured target once and continue after individual failures."""
    failures = 0
    records = []
    for monitor in monitors:
        try:
            result = monitor.check_once()
            report_result(
                monitor.config.name,
                result.status,
                result.matched_elements,
                show_name,
            )
            records.append(
                HealthRecord(
                    name=monitor.config.name,
                    status=result.status,
                    matched_elements=result.matched_elements,
                )
            )
        except MonitorError as exc:
            failures += 1
            prefix = f"[{monitor.config.name}] " if show_name else ""
            print(f"{prefix}Check failed: {exc}", file=sys.stderr)
            records.append(
                HealthRecord(
                    name=monitor.config.name,
                    status="error",
                    error=str(exc),
                )
            )
    return failures, records


def write_health(suite: MonitorSuiteConfig, records: list[HealthRecord]) -> bool:
    if suite.health_file is None:
        return True
    try:
        HealthReporter(suite.health_file).write(records)
        return True
    except MonitorError as exc:
        print(f"Health output failed: {exc}", file=sys.stderr)
        return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Monitor selected content across one or more webpages and report digest changes."
        )
    )
    parser.add_argument(
        "--config",
        default="config.json",
        help="Path to a JSON configuration file (default: config.json)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one check for every configured target and exit",
    )
    parser.add_argument(
        "--validate-config",
        action="store_true",
        help="Validate configuration without making a network request",
    )
    parser.add_argument(
        "--desktop-notifications",
        action="store_true",
        help="Override configured notification backends with desktop notifications",
    )
    args = parser.parse_args()
    monitors = []

    try:
        suite = MonitorSuiteConfig.from_file(args.config)
        if args.validate_config:
            print(f"Configuration valid: {len(suite.targets)} target(s).")
            return 0

        monitors = build_monitors(suite, args.desktop_notifications)
        show_name = len(monitors) > 1

        if args.once:
            failures, records = run_checks(monitors, show_name)
            health_ok = write_health(suite, records)
            return 1 if failures or not health_ok else 0

        print(
            "Monitoring started. Press Ctrl+C to stop. "
            f"Targets: {len(monitors)}; interval: {suite.check_interval_seconds:g}s"
        )
        while True:
            _failures, records = run_checks(monitors, show_name)
            write_health(suite, records)
            time.sleep(suite.check_interval_seconds)

    except FileNotFoundError:
        print(
            "Configuration file not found. Copy config.example.json to config.json "
            "and customize it locally.",
            file=sys.stderr,
        )
        return 2
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Monitoring stopped.")
        return 0
    finally:
        for monitor in monitors:
            monitor.close()


if __name__ == "__main__":
    raise SystemExit(main())
