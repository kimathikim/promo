#!/usr/bin/env python3
"""this module implements a pomodoro timer."""

import csv
import subprocess
import time
import sys
from datetime import datetime
import os


def write_to_csv(filename, data):
    with open(filename, "a", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(data)


def break_time(break_time: int, message: str) -> None:
    """This function implements a break time."""
    timer = break_time
    total_break_time = 0
    print("Break Timer")
    print("Press Ctrl-C to stop the timer.")
    try:
        total_break_time += int(timer)
        subprocess.run(
            [
                "mytimer",
                f"--minute={timer}",
                f"--message={message}",
                "--countdown",
                "--alarm=2",
            ]
        )
        subprocess.run(["clear"])
    except KeyboardInterrupt as e:
        print(f"\nBreak timer stopped.{e}")
        return 0


def long_break_time(count: str) -> None:
    print(
        f"Congratulations! You have completed more than 4 \
hours of focused work. Precisely {count} minutes."
    )
    print("You deserve a long break ...")
    break_time(30, "Enjoy your break!😶️!.")


def pomodoro(
    hour: int = 0, minutes: int = 5, message: str = "Let's Get Started!!!"
) -> int:
    """This function implements a pomodoro timer."""
    timer = hour * 60 + minutes
    initial_timer = timer
    total_focus_time = 0
    total_break_time = 0
    focus_time = 0
    home_dir = os.path.expanduser("~")
    new_dir = f"{home_dir}"
    new_file = f"{new_dir}/timeManager.csv"

    print("PROmodoro Timer")
    if initial_timer >= 200:
        print("You are a machine!!!😎️")

    print("\nPress Ctrl-C to stop the timer.")
    try:
        time.sleep(4)
        count = timer
    except KeyboardInterrupt:
        print("\nPomodoro timer stopped.")

        return 0
    try:
        while True:
            if timer <= 0:
                break
                print(count)
                return count

            try:
                subprocess.run(
                    [
                        "mytimer",
                        f"--minute={timer}",
                        f"--message={message}",
                        "--countdown",
                        "--alarm=4",
                        "--tone=5",
                    ]
                )
                subprocess.run(["clear"])
                focus_time += timer
                if timer >= 25:
                    break_t = timer // 5
                    break_time(break_t, "Take a break.")
                    total_break_time += break_t
                    focus_time = 0

                total_focus_time += timer
                print(f"Last timer: {timer} \
minutes.\nFocus time: {total_focus_time} \
minutes.\nTotal focus time: {count} \
minutes.\nTotal break time: {total_break_time} \
minutes.\n")

                focus = input(
                    "Enter your focus level:\n\
BREAK = 0, Distracted= 1, Normal = 2, Focused = 3, Flow = 4:\n"
                )
                if focus in ["1", "2", "3", "4"]:
                    focus_time += timer
                    timer += [-5, 5, 10, 20][int(focus) - 1]
                elif focus == "0":
                    break_time(30, "Taking a Long break!😶️!.")
                    total_break_time += 30

                else:
                    print("Invalid input. Prove that you are not focused!!")
                    focus_time += timer
                print(f"Next timer is set to {timer} minutes.")
                time.sleep(3)

                count += timer

                write_to_csv(
                    new_file,
                    [
                        datetime.today().strftime(" %H:%M:%S"),
                        datetime.today().strftime("%Y-%m-%d"),
                        message,
                        total_break_time,
                        focus_time,
                        total_focus_time,
                    ],
                )
                if count >= 180:
                    long_break_time(count)
                    total_break_time += 30
                    count = 0
                    time.sleep(3)

            except KeyboardInterrupt:
                print("Pomodoro timer stopped.")
                print("Total focus time not calculated accurately.")
                return count
    except KeyboardInterrupt:
        print("Pomodoro timer stopped.")
        print("Total focus time not calculated accurately.")
        return 0
    return count


def main():
    if len(sys.argv) == 1:
        count = pomodoro()
        print(f"Total time spent: {count} minutes.")
        return

    if len(sys.argv) < 4 and len(sys.argv) > 1:
        print("Usage: python script.py <hour> <minutes> <message>")
        return

    try:
        hour = int(sys.argv[1])
        minutes = int(sys.argv[2])
        message = sys.argv[3]
    except ValueError:
        print("usage: python script.py <hour> <minutes> <message>")
        print("Invalid input. Please enter a number.")
        return
    if len(sys.argv) > 3:
        count = pomodoro(hour, minutes, message)

    print(f"Total time spent: {count} minutes.")


if __name__ == "__main__":
    main()
