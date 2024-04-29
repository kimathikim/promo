#!/usr/bin/env python3
"""this module implements a pomodoro timer."""

import csv
import subprocess
import time
import sys
from datetime import datetime
import os


def write_to_csv(filename, data):
    """This function writes data to a csv file."""
    try:
        if filename:
            home_dir = os.path.expanduser("~")
            new_file = os.path.join(home_dir, filename)
            sleeper(2)
        if not os.path.exists(new_file):
            with open(new_file, "a", newline="") as file:
                writer = csv.writer(file)
                writer.writerow(
                    [
                        "Time",
                        "Date",
                        "Message",
                        "Break Time",
                        "Total Break Time",
                        "Focus Time",
                        "Total Focus Time",
                    ]
                )
    except Exception as e:
        print(f"File not found. {e}")

    with open(new_file, "a", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(data)


def break_time(break_time: int, message: str) -> None:
    """This function implements a break time."""
    timer = break_time
    total_break_time = 0
    print("Break Timer")
    print("Press Ctrl-C to stop the timer.")
    sleeper(4)
    try:
        total_break_time += int(timer)
        subprocess.run(
            [
                "mytimer",
                f"--second={timer}",
                f"--message={message}",
                "--countdown",
                "--alarm=2",
                "--alarm-repeat=3",
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
    sleeper(5)
    break_time(30, "Enjoy your break!😶️!.")


def sleeper(sec):
    """This function implements a sleeper timer."""
    try:
        time.sleep(sec)
    except KeyboardInterrupt:
        print("\nPomodoro timer stopped.")


def pomodoro(
    hour: int = 0, minutes: int = 5, message: str = "Let's Get Started!!!"
) -> int:
    """This function implements a pomodoro timer."""
    timer = hour * 60 + minutes
    initial_timer = timer
    total_focus_time = 0
    total_break_time = 0
    break_t = 0
    print("PROmodoro Timer")
    if initial_timer >= 180:
        print("You are a machine!!!😎. Keep it up!.")
        print("\nPress Ctrl-C to stop the timer.")
    sleeper(1)
    try:
        while True:
            total_focus_time += timer
            count = total_focus_time

            if timer <= 0:
                break
                print(count)
                return count

            write_to_csv(
                "timeManager.csv",
                [
                    datetime.today().strftime(" %H:%M:%S"),
                    datetime.today().strftime("%Y-%m-%d"),
                    message,
                    break_t,
                    total_break_time,
                    timer,
                    total_focus_time,
                ],
            )
            try:
                subprocess.run(
                    [
                        "mytimer",
                        f"--second={timer}",
                        f"--message={message}",
                        "--countdown",
                        "--alarm=4",
                        "--alarm-repeat=3",
                        "--tone=5",
                    ]
                )
                subprocess.run(["clear"])
                print(f"Focus time: {total_focus_time} \
minutes.\nTotal focus time: {count} \
minutes.\nTotal break time: {total_break_time} \
minutes.\n")

                if timer >= 30:
                    break_t = timer // 5
                    if break_t >= 36:
                        long_break_time(count)
                        return count
                    break_time(break_t, "Take a break.")
                    total_break_time += break_t
                if count >= 180:
                    long_break_time(count)
                    return count

                focus = input(
                    "Enter your focus level:\n\
BREAK = 0, Distracted= 1, Normal = 2, Focused = 3, Flow = 4:\n"
                )
                if focus in ["1", "2", "3", "4"]:
                    timer += [-5, 5, 10, 20][int(focus) - 1]
                elif focus == "0":
                    break_time(30, "Taking a Long break!😶️!.")
                    total_break_time += 30

                else:
                    print("Invalid input. Prove that you are not focused!!")
                print(f"Next timer is set to {timer} minutes.")
                sleeper(3)

            except KeyboardInterrupt:
                print("Pomodoro timer stopped.")
                print("Total focus time not calculated accurately.")
                return count
    except KeyboardInterrupt:
        print("Pomodoro timer stopped.")
        print("Total focus time not calculated accurately.")
        return count
    return count


def main():
    if len(sys.argv) == 1:
        count = pomodoro()
        return

    if len(sys.argv) != 4:
        print("Usage: python script.py <hour> <minutes> <message>")
        return

    try:
        hour = int(sys.argv[1])
        minutes = int(sys.argv[2])
        message = sys.argv[3]
    except ValueError:
        print("Usage: python script.py <hour> <minutes> <message>")
        return

    count = pomodoro(hour, minutes, message)

    print(f"Total time spent: {count} minutes.")


if __name__ == "__main__":
    main()
